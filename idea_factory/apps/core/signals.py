"""Create UserProfile when a User is created; sync calendar actions to Google Calendar."""
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.core.models import UserProfile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_user_profile(sender, instance, created, **kwargs) -> None:
    if created:
        UserProfile.objects.get_or_create(
            user=instance,
            defaults={"must_change_password": False},
        )


def _register_calendar_sync_signal() -> None:
    from apps.ideas.models import CompanyCalendarAction

    @receiver(post_save, sender=CompanyCalendarAction)
    def sync_company_calendar_action_to_google(
        sender, instance, created, update_fields=None, **kwargs
    ) -> None:
        if update_fields is not None:
            skip_only = {"google_event_id", "google_calendar_synced_at", "updated_at"}
            if set(update_fields) <= skip_only:
                return
        from apps.core.google_calendar import sync_entry_to_google_calendar

        sync_entry_to_google_calendar(instance)


def _register_task_sync_signal() -> None:
    from apps.ideas.models import CompanyTask

    @receiver(post_save, sender=CompanyTask)
    def sync_company_task_to_google(
        sender, instance, created, update_fields=None, **kwargs
    ) -> None:
        if update_fields is not None:
            skip_only = {"google_event_id", "google_calendar_synced_at", "updated_at"}
            if set(update_fields) <= skip_only:
                return
        from apps.core.google_calendar import sync_task_to_google_calendar

        sync_task_to_google_calendar(instance)


_register_calendar_sync_signal()
_register_task_sync_signal()
