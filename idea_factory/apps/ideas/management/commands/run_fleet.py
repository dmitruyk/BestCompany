"""Management command to generate company agent fleet from accepted idea."""
import sys

from django.core.management.base import BaseCommand

from apps.ideas.models import IdeaRequest
from apps.agents.fleet import generate_fleet


class Command(BaseCommand):
    help = "Generate company and agent fleet for accepted idea (run_fleet <idea_uuid>)"

    def add_arguments(self, parser):
        parser.add_argument("idea_id", type=str)

    def handle(self, *args, **options):
        idea_id = options["idea_id"]
        try:
            idea = IdeaRequest.objects.get(pk=idea_id)
        except IdeaRequest.DoesNotExist:
            self.stderr.write(f"Idea {idea_id} not found")
            sys.exit(1)

        company = generate_fleet(idea)
        if company:
            self.stdout.write(f"Created company {company.name} ({company.pk}) with {company.agents.count()} agents")
        else:
            self.stderr.write("Fleet generation failed")
            sys.exit(1)
