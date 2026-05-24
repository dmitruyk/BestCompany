"""Tests for shared calendar LLM context."""
import pytest
from django.utils import timezone

from apps.ideas.calendar_context import build_calendar_context, get_company_start_date
from apps.ideas.models import CompanyCalendarAction


@pytest.mark.django_db
def test_get_company_start_date(company):
    assert get_company_start_date(company) == timezone.localtime(company.created_at).date()


@pytest.mark.django_db
def test_build_calendar_context_empty(company):
    assert "No calendar actions" in build_calendar_context(company)


@pytest.mark.django_db
def test_build_calendar_context_lists_actions(company):
    today = timezone.localdate()
    CompanyCalendarAction.objects.create(
        company=company,
        action_date=today,
        title="Ship beta",
        status=CompanyCalendarAction.ActionStatus.PLANNED,
    )
    text = build_calendar_context(company)
    assert "Ship beta" in text
    assert today.isoformat() in text
