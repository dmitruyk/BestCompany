"""Automatically start and execute agent-assigned company tasks."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from apps.ideas.activity_checks import _env_bool, _env_int
from apps.ideas.company_history import record_history
from apps.ideas.models import (
    Company,
    CompanyAgent,
    CompanyHistoryEntry,
    CompanyTask,
    CompanyTeamMember,
)
from apps.ideas.planning_context import build_strategic_planning_context

logger = logging.getLogger(__name__)


@dataclass
class TaskExecutionResult:
    companies_processed: int = 0
    tasks_started: int = 0
    tasks_completed: int = 0
    tasks_partial: int = 0
    tasks_escalated: int = 0
    tasks_failed: int = 0
    messages: list[str] = field(default_factory=list)


def explain_task_skip(task: CompanyTask) -> str:
    """Human-readable reason why automatic execution will not pick this task."""
    if task.status != CompanyTask.Status.TODO:
        return f"status is {task.get_status_display()} (need To Do)"
    if task.assignee_type == CompanyTask.AssigneeType.HUMAN:
        return "assigned to human (only AI agent tasks run automatically)"
    if not task.assigned_agent_id:
        return "no AI agent assigned"
    if task.is_blocked_by_dependencies:
        return "blocked by unfinished dependencies"
    return "eligible"


def is_task_runnable(task: CompanyTask) -> bool:
    """True if a TODO agent task may be picked up now."""
    return explain_task_skip(task) == "eligible"


def count_runnable_tasks(company: Company) -> int:
    """How many tasks are eligible right now (for UI badges)."""
    return len(get_runnable_tasks(company, limit=100))


def sync_task_target_date_to_run_day(task: CompanyTask, *, today=None) -> bool:
    """Set target_date to today when a task is started (user or ticker). Returns True if changed."""
    today = today or timezone.localdate()
    if task.target_date == today:
        return False
    task.target_date = today
    return True


def get_runnable_tasks(company: Company, *, limit: int) -> list[CompanyTask]:
    qs = (
        company.tasks.filter(
            status=CompanyTask.Status.TODO,
            assigned_agent__isnull=False,
        )
        .exclude(assignee_type=CompanyTask.AssigneeType.HUMAN)
        .select_related("assigned_agent", "company", "company__idea_request")
        .prefetch_related(
            "dependencies__depends_on",
        )
        .order_by("sort_order", "created_at")
    )
    runnable: list[CompanyTask] = []
    for task in qs:
        if is_task_runnable(task):
            runnable.append(task)
        if len(runnable) >= limit:
            break
    return runnable


def _escalate_task_to_human(task: CompanyTask, summary: str) -> None:
    founder = (
        task.company.team_members.filter(
            is_active=True,
            role=CompanyTeamMember.Role.FOUNDER,
        )
        .first()
    )
    task.escalated_to_human = True
    task.status = CompanyTask.Status.BLOCKED
    task.assigned_agent = None
    task.assignee_type = CompanyTask.AssigneeType.HUMAN
    task.assigned_human = founder
    task.result_summary = summary[:4000]
    task.save(
        update_fields=[
            "escalated_to_human",
            "status",
            "assigned_agent",
            "assignee_type",
            "assigned_human",
            "result_summary",
            "updated_at",
        ]
    )
    record_history(
        task.company,
        CompanyHistoryEntry.EntryType.TASK_ESCALATED,
        task.title,
        summary=summary[:500],
        related_task=task,
    )


def _mark_task_in_progress(
    task: CompanyTask,
    company: Company,
    agent: CompanyAgent,
    *,
    manual_trigger: bool = False,
) -> None:
    """Move task to IN_PROGRESS and align target_date with the run day."""
    today = timezone.localdate()
    task.status = CompanyTask.Status.IN_PROGRESS
    task.progress_percent = max(task.progress_percent, 10)
    update_fields = ["status", "progress_percent", "updated_at"]
    if sync_task_target_date_to_run_day(task, today=today):
        update_fields.append("target_date")
    task.save(update_fields=update_fields)
    if manual_trigger:
        summary = f"Started on user request; due date set to {today.isoformat()}"
    else:
        summary = f"Started automatically by {agent.name}"
    record_history(
        company,
        CompanyHistoryEntry.EntryType.TASK_UPDATED,
        task.title,
        summary=summary,
        related_task=task,
    )


@transaction.atomic
def execute_company_task(task: CompanyTask, *, manual_trigger: bool = False) -> str:
    """
    Run the assigned agent on a task. Returns: completed | escalated | failed | skipped.
    Caller should only pass runnable TODO tasks; re-checks under row lock.
    """
    locked = CompanyTask.objects.select_for_update().get(pk=task.pk)
    if not is_task_runnable(locked):
        return "skipped"

    company = Company.objects.select_related("idea_request").get(pk=locked.company_id)
    agent = (
        CompanyAgent.objects.get(pk=locked.assigned_agent_id)
        if locked.assigned_agent_id
        else None
    )
    if not agent:
        return "skipped"

    _mark_task_in_progress(locked, company, agent, manual_trigger=manual_trigger)

    from apps.agents.agents import _run_agent
    from apps.agents.providers import get_model_for_idea, validate_provider_config
    from apps.agents.schemas import CompanyTaskExecutionOutput

    idea = company.idea_request
    err = validate_provider_config(idea.provider)
    if err:
        logger.error("Task execution provider error: %s", err)
        locked.status = CompanyTask.Status.TODO
        locked.save(update_fields=["status", "updated_at"])
        return "failed"

    try:
        model = get_model_for_idea(idea)
    except (ValueError, ImportError) as e:
        logger.exception("Task execution model setup failed: %s", e)
        locked.status = CompanyTask.Status.TODO
        locked.save(update_fields=["status", "updated_at"])
        return "failed"

    context = build_strategic_planning_context(company, max_task_lines=15)
    user_prompt = f"""Complete this company task.

