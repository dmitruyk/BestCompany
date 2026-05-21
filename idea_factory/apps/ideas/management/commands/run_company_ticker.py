"""
Company activity ticker — runs autonomous loop, weekly planning, and health checks.

Docker (loop):
  python manage.py run_company_ticker --loop

Cron / one-shot:
  python manage.py run_company_ticker --once

Environment:
  TICKER_INTERVAL_SECONDS  — sleep between ticks in --loop mode (default 3600)
  TICKER_ENABLED           — set false to no-op (default true)
  TICKER_WEEKLY_PLANNING   — run run_weekly_planning on Mondays (default true)
  TICKER_WEEKLY_PLANNING_HOUR — local hour (0-23) to allow weekly planning (default 8)
  TICKER_STALE_PLANNING_HOURS — hours before IN_PROGRESS planning is FAILED (default 2)
  TICKER_TASK_EXECUTION — run agent TODO tasks automatically (default true)
  TICKER_TASK_MAX_PER_COMPANY — max tasks per company per tick (default 2)
  TICKER_TASK_AUTONOMOUS_ONLY — only Self-Run companies (default false)
"""
from __future__ import annotations

import logging
import os
import time

from django.core.management import call_command
from django.core.management.base import BaseCommand
from apps.ideas.activity_checks import (
    _env_bool,
    _env_int,
    run_activity_checks,
    should_run_weekly_planning_now,
)

logger = logging.getLogger(__name__)


def run_ticker_tick(*, dry_run: bool = False) -> None:
    """Single ticker cycle: checks → autonomous loop → optional weekly planning."""
    if not _env_bool("TICKER_ENABLED", True):
        logger.info("Ticker disabled (TICKER_ENABLED=false).")
        return

    stale_hours = _env_int("TICKER_STALE_PLANNING_HOURS", 2)
    logger.info("Ticker tick started.")

    if dry_run:
        logger.info("Dry run — no changes.")
        logger.info("Would run activity_checks(stale_planning_hours=%s)", stale_hours)
        logger.info("Would run autonomous_loop")
        from apps.ideas.task_execution import run_company_task_execution

        run_company_task_execution(dry_run=True)
        if should_run_weekly_planning_now():
            logger.info("Would run weekly_planning (Monday)")
        return

    check_result = run_activity_checks(stale_planning_hours=stale_hours)
    for msg in check_result.messages:
        logger.info("Activity check: %s", msg)

    from apps.ideas.autonomous_loop import run_autonomous_loop
    from apps.ideas.task_execution import run_company_task_execution

    run_autonomous_loop()

    task_result = run_company_task_execution()
    for msg in task_result.messages:
        logger.info("Task execution: %s", msg)

    if should_run_weekly_planning_now():
        logger.info("Running weekly planning (Monday).")
        call_command("run_weekly_planning")

    logger.info(
        "Ticker tick done (active=%s open_tasks=%s overdue=%s "
        "tasks_started=%s tasks_done=%s tasks_failed=%s).",
        check_result.active_companies,
        check_result.open_tasks,
        check_result.overdue_tasks,
        task_result.tasks_started,
        task_result.tasks_completed,
        task_result.tasks_failed,
    )


class Command(BaseCommand):
    help = (
        "Drive company activity: health checks, autonomous loop, Monday weekly planning. "
        "Use --loop in Docker ticker service."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Run a single tick and exit (cron-friendly).",
        )
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Run ticks forever with TICKER_INTERVAL_SECONDS between runs.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Log what would run without making changes.",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        if options.get("once") and options.get("loop"):
            self.stderr.write("Use only one of --once or --loop.")
            return

        if options.get("loop"):
            interval = max(60, _env_int("TICKER_INTERVAL_SECONDS", 3600))
            self.stdout.write(f"Ticker loop started (interval={interval}s).")
            while True:
                try:
                    run_ticker_tick(dry_run=dry_run)
                except Exception:
                    logger.exception("Ticker tick failed")
                time.sleep(interval)
            return

        run_ticker_tick(dry_run=dry_run)
        self.stdout.write("Ticker tick completed.")
