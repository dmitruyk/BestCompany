# Team roles expansion and human team members

import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("ideas", "0010_ideaattachment"),
    ]

    operations = [
        migrations.CreateModel(
            name="CompanyTeamMember",
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
                ("name", models.CharField(max_length=120)),
                ("email", models.EmailField(blank=True, default="", max_length=254)),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("founder", "Founder"),
                            ("founder_assistant", "Founder Assistant"),
                            ("director", "Director (Human)"),
                            ("planner", "Planner"),
                            ("qa", "QA"),
                            ("accountant", "Accountant"),
                            ("marketing", "Marketing"),
                            ("operations", "Operations"),
                            ("other", "Other"),
                        ],
                        max_length=30,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="team_members",
                        to="ideas.company",
                    ),
                ),
            ],
            options={
                "ordering": ["role", "name"],
            },
        ),
        migrations.AlterField(
            model_name="companyagent",
            name="role",
            field=models.CharField(
                choices=[
                    ("founder", "Founder (AI)"),
                    ("founder_assistant", "Founder Assistant (AI)"),
                    ("director", "Director"),
                    ("planner", "Planner"),
                    ("qa", "QA / Quality"),
                    ("cpa", "CPA (Budget & Finance)"),
                    ("marketer", "Marketer"),
                    ("developer", "Developer"),
                    ("product", "Product Manager"),
                    ("operations", "Operations"),
                ],
                max_length=30,
            ),
        ),
    ]
