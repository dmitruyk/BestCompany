import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ideas", "0018_companyassistantconversation"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CompanyAssistantProposedAction",
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
                    "action_type",
                    models.CharField(
                        choices=[
                            (
                                "start_planning_session",
                                "Start AI planning session",
                            ),
                            (
                                "seed_tasks_from_idea",
                                "Create tasks from idea pipeline",
                            ),
                            (
                                "draft_strategic_direction",
                                "Draft strategic direction from idea summary",
                            ),
                        ],
                        max_length=40,
                    ),
                ),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True, default="")),
                ("payload", models.JSONField(blank=True, default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending approval"),
                            ("running", "Running"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                            ("rejected", "Rejected"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("result_message", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("executed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assistant_proposed_actions",
                        to="ideas.company",
                    ),
                ),
                (
                    "message",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proposed_actions",
                        to="ideas.companyassistantmessage",
                    ),
                ),
                (
                    "planning_session",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assistant_proposals",
                        to="ideas.planningsession",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assistant_proposed_actions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="companyassistantproposedaction",
            index=models.Index(
                fields=["message", "status"],
                name="ideas_ca_msg_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="companyassistantproposedaction",
            index=models.Index(
                fields=["company", "user", "-created_at"],
                name="ideas_ca_co_user_cr_idx",
            ),
        ),
    ]
