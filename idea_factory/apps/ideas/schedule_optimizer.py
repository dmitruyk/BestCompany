"""LLM-assisted redistribution of company task due dates to close schedule gaps."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.agents.autonomous import _build_calendar_context, _get_provider_model
from apps.agents.agents import _run_agent
from apps.agents.schemas import ScheduleOptimizationOutput
from apps.ideas.company_history import record_history
from apps.ideas.models import (
    Company,
    CompanyHistoryEntry,
    CompanyTask,
)

logger = logging.getLogger(__name__)

OPEN_STATUSES = (
    CompanyTask.Status.TODO,
    CompanyTask.Status.BLOCKED,
)


@dataclass
class ScheduleOptimizeResult:
    ok: bool
    tasks_moved: int = 0
    summary: str = ""
    error: str = ""


def schedulable_tasks(company: Company) -> list[CompanyTask]:
    """Open tasks with a due date or assignee — candidates for schedule optimization."""
    return list(
        company.tasks.filter(status__in=OPEN_STATUSES)
        .exclude(target_date__isnull=True)
        .select_related("assigned_agent", "assigned_human", "calendar_action")
        .prefetch_related("dependencies__depends_on")
        .order_by("target_date", "sort_order", "created_at")
    )


def count_schedulable_tasks(company: Company) -> int:
    return company.tasks.filter(
        status__in=OPEN_STATUSES,
        target_date__isnull=False,
    ).count()


def _is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def _next_calendar_day(d: date) -> date:
    return d + timedelta(days=1)


def _next_weekday(d: date) -> date:
    n = d + timedelta(days=1)
    while _is_weekend(n):
        n += timedelta(days=1)
    return n


def _snap_for_assignee(d: date, assignee_type: str) -> date:
    if assignee_type == CompanyTask.AssigneeType.HUMAN and _is_weekend(d):
        return _next_weekday(d - timedelta(days=1))
    return d


def _dependency_earliest(task: CompanyTask) -> Optional[date]:
    earliest: Optional[date] = None
    for dep in task.dependencies.all():
        prereq = dep.depends_on
        if prereq.status in (CompanyTask.Status.DONE, CompanyTask.Status.CANCELLED):
            continue
        if prereq.target_date is None:
            continue
        candidate = (
            _next_weekday(prereq.target_date)
            if task.assignee_type == CompanyTask.AssigneeType.HUMAN
            else _next_calendar_day(prereq.target_date)
        )
        if earliest is None or candidate > earliest:
            earliest = candidate
    return earliest


def _topological_order(tasks: list[CompanyTask]) -> list[CompanyTask]:
    by_id = {t.pk: t for t in tasks}
    in_degree = {t.pk: 0 for t in tasks}
    dependents: dict = {t.pk: [] for t in tasks}
    for t in tasks:
        for dep in t.dependencies.all():
            if dep.depends_on_id in by_id:
                in_degree[t.pk] += 1
                dependents[dep.depends_on_id].append(t.pk)
    queue = [t.pk for t in tasks if in_degree[t.pk] == 0]
    ordered: list[CompanyTask] = []
    while queue:
        pk = queue.pop(0)
        ordered.append(by_id[pk])
        for child_pk in dependents[pk]:
            in_degree[child_pk] -= 1
            if in_degree[child_pk] == 0:
                queue.append(child_pk)
    if len(ordered) < len(tasks):
        seen = {t.pk for t in ordered}
        for t in tasks:
            if t.pk not in seen:
                ordered.append(t)
    return ordered


def _pack_agent_dates(
    agent_tasks: list[CompanyTask], anchor: date
) -> dict:
    """Assign consecutive calendar days (including weekends) for agent tasks."""
    cursor = anchor
    dates: dict = {}
    for task in _topological_order(agent_tasks):
        dep_min = _dependency_earliest(task)
        d = cursor
        if dep_min and dep_min > d:
            d = dep_min
        if d < anchor:
            d = anchor
        dates[task.pk] = d
        cursor = _next_calendar_day(d)
    return dates


def _pack_human_dates(
    human_tasks: list[CompanyTask], anchor: date
) -> dict:
    """Assign weekdays only for human tasks."""
    cursor = anchor if not _is_weekend(anchor) else _next_weekday(anchor - timedelta(days=1))
    dates: dict = {}
    for task in _topological_order(human_tasks):
        dep_min = _dependency_earliest(task)
        d = cursor
        if dep_min and dep_min > d:
            d = dep_min
        d = _snap_for_assignee(d, CompanyTask.AssigneeType.HUMAN)
        if d < anchor:
            d = _snap_for_assignee(anchor, CompanyTask.AssigneeType.HUMAN)
        dates[task.pk] = d
        cursor = _next_weekday(d)
    return dates


def enforce_schedule_rules(
    tasks: list[CompanyTask], start_date: date, llm_dates: Optional[dict] = None
) -> dict:
    """
    Build final dates honoring dependencies, agent consecutive days, and human weekdays.
    llm_dates maps task pk -> suggested date (used as soft target when packing).
    """
    llm_dates = llm_dates or {}
    agent_tasks = [
        t
        for t in tasks
        if t.assignee_type == CompanyTask.AssigneeType.AGENT
        or (
            t.assignee_type == CompanyTask.AssigneeType.UNASSIGNED
            and t.assigned_agent_id
        )
    ]
    human_tasks = [
        t
        for t in tasks
        if t.assignee_type == CompanyTask.AssigneeType.HUMAN
        or (
            t.assignee_type == CompanyTask.AssigneeType.UNASSIGNED
            and t.assigned_human_id
            and not t.assigned_agent_id
        )
    ]
    other = [t for t in tasks if t not in agent_tasks and t not in human_tasks]
    for t in other:
        if t.assignee_type == CompanyTask.AssigneeType.HUMAN:
            human_tasks.append(t)
        else:
            agent_tasks.append(t)

    if agent_tasks and llm_dates:
        agent_tasks.sort(
            key=lambda t: (llm_dates.get(t.pk, t.target_date or start_date), t.sort_order)
        )
    if human_tasks and llm_dates:
        human_tasks.sort(
            key=lambda t: (llm_dates.get(t.pk, t.target_date or start_date), t.sort_order)
        )

    final: dict = {}
    final.update(_pack_agent_dates(agent_tasks, start_date))
    if final:
        human_anchor = _next_weekday(max(final.values()))
    elif _is_weekend(start_date):
        human_anchor = _next_weekday(start_date - timedelta(days=1))
    else:
        human_anchor = start_date
    final.update(_pack_human_dates(human_tasks, human_anchor))
    for t in other:
        if t.pk not in final:
            d = llm_dates.get(t.pk) or t.target_date or start_date
            final[t.pk] = _snap_for_assignee(max(d, start_date), t.assignee_type)
    return final


def build_task_schedule_context(
    company: Company,
    tasks: list[CompanyTask],
    start_date: date,
) -> str:
    lines = [
        f"Company: {company.name}",
        f"Schedule anchor (do not assign before): {start_date.isoformat()}",
        f"Today: {timezone.localdate().isoformat()}",
        "",
        "Schedulable tasks (1-based index — return moves using these indices):",
    ]
    if not tasks:
        lines.append("(none)")
    for i, task in enumerate(tasks, start=1):
        assignee = "agent"
        if task.assignee_type == CompanyTask.AssigneeType.HUMAN:
            assignee = "human"
        elif task.assigned_human_id and not task.assigned_agent_id:
            assignee = "human"
        elif task.assigned_agent_id:
            assignee = "agent"
        dep_idxs = []
        task_by_pk = {t.pk: j for j, t in enumerate(tasks, start=1)}
        for dep in task.dependencies.all():
            if dep.depends_on_id in task_by_pk:
                dep_idxs.append(str(task_by_pk[dep.depends_on_id]))
        dep_txt = f" depends on task(s): {', '.join(dep_idxs)}" if dep_idxs else ""
        due = task.target_date.isoformat() if task.target_date else "—"
        lines.append(
            f"{i}. [{assignee}] {task.title} — due {due} — {task.get_status_display()}{dep_txt}"
        )
    lines.append("")
    lines.append(_build_calendar_context(company, start_date))
    return "\n".join(lines)


def agent_optimize_task_schedule(
    company: Company, tasks: list[CompanyTask], start_date: date
) -> tuple[Optional[ScheduleOptimizationOutput], Optional[str]]:
    idea = company.idea_request
    model = _get_provider_model(idea)
    if not model:
        return None, "LLM provider is not configured."
    context = build_task_schedule_context(company, tasks, start_date)
    system = """You are a schedule optimizer for a company task board.

