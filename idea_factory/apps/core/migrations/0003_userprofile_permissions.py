from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_servicellmconfig"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="can_create_ideas",
            field=models.BooleanField(
                default=True,
                help_text="User may create new idea requests in the web UI.",
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="can_create_companies",
            field=models.BooleanField(
                default=True,
                help_text="User may accept ideas and create companies (agent fleets).",
            ),
        ),
    ]
