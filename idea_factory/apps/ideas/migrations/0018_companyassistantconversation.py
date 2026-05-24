import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def backfill_conversations(apps, schema_editor):
    Conversation = apps.get_model("ideas", "CompanyAssistantConversation")
    Message = apps.get_model("ideas", "CompanyAssistantMessage")

    groups: dict[tuple, list] = {}
    for msg in Message.objects.order_by("created_at").iterator():
        key = (msg.company_id, msg.user_id)
        groups.setdefault(key, []).append(msg)

    for (company_id, user_id), msgs in groups.items():
        conv = Conversation.objects.create(
            company_id=company_id,
            user_id=user_id,
            title="Previous chat",
        )
        for msg in msgs:
            msg.conversation_id = conv.pk
            msg.save(update_fields=["conversation_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("ideas", "0017_companyassistantmessage_index"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CompanyAssistantConversation",
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
                ("title", models.CharField(blank=True, default="", max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assistant_conversations",
                        to="ideas.company",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="company_assistant_conversations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
        migrations.AddIndex(
            model_name="companyassistantconversation",
            index=models.Index(
                fields=["company", "user", "-updated_at"],
                name="ideas_co_as_conv_co_user_up_idx",
            ),
        ),
        migrations.AddField(
            model_name="companyassistantmessage",
            name="conversation",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="messages",
                to="ideas.companyassistantconversation",
            ),
        ),
        migrations.RunPython(backfill_conversations, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="companyassistantmessage",
            name="conversation",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="messages",
                to="ideas.companyassistantconversation",
            ),
        ),
        migrations.AddIndex(
            model_name="companyassistantmessage",
            index=models.Index(
                fields=["conversation", "created_at"],
                name="ideas_co_as_msg_conv_cr_idx",
            ),
        ),
    ]
