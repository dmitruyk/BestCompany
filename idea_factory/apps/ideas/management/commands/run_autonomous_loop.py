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
from django.core.management.base import BaseCommand

from apps.ideas.autonomous_loop import run_autonomous_loop
from apps.ideas.models import Company


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
        run_autonomous_loop()
        self.stdout.write("Autonomous loop completed")
