from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ideas", "0014_companyteammember_user"),
    ]

    operations = [
        migrations.AddField(
            model_name="companytask",
            name="google_event_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Google Calendar event ID when synced for the company owner.",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="companytask",
            name="google_calendar_synced_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Last successful sync to Google Calendar.",
                null=True,
            ),
        ),
    ]
