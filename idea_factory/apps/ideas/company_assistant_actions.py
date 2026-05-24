"""Propose and execute user-confirmed company assistant actions."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.core.access import user_can_manage_company
from apps.core.assistant_markdown import render_assistant_markdown
from apps.core.public_urls import public_absolute_url
from apps.ideas.best_practices import assess_company_readiness
from apps.ideas.company_history import record_history
from apps.ideas.development_plan import get_development_plan_summary
from apps.ideas.models import (
    Company,
    CompanyAssistantMessage,
    CompanyAssistantProposedAction,
    CompanyHistoryEntry,
    CompanyStrategicDirection,
    CompanyTask,
    PlanningSession,
)
from apps.ideas.planning import (
    monday_of_week,
    resolve_assignee,
    spawn_planning_process,
    start_planning_session,
)
from apps.ideas.planning_context import get_active_direction

logger = logging.getLogger(__name__)

_ACTION_INTENT_RE = re.compile(
    r"\b("
    r"fix|address|resolve|help me|can you|please|do it|create|start|run|set up|"
    r"implement|improve|remediate|correct|setup|generate|make a plan|develop"
    r")\b",
    re.I,
)


@dataclass(frozen=True)
class _ProposalSpec:
    action_type: str
    title: str
    description: str
    payload: dict


def user_wants_assistant_action(user_content: str) -> bool:
    text = user_content.strip()
    if not text:
        return False
    lower = text.lower()
    if _ACTION_INTENT_RE.search(text):
        return True
    return any(
        w in lower
        for w in (
            "readiness",
            "fail",
            "failed",
            "red",
            "development plan",
            "fix this",
            "fix the",
        )
    )


def propose_actions_for_message(message: CompanyAssistantMessage) -> list[CompanyAssistantProposedAction]:
    """
    Create pending action proposals from readiness failures when the user asks to fix/improve.
    Only company owners/admins may approve (checked at execution).
    """
    if not user_wants_assistant_action(message.user_content):
        return []

    company = message.company
    specs = _build_proposal_specs(company)
    if not specs:
        return []

    created: list[CompanyAssistantProposedAction] = []
    for spec in specs:
        action, was_created = CompanyAssistantProposedAction.objects.get_or_create(
            message=message,
            action_type=spec.action_type,
            status=CompanyAssistantProposedAction.Status.PENDING,
            defaults={
                "company": company,
                "user": message.user,
                "title": spec.title,
                "description": spec.description,
                "payload": spec.payload,
            },
        )
        if was_created:
            created.append(action)
    return created


def _build_proposal_specs(company: Company) -> list[_ProposalSpec]:
    report = assess_company_readiness(company)
    failed_ids = {c.check_id for c in report.checks if c.status == "fail"}
    plan = get_development_plan_summary(company.idea_request)
    direction = get_active_direction(company)
    specs: list[_ProposalSpec] = []
    seen_types: set[str] = set()

    def add(spec: _ProposalSpec) -> None:
        if spec.action_type in seen_types:
            return
        seen_types.add(spec.action_type)
        specs.append(spec)

    if "development_plan" in failed_ids:
        if plan["has_plan"]:
            milestone_n = len(plan["milestones"])
            backlog_n = len(plan["mvp_backlog"])
            add(
                _ProposalSpec(
                    action_type=CompanyAssistantProposedAction.ActionType.SEED_TASKS_FROM_IDEA,
                    title="Create tasks from idea pipeline",
                    description=(
                        f"Add up to {milestone_n} milestone(s) and {backlog_n} backlog item(s) "
                        "as tasks on the company board (skips titles that already exist)."
                    ),
                    payload={"check_id": "development_plan"},
                )
            )
        else:
            add(
                _ProposalSpec(
                    action_type=CompanyAssistantProposedAction.ActionType.START_PLANNING_SESSION,
                    title="Start AI planning session",
                    description=(
                        "Run an on-demand planning session to generate milestones and tasks "
                        "from your company context (runs in the background)."
                    ),
                    payload={"check_id": "development_plan"},
                )
            )

    if not direction and plan.get("executive_summary"):
        add(
            _ProposalSpec(
                action_type=CompanyAssistantProposedAction.ActionType.DRAFT_STRATEGIC_DIRECTION,
                title="Draft strategic direction",
                description=(
                    "Create a draft strategic direction from your idea pipeline executive summary. "
                    "You can edit and founder-verify it on the Direction page."
                ),
                payload={"source": "executive_summary"},
            )
        )

    if "development_plan" in failed_ids and not plan["has_plan"]:
        # Planning session is the primary fix when pipeline has no milestones.
        pass
    elif (
        "calendar_plan" in failed_ids
        and CompanyAssistantProposedAction.ActionType.START_PLANNING_SESSION
        not in seen_types
    ):
        add(
            _ProposalSpec(
                action_type=CompanyAssistantProposedAction.ActionType.START_PLANNING_SESSION,
                title="Start AI planning session",
                description=(
                    "Generate a scoped task plan and calendar-ready work items via the planner agent."
                ),
                payload={"check_id": "calendar_plan"},
            )
        )

    return specs


def serialize_proposed_action(action: CompanyAssistantProposedAction) -> dict:
    data = {
        "id": str(action.pk),
        "action_type": action.action_type,
        "title": action.title,
        "description": action.description,
        "status": action.status,
        "result_message": action.result_message,
        "can_approve": action.status == CompanyAssistantProposedAction.Status.PENDING,
    }
    if action.planning_session_id:
        path = reverse(
            "company_planning_detail",
            kwargs={
                "company_pk": action.company_id,
                "session_pk": action.planning_session_id,
            },
        )
        data["planning_session_url"] = public_absolute_url(path)
    if action.result_message:
        data["result_message_html"] = str(render_assistant_markdown(action.result_message))
    return data


@transaction.atomic
def approve_proposed_action(
    action: CompanyAssistantProposedAction,
    *,
    approved_by: AbstractBaseUser,
) -> CompanyAssistantProposedAction:
    if not user_can_manage_company(approved_by, action.company):
        raise PermissionError("Only the company owner or an admin can approve actions.")
    if action.status != CompanyAssistantProposedAction.Status.PENDING:
        raise ValueError(f"Action is not pending (status={action.status}).")

    action.status = CompanyAssistantProposedAction.Status.RUNNING
    action.save(update_fields=["status", "updated_at"])

    try:
        if action.action_type == CompanyAssistantProposedAction.ActionType.START_PLANNING_SESSION:
            _execute_start_planning(action, approved_by)
        elif action.action_type == CompanyAssistantProposedAction.ActionType.SEED_TASKS_FROM_IDEA:
            _execute_seed_tasks(action)
        elif action.action_type == CompanyAssistantProposedAction.ActionType.DRAFT_STRATEGIC_DIRECTION:
            _execute_draft_direction(action)
        else:
            raise ValueError(f"Unknown action type: {action.action_type}")

        action.status = CompanyAssistantProposedAction.Status.COMPLETED
        action.executed_at = timezone.now()
        action.save(
            update_fields=["status", "result_message", "planning_session", "executed_at", "updated_at"]
        )
    except Exception as exc:
        logger.exception("Assistant action failed action_id=%s", action.pk)
        action.status = CompanyAssistantProposedAction.Status.FAILED
        action.result_message = str(exc)[:2000]
        action.executed_at = timezone.now()
        action.save(update_fields=["status", "result_message", "executed_at", "updated_at"])
        raise

    return action


def reject_proposed_action(
    action: CompanyAssistantProposedAction,
    *,
    rejected_by: AbstractBaseUser,
) -> None:
    if not user_can_manage_company(rejected_by, action.company):
        raise PermissionError("Only the company owner or an admin can reject actions.")
    if action.status != CompanyAssistantProposedAction.Status.PENDING:
        raise ValueError(f"Action is not pending (status={action.status}).")
    action.status = CompanyAssistantProposedAction.Status.REJECTED
    action.result_message = "Rejected by user."
    action.save(update_fields=["status", "result_message", "updated_at"])


def _execute_start_planning(
    action: CompanyAssistantProposedAction,
    user: AbstractBaseUser,
) -> None:
    in_progress = action.company.planning_sessions.filter(
        status=PlanningSession.Status.IN_PROGRESS
    ).exists()
    if in_progress:
        action.result_message = "A planning session is already running for this company."
        return

    session = start_planning_session(
        action.company,
        trigger=PlanningSession.Trigger.MANUAL,
        user=user,
        week_start=monday_of_week(),
    )
    action.planning_session = session
    spawn_planning_process(str(session.pk))
    path = reverse(
        "company_planning_detail",
        kwargs={"company_pk": action.company_id, "session_pk": session.pk},
    )
    action.result_message = (
        "Planning session started. "
        f"[View planning session]({public_absolute_url(path)}) — tasks appear when it completes."
    )


def _execute_seed_tasks(action: CompanyAssistantProposedAction) -> None:
    company = action.company
    plan = get_development_plan_summary(company.idea_request)
    if not plan["has_plan"]:
        raise ValueError(
            "No milestones or backlog in the idea pipeline. Start a planning session instead."
        )

    existing_titles = set(company.tasks.values_list("title", flat=True))
    sort_order = company.tasks.count()
    created = 0

    def add_task(title: str, description: str) -> None:
        nonlocal sort_order, created
        title = (title or "").strip()[:255]
        if not title or title in existing_titles:
            return
        assignee_type, agent, human = resolve_assignee(company, "planner")
        if assignee_type == CompanyTask.AssigneeType.AGENT and agent is None:
            assignee_type = CompanyTask.AssigneeType.UNASSIGNED
        task = CompanyTask.objects.create(
            company=company,
            title=title,
            description=(description or "")[:8000],
            assignee_type=assignee_type,
            assigned_agent=agent,
            assigned_human=human,
            sort_order=sort_order,
        )
        sort_order += 1
        created += 1
        existing_titles.add(title)
        record_history(
            company,
            CompanyHistoryEntry.EntryType.TASK_CREATED,
            task.title,
            summary=task.description[:300],
            related_task=task,
        )

    for item in plan["milestones"][:12]:
        add_task(str(item), "Milestone from idea pipeline (assistant).")
    for item in plan["mvp_backlog"][:20]:
        add_task(str(item), "MVP backlog item from idea pipeline (assistant).")

    if created == 0:
        action.result_message = (
            "All pipeline items already exist as tasks on the board. "
            "No new tasks were created."
        )
        return

    path = reverse("company_tasks", kwargs={"company_pk": company.pk})
    action.result_message = (
        f"Created **{created}** task(s) from the idea pipeline. "
        f"[View task board]({public_absolute_url(path)})."
    )


def _execute_draft_direction(action: CompanyAssistantProposedAction) -> None:
    company = action.company
    if get_active_direction(company):
        action.result_message = "Strategic direction already exists — edit it on the Direction page."
        return

    plan = get_development_plan_summary(company.idea_request)
    statement = (plan.get("executive_summary") or "").strip()
    if not statement:
        raise ValueError("No executive summary available to draft a direction.")

    if len(statement) < 40:
        statement = (
            f"{statement}\n\n"
            "Refine this direction with your founders on the Direction page."
        )

    CompanyStrategicDirection.objects.filter(company=company, is_active=True).update(
        is_active=False
    )
    direction = CompanyStrategicDirection.objects.create(
        company=company,
        statement=statement[:8000],
        is_active=True,
        founder_verified=False,
    )
    record_history(
        company,
        CompanyHistoryEntry.EntryType.DIRECTION_CREATED,
        "Strategic direction drafted (assistant)",
        summary=statement[:500],
    )
    path = reverse("company_direction", kwargs={"company_pk": company.pk})
    action.result_message = (
        "Draft strategic direction created. "
        f"[Review direction]({public_absolute_url(path)})."
    )
    action.payload = {**(action.payload or {}), "direction_id": str(direction.pk)}
