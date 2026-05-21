"""Shared UI context for company workspace pages (nav, KPIs, attention items)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from django.urls import reverse
from django.utils import timezone

from apps.ideas.best_practices import assess_company_readiness
from apps.ideas.development_plan import get_development_plan_summary
from apps.ideas.models import (
    ActionProposal,
    Company,
    CompanyCalendarAction,
    CompanyTask,
    DirectorDiscussion,
)
from apps.ideas.planning_context import compute_progress_metrics, get_active_direction
from apps.ideas.task_execution import count_runnable_tasks, explain_task_skip

CompanyTab = Literal[
    "overview", "tasks", "planning", "direction", "calendar", "history", "discussions"
]


@dataclass(frozen=True)
class AttentionItem:
    severity: Literal["high", "medium", "low"]
    label: str
    detail: str
    href: str


def build_attention_items(company: Company, *, counts: dict[str, int]) -> list[AttentionItem]:
    """Actionable items surfaced at the top of the company workspace."""
    items: list[AttentionItem] = []
    pk = str(company.pk)

    if counts.get("awaiting_selection", 0) > 0:
        n = counts["awaiting_selection"]
        items.append(
            AttentionItem(
                severity="high",
                label=f"Review {n} discussion{'s' if n != 1 else ''} awaiting your decision",
                detail="Directors proposed actions — select or reject, then schedule.",
                href=reverse("company_detail", kwargs={"pk": pk}) + "#discussions",
            )
        )

    if counts.get("unscheduled_selected", 0) > 0:
        n = counts["unscheduled_selected"]
        items.append(
            AttentionItem(
                severity="high",
                label=f"Schedule {n} selected action{'s' if n != 1 else ''}",
                detail="Approved actions are not on the calendar yet.",
                href=reverse("company_detail", kwargs={"pk": pk}) + "#discussions",
            )
        )

    if counts.get("calendar_overdue", 0) > 0:
        n = counts["calendar_overdue"]
        items.append(
            AttentionItem(
                severity="high",
                label=f"{n} overdue calendar action{'s' if n != 1 else ''}",
                detail="Open the calendar and mark progress or defer.",
                href=reverse("company_calendar", kwargs={"company_pk": pk}),
            )
        )

    direction = get_active_direction(company)
    if not direction:
        items.append(
            AttentionItem(
                severity="medium",
                label="Set strategic direction",
                detail="Founders should align on direction before weekly planning.",
                href=reverse("company_direction", kwargs={"company_pk": pk}),
            )
        )
    elif not direction.founder_verified:
        items.append(
            AttentionItem(
                severity="medium",
                label="Verify strategic direction with founders",
                detail="Mark direction as founder-verified when aligned.",
                href=reverse("company_direction", kwargs={"company_pk": pk}),
            )
        )

    if counts.get("blocked_tasks", 0) > 0:
        n = counts["blocked_tasks"]
        items.append(
            AttentionItem(
                severity="medium",
                label=f"{n} blocked task{'s' if n != 1 else ''}",
                detail="Resolve dependencies or escalate to a human owner.",
                href=reverse("company_tasks", kwargs={"company_pk": pk}) + "?status=BLOCKED",
            )
        )

    if counts.get("runnable_tasks", 0) > 0 and company.status == Company.Status.ACTIVE:
        n = counts["runnable_tasks"]
        items.append(
            AttentionItem(
                severity="low",
                label=f"{n} agent task{'s' if n != 1 else ''} ready to run",
                detail="Execute now or wait for the hourly company ticker.",
                href=reverse("company_tasks", kwargs={"company_pk": pk}),
            )
        )

    if counts.get("readiness_fails", 0) > 0:
        n = counts["readiness_fails"]
        items.append(
            AttentionItem(
                severity="medium",
                label=f"{n} readiness check{'s' if n != 1 else ''} failing",
                detail="See readiness panel on overview for owners and next steps.",
                href=reverse("company_detail", kwargs={"pk": pk}) + "#readiness",
            )
        )

    if counts.get("open_tasks", 0) == 0 and company.status == Company.Status.ACTIVE:
        items.append(
            AttentionItem(
                severity="low",
                label="No tasks on the board",
                detail="Run planning to generate weekly scope from direction and pipeline KPIs.",
                href=reverse("company_planning", kwargs={"company_pk": pk}),
            )
        )

    return items


def _company_counts(company: Company) -> dict[str, int]:
    from apps.ideas.autonomous_loop import count_unscheduled_selected

    today = timezone.localdate()
    open_statuses = [
        CompanyTask.Status.TODO,
        CompanyTask.Status.IN_PROGRESS,
        CompanyTask.Status.BLOCKED,
    ]
    return {
        "open_tasks": company.tasks.filter(status__in=open_statuses).count(),
        "blocked_tasks": company.tasks.filter(status=CompanyTask.Status.BLOCKED).count(),
        "runnable_tasks": count_runnable_tasks(company),
        "unscheduled_selected": count_unscheduled_selected(company),
        "awaiting_selection": company.discussions.filter(
            status=DirectorDiscussion.Status.AWAITING_SELECTION
        ).count(),
        "active_discussions": company.discussions.filter(
            status=DirectorDiscussion.Status.ACTIVE
        ).count(),
        "calendar_today": company.calendar_actions.filter(
            action_date=today
        )
        .exclude(status=CompanyCalendarAction.ActionStatus.DONE)
        .count(),
        "calendar_overdue": company.calendar_actions.filter(
            action_date__lt=today
        )
        .exclude(
            status__in=[
                CompanyCalendarAction.ActionStatus.DONE,
                CompanyCalendarAction.ActionStatus.DEFERRED,
            ]
        )
        .count(),
        "calendar_open": company.calendar_actions.exclude(
            status__in=[
                CompanyCalendarAction.ActionStatus.DONE,
                CompanyCalendarAction.ActionStatus.DEFERRED,
            ]
        ).count(),
        "selected_actions": ActionProposal.objects.filter(
            discussion__company=company,
            status=ActionProposal.ActionStatus.SELECTED,
        ).count(),
    }


def build_company_workspace_context(
    company: Company,
    *,
    active_tab: CompanyTab = "overview",
) -> dict[str, Any]:
    """Context merged into all company workspace templates."""
    progress = compute_progress_metrics(company)
    readiness = assess_company_readiness(company)
    dev_plan = get_development_plan_summary(company.idea_request)
    direction = get_active_direction(company)
    counts = _company_counts(company)
    counts["readiness_fails"] = readiness.fail_count
    counts["readiness_warns"] = readiness.warn_count

    return {
        "company": company,
        "active_tab": active_tab,
        "progress": progress,
        "readiness": readiness,
        "dev_plan": dev_plan,
        "direction": direction,
        "counts": counts,
        "attention_items": build_attention_items(company, counts=counts),
        "go_no_go": (dev_plan.get("go_no_go") or "").strip(),
        "executive_summary": (dev_plan.get("executive_summary") or "").strip(),
    }


def annotate_task_execution_hints(tasks) -> None:
    """Set task.execution_hint on each task for the task board UI."""
    for task in tasks:
        if task.status == CompanyTask.Status.TODO:
            hint = explain_task_skip(task)
            task.execution_hint = None if hint == "eligible" else hint
        else:
            task.execution_hint = None
