"""Autonomous company loop — schedule, execute, and cycle discussions."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, timedelta

from django.utils import timezone

from apps.agents.autonomous import (
    agent_check_result,
    agent_execute_calendar_action,
    agent_schedule_action,
    agent_select_actions,
)
from apps.ideas.models import (
    ActionProposal,
    Company,
    CompanyCalendarAction,
    DirectorDiscussion,
)

logger = logging.getLogger(__name__)


@dataclass
class CompanyLoopResult:
    actions_selected: int = 0
    actions_scheduled: int = 0
    actions_executed: int = 0
    improvement_discussion_started: bool = False
    next_steps_discussion_started: bool = False


def company_start_date(company: Company) -> date:
    created = company.created_at
    if timezone.is_naive(created):
        return created.date()
    return timezone.localtime(created).date()


def scheduled_action_proposal_ids() -> list:
    return list(
        CompanyCalendarAction.objects.exclude(action_proposal__isnull=True).values_list(
            "action_proposal_id", flat=True
        )
    )


def unscheduled_selected_actions(company: Company):
    """Selected proposals not yet on the company calendar."""
    return ActionProposal.objects.filter(
        discussion__company=company,
        status=ActionProposal.ActionStatus.SELECTED,
    ).exclude(pk__in=scheduled_action_proposal_ids())


def count_unscheduled_selected(company: Company) -> int:
    return unscheduled_selected_actions(company).count()


def process_company(
    company: Company,
    today: date | None = None,
    *,
    schedule_and_execute_only: bool = False,
) -> CompanyLoopResult:
    """
    Run autonomous steps for one company.

    When schedule_and_execute_only is True (e.g. manual-mode owner trigger),
    only schedules selected actions and executes today's calendar items.
    """
    today = today or timezone.localdate()
    result = CompanyLoopResult()
    start_date = company_start_date(company)
    if today < start_date:
        return result

    run_full = company.autonomous_mode and not schedule_and_execute_only

    if run_full:
        discussions = DirectorDiscussion.objects.filter(
            company=company, status=DirectorDiscussion.Status.AWAITING_SELECTION
        )
        for discussion in discussions:
            if discussion.actions.filter(
                status=ActionProposal.ActionStatus.PROPOSED
            ).exists():
                before = discussion.actions.filter(
                    status=ActionProposal.ActionStatus.SELECTED
                ).count()
                if agent_select_actions(discussion):
                    after = discussion.actions.filter(
                        status=ActionProposal.ActionStatus.SELECTED
                    ).count()
                    result.actions_selected += max(0, after - before)

    scheduled_ids = scheduled_action_proposal_ids()
    selected = ActionProposal.objects.filter(
        discussion__company=company,
        status=ActionProposal.ActionStatus.SELECTED,
    ).exclude(pk__in=scheduled_ids)
    for action in selected[:3]:
        proposed_date = agent_schedule_action(company, action, start_date)
        if proposed_date and proposed_date < start_date:
            proposed_date = start_date
        if proposed_date:
            _, created = CompanyCalendarAction.objects.get_or_create(
                action_proposal=action,
                company=company,
                defaults={
                    "action_date": proposed_date,
                    "title": action.action_type,
                    "description": action.description,
                },
            )
            if created:
                result.actions_scheduled += 1

    due_actions = CompanyCalendarAction.objects.filter(
        company=company,
        action_date=today,
        status__in=[
            CompanyCalendarAction.ActionStatus.PLANNED,
            CompanyCalendarAction.ActionStatus.IN_PROGRESS,
        ],
    )
    for entry in due_actions:
        if agent_execute_calendar_action(entry):
            result.actions_executed += 1

    if not run_full:
        return result

    recent_start = today - timedelta(days=3)
    done_entries = CompanyCalendarAction.objects.filter(
        company=company,
        action_date__gte=recent_start,
        action_date__lte=today,
        status=CompanyCalendarAction.ActionStatus.DONE,
    )
    for entry in done_entries[:2]:
        topic = agent_check_result(entry)
        if topic:
            disc = DirectorDiscussion.objects.create(
                company=company,
                topic=topic,
                status=DirectorDiscussion.Status.ACTIVE,
            )
            _spawn_discussion_process(str(disc.pk))
            result.improvement_discussion_started = True
            logger.info(
                "Spawned improvement discussion %s for company %s",
                disc.pk,
                company.pk,
            )
            break

    last_discussion = (
        DirectorDiscussion.objects.filter(company=company).order_by("-created_at").first()
    )
    has_active = DirectorDiscussion.objects.filter(
        company=company, status=DirectorDiscussion.Status.ACTIVE
    ).exists()
    has_awaiting = DirectorDiscussion.objects.filter(
        company=company, status=DirectorDiscussion.Status.AWAITING_SELECTION
    ).exists()
    if not has_active and not has_awaiting:
        if not last_discussion or (
            timezone.now() - last_discussion.created_at
        ) > timedelta(days=1):
            disc = DirectorDiscussion.objects.create(
                company=company,
                topic="Next steps",
                status=DirectorDiscussion.Status.ACTIVE,
            )
            _spawn_discussion_process(str(disc.pk))
            result.next_steps_discussion_started = True
            logger.info("Auto-started discussion %s for company %s", disc.pk, company.pk)

    return result


def run_autonomous_loop(today: date | None = None) -> None:
    """Process all ACTIVE companies with autonomous_mode enabled."""
    today = today or timezone.localdate()
    companies = Company.objects.filter(
        status=Company.Status.ACTIVE, autonomous_mode=True
    )
    for company in companies:
        try:
            process_company(company, today)
        except Exception as e:
            logger.exception("Autonomous loop failed for company %s: %s", company.pk, e)


def _get_project_root() -> str:
    path = os.path.abspath(__file__)
    for _ in range(4):
        path = os.path.dirname(path)
    return path


def _get_subprocess_env() -> dict:
    from apps.core.subprocess_env import enrich_subprocess_env

    root = _get_project_root()
    env = enrich_subprocess_env()
    env["PYTHONPATH"] = root + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _spawn_discussion_process(discussion_pk: str) -> None:
    root = _get_project_root()
    subprocess.Popen(
        [sys.executable, os.path.join(root, "manage.py"), "run_discussion", discussion_pk],
        cwd=root,
        env=_get_subprocess_env(),
        start_new_session=True,
    )
