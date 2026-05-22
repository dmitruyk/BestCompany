from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_userprofile_google_calendar"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="google_calendar_remove_events_on_disconnect",
            field=models.BooleanField(
                default=True,
                help_text="When True, disconnecting removes Idea Factory events from Google Calendar.",
            ),
        ),
        migrations.AlterField(
            model_name="userprofile",
            name="google_calendar_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Google Calendar ID; empty uses the dedicated Idea Factory calendar.",
                max_length=255,
            ),
        ),
    ]
