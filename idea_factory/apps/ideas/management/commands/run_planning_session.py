"""Run a single planning session in background."""
import sys

from django.core.management.base import BaseCommand

from apps.ideas.models import PlanningSession
from apps.ideas.planning import run_planning_session


class Command(BaseCommand):
    help = "Run planning session LLM and create tasks (run_planning_session <session_uuid>)"

    def add_arguments(self, parser):
        parser.add_argument("session_id", type=str)

    def handle(self, *args, **options):
        session_id = options["session_id"]
        try:
            session = PlanningSession.objects.get(pk=session_id)
        except PlanningSession.DoesNotExist:
            self.stderr.write(f"Session {session_id} not found")
            sys.exit(1)

        ok = run_planning_session(session)
        if not ok:
            sys.exit(1)
        self.stdout.write(
            f"Planning completed: {session.tasks.count()} tasks for {session.company.name}"
        )
