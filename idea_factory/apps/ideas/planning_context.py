"""Build high-level company context for strategic planning (not full task dumps)."""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from apps.ideas.development_plan import get_development_plan_summary
from apps.ideas.models import (
    Company,
    CompanyStrategicDirection,
    CompanyTask,
    PlanningSession,
)


def get_active_direction(company: Company) -> CompanyStrategicDirection | None:
    return (
        company.strategic_directions.filter(is_active=True)
        .order_by("-created_at")
        .first()
    )


def build_strategic_planning_context(company: Company, max_task_lines: int = 25) -> str:
    """
    High-level context for LLM planning: direction, milestones, completed task outcomes,
    and open work summaries — not full descriptions.
    """
    lines: list[str] = [f"Company: {company.name}"]

    direction = get_active_direction(company)
    if direction:
        verified = "founder-verified" if direction.founder_verified else "draft"
        lines.append(f"Strategic direction ({verified}): {direction.statement[:800]}")
    else:
        lines.append(
            "Strategic direction: not set — propose tasks aligned with idea pipeline milestones."
        )

    dev = get_development_plan_summary(company.idea_request)
    if dev.get("executive_summary"):
        lines.append(f"Pipeline summary: {dev['executive_summary'][:400]}")
    if dev.get("milestones"):
        lines.append("Milestones: " + "; ".join(str(m) for m in dev["milestones"][:6]))
    if dev.get("kpis"):
        lines.append("KPIs: " + "; ".join(str(k) for k in dev["kpis"][:6]))

    last_session = (
        company.planning_sessions.filter(status=PlanningSession.Status.COMPLETED)
        .order_by("-created_at")
        .first()
    )
    if last_session and last_session.summary:
        lines.append(f"Last planning ({last_session.week_start}): {last_session.summary[:500]}")

    done_tasks = (
        company.tasks.filter(status=CompanyTask.Status.DONE)
        .exclude(result_summary="")
        .order_by("-completed_at")[:max_task_lines]
    )
    if done_tasks.exists():
        lines.append("Completed task outcomes (for next plan):")
        for t in done_tasks:
            lines.append(
                f"- {t.title}: {t.result_summary[:200]}"
                + (f" [{t.progress_percent}%]" if t.progress_percent else "")
            )

    open_tasks = company.tasks.exclude(
        status__in=[CompanyTask.Status.DONE, CompanyTask.Status.CANCELLED]
    ).order_by("sort_order", "created_at")[:max_task_lines]
    if open_tasks.exists():
        lines.append("Open work:")
        for t in open_tasks:
            assignee = ""
            if t.assigned_agent_id:
                assignee = f" → {t.assigned_agent.name}"
            elif t.assigned_human_id:
                assignee = f" → {t.assigned_human.name} (human)"
            blocked = " [blocked by deps]" if t.is_blocked_by_dependencies else ""
            lines.append(
                f"- {t.title} [{t.get_status_display()} {t.progress_percent}%]{assignee}{blocked}"
            )

    return "\n".join(lines)


def compute_progress_metrics(company: Company) -> dict:
    """Estimate progress toward goals from task completion."""
    qs = company.tasks.all()
    total = qs.count()
    if total == 0:
        return {
            "total_tasks": 0,
            "done_count": 0,
            "in_progress_count": 0,
            "blocked_count": 0,
            "completion_percent": 0,
            "weighted_progress_percent": 0,
            "has_direction": get_active_direction(company) is not None,
            "direction_verified": bool(
                get_active_direction(company) and get_active_direction(company).founder_verified
            ),
        }

    done = qs.filter(status=CompanyTask.Status.DONE).count()
    in_progress = qs.filter(status=CompanyTask.Status.IN_PROGRESS).count()
    blocked = qs.filter(status=CompanyTask.Status.BLOCKED).count()
    active = total - qs.filter(
        status__in=[CompanyTask.Status.CANCELLED]
    ).count()

    completion_percent = int(round(100 * done / active)) if active else 0

    weighted = 0
    for t in qs.exclude(status=CompanyTask.Status.CANCELLED):
        if t.status == CompanyTask.Status.DONE:
            weighted += 100
        else:
            weighted += min(100, max(0, t.progress_percent))
    weighted_progress = int(round(weighted / active)) if active else 0

    direction = get_active_direction(company)
    return {
        "total_tasks": total,
        "active_tasks": active,
        "done_count": done,
        "in_progress_count": in_progress,
        "blocked_count": blocked,
        "completion_percent": completion_percent,
        "weighted_progress_percent": weighted_progress,
        "has_direction": direction is not None,
        "direction_verified": bool(direction and direction.founder_verified),
    }
