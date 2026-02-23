"""Management command to run director discussion in background."""
import sys

from django.core.management.base import BaseCommand

from apps.ideas.models import DirectorDiscussion


class Command(BaseCommand):
    help = "Run director discussion - directors propose actions (run_discussion <discussion_uuid>)"

    def add_arguments(self, parser):
        parser.add_argument("discussion_id", type=str)

    def handle(self, *args, **options):
        discussion_id = options["discussion_id"]
        try:
            discussion = DirectorDiscussion.objects.get(pk=discussion_id)
        except DirectorDiscussion.DoesNotExist:
            self.stderr.write(f"Discussion {discussion_id} not found")
            sys.exit(1)

        from apps.web.views import _run_director_discussion

        _run_director_discussion(discussion)
        self.stdout.write(f"Discussion {discussion.topic} completed")
