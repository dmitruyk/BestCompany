"""Management command to run pipeline in a separate process."""
import sys
import os

from django.core.management.base import BaseCommand

from apps.ideas.models import IdeaRequest
from apps.agents.orchestration import run_from_scratch, run_pipeline, rerun_failed


class Command(BaseCommand):
    help = "Run idea pipeline (usage: run_pipeline <idea_uuid> [--rerun|--from-scratch])"

    def add_arguments(self, parser):
        parser.add_argument("idea_id", type=str)
        parser.add_argument("--rerun", action="store_true", help="Rerun failed steps only")
        parser.add_argument("--from-scratch", action="store_true", help="Delete all runs and rerun from beginning")

    def handle(self, *args, **options):
        idea_id = options["idea_id"]
        do_rerun = options.get("rerun", False)
        from_scratch = options.get("from_scratch", False)

        try:
            idea = IdeaRequest.objects.get(pk=idea_id)
        except IdeaRequest.DoesNotExist:
            self.stderr.write(f"Idea {idea_id} not found")
            sys.exit(1)

        if from_scratch:
            run_from_scratch(idea)
        elif do_rerun:
            if not rerun_failed(idea):
                self.stdout.write("No failed runs to rerun")
        else:
            run_pipeline(idea)
