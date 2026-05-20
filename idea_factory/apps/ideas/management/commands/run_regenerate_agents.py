"""Regenerate agent fleet for existing company based on current state."""
import sys

from django.core.management.base import BaseCommand

from apps.ideas.models import Company
from apps.agents.fleet import regenerate_fleet


class Command(BaseCommand):
    help = "Regenerate agent fleet for company (run_regenerate_agents <company_uuid>)"

    def add_arguments(self, parser):
        parser.add_argument("company_id", type=str)

    def handle(self, *args, **options):
        company_id = options["company_id"]
        try:
            company = Company.objects.get(pk=company_id)
        except Company.DoesNotExist:
            self.stderr.write(f"Company {company_id} not found")
            sys.exit(1)

        if regenerate_fleet(company):
            self.stdout.write(f"Regenerated {company.name} with {company.agents.count()} agents")
        else:
            self.stderr.write("Regeneration failed")
            sys.exit(1)
