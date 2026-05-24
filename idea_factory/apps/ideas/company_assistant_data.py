"""Read-only data fetchers for the company assistant (used by tools and Ollama fallback)."""
from __future__ import annotations

import json

from django.contrib.auth.models import AbstractBaseUser
from django.urls import reverse

from apps.core.access import is_company_owner
from apps.core.public_urls import public_absolute_url
from apps.ideas.autonomous_loop import count_unscheduled_selected
from apps.ideas.best_practices import assess_company_readiness
from apps.ideas.calendar_context import build_calendar_context
from apps.ideas.context import build_idea_request_prompt
from apps.ideas.development_plan import get_development_plan_summary
from apps.ideas.models import (
    ActionProposal,
    Company,
    CompanyTask,
    DirectorDiscussion,
)
from apps.ideas.planning_context import (
    build_strategic_planning_context,
    compute_progress_metrics,
    get_active_direction,
)

OPEN_TASK_STATUSES = [
    CompanyTask.Status.TODO,
    CompanyTask.Status.IN_PROGRESS,
    CompanyTask.Status.BLOCKED,
]


def _company_pk(company: Company) -> str:
    return str(company.pk)


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 40] + "\n...[truncated]"


def fetch_team_roster(company: Company) -> str:
    """Human team members and AI agent fleet (assignees)."""
    humans = list(
        company.team_members.filter(is_active=True)
        .select_related("user")
        .order_by("role", "name")
    )
    agents = list(company.agents.order_by("-priority", "name"))
    lines = ["Human team:"]
    if not humans:
        lines.append("- (no active team members)")
    else:
        for member in humans:
            linked = (
                f" (login: {member.user.get_username()})" if member.user_id else " (no login)"
            )
            lines.append(f"- {member.name} [{member.get_role_display()}]{linked}")
    lines.append("AI agents:")
    if not agents:
        lines.append("- (none)")
    else:
        for agent in agents:
            lines.append(f"- {agent.name} [{agent.get_role_display()}]")
    return "\n".join(lines)


def _task_line(company: Company, task: CompanyTask) -> str:
    path = reverse(
        "company_task_detail",
        kwargs={"company_pk": _company_pk(company), "task_pk": str(task.pk)},
    )
    assignee = ""
    if task.assigned_agent_id:
        assignee = f" → {task.assigned_agent.name} (agent)"
    elif task.assigned_human_id:
        assignee = f" → {task.assigned_human.name} (human)"
    blocked = " [blocked by deps]" if task.is_blocked_by_dependencies else ""
    line = (
        f"- [{task.title}]({public_absolute_url(path)}) "
        f"[{task.get_status_display()} {task.progress_percent}%]"
        f"{assignee}{blocked}"
    )
    if task.description:
        line += f"\n  {task.description[:200]}"
    if task.result_summary and task.status == CompanyTask.Status.DONE:
        line += f"\n  Result: {task.result_summary[:200]}"
    return line


def fetch_company_overview(company: Company) -> str:
    progress = compute_progress_metrics(company)
    dev = get_development_plan_summary(company.idea_request)
    awaiting = company.discussions.filter(
        status=DirectorDiscussion.Status.AWAITING_SELECTION
    ).count()
    lines = [
        f"Company: {company.name}",
        f"Status: {company.get_status_display()}",
        f"Autonomous mode: {company.autonomous_mode}",
        f"Open tasks: {progress['done_count']} done / "
        f"{progress.get('active_tasks', progress['total_tasks'])} active "
        f"({progress['completion_percent']}% complete)",
        f"Blocked tasks: {progress['blocked_count']}",
        f"Discussions awaiting your selection: {awaiting}",
        f"Unscheduled selected actions: {count_unscheduled_selected(company)}",
    ]
    if dev.get("go_no_go"):
        lines.append(f"GO/NO-GO: {dev['go_no_go']}")
    if dev.get("executive_summary"):
        lines.append(f"Executive summary: {dev['executive_summary'][:600]}")
    return "\n".join(lines)


def fetch_asking_user(company: Company, user: AbstractBaseUser) -> str:
    if is_company_owner(user, company):
        role = "company owner (full read access)"
    else:
        memberships = list(
            company.team_members.filter(user=user, is_active=True).values_list(
                "name", "role"
            )
        )
        role = (
            f"team member: {', '.join(f'{n} ({r})' for n, r in memberships)}"
            if memberships
            else "user with company access"
        )
    return f"Asking user: {user.get_username()} — {role}"


def fetch_tasks_for_current_user(
    company: Company,
    user: AbstractBaseUser,
    *,
    status_filter: str = "",
) -> str:
    """Human-assigned tasks for this user; owners without a team row get a hint."""
    member_ids = list(
        company.team_members.filter(user=user, is_active=True).values_list("pk", flat=True)
    )
    if not member_ids:
        if is_company_owner(user, company):
            return (
                "No human team membership linked to your account. "
                "Use get_open_tasks for the full company task board."
            )
        return "No tasks assigned — you are not linked as a team member on this company."

    qs = (
        company.tasks.filter(
            assignee_type=CompanyTask.AssigneeType.HUMAN,
            assigned_human_id__in=member_ids,
        )
        .select_related("assigned_human", "assigned_agent")
        .order_by("sort_order", "created_at")
    )
    if status_filter and status_filter.upper() in dict(CompanyTask.Status.choices):
        qs = qs.filter(status=status_filter.upper())
    tasks = list(qs[:40])
    if not tasks:
        label = f" (status={status_filter})" if status_filter else ""
        return f"No tasks assigned to you{label}."
    lines = [f"Tasks assigned to you ({len(tasks)} shown):"]
    lines.extend(_task_line(company, t) for t in tasks)
    return "\n".join(lines)


