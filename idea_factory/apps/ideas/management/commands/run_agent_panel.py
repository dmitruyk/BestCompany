"""Management command to run a multi-agent panel discussion in background."""
import sys

from django.core.management.base import BaseCommand

from apps.ideas.agent_panel_discussion import run_agent_panel_discussion
from apps.ideas.models import AgentPanelDiscussion


class Command(BaseCommand):
    help = "Run agent panel discussion (run_agent_panel <discussion_uuid>)"

    def add_arguments(self, parser):
        parser.add_argument("discussion_id", type=str)

    def handle(self, *args, **options):
        discussion_id = options["discussion_id"]
        try:
            discussion = AgentPanelDiscussion.objects.get(pk=discussion_id)
        except AgentPanelDiscussion.DoesNotExist:
            self.stderr.write(f"Agent panel {discussion_id} not found")
            sys.exit(1)

        run_agent_panel_discussion(discussion)
        self.stdout.write(f"Agent panel completed with status {discussion.status}")
