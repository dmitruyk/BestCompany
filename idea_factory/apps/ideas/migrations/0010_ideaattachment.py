# Generated manually for PDF attachments on ideas

import apps.ideas.models
import django.core.validators
import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ideas", "0009_company_autonomous_mode"),
    ]

    operations = [
        migrations.CreateModel(
            name="IdeaAttachment",
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
                    "file",
                    models.FileField(
                        upload_to=apps.ideas.models.idea_attachment_upload_to,
                        validators=[
                            django.core.validators.FileExtensionValidator(
                                allowed_extensions=["pdf"]
                            )
                        ],
                    ),
                ),
                ("original_filename", models.CharField(max_length=255)),
                (
                    "extracted_text",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Plain text extracted from the PDF for agent context",
                    ),
                ),
                ("file_size", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "idea_request",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attachments",
                        to="ideas.idearequest",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at"],
            },
        ),
    ]
