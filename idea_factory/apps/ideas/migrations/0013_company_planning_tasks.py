import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("ideas", "0012_companycalendaraction_google_event"),
    ]

    operations = [
        migrations.CreateModel(
            name="CompanyStrategicDirection",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "statement",
                    models.TextField(
                        help_text="Where the company is heading; used in weekly planning."
                    ),
                ),
                (
                    "founder_verified",
                    models.BooleanField(
                        default=False,
                        help_text="True when founders have agreed or clarified this direction.",
                    ),
                ),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="strategic_directions",
                        to="ideas.company",
                    ),
                ),
                (
                    "verified_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="verified_directions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="PlanningSession",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "trigger",
                    models.CharField(
                        choices=[
                            ("weekly", "Weekly (Monday)"),
                            ("manual", "User Request"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("DRAFT", "Draft"),
                            ("IN_PROGRESS", "In Progress"),
                            ("COMPLETED", "Completed"),
                            ("FAILED", "Failed"),
                        ],
                        default="DRAFT",
                        max_length=20,
                    ),
                ),
                ("week_start", models.DateField(blank=True, null=True)),
                ("summary", models.TextField(blank=True, default="")),
                ("context_snapshot", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="planning_sessions",
                        to="ideas.company",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="planning_sessions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="CompanyTask",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True, default="")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("TODO", "To Do"),
                            ("IN_PROGRESS", "In Progress"),
                            ("BLOCKED", "Blocked"),
                            ("DONE", "Done"),
                            ("CANCELLED", "Cancelled"),
                        ],
                        default="TODO",
                        max_length=20,
                    ),
                ),
                ("progress_percent", models.PositiveSmallIntegerField(default=0)),
                (
                    "assignee_type",
                    models.CharField(
                        choices=[
                            ("unassigned", "Unassigned"),
                            ("agent", "AI Agent"),
                            ("human", "Human"),
                        ],
                        default="unassigned",
                        max_length=20,
                    ),
                ),
                ("escalated_to_human", models.BooleanField(default=False)),
                ("target_date", models.DateField(blank=True, null=True)),
                ("result_summary", models.TextField(blank=True, default="")),
                ("result_notes", models.TextField(blank=True, default="")),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "assigned_agent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assigned_tasks",
                        to="ideas.companyagent",
                    ),
                ),
                (
                    "assigned_human",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assigned_tasks",
                        to="ideas.companyteammember",
                    ),
                ),
                (
                    "calendar_action",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="linked_tasks",
                        to="ideas.companycalendaraction",
                    ),
                ),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tasks",
                        to="ideas.company",
                    ),
                ),
                (
                    "planning_session",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="tasks",
                        to="ideas.planningsession",
                    ),
                ),
            ],
            options={"ordering": ["sort_order", "created_at"]},
        ),
        migrations.CreateModel(
            name="CompanyHistoryEntry",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "entry_type",
                    models.CharField(
                        choices=[
                            ("direction_created", "Direction Set"),
                            ("direction_verified", "Direction Verified"),
                            ("planning_started", "Planning Started"),
                            ("planning_completed", "Planning Completed"),
                            ("task_created", "Task Created"),
                            ("task_updated", "Task Updated"),
                            ("task_completed", "Task Completed"),
                            ("task_escalated", "Task Escalated to Human"),
                            ("calendar_linked", "Calendar Linked"),
                        ],
                        max_length=30,
                    ),
                ),
                ("title", models.CharField(max_length=255)),
                ("summary", models.TextField(blank=True, default="")),
                ("metadata_json", models.TextField(blank=True, default="{}")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="history_entries",
                        to="ideas.company",
                    ),
                ),
                (
                    "related_planning_session",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="history_entries",
                        to="ideas.planningsession",
                    ),
                ),
                (
                    "related_task",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="history_entries",
                        to="ideas.companytask",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "verbose_name_plural": "Company history entries",
            },
        ),
        migrations.CreateModel(
            name="CompanyTaskDependency",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "depends_on",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="dependents",
                        to="ideas.companytask",
                    ),
                ),
                (
                    "task",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="dependencies",
                        to="ideas.companytask",
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("task", "depends_on"),
                        name="unique_task_dependency",
                    )
                ],
            },
        ),
    ]
