"""Periodic activity checks for companies (tasks, planning, readiness)."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import timedelta

from django.utils import timezone

from apps.ideas.models import (
    Company,
    CompanyTask,
    PlanningSession,
)

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name, "true" if default else "false").strip().lower()
    return raw in ("true", "1", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def should_run_weekly_planning_now() -> bool:
    """True on Monday at or after TICKER_WEEKLY_PLANNING_HOUR (local time)."""
    if not _env_bool("TICKER_WEEKLY_PLANNING", True):
        return False
    now = timezone.localtime()
    if now.weekday() != 0:
        return False
    hour = _env_int("TICKER_WEEKLY_PLANNING_HOUR", 8)
    return now.hour >= hour


@dataclass
class ActivityCheckResult:
    active_companies: int = 0
    overdue_tasks: int = 0
    stale_planning_sessions: int = 0
    open_tasks: int = 0
    messages: list[str] = field(default_factory=list)


def run_activity_checks(
    *,
    stale_planning_hours: int = 2,
) -> ActivityCheckResult:
    """
    Inspect company activity without LLM calls.
    - Mark planning sessions stuck IN_PROGRESS as FAILED.
    - Count overdue open tasks (target_date in the past).
    """
    now = timezone.now()
    today = timezone.localdate()
    result = ActivityCheckResult()

    active = Company.objects.filter(status=Company.Status.ACTIVE)
    result.active_companies = active.count()

    stale_cutoff = now - timedelta(hours=stale_planning_hours)
    stale_qs = PlanningSession.objects.filter(
        status=PlanningSession.Status.IN_PROGRESS,
        updated_at__lt=stale_cutoff,
    )
    stale_count = stale_qs.update(status=PlanningSession.Status.FAILED)
    result.stale_planning_sessions = stale_count
    if stale_count:
        msg = f"Marked {stale_count} stale planning session(s) as FAILED."
        result.messages.append(msg)
        logger.warning(msg)

    open_tasks = CompanyTask.objects.exclude(
        status__in=[CompanyTask.Status.DONE, CompanyTask.Status.CANCELLED]
    )
    result.open_tasks = open_tasks.count()

    overdue = open_tasks.filter(target_date__lt=today).exclude(target_date__isnull=True)
    result.overdue_tasks = overdue.count()
    if result.overdue_tasks:
        msg = f"{result.overdue_tasks} open task(s) past target date."
        result.messages.append(msg)
        logger.info(msg)
        for task in overdue.select_related("company")[:20]:
            logger.info(
                "Overdue task %s [%s] company=%s due=%s",
                task.pk,
                task.title,
                task.company.name,
                task.target_date,
            )

    return result
