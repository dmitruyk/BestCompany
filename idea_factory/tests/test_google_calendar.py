"""Tests for Google Calendar sync helpers."""
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from apps.core.google_calendar import (
    align_calendar_actions_with_task_dates,
    build_google_event_body,
    default_reminder_minutes,
    encrypt_token,
    decrypt_token,
    is_google_calendar_configured,
    profile_reminder_minutes,
    sync_all_owner_calendar_actions,
    sync_entry_to_google_calendar,
)
from apps.ideas.models import CompanyTask
from apps.core.models import UserProfile
from apps.ideas.models import CompanyCalendarAction


@pytest.mark.django_db
def test_encrypt_decrypt_roundtrip() -> None:
    assert decrypt_token(encrypt_token("secret-token")) == "secret-token"


@override_settings(
    GOOGLE_CALENDAR_CLIENT_ID="id",
    GOOGLE_CALENDAR_CLIENT_SECRET="secret",
)
def test_is_configured() -> None:
    assert is_google_calendar_configured() is True


@override_settings(GOOGLE_CALENDAR_CLIENT_ID="", GOOGLE_CALENDAR_CLIENT_SECRET="")
def test_is_not_configured() -> None:
    assert is_google_calendar_configured() is False


def test_default_reminder_minutes() -> None:
    with override_settings(GOOGLE_CALENDAR_DEFAULT_REMINDERS="30,60"):
        assert default_reminder_minutes() == [30, 60]


@pytest.mark.django_db
def test_build_google_event_body(company) -> None:
    profile = company.owner.profile
    profile.google_calendar_reminder_minutes = "60"
    entry = CompanyCalendarAction.objects.create(
        company=company,
        action_date=date(2026, 5, 20),
        title="Ship MVP",
        description="Release first version",
    )
    body = build_google_event_body(entry, profile)
    assert "[{}]".format(company.name) in body["summary"]
    assert body["start"]["date"] == "2026-05-20"
    assert body["reminders"]["useDefault"] is False
    assert body["reminders"]["overrides"] == [{"method": "popup", "minutes": 60}]


@pytest.mark.django_db
def test_profile_reminder_minutes_fallback(company) -> None:
    profile = company.owner.profile
    profile.google_calendar_reminder_minutes = ""
    with override_settings(GOOGLE_CALENDAR_DEFAULT_REMINDERS="15"):
        assert profile_reminder_minutes(profile) == [15]


@pytest.mark.django_db
@override_settings(
    GOOGLE_CALENDAR_CLIENT_ID="id",
    GOOGLE_CALENDAR_CLIENT_SECRET="secret",
)
def test_sync_creates_event(company) -> None:
    profile = company.owner.profile
    profile.google_calendar_sync_enabled = True
    profile.google_calendar_refresh_token = encrypt_token("refresh")
    profile.google_calendar_access_token = encrypt_token("access")
    profile.save()

    entry = CompanyCalendarAction.objects.create(
        company=company,
        action_date=date.today(),
        title="Test action",
    )

    mock_service = MagicMock()
    mock_events = MagicMock()
    mock_service.events.return_value = mock_events
    mock_events.insert.return_value.execute.return_value = {"id": "evt-123"}

    with patch(
        "apps.core.google_calendar._get_calendar_service", return_value=mock_service
    ), patch(
        "apps.core.google_calendar._get_valid_access_token", return_value="access"
    ):
        assert sync_entry_to_google_calendar(entry) is True

    entry.refresh_from_db()
    assert entry.google_event_id == "evt-123"
    mock_events.insert.assert_called_once()


@pytest.mark.django_db
@override_settings(
    GOOGLE_CALENDAR_CLIENT_ID="id",
    GOOGLE_CALENDAR_CLIENT_SECRET="secret",
)
def test_sync_all_owner_calendar_actions(company) -> None:
    profile = company.owner.profile
    profile.google_calendar_sync_enabled = True
    profile.google_calendar_refresh_token = encrypt_token("refresh")
    profile.google_calendar_access_token = encrypt_token("access")
    profile.save()

    CompanyCalendarAction.objects.create(
        company=company,
        action_date=date.today(),
        title="Existing",
    )

    with patch(
        "apps.core.google_calendar.sync_entry_to_google_calendar",
        return_value=True,
    ) as mock_sync:
        result = sync_all_owner_calendar_actions(company.owner)

    assert result.synced == 1
    assert result.failed == 0
    mock_sync.assert_called_once()


@pytest.mark.django_db
def test_align_calendar_actions_with_task_dates(company) -> None:
    action = CompanyCalendarAction.objects.create(
        company=company,
        action_date=date(2026, 6, 1),
        title="Linked action",
    )
    task = CompanyTask.objects.create(
        company=company,
        title="Task A",
        target_date=date(2026, 6, 10),
        calendar_action=action,
    )
    final_dates = {task.pk: date(2026, 6, 15)}

    with patch(
        "apps.core.google_calendar.sync_entry_to_google_calendar",
        return_value=True,
    ):
        moved = align_calendar_actions_with_task_dates([task], final_dates)

    assert moved == 1
    action.refresh_from_db()
    assert action.action_date == date(2026, 6, 15)


@pytest.mark.django_db
@override_settings(
    GOOGLE_CALENDAR_CLIENT_ID="id",
    GOOGLE_CALENDAR_CLIENT_SECRET="secret",
)
def test_sync_task_updates_google_event(company) -> None:
    profile = company.owner.profile
    profile.google_calendar_sync_enabled = True
    profile.google_calendar_refresh_token = encrypt_token("refresh")
    profile.google_calendar_access_token = encrypt_token("access")
    profile.save()

    task = CompanyTask.objects.create(
        company=company,
        title="Planning item",
        target_date=date.today(),
        status=CompanyTask.Status.TODO,
    )

    mock_service = MagicMock()
    mock_events = MagicMock()
    mock_service.events.return_value = mock_events
    mock_events.insert.return_value.execute.return_value = {"id": "task-evt-1"}

    with patch(
        "apps.core.google_calendar._get_calendar_service", return_value=mock_service
    ), patch(
        "apps.core.google_calendar._get_valid_access_token", return_value="access"
    ):
        from apps.core.google_calendar import sync_task_to_google_calendar

        assert sync_task_to_google_calendar(task) is True

    task.refresh_from_db()
    assert task.google_event_id == "task-evt-1"