Task: {locked.title}
Description:
{locked.description or '(no description)'}

Company context:
{context}

Produce a concrete result_summary for the next planning cycle. If you cannot complete
this without a human (legal, payment, external account, physical world), set needs_human=true.
"""

    system = agent.system_prompt or f"You are {agent.name}, role {agent.get_role_display()}."
    system += (
        "\n\nYou are executing an assigned company task. Be specific and actionable "
        "in result_summary. Do not invent URLs or credentials."
    )

    try:
        output, _ = _run_agent(
            model,
            agent.role,
            system,
            user_prompt,
            CompanyTaskExecutionOutput,
            tools=None,
        )
    except Exception:
        logger.exception("Task LLM failed for task %s", locked.pk)
        locked.status = CompanyTask.Status.TODO
        locked.save(update_fields=["status", "updated_at"])
        return "failed"

    if not output:
        locked.status = CompanyTask.Status.TODO
        locked.save(update_fields=["status", "updated_at"])
        return "failed"

    if output.needs_human or (output.outcome_assessment or "").lower() == "blocked":
        _escalate_task_to_human(
            locked,
            output.result_summary or "Agent requested human takeover.",
        )
        return "escalated"

    locked.result_summary = (output.result_summary or "")[:4000]
    locked.result_notes = (output.result_notes or "")[:8000]
    locked.progress_percent = min(100, max(0, output.progress_percent))
    assessment = (output.outcome_assessment or "").lower()
    if assessment == "partial" and locked.progress_percent >= 100:
        locked.progress_percent = 75

    if locked.progress_percent >= 100 or assessment == "success":
        locked.status = CompanyTask.Status.DONE
        locked.progress_percent = 100
        locked.completed_at = timezone.now()
        locked.save(
            update_fields=[
                "status",
                "result_summary",
                "result_notes",
                "progress_percent",
                "completed_at",
                "updated_at",
            ]
        )
        record_history(
            company,
            CompanyHistoryEntry.EntryType.TASK_COMPLETED,
            locked.title,
            summary=locked.result_summary[:500],
            related_task=locked,
        )
        return "completed"

    locked.status = CompanyTask.Status.IN_PROGRESS
    locked.save(
        update_fields=[
            "status",
            "result_summary",
            "result_notes",
            "progress_percent",
            "updated_at",
        ]
    )
    record_history(
        company,
        CompanyHistoryEntry.EntryType.TASK_UPDATED,
        locked.title,
        summary=f"Partial progress {locked.progress_percent}% — {locked.result_summary[:200]}",
        related_task=locked,
    )
    return "partial"


def run_task_execution_for_company(
    company: Company,
    *,
    max_tasks: int,
    manual_trigger: bool = False,
) -> TaskExecutionResult:
    result = TaskExecutionResult(companies_processed=1)
    runnable = get_runnable_tasks(company, limit=max_tasks)
    if manual_trigger:
        today = timezone.localdate()
        for task in runnable:
            if sync_task_target_date_to_run_day(task, today=today):
                task.save(update_fields=["target_date", "updated_at"])
    for task in runnable:
        outcome = execute_company_task(task, manual_trigger=manual_trigger)
        if outcome in ("completed", "partial", "escalated", "failed"):
            result.tasks_started += 1
        if outcome == "completed":
            result.tasks_completed += 1
        elif outcome == "partial":
            result.tasks_partial += 1
        elif outcome == "escalated":
            result.tasks_escalated += 1
        elif outcome == "failed":
            result.tasks_failed += 1
    return result


def run_company_task_execution(
    *,
    dry_run: bool = False,
    max_per_company: int | None = None,
) -> TaskExecutionResult:
    """
    For each ACTIVE company, run up to N agent TODO tasks (deps satisfied, AI-assigned).
    """
    if not _env_bool("TICKER_TASK_EXECUTION", True):
        logger.info("Task execution disabled (TICKER_TASK_EXECUTION=false).")
        return TaskExecutionResult()

    limit = max_per_company if max_per_company is not None else _env_int(
        "TICKER_TASK_MAX_PER_COMPANY", 2
    )
    limit = max(1, min(limit, 10))
    aggregate = TaskExecutionResult()

    companies = Company.objects.filter(status=Company.Status.ACTIVE).order_by("name")
    if _env_bool("TICKER_TASK_AUTONOMOUS_ONLY", False):
        companies = companies.filter(autonomous_mode=True)

    for company in companies:
        if dry_run:
            runnable = get_runnable_tasks(company, limit=limit)
            if runnable:
                msg = f"Would run {len(runnable)} task(s) for {company.name}"
                aggregate.messages.append(msg)
                logger.info(msg)
            aggregate.companies_processed += 1
            continue

        try:
            one = run_task_execution_for_company(company, max_tasks=limit)
        except Exception:
            logger.exception("Task execution failed for company %s", company.pk)
            continue

        aggregate.companies_processed += one.companies_processed
        aggregate.tasks_started += one.tasks_started
        aggregate.tasks_completed += one.tasks_completed
        aggregate.tasks_partial += one.tasks_partial
        aggregate.tasks_escalated += one.tasks_escalated
        aggregate.tasks_failed += one.tasks_failed
        aggregate.messages.extend(one.messages)

    if (
        aggregate.tasks_completed
        or aggregate.tasks_partial
        or aggregate.tasks_escalated
        or aggregate.tasks_failed
    ):
        msg = (
            f"Task execution: {aggregate.tasks_completed} done, "
            f"{aggregate.tasks_partial} partial, "
            f"{aggregate.tasks_escalated} escalated, {aggregate.tasks_failed} failed."
        )
        aggregate.messages.append(msg)
        logger.info(msg)

    if aggregate.tasks_started == 0 and aggregate.companies_processed:
        _log_skip_summary(companies)

    return aggregate


def _log_skip_summary(companies) -> None:
    """Log why open tasks were not executed (helps debug tasks_done=0)."""
    for company in companies:
        open_tasks = company.tasks.exclude(
            status__in=[CompanyTask.Status.DONE, CompanyTask.Status.CANCELLED]
        ).order_by("sort_order", "created_at")[:30]
        if not open_tasks:
            continue
        runnable = get_runnable_tasks(company, limit=1)
        if runnable:
            continue
        logger.info(
            "No runnable tasks for %s (%s open). Examples:",
            company.name,
            open_tasks.count(),
        )
        for task in open_tasks[:5]:
            logger.info(
                "  - %s [%s] assignee=%s agent=%s due=%s → %s",
                task.title[:60],
                task.get_status_display(),
                task.get_assignee_type_display(),
                task.assigned_agent.name if task.assigned_agent_id else "—",
                task.target_date or "—",
                explain_task_skip(task),
            )
