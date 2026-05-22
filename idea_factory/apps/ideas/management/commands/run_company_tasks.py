"""Run eligible agent tasks for one company (manual / cron)."""
from django.core.management.base import BaseCommand

from apps.ideas.models import Company, CompanyTask
from apps.ideas.task_execution import (
    count_runnable_tasks,
    explain_task_skip,
    get_runnable_tasks,
    run_task_execution_for_company,
)


class Command(BaseCommand):
    help = "Execute eligible agent TODO tasks for a company (same as UI Run agent tasks now)"

    def add_arguments(self, parser):
        parser.add_argument("company_id", type=str, help="Company UUID")
        parser.add_argument(
            "--max",
            type=int,
            default=10,
            help="Maximum tasks to run in one invocation (default 10)",
        )

    def handle(self, *args, **options):
        company_id = options["company_id"]
        max_tasks = max(1, min(options["max"], 10))
        try:
            company = Company.objects.get(pk=company_id)
        except Company.DoesNotExist:
            self.stderr.write(f"Company {company_id} not found")
            return

        if company.status != Company.Status.ACTIVE:
            self.stderr.write("Company is not ACTIVE")
            return

        runnable = count_runnable_tasks(company)
        self.stdout.write(f"Runnable tasks: {runnable}")
        if runnable == 0:
            open_tasks = company.tasks.exclude(
                status__in=[CompanyTask.Status.DONE, CompanyTask.Status.CANCELLED]
            )[:5]
            for task in open_tasks:
                self.stdout.write(
                    f"  skip {task.title}: {explain_task_skip(task)}"
                )
            return

        result = run_task_execution_for_company(
            company, max_tasks=max_tasks, manual_trigger=True
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {result.tasks_completed} completed, "
                f"{result.tasks_partial} partial, "
                f"{result.tasks_escalated} escalated, "
                f"{result.tasks_failed} failed"
            )
        )
