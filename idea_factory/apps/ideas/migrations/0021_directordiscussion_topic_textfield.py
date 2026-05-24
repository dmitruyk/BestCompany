from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ideas", "0020_agent_panel_discussion"),
    ]

    operations = [
        migrations.AlterField(
            model_name="directordiscussion",
            name="topic",
            field=models.TextField(),
        ),
    ]
