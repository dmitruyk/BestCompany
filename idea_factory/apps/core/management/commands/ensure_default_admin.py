"""
Create the default bootstrap admin account (username: admin).

Password is set only when the user is first created. Re-run does not reset password.
Use --reset-password to force password back to default (dev/bootstrap only).
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.core.models import UserProfile

DEFAULT_USERNAME = "admin"
LEGACY_USERNAME = "adnit"
DEFAULT_PASSWORD = "1234"


class Command(BaseCommand):
    help = "Ensure default admin user exists (admin / must change password on first login)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-password",
            action="store_true",
            help="Reset password to default (1234) and require change on next login",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        self._migrate_legacy_username(User)
        user, created = User.objects.get_or_create(
            username=DEFAULT_USERNAME,
            defaults={
                "email": "",
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
        )
        if created:
            user.set_password(DEFAULT_PASSWORD)
            user.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Created default admin '{DEFAULT_USERNAME}' (password: {DEFAULT_PASSWORD})"
                )
            )
        else:
            if not user.is_staff or not user.is_superuser:
                user.is_staff = True
                user.is_superuser = True
                user.is_active = True
                user.save(update_fields=["is_staff", "is_superuser", "is_active"])
            self.stdout.write(f"Default admin '{DEFAULT_USERNAME}' already exists")

        profile, _ = UserProfile.objects.get_or_create(user=user)

        if options.get("reset_password"):
            user.set_password(DEFAULT_PASSWORD)
            user.save(update_fields=["password"])
            profile.must_change_password = True
            profile.save(update_fields=["must_change_password", "updated_at"])
            self.stdout.write(self.style.WARNING("Password reset to default; must change on login"))
        elif created:
            profile.must_change_password = True
            profile.save(update_fields=["must_change_password", "updated_at"])
            self.stdout.write("User must change password on first login")

    @staticmethod
    def _migrate_legacy_username(User) -> None:
        """Rename bootstrap user adnit → admin if present from older installs."""
        if User.objects.filter(username=DEFAULT_USERNAME).exists():
            return
        try:
            legacy = User.objects.get(username=LEGACY_USERNAME)
        except User.DoesNotExist:
            return
        legacy.username = DEFAULT_USERNAME
        legacy.save(update_fields=["username"])
