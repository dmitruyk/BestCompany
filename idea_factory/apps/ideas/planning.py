"""Run planning sessions and materialize task scope."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from datetime import date, timedelta

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.utils import timezone

from apps.ideas.company_history import record_history
from apps.ideas.models import (
    Company,
    CompanyAgent,
    CompanyTask,
    CompanyTaskDependency,
    CompanyTeamMember,
    PlanningSession,
)
from apps.ideas.planning_context import build_strategic_planning_context

logger = logging.getLogger(__name__)

HUMAN_ROLE = "human"


def monday_of_week(d: date | None = None) -> date:
    d = d or timezone.localdate()
    return d - timedelta(days=d.weekday())


def resolve_assignee(
    company: Company, suggested_role: str
) -> tuple[str, CompanyAgent | None, CompanyTeamMember | None]:
    role = (suggested_role or "planner").strip().lower()
    if role == HUMAN_ROLE:
        human = (
            company.team_members.filter(
                is_active=True,
                role__in=[
                    CompanyTeamMember.Role.FOUNDER,
                    CompanyTeamMember.Role.DIRECTOR,
                    CompanyTeamMember.Role.PLANNER,
                    CompanyTeamMember.Role.OPERATIONS,
                ],
            )
            .order_by("role")
            .first()
        )
        if human:
            return CompanyTask.AssigneeType.HUMAN, None, human
        return CompanyTask.AssigneeType.UNASSIGNED, None, None

    agent = company.agents.filter(role=role).order_by("-priority").first()
    if not agent:
        agent = company.agents.filter(role=CompanyAgent.Role.PLANNER).first()
    if agent:
        return CompanyTask.AssigneeType.AGENT, agent, None
    return CompanyTask.AssigneeType.UNASSIGNED, None, None


def run_planning_session(session: PlanningSession) -> bool:
    """
    Execute LLM planning for a session; create tasks and dependencies.
    Returns True on success.
    """
    from apps.ideas.models import CompanyHistoryEntry

    company = session.company
    session.status = PlanningSession.Status.IN_PROGRESS
    session.save(update_fields=["status", "updated_at"])

    record_history(
        company,
        CompanyHistoryEntry.EntryType.PLANNING_STARTED,
        f"Planning started ({session.get_trigger_display()})",
        summary=session.week_start.isoformat() if session.week_start else "",
        related_planning_session=session,
    )

    context = build_strategic_planning_context(company)
    session.context_snapshot = context
    session.save(update_fields=["context_snapshot", "updated_at"])

    from apps.agents.agents import _run_agent
    from apps.agents.providers import get_model_for_idea, validate_provider_config
    from apps.agents.schemas import PlanningSessionOutput

    idea = company.idea_request
    err = validate_provider_config(idea.provider)
    if err:
        logger.error("Planning provider error: %s", err)
        session.status = PlanningSession.Status.FAILED
        session.save(update_fields=["status", "updated_at"])
        return False

    try:
        model = get_model_for_idea(idea)
    except (ValueError, ImportError) as e:
        logger.exception("Planning model setup failed: %s", e)
        session.status = PlanningSession.Status.FAILED
        session.save(update_fields=["status", "updated_at"])
        return False

    planner = company.agents.filter(role=CompanyAgent.Role.PLANNER).first()
    system = (
        planner.system_prompt
        if planner
        else "You are the company planner. Produce a focused weekly task scope."
    )
    week = session.week_start or monday_of_week()
    user_prompt = f"""Plan the company's work for the week starting {week}.

Use ONLY high-level context below. Prioritize founder-verified direction when present.
Assign each task to the best agent role or 'human' if founders/operators must act.
Use depends_on_indices for tasks that must wait on others (0-based within your task list).

Context:
{context}
"""

    try:
        output, _ = _run_agent(
            model,
            "planner",
            system,
            user_prompt,
            PlanningSessionOutput,
        )
    except Exception:
        logger.exception("Planning LLM failed for session %s", session.pk)
        session.status = PlanningSession.Status.FAILED
        session.save(update_fields=["status", "updated_at"])
        return False

    if not output or not getattr(output, "tasks", None):
        session.status = PlanningSession.Status.FAILED
        session.save(update_fields=["status", "updated_at"])
        return False

    _materialize_tasks(session, output, week)
    session.summary = (output.session_summary or "")[:4000]
    if output.progress_assessment:
        session.summary += "\n\nProgress: " + output.progress_assessment[:1500]
    session.status = PlanningSession.Status.COMPLETED
    session.save(update_fields=["summary", "status", "updated_at"])

    record_history(
        company,
        CompanyHistoryEntry.EntryType.PLANNING_COMPLETED,
        f"Planning completed — {len(output.tasks)} tasks",
        summary=session.summary[:500],
        related_planning_session=session,
    )
    return True


@transaction.atomic
def _materialize_tasks(
    session: PlanningSession, output: PlanningSessionOutput, week_start: date
) -> list[CompanyTask]:
    from apps.ideas.models import CompanyHistoryEntry

    company = session.company
    created: list[CompanyTask] = []

    for idx, item in enumerate(output.tasks):
        assignee_type, agent, human = resolve_assignee(company, item.suggested_role)
        target = week_start + timedelta(days=min(90, max(0, item.target_days_offset)))
        task = CompanyTask.objects.create(
            company=company,
            planning_session=session,
            title=item.title[:255],
            description=(item.description or "")[:8000],
            assignee_type=assignee_type,
            assigned_agent=agent,
            assigned_human=human,
            target_date=target,
            sort_order=idx,
        )
        created.append(task)
        record_history(
            company,
            CompanyHistoryEntry.EntryType.TASK_CREATED,
            task.title,
            summary=task.description[:300],
            related_task=task,
            related_planning_session=session,
        )

    for idx, item in enumerate(output.tasks):
        task = created[idx]
        for dep_idx in item.depends_on_indices or []:
            if 0 <= dep_idx < len(created) and dep_idx != idx:
                CompanyTaskDependency.objects.get_or_create(
                    task=task,
                    depends_on=created[dep_idx],
                )

    return created


def start_planning_session(
    company: Company,
    *,
    trigger: str = PlanningSession.Trigger.MANUAL,
    user: AbstractBaseUser | None = None,
    week_start: date | None = None,
) -> PlanningSession:
    """Create a planning session record (caller runs LLM or spawns subprocess)."""
    return PlanningSession.objects.create(
        company=company,
        trigger=trigger,
        week_start=week_start or monday_of_week(),
        created_by=user,
        status=PlanningSession.Status.DRAFT,
    )


def spawn_planning_process(session_pk: str) -> None:
    """Run planning in a background manage.py subprocess."""
    from apps.web.views import _get_project_root, _get_subprocess_env

    root = _get_project_root()
    subprocess.Popen(
        [
            sys.executable,
            os.path.join(root, "manage.py"),
            "run_planning_session",
            session_pk,
        ],
        cwd=root,
        env=_get_subprocess_env(),
        start_new_session=True,
    )
