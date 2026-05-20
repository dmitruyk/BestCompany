"""Tests for company activity checks and ticker helpers."""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.ideas.activity_checks import run_activity_checks
from apps.ideas.activity_checks import should_run_weekly_planning_now
from apps.ideas.models import CompanyTask, PlanningSession


@pytest.mark.django_db
def test_activity_checks_marks_stale_planning(company):
    session = PlanningSession.objects.create(
        company=company,
        trigger=PlanningSession.Trigger.MANUAL,
        status=PlanningSession.Status.IN_PROGRESS,
    )
    PlanningSession.objects.filter(pk=session.pk).update(
        updated_at=timezone.now() - timedelta(hours=5)
    )
    result = run_activity_checks(stale_planning_hours=2)
    assert result.stale_planning_sessions == 1
    session.refresh_from_db()
    assert session.status == PlanningSession.Status.FAILED


@pytest.mark.django_db
def test_activity_checks_counts_overdue(company):
    today = timezone.localdate()
    CompanyTask.objects.create(
        company=company,
        title="Late task",
        status=CompanyTask.Status.TODO,
        target_date=today - timedelta(days=2),
    )
    result = run_activity_checks()
    assert result.overdue_tasks == 1


def test_should_run_weekly_planning_monday(mocker):
    class FakeDatetime:
        @staticmethod
        def localtime():
            from datetime import datetime

            return datetime(2026, 5, 18, 9, 0, 0)  # Monday 09:00

    mocker.patch(
        "apps.ideas.activity_checks.timezone",
        FakeDatetime,
    )
    assert should_run_weekly_planning_now() is True
