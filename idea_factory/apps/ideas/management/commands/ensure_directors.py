"""Ensure all companies have at least 3 directors. Adds missing directors."""
from django.core.management.base import BaseCommand

from apps.ideas.models import Company, CompanyAgent
from apps.agents.fleet import _ensure_min_directors, _build_context_text, MIN_DIRECTORS


class Command(BaseCommand):
    help = "Add directors to companies that have fewer than 3 (ensure_directors)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        companies = Company.objects.all()
        updated = 0
        for company in companies:
            count = company.agents.filter(role=CompanyAgent.Role.DIRECTOR).count()
            if count < MIN_DIRECTORS:
                if dry_run:
                    self.stdout.write(
                        f"Would add {MIN_DIRECTORS - count} director(s) to {company.name} ({company.pk})"
                    )
                else:
                    context_text = _build_context_text(company.idea_request)
                    _ensure_min_directors(company, context_text)
                    new_count = company.agents.filter(role=CompanyAgent.Role.DIRECTOR).count()
                    self.stdout.write(
                        f"Updated {company.name}: {count} -> {new_count} directors"
                    )
                updated += 1
        if updated == 0:
            self.stdout.write("All companies already have at least 3 directors.")
        elif dry_run:
            self.stdout.write(f"Dry run: {updated} companies would be updated.")
