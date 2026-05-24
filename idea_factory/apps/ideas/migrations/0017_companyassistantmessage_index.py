from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ideas", "0016_companyassistantmessage"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="companyassistantmessage",
            index=models.Index(
                fields=["company", "user", "created_at"],
                name="ideas_co_assist_co_user_cr_idx",
            ),
        ),
    ]
