"""Google Calendar OAuth and sync for company calendar actions."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlencode

from django.conf import settings
from django.core import signing
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger(__name__)

GOOGLE_CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar"
_TOKEN_SALT = "google-calendar-token-v1"


def portal_calendar_display_name() -> str:
    return getattr(settings, "GOOGLE_CALENDAR_PORTAL_NAME", "Idea Factory") or "Idea Factory"


@dataclass
class GoogleCalendarBulkSyncResult:
    synced: int = 0
    failed: int = 0
    skipped: int = 0


def is_google_calendar_configured() -> bool:
    return bool(
        getattr(settings, "GOOGLE_CALENDAR_CLIENT_ID", "")
        and getattr(settings, "GOOGLE_CALENDAR_CLIENT_SECRET", "")
    )


def default_reminder_minutes() -> list[int]:
    raw = getattr(settings, "GOOGLE_CALENDAR_DEFAULT_REMINDERS", "60,1440")
    minutes: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            value = int(part)
        except ValueError:
            continue
        if value > 0:
            minutes.append(value)
    return minutes or [60, 1440]


def profile_reminder_minutes(profile) -> list[int]:
    raw = (profile.google_calendar_reminder_minutes or "").strip()
    if not raw:
        return default_reminder_minutes()
    minutes: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            value = int(part)
        except ValueError:
            continue
        if value > 0:
            minutes.append(value)
    return minutes or default_reminder_minutes()


def encrypt_token(value: str) -> str:
    if not value:
        return ""
    return signing.dumps(value, salt=_TOKEN_SALT)


def decrypt_token(value: str) -> str:
    if not value:
        return ""
    try:
        return signing.loads(value, salt=_TOKEN_SALT, max_age=None)
    except signing.BadSignature:
        logger.warning("Failed to decrypt Google Calendar token")
        return ""


def profile_has_google_credentials(profile) -> bool:
    return bool(decrypt_token(profile.google_calendar_refresh_token or ""))


def build_oauth_authorization_url(request) -> str:
    redirect_uri = _callback_redirect_uri(request)
    params = {
        "client_id": settings.GOOGLE_CALENDAR_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GOOGLE_CALENDAR_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"


def exchange_code_for_tokens(request, code: str) -> dict[str, Any]:
    import requests

    redirect_uri = _callback_redirect_uri(request)
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": settings.GOOGLE_CALENDAR_CLIENT_ID,
            "client_secret": settings.GOOGLE_CALENDAR_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def refresh_access_token(profile) -> str | None:
    import requests

    refresh_token = decrypt_token(profile.google_calendar_refresh_token or "")
    if not refresh_token:
        return None
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": settings.GOOGLE_CALENDAR_CLIENT_ID,
            "client_secret": settings.GOOGLE_CALENDAR_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    if response.status_code != 200:
        logger.warning("Google token refresh failed: %s", response.text[:200])
        return None
    payload = response.json()
    access_token = payload.get("access_token", "")
    if not access_token:
        return None
    expires_in = int(payload.get("expires_in", 3600))
    profile.google_calendar_access_token = encrypt_token(access_token)
    profile.google_calendar_token_expiry = timezone.now() + timedelta(seconds=expires_in)
    profile.save(
        update_fields=[
            "google_calendar_access_token",
            "google_calendar_token_expiry",
            "updated_at",
        ]
    )
    return access_token


def save_tokens_to_profile(profile, token_payload: dict[str, Any]) -> None:
    access_token = token_payload.get("access_token", "")
    refresh_token = token_payload.get("refresh_token", "")
    expires_in = int(token_payload.get("expires_in", 3600))
    if access_token:
        profile.google_calendar_access_token = encrypt_token(access_token)
        profile.google_calendar_token_expiry = timezone.now() + timedelta(
            seconds=expires_in
        )
    if refresh_token:
        profile.google_calendar_refresh_token = encrypt_token(refresh_token)
    profile.google_calendar_connected_at = timezone.now()
    profile.google_calendar_sync_enabled = True
    profile.save(
        update_fields=[
            "google_calendar_access_token",
            "google_calendar_refresh_token",
            "google_calendar_token_expiry",
            "google_calendar_connected_at",
            "google_calendar_sync_enabled",
            "updated_at",
        ]
    )
    ensure_portal_calendar(profile)


def calendar_id_for_profile(profile) -> str:
    """Calendar used for sync; falls back to primary only if portal setup failed."""
    calendar_id = (profile.google_calendar_id or "").strip()
    if calendar_id and calendar_id.lower() != "primary":
        return calendar_id
    return calendar_id or "primary"


def ensure_portal_calendar(profile) -> str | None:
    """
    Find or create a dedicated Google Calendar (portal name) so events do not use primary.
    No-op when the user set a custom calendar ID.
    """
    custom = (profile.google_calendar_id or "").strip()
    if custom and custom.lower() != "primary":
        return custom

    service = _get_calendar_service(profile)
    if service is None:
        return None

    portal_name = portal_calendar_display_name()
    page_token: str | None = None
    try:
        while True:
            result = (
                service.calendarList()
                .list(pageToken=page_token, minAccessRole="owner")
                .execute()
            )
            for item in result.get("items", []):
                if item.get("summary") == portal_name:
                    calendar_id = item["id"]
                    profile.google_calendar_id = calendar_id
                    profile.save(update_fields=["google_calendar_id", "updated_at"])
                    logger.info("Using existing Google portal calendar %s", calendar_id)
                    return calendar_id
            page_token = result.get("nextPageToken")
            if not page_token:
                break

        created = (
            service.calendars()
            .insert(body={"summary": portal_name, "timeZone": settings.TIME_ZONE})
            .execute()
        )
        calendar_id = created.get("id", "")
        if not calendar_id:
            return None
        profile.google_calendar_id = calendar_id
        profile.save(update_fields=["google_calendar_id", "updated_at"])
        logger.info("Created Google portal calendar %s (%s)", portal_name, calendar_id)
        return calendar_id
    except Exception:
        logger.exception("Failed to ensure portal calendar %s", portal_name)
        return None


def clear_google_calendar_credentials(profile) -> None:
    profile.google_calendar_access_token = ""
    profile.google_calendar_refresh_token = ""
    profile.google_calendar_token_expiry = None
    profile.google_calendar_connected_at = None
    profile.google_calendar_sync_enabled = False
    profile.save(
        update_fields=[
            "google_calendar_access_token",
            "google_calendar_refresh_token",
            "google_calendar_token_expiry",
            "google_calendar_connected_at",
            "google_calendar_sync_enabled",
            "updated_at",
        ]
    )


def _get_valid_access_token(profile) -> str | None:
    access_token = decrypt_token(profile.google_calendar_access_token or "")
    expiry = profile.google_calendar_token_expiry
    if access_token and expiry and expiry > timezone.now() + timedelta(minutes=2):
        return access_token
    return refresh_access_token(profile)


def _get_calendar_service(profile):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    access_token = _get_valid_access_token(profile)
    refresh_token = decrypt_token(profile.google_calendar_refresh_token or "")
    if not access_token or not refresh_token:
        return None
    credentials = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CALENDAR_CLIENT_ID,
        client_secret=settings.GOOGLE_CALENDAR_CLIENT_SECRET,
        scopes=[GOOGLE_CALENDAR_SCOPE],
    )
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def _company_task_url(task) -> str:
    path = reverse(
        "company_task_detail",
        kwargs={"company_pk": task.company_id, "task_pk": task.pk},
    )
    host = getattr(settings, "DJANGO_PUBLIC_HOST", "").strip()
    if not host:
        return path
    scheme = "https" if not settings.DEBUG else "http"
    return f"{scheme}://{host}{path}"


def _calendar_entry_url(entry) -> str:
    path = reverse(
        "company_calendar_date",
        kwargs={
            "company_pk": entry.company_id,
            "year": entry.action_date.year,
            "month": entry.action_date.month,
            "day": entry.action_date.day,
        },
    )
    host = getattr(settings, "DJANGO_PUBLIC_HOST", "").strip()
    if not host:
        return path
    scheme = "https" if not settings.DEBUG else "http"
    return f"{scheme}://{host}{path}"


def build_google_event_body(entry, profile) -> dict[str, Any]:
    from apps.ideas.models import CompanyCalendarAction

    company_name = entry.company.name
    status_label = entry.get_status_display()
    title_prefix = f"[{company_name}] "
    if entry.status == CompanyCalendarAction.ActionStatus.DONE:
        title_prefix = f"[{company_name}] ✓ "
    summary = f"{title_prefix}{entry.title}"
    description_parts = [
        f"Company: {company_name}",
        f"Status: {status_label}",
    ]
    if entry.description:
        description_parts.append("")
        description_parts.append(entry.description)
    if entry.completion_notes:
        description_parts.append("")
        description_parts.append(f"Completion notes:\n{entry.completion_notes}")
    description_parts.append("")
    description_parts.append(f"View in Idea Factory: {_calendar_entry_url(entry)}")

    reminders = [
        {"method": "popup", "minutes": minutes}
        for minutes in profile_reminder_minutes(profile)
    ]
    action_date: date = entry.action_date
    return {
        "summary": summary[:1024],
        "description": "\n".join(description_parts)[:8000],
        "start": {"date": action_date.isoformat()},
        "end": {"date": (action_date + timedelta(days=1)).isoformat()},
        "reminders": {
            "useDefault": False,
            "overrides": reminders,
        },
        "extendedProperties": {
            "private": {
                "idea_factory_entry_id": str(entry.pk),
                "idea_factory_company_id": str(entry.company_id),
            }
        },
    }


def build_google_task_event_body(task, profile) -> dict[str, Any]:
    from apps.ideas.models import CompanyTask

    company_name = task.company.name
    status_label = task.get_status_display()
    if task.status == CompanyTask.Status.DONE:
        title_prefix = f"[{company_name}] ✓ 📋 "
    else:
        title_prefix = f"[{company_name}] 📋 "
    summary = f"{title_prefix}{task.title}"
    if task.assignee_type == CompanyTask.AssigneeType.HUMAN or task.assigned_human_id:
        assignee = "Human"
    elif task.assignee_type == CompanyTask.AssigneeType.AGENT or task.assigned_agent_id:
        assignee = "AI Agent"
    else:
        assignee = "Unassigned"
    description_parts = [
        f"Company: {company_name}",
        f"Type: Planning task",
        f"Status: {status_label}",
        f"Assignee: {assignee}",
    ]
    if task.description:
        description_parts.append("")
        description_parts.append(task.description)
    if task.result_summary:
        description_parts.append("")
        description_parts.append(f"Result:\n{task.result_summary}")
    description_parts.append("")
    description_parts.append(f"View in Idea Factory: {_company_task_url(task)}")

    reminders = [
        {"method": "popup", "minutes": minutes}
        for minutes in profile_reminder_minutes(profile)
    ]
    due: date = task.target_date
    return {
        "summary": summary[:1024],
        "description": "\n".join(description_parts)[:8000],
        "start": {"date": due.isoformat()},
        "end": {"date": (due + timedelta(days=1)).isoformat()},
        "reminders": {
            "useDefault": False,
            "overrides": reminders,
        },
        "extendedProperties": {
            "private": {
                "idea_factory_task_id": str(task.pk),
                "idea_factory_company_id": str(task.company_id),
            }
        },
    }


def _task_should_sync_to_google(task) -> bool:
    from apps.ideas.models import CompanyTask

    if not task.target_date:
        return False
    if task.status == CompanyTask.Status.CANCELLED:
        return False
    if task.calendar_action_id:
        return False
    return True


def sync_task_to_google_calendar(task) -> bool:
    """Create or update a Google Calendar event for a planning task. Returns True on success."""
    from apps.ideas.models import CompanyTask

    if not is_google_calendar_configured() or not _task_should_sync_to_google(task):
        return False

    owner = task.company.owner
    profile = getattr(owner, "profile", None)
    if profile is None:
        return False
    if not profile.google_calendar_sync_enabled or not profile_has_google_credentials(profile):
        return False

    service = _get_calendar_service(profile)
    if service is None:
        return False

    calendar_id = calendar_id_for_profile(profile)
    body = build_google_task_event_body(task, profile)

    try:
        if task.google_event_id:
            service.events().update(
                calendarId=calendar_id,
                eventId=task.google_event_id,
                body=body,
            ).execute()
            CompanyTask.objects.filter(pk=task.pk).update(
                google_calendar_synced_at=timezone.now(),
            )
        else:
            created = service.events().insert(calendarId=calendar_id, body=body).execute()
            event_id = created.get("id", "")
            if event_id:
                CompanyTask.objects.filter(pk=task.pk).update(
                    google_event_id=event_id,
                    google_calendar_synced_at=timezone.now(),
                )
                task.google_event_id = event_id
        logger.info("Synced planning task %s to Google Calendar", task.pk)
        return True
    except Exception:
        logger.exception("Failed to sync planning task %s to Google Calendar", task.pk)
        return False


def sync_entry_to_google_calendar(entry) -> bool:
    """Create or update a Google Calendar event for a calendar action. Returns True on success."""
    from apps.ideas.models import CompanyCalendarAction

    if not is_google_calendar_configured():
        return False

    owner = entry.company.owner
    profile = getattr(owner, "profile", None)
    if profile is None:
        return False
    if not profile.google_calendar_sync_enabled or not profile_has_google_credentials(profile):
        return False

    service = _get_calendar_service(profile)
    if service is None:
        return False

    calendar_id = calendar_id_for_profile(profile)
    body = build_google_event_body(entry, profile)

    try:
        if entry.google_event_id:
            service.events().update(
                calendarId=calendar_id,
                eventId=entry.google_event_id,
                body=body,
            ).execute()
            CompanyCalendarAction.objects.filter(pk=entry.pk).update(
                google_calendar_synced_at=timezone.now(),
            )
        else:
            created = service.events().insert(calendarId=calendar_id, body=body).execute()
            event_id = created.get("id", "")
            if event_id:
                CompanyCalendarAction.objects.filter(pk=entry.pk).update(
                    google_event_id=event_id,
                    google_calendar_synced_at=timezone.now(),
                )
                entry.google_event_id = event_id
        logger.info("Synced calendar entry %s to Google Calendar", entry.pk)
        return True
    except Exception:
        logger.exception("Failed to sync calendar entry %s to Google Calendar", entry.pk)
        return False


def _delete_google_event(profile, event_id: str) -> bool:
    if not event_id or not is_google_calendar_configured():
        return False
    if not profile_has_google_credentials(profile):
        return False
    service = _get_calendar_service(profile)
    if service is None:
        return False
    calendar_id = calendar_id_for_profile(profile)
    try:
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        return True
    except Exception:
        logger.exception("Failed to delete Google event %s", event_id)
        return False


def delete_google_calendar_event(entry) -> None:
    owner = entry.company.owner
    profile = getattr(owner, "profile", None)
    if profile is None:
        return
    _delete_google_event(profile, entry.google_event_id)


def delete_google_task_event(task) -> None:
    owner = task.company.owner
    profile = getattr(owner, "profile", None)
    if profile is None:
        return
    _delete_google_event(profile, task.google_event_id)


def remove_all_owner_google_events(user) -> GoogleCalendarBulkSyncResult:
    """Delete synced Google events for all companies owned by user; clear local event IDs."""
    from apps.ideas.models import CompanyCalendarAction, CompanyTask

    result = GoogleCalendarBulkSyncResult()
    profile = getattr(user, "profile", None)
    if profile is None or not profile_has_google_credentials(profile):
        action_qs = CompanyCalendarAction.objects.filter(company__owner=user).exclude(
            google_event_id=""
        )
        task_qs = CompanyTask.objects.filter(company__owner=user).exclude(
            google_event_id=""
        )
        result.skipped = action_qs.count() + task_qs.count()
        return result

    for entry in CompanyCalendarAction.objects.filter(company__owner=user).exclude(
        google_event_id=""
    ):
        if _delete_google_event(profile, entry.google_event_id):
            result.synced += 1
        else:
            result.failed += 1

    for task in CompanyTask.objects.filter(company__owner=user).exclude(
        google_event_id=""
    ):
        if _delete_google_event(profile, task.google_event_id):
            result.synced += 1
        else:
            result.failed += 1

    CompanyCalendarAction.objects.filter(company__owner=user).update(
        google_event_id="",
        google_calendar_synced_at=None,
    )
    CompanyTask.objects.filter(company__owner=user).update(
        google_event_id="",
        google_calendar_synced_at=None,
    )
    return result


def _owner_profile_for_sync(user):
    profile = getattr(user, "profile", None)
    if profile is None:
        return None
    if not profile.google_calendar_sync_enabled or not profile_has_google_credentials(profile):
        return None
    if not is_google_calendar_configured():
        return None
    return profile


def sync_all_owner_calendar_actions(user) -> GoogleCalendarBulkSyncResult:
    """Push calendar actions and planning tasks for companies this user owns."""
    from apps.ideas.models import CompanyCalendarAction, CompanyTask

    result = GoogleCalendarBulkSyncResult()
    profile = _owner_profile_for_sync(user)
    action_count = CompanyCalendarAction.objects.filter(company__owner=user).count()
    task_count = CompanyTask.objects.filter(
        company__owner=user,
        target_date__isnull=False,
        calendar_action__isnull=True,
    ).exclude(status=CompanyTask.Status.CANCELLED).count()
    if profile is None:
        result.skipped = action_count + task_count
        return result
    ensure_portal_calendar(profile)

    entries = (
        CompanyCalendarAction.objects.filter(company__owner=user)
        .select_related("company")
        .order_by("action_date", "title")
    )
    for entry in entries:
        if sync_entry_to_google_calendar(entry):
            result.synced += 1
        else:
            result.failed += 1

    tasks = (
        CompanyTask.objects.filter(
            company__owner=user,
            target_date__isnull=False,
            calendar_action__isnull=True,
        )
        .exclude(status=CompanyTask.Status.CANCELLED)
        .select_related("company", "assigned_agent", "assigned_human")
        .order_by("target_date", "title")
    )
    for task in tasks:
        if sync_task_to_google_calendar(task):
            result.synced += 1
        else:
            result.failed += 1
    return result


def sync_company_calendar_actions(company) -> GoogleCalendarBulkSyncResult:
    """Re-sync calendar actions and planning tasks for one company."""
    from apps.ideas.models import CompanyTask

    result = GoogleCalendarBulkSyncResult()
    owner = company.owner
    task_qs = company.tasks.filter(
        target_date__isnull=False,
        calendar_action__isnull=True,
    ).exclude(status=CompanyTask.Status.CANCELLED)
    profile = _owner_profile_for_sync(owner)
    if profile is None:
        result.skipped = company.calendar_actions.count() + task_qs.count()
        return result
    ensure_portal_calendar(profile)

    entries = company.calendar_actions.select_related("company").order_by(
        "action_date", "title"
    )
    for entry in entries:
        if sync_entry_to_google_calendar(entry):
            result.synced += 1
        else:
            result.failed += 1

    for task in task_qs.select_related(
        "company", "assigned_agent", "assigned_human"
    ).order_by("target_date", "title"):
        if sync_task_to_google_calendar(task):
            result.synced += 1
        else:
            result.failed += 1
    return result


def align_calendar_actions_with_task_dates(
    tasks: list, final_dates: dict
) -> int:
    """Move linked calendar actions when schedule optimization changes task due dates."""
    from apps.ideas.models import CompanyCalendarAction

    moved = 0
    for task in tasks:
        new_date = final_dates.get(task.pk)
        if not new_date:
            continue
        action = getattr(task, "calendar_action", None)
        if action is None:
            continue
        if action.action_date == new_date:
            continue
        action.action_date = new_date
        action.save(update_fields=["action_date", "updated_at"])
        moved += 1
    return moved


def _callback_redirect_uri(request) -> str:
    return request.build_absolute_uri(reverse("google_calendar_callback"))
