"""Autonomous company loop - agents make plans, select, schedule, execute, and improve."""
import json
import logging
from datetime import date, timedelta
from typing import Any, Optional

from apps.ideas.models import (
    ActionProposal,
    Company,
    CompanyAgent,
    CompanyCalendarAction,
    DirectorDiscussion,
    IdeaRequest,
)

from .agents import _run_agent
from .providers import get_model_for_idea, validate_provider_config
from .schemas import (
    ActionSelectionOutput,
    ExecutionOutput,
    ResultCheckOutput,
    ScheduleProposalOutput,
)

logger = logging.getLogger(__name__)


def _get_provider_model(idea_request: IdeaRequest) -> Any | None:
    """Get model for idea_request provider."""
    try:
        err = validate_provider_config(idea_request.provider)
        if err:
            logger.error("Provider config error: %s", err)
            return None
        return get_model_for_idea(idea_request)
    except (ValueError, ImportError) as e:
        logger.error("Provider setup failed: %s", e)
        return None


def _build_calendar_context(company: Company, start_date: date) -> str:
    """Build calendar state for agents."""
    end = start_date + timedelta(days=60)
    entries = CompanyCalendarAction.objects.filter(
        company=company, action_date__gte=start_date, action_date__lte=end
    ).order_by("action_date", "title")[:60]
    if not entries:
        return "No calendar actions yet."
    lines = [f"Calendar {start_date} through {end}:"]
    for e in entries:
        lines.append(f"- {e.action_date}: {e.title} [{e.get_status_display}]")
    return "\n".join(lines)


def agent_select_actions(discussion: DirectorDiscussion) -> bool:
    """
    Agent selects best proposed actions. Marks them SELECTED.
    Returns True if selection was made.
    """
    actions = list(
        discussion.actions.filter(status=ActionProposal.ActionStatus.PROPOSED).order_by(
            "created_at"
        )
    )
    if not actions:
        return False

    idea = discussion.company.idea_request
    model = _get_provider_model(idea)
    if not model:
        logger.error("Provider setup failed for action selection")
        return False

    lines = []
    for i, a in enumerate(actions, start=1):
        lines.append(
            f"{i}. [{a.action_type}] {a.description[:200]}"
            + ("..." if len(a.description) > 200 else "")
            + f" (by {a.proposed_by.name if a.proposed_by else 'Unknown'})"
        )
    context = (
        f"Company: {discussion.company.name}\n"
        f"Topic: {discussion.topic}\n"
        f"Proposed actions:\n" + "\n".join(lines)
    )
    system = """You are an orchestrator. Select 1-2 best actions from the proposals.
Consider impact, feasibility, and alignment with company goals. Output valid JSON with
selected_action_ids (1-based indices) and rationale."""
    out, _ = _run_agent(
        model, "action_selector", system, context, ActionSelectionOutput, tools=None
    )
    if not out or not out.selected_action_ids:
        return False
    selected = []
    for idx in out.selected_action_ids:
        if 1 <= idx <= len(actions):
            selected.append(actions[idx - 1])
    for a in selected:
        a.status = ActionProposal.ActionStatus.SELECTED
        a.save(update_fields=["status"])
    logger.info("Agent selected %d actions for discussion %s", len(selected), discussion.pk)
    return True


def agent_schedule_action(
    company: Company, action: ActionProposal, start_date: date
) -> Optional[date]:
    """
    Agent proposes calendar date for selected action. Returns the date or None.
    """
    idea = company.idea_request
    model = _get_provider_model(idea)
    if not model:
        return None
    calendar_ctx = _build_calendar_context(company, start_date)
    context = (
        f"Company: {company.name}\n"
        f"Action to schedule: {action.action_type}\n{action.description[:500]}\n\n"
        f"{calendar_ctx}"
    )
    system = """You are a scheduler. Assign the best date for this action.
Consider existing calendar entries and logical sequencing. Return action_date in YYYY-MM-DD."""
    out, _ = _run_agent(
        model, "scheduler", system, context, ScheduleProposalOutput, tools=None
    )
    if not out or not out.action_date:
        return start_date
    try:
        return date.fromisoformat(out.action_date.strip())
    except (ValueError, AttributeError):
        return start_date


def agent_execute_calendar_action(entry: CompanyCalendarAction) -> bool:
    """
    Agent 'executes' a calendar action: produces completion notes and marks DONE.
    Returns True on success.
    """
    company = entry.company
    idea = company.idea_request
    model = _get_provider_model(idea)
    if not model:
        return False
    start_date = company.created_at.date()
    calendar_ctx = _build_calendar_context(company, start_date)
    context = (
        f"Company: {company.name}\n"
        f"Action due {entry.action_date}: {entry.title}\n{entry.description}\n\n"
        f"{calendar_ctx}"
    )
    system = """You are an executor. Simulate completing this action.
Provide completion_notes (what was accomplished), outcome_assessment (success/partial/needs_follow_up),
and whether follow_up_suggested."""
    out, _ = _run_agent(
        model, "executor", system, context, ExecutionOutput, tools=None
    )
    if not out:
        return False
    entry.completion_notes = out.completion_notes
    if out.outcome_assessment:
        entry.completion_notes += f"\n[Assessment: {out.outcome_assessment}]"
    entry.status = CompanyCalendarAction.ActionStatus.DONE
    entry.save(update_fields=["status", "completion_notes", "updated_at"])
    logger.info("Agent executed calendar action %s", entry.pk)
    return True


def agent_check_result(entry: CompanyCalendarAction) -> Optional[str]:
    """
    Agent evaluates a completed action. Returns improvement_topic if needs_improvement, else None.
    """
    company = entry.company
    idea = company.idea_request
    model = _get_provider_model(idea)
    if not model:
        return None
    context = (
        f"Company: {company.name}\n"
        f"Completed: {entry.title}\n"
        f"Notes: {entry.completion_notes}\n"
    )
    system = """Evaluate this completed action. Rate quality (0-1). If it needs improvement or follow-up,
set needs_improvement=True and provide improvement_topic for a new discussion."""
    out, _ = _run_agent(
        model, "result_checker", system, context, ResultCheckOutput, tools=None
    )
    if not out or not out.needs_improvement:
        return None
    return out.improvement_topic or f"Follow up: {entry.title}"
