from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_userprofile_permissions"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="google_calendar_sync_enabled",
            field=models.BooleanField(
                default=False,
                help_text="When True and connected, scheduled company calendar actions sync to Google Calendar.",
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="google_calendar_id",
            field=models.CharField(
                blank=True,
                default="primary",
                help_text="Google Calendar ID (usually 'primary' for the user's main calendar).",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="google_calendar_reminder_minutes",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Comma-separated reminder offsets in minutes, e.g. 60,1440 for 1 hour and 1 day before.",
                max_length=120,
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="google_calendar_access_token",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="google_calendar_refresh_token",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="google_calendar_token_expiry",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="google_calendar_connected_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
