"""Print why company tasks are or are not picked up by the ticker."""
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.ideas.models import Company, CompanyTask
from apps.ideas.task_execution import (
    explain_task_skip,
    get_runnable_tasks,
    task_due_cutoff,
)


class Command(BaseCommand):
    help = "Show which tasks are eligible for automatic execution and why others are skipped"

    def add_arguments(self, parser):
        parser.add_argument(
            "--company",
            type=str,
            default="",
            help="Company UUID (default: all ACTIVE companies)",
        )

    def handle(self, *args, **options):
        today = timezone.localdate()
        cutoff = task_due_cutoff(today=today)
        self.stdout.write(f"Today: {today}  |  Run tasks with target_date ≤ {cutoff}\n")

        companies = Company.objects.filter(status=Company.Status.ACTIVE).order_by("name")
        if options["company"]:
            companies = companies.filter(pk=options["company"])

        if not companies.exists():
            self.stdout.write(self.style.WARNING("No active companies found."))
            return

        for company in companies:
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n{company.name} ({company.pk})"))
            runnable = get_runnable_tasks(company, limit=20, today=today)
            self.stdout.write(
                self.style.SUCCESS(f"  Runnable now: {len(runnable)} task(s)")
            )
            for t in runnable:
                agent = t.assigned_agent.name if t.assigned_agent_id else "—"
                self.stdout.write(f"    ✓ {t.title} → {agent} (due {t.target_date or '—'})")

            open_qs = company.tasks.exclude(
                status__in=[CompanyTask.Status.DONE, CompanyTask.Status.CANCELLED]
            ).select_related("assigned_agent", "assigned_human").order_by(
                "sort_order", "created_at"
            )
            self.stdout.write(f"  Open tasks: {open_qs.count()}")
            for task in open_qs:
                if task in runnable:
                    continue
                agent = (
                    task.assigned_agent.name
                    if task.assigned_agent_id
                    else (
                        task.assigned_human.name
                        if task.assigned_human_id
                        else "—"
                    )
                )
                reason = explain_task_skip(task, today=today)
                self.stdout.write(
                    f"    ✗ {task.title[:50]} [{task.get_status_display()}] "
                    f"{task.get_assignee_type_display()} / {agent} / due={task.target_date or '—'}"
                )
                self.stdout.write(f"      → {reason}")
