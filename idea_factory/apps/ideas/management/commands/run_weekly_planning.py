"""Start weekly (Monday) planning for all active companies."""
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.ideas.models import Company, PlanningSession
from apps.ideas.planning import monday_of_week, start_planning_session


class Command(BaseCommand):
    help = "Create and queue weekly planning sessions for active companies (run on Mondays via cron)"

    def handle(self, *args, **options):
        week = monday_of_week()
        today = timezone.localdate()
        if today.weekday() != 0:
            self.stdout.write(
                self.style.WARNING(
                    f"Today is not Monday ({today}); still using week_start={week}"
                )
            )

        companies = Company.objects.filter(status=Company.Status.ACTIVE)
        started = 0
        for company in companies:
            existing = company.planning_sessions.filter(
                trigger=PlanningSession.Trigger.WEEKLY,
                week_start=week,
            ).exclude(status=PlanningSession.Status.FAILED)
            if existing.exists():
                continue
            session = start_planning_session(
                company,
                trigger=PlanningSession.Trigger.WEEKLY,
                week_start=week,
            )
            from apps.ideas.planning import spawn_planning_process

            spawn_planning_process(str(session.pk))
            started += 1
            self.stdout.write(f"Queued planning for {company.name} ({session.pk})")

        self.stdout.write(self.style.SUCCESS(f"Started {started} planning session(s)."))
