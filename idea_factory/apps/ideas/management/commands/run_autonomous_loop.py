"""
Autonomous company loop - self-running system.

For each ACTIVE company with autonomous_mode=True:
1. Agent selects best proposed actions (discussions AWAITING_SELECTION)
2. Agent schedules selected actions to calendar
3. Agent executes today's planned actions (marks DONE with notes)
4. Agent checks completed actions, spawns improvement discussion if needed
5. Auto-start discussion when appropriate (no pending work, time for next cycle)

Run via cron, e.g. daily:
  0 9 * * * cd /path/to/idea_factory && python manage.py run_autonomous_loop
"""
import logging
import os
import subprocess
import sys
from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.ideas.models import (
    ActionProposal,
    Company,
    CompanyCalendarAction,
    DirectorDiscussion,
)
from apps.agents.autonomous import (
    agent_check_result,
    agent_execute_calendar_action,
    agent_schedule_action,
    agent_select_actions,
)

logger = logging.getLogger(__name__)


def _company_start_date(company: Company):
    created = company.created_at
    if timezone.is_naive(created):
        return created.date()
    return timezone.localtime(created).date()


def _spawn_discussion_process(discussion_pk: str, root: str, env: dict) -> None:
    subprocess.Popen(
        [sys.executable, os.path.join(root, "manage.py"), "run_discussion", discussion_pk],
        cwd=root,
        env=env,
        start_new_session=True,
    )


def _run_autonomous_loop() -> None:
    today = timezone.localdate()
    companies = Company.objects.filter(
        status=Company.Status.ACTIVE, autonomous_mode=True
    )

    for company in companies:
        try:
            _process_company(company, today)
        except Exception as e:
            logger.exception("Autonomous loop failed for company %s: %s", company.pk, e)


def _process_company(company: Company, today: date) -> None:
    start_date = _company_start_date(company)
    if today < start_date:
        return

    # 1. Process discussions AWAITING_SELECTION - agent selects actions
    discussions = DirectorDiscussion.objects.filter(
        company=company, status=DirectorDiscussion.Status.AWAITING_SELECTION
    )
    for d in discussions:
        if d.actions.filter(status=ActionProposal.ActionStatus.PROPOSED).exists():
            agent_select_actions(d)

    # 2. Schedule selected actions that don't have calendar entries
    scheduled_ids = CompanyCalendarAction.objects.exclude(
        action_proposal__isnull=True
    ).values_list("action_proposal_id", flat=True)
    selected = ActionProposal.objects.filter(
        discussion__company=company,
        status=ActionProposal.ActionStatus.SELECTED,
    ).exclude(pk__in=scheduled_ids)
    for action in selected[:3]:  # Limit per run
        proposed_date = agent_schedule_action(company, action, start_date)
        if proposed_date and proposed_date < start_date:
            proposed_date = start_date
        if proposed_date:
            CompanyCalendarAction.objects.get_or_create(
                action_proposal=action,
                company=company,
                defaults={
                    "action_date": proposed_date,
                    "title": action.action_type,
                    "description": action.description,
                },
            )

    # 3. Execute today's planned actions
    due_actions = CompanyCalendarAction.objects.filter(
        company=company,
        action_date=today,
        status__in=[
            CompanyCalendarAction.ActionStatus.PLANNED,
            CompanyCalendarAction.ActionStatus.IN_PROGRESS,
        ],
    )
    for entry in due_actions:
        agent_execute_calendar_action(entry)

    # 4. Check recently completed actions for improvement
    recent_start = today - timedelta(days=3)
    done_entries = CompanyCalendarAction.objects.filter(
        company=company,
        action_date__gte=recent_start,
        action_date__lte=today,
        status=CompanyCalendarAction.ActionStatus.DONE,
    )
    for entry in done_entries[:2]:  # Limit per run
        topic = agent_check_result(entry)
        if topic:
            disc = DirectorDiscussion.objects.create(
                company=company,
                topic=topic,
                status=DirectorDiscussion.Status.ACTIVE,
            )
            root = _get_project_root()
            env = _get_subprocess_env()
            _spawn_discussion_process(str(disc.pk), root, env)
            logger.info("Spawned improvement discussion %s for company %s", disc.pk, company.pk)
            break  # One improvement discussion per run

    # 5. Auto-start discussion when idle
    last_discussion = (
        DirectorDiscussion.objects.filter(company=company)
        .order_by("-created_at")
        .first()
    )
    has_active = DirectorDiscussion.objects.filter(
        company=company, status=DirectorDiscussion.Status.ACTIVE
    ).exists()
    has_awaiting = DirectorDiscussion.objects.filter(
        company=company, status=DirectorDiscussion.Status.AWAITING_SELECTION
    ).exists()
    if not has_active and not has_awaiting:
        if not last_discussion or (timezone.now() - last_discussion.created_at) > timedelta(days=1):
            disc = DirectorDiscussion.objects.create(
                company=company,
                topic="Next steps",
                status=DirectorDiscussion.Status.ACTIVE,
            )
            root = _get_project_root()
            env = _get_subprocess_env()
            _spawn_discussion_process(str(disc.pk), root, env)
            logger.info("Auto-started discussion %s for company %s", disc.pk, company.pk)


def _get_project_root() -> str:
    # idea_factory/apps/ideas/management/commands/run_autonomous_loop.py -> idea_factory/
    path = os.path.abspath(__file__)
    for _ in range(5):
        path = os.path.dirname(path)
    return path


def _get_subprocess_env() -> dict:
    from apps.core.subprocess_env import enrich_subprocess_env

    root = _get_project_root()
    env = enrich_subprocess_env()
    env["PYTHONPATH"] = root + os.pathsep + env.get("PYTHONPATH", "")
    return env


class Command(BaseCommand):
    help = "Run autonomous loop for companies with autonomous_mode=True (agents select, schedule, execute, improve)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Log what would be done without making changes",
        )

    def handle(self, *args, **options):
        if options.get("dry_run"):
            self.stdout.write("Dry run - no changes")
            companies = Company.objects.filter(
                status=Company.Status.ACTIVE, autonomous_mode=True
            )
            for c in companies:
                self.stdout.write(f"  Would process: {c.name} ({c.pk})")
            return
        _run_autonomous_loop()
        self.stdout.write("Autonomous loop completed")
