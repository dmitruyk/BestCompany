# Generated manually for team member ↔ user linking

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ideas", "0013_company_planning_tasks"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="companyteammember",
            name="user",
            field=models.ForeignKey(
                blank=True,
                help_text="Login account linked to this human; grants company access and task assignment.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="team_memberships",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddConstraint(
            model_name="companyteammember",
            constraint=models.UniqueConstraint(
                condition=models.Q(("user__isnull", False)),
                fields=("company", "user"),
                name="unique_company_user_team_member",
            ),
        ),
    ]