Goal: reduce large empty gaps between due dates by moving tasks earlier when possible,
while respecting dependencies and assignee rules.

Rules (mandatory):
- Agent tasks (assignee type agent): use every calendar day in sequence — including
  Saturday and Sunday. Do not skip calendar days between consecutive agent tasks.
- Human tasks: due dates must fall on weekdays only (Monday–Friday). Never assign
  Saturday or Sunday to human tasks.
- A task cannot be due before any unfinished prerequisite task it depends on.
- Do not assign any date before the schedule anchor.
- Only include tasks in moves that should change; omit tasks that stay on the same date.
- Prefer moving later tasks earlier to fill gaps; never move a task before its prerequisites.

Return valid JSON with summary and moves (task_index, new_target_date YYYY-MM-DD, reason)."""
    out, _ = _run_agent(
        model,
        "schedule_optimizer",
        system,
        context,
        ScheduleOptimizationOutput,
        tools=None,
    )
    if not out:
        return None, "Schedule optimizer returned no result."
    return out, None


def _parse_llm_dates(
    tasks: list[CompanyTask], output: ScheduleOptimizationOutput
) -> dict:
    dates: dict = {}
    for move in output.moves or []:
        idx = move.task_index
        if idx < 1 or idx > len(tasks):
            continue
        try:
            d = date.fromisoformat(move.new_target_date.strip())
        except (ValueError, AttributeError):
            continue
        dates[tasks[idx - 1].pk] = d
    return dates


@transaction.atomic
def optimize_company_schedule(
    company: Company, *, start_date: Optional[date] = None
) -> ScheduleOptimizeResult:
    today = timezone.localdate()
    created = company.created_at.date()
    anchor = start_date or max(today, created)
    tasks = schedulable_tasks(company)
    if len(tasks) < 2:
        return ScheduleOptimizeResult(
            ok=False,
            error="Need at least two open tasks with due dates to optimize.",
        )

    llm_out, err = agent_optimize_task_schedule(company, tasks, anchor)
    if err:
        return ScheduleOptimizeResult(ok=False, error=err)

    llm_dates = _parse_llm_dates(tasks, llm_out) if llm_out else {}
    final_dates = enforce_schedule_rules(tasks, anchor, llm_dates)

    moved = 0
    for task in tasks:
        new_date = final_dates.get(task.pk)
        if not new_date or task.target_date == new_date:
            continue
        old = task.target_date
        task.target_date = new_date
        task.save(update_fields=["target_date", "updated_at"])
        moved += 1
        if not task.calendar_action_id:
            from apps.core.google_calendar import sync_task_to_google_calendar

            sync_task_to_google_calendar(task)
        record_history(
            company,
            CompanyHistoryEntry.EntryType.TASK_UPDATED,
            f"Due date: {task.title}",
            summary=f"Schedule optimize: {old} → {new_date}",
            related_task=task,
            metadata={"old_date": old.isoformat(), "new_date": new_date.isoformat()},
        )

    calendar_actions_moved = 0
    if moved > 0:
        from apps.core.google_calendar import (
            align_calendar_actions_with_task_dates,
            sync_company_calendar_actions,
        )

        calendar_actions_moved = align_calendar_actions_with_task_dates(
            tasks, final_dates
        )
        sync_company_calendar_actions(company)

    summary = (llm_out.summary if llm_out else "") or f"Moved {moved} task(s)."
    if moved > 0:
        summary = (
            f"{summary} Google Calendar was updated for moved tasks and calendar actions."
        )
    elif calendar_actions_moved:
        summary = (
            f"{summary} ({calendar_actions_moved} linked calendar action"
            f"{'s' if calendar_actions_moved != 1 else ''} rescheduled for Google Calendar.)"
        )
    return ScheduleOptimizeResult(ok=True, tasks_moved=moved, summary=summary)


def tasks_by_date_for_month(
    company: Company, first: date, last: date
) -> dict[date, list[CompanyTask]]:
    """Tasks with target_date in range for calendar display."""
    qs = (
        company.tasks.filter(
            target_date__gte=first,
            target_date__lte=last,
        )
        .exclude(status=CompanyTask.Status.CANCELLED)
        .select_related("assigned_agent", "assigned_human")
        .order_by("target_date", "sort_order")
    )
    by_date: dict[date, list[CompanyTask]] = {}
    for task in qs:
        d = task.target_date
        if d not in by_date:
            by_date[d] = []
        by_date[d].append(task)
    return by_date