def fetch_open_tasks(
    company: Company,
    *,
    status_filter: str = "",
    limit: int = 40,
) -> str:
    qs = company.tasks.select_related("assigned_agent", "assigned_human").order_by(
        "sort_order", "created_at"
    )
    if status_filter and status_filter.upper() in dict(CompanyTask.Status.choices):
        qs = qs.filter(status=status_filter.upper())
    else:
        qs = qs.filter(status__in=OPEN_TASK_STATUSES)
    tasks = list(qs[:limit])
    if not tasks:
        return "No matching tasks on the board."
    lines = [f"Company tasks ({len(tasks)} shown):"]
    lines.extend(_task_line(company, t) for t in tasks)
    return "\n".join(lines)


def fetch_strategic_direction(company: Company) -> str:
    direction = get_active_direction(company)
    if not direction:
        return "Strategic direction: not set."
    verified = "founder-verified" if direction.founder_verified else "draft"
    path = reverse("company_direction", kwargs={"company_pk": _company_pk(company)})
    return (
        f"Strategic direction ({verified}): {direction.statement[:1200]}\n"
        f"Link: [{verified} direction]({public_absolute_url(path)})"
    )


def fetch_planning_sessions(company: Company, *, limit: int = 6) -> str:
    sessions = company.planning_sessions.order_by("-created_at")[:limit]
    if not sessions:
        return "Planning sessions: none."
    lines = ["Planning sessions:"]
    pk = _company_pk(company)
    for session in sessions:
        path = reverse(
            "company_planning_detail",
            kwargs={"company_pk": pk, "session_pk": str(session.pk)},
        )
        lines.append(
            f"- [{session.week_start or 'on-demand'}]({public_absolute_url(path)}) "
            f"[{session.get_status_display()}] {session.get_trigger_display()}"
        )
        if session.summary:
            lines.append(f"  Summary: {session.summary[:400]}")
    return "\n".join(lines)


def fetch_director_discussions(company: Company, *, limit: int = 8) -> str:
    discussions = company.discussions.order_by("-created_at")[:limit]
    if not discussions:
        return "Director discussions: none."
    lines = ["Director discussions and action proposals:"]
    pk = _company_pk(company)
    for disc in discussions:
        path = reverse(
            "director_discussion_detail",
            kwargs={"company_pk": pk, "discussion_pk": str(disc.pk)},
        )
        lines.append(
            f"- [{disc.topic}]({public_absolute_url(path)}) [{disc.get_status_display()}]"
        )
        for action in disc.actions.select_related("proposed_by").order_by("-created_at")[:6]:
            by = action.proposed_by.name if action.proposed_by_id else "Director"
            lines.append(
                f"  · {action.action_type} [{action.get_status_display()}] by {by}: "
                f"{action.description[:200]}"
            )
    pending = ActionProposal.objects.filter(
        discussion__company=company,
        status=ActionProposal.ActionStatus.PROPOSED,
    ).count()
    if pending:
        lines.append(f"Proposed actions awaiting selection: {pending}")
    return "\n".join(lines)


def fetch_calendar(company: Company) -> str:
    body = build_calendar_context(company)
    synced = company.calendar_actions.exclude(google_event_id="").count()
    total = company.calendar_actions.count()
    lines = [body, f"Google Calendar sync: {synced}/{total} entries have a linked Google event."]
    return "\n".join(lines)


def fetch_recent_history(company: Company, *, limit: int = 25) -> str:
    entries = (
        company.history_entries.select_related("related_task", "related_planning_session")
        .order_by("-created_at")[:limit]
    )
    if not entries:
        return "History: no entries yet."
    lines = ["Recent history (newest first):"]
    for entry in entries:
        lines.append(f"- [{entry.get_entry_type_display()}] {entry.title}")
        if entry.summary:
            lines.append(f"  {entry.summary[:200]}")
    return "\n".join(lines)


def fetch_readiness_report(company: Company) -> str:
    report = assess_company_readiness(company)
    lines = [
        f"Readiness phase: {report.phase}",
        f"Score: {report.score_percent}% "
        f"({report.pass_count} pass, {report.warn_count} warn, {report.fail_count} fail)",
    ]
    for check in report.checks:
        lines.append(f"- {check.icon} {check.label}: {check.message[:120]}")
    return "\n".join(lines)


def fetch_strategic_planning_snapshot(company: Company) -> str:
    return build_strategic_planning_context(company, max_task_lines=20)


def fetch_idea_pipeline_summary(company: Company, *, max_chars: int = 6_000) -> str:
    return _truncate(build_idea_request_prompt(company.idea_request), max_chars)


def fetch_navigation_links(company: Company) -> str:
    pk = _company_pk(company)
    links = {
        "overview": f"/companies/{pk}/",
        "tasks": f"/companies/{pk}/tasks/",
        "planning": f"/companies/{pk}/planning/",
        "direction": f"/companies/{pk}/direction/",
        "calendar": f"/companies/{pk}/calendar/",
        "history": f"/companies/{pk}/history/",
        "assistant": f"/companies/{pk}/assistant/",
    }
    absolute = {key: public_absolute_url(path) for key, path in links.items()}
    return (
        "Use markdown links [label](url) with these exact URLs (do not change the host):\n"
        + json.dumps(absolute, indent=2)
    )

