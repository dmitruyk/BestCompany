"""Tests for LLM schedule optimization (mocked LLM)."""
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.urls import reverse

from apps.agents.schemas import ScheduleOptimizationOutput, ScheduleTaskMove
from apps.ideas.models import CompanyTask, CompanyTaskDependency
from apps.ideas.schedule_optimizer import (
    _pack_agent_dates,
    _snap_for_assignee,
    enforce_schedule_rules,
    optimize_company_schedule,
    schedulable_tasks,
)


@pytest.mark.django_db
def test_snap_human_weekend():
    sat = date(2026, 5, 23)
    assert sat.weekday() == 5
    mon = _snap_for_assignee(sat, CompanyTask.AssigneeType.HUMAN)
    assert mon.weekday() < 5


@pytest.mark.django_db
def test_pack_agent_consecutive_days(company, full_agent_fleet):
    del full_agent_fleet
    anchor = date(2026, 5, 20)
    t1 = CompanyTask.objects.create(
        company=company,
        title="A",
        assignee_type=CompanyTask.AssigneeType.AGENT,
        target_date=anchor + timedelta(days=10),
        status=CompanyTask.Status.TODO,
    )
    t2 = CompanyTask.objects.create(
        company=company,
        title="B",
        assignee_type=CompanyTask.AssigneeType.AGENT,
        target_date=anchor + timedelta(days=20),
        status=CompanyTask.Status.TODO,
    )
    packed = _pack_agent_dates([t1, t2], anchor)
    assert packed[t1.pk] == anchor
    assert packed[t2.pk] == anchor + timedelta(days=1)


@pytest.mark.django_db
def test_pack_human_skips_weekend(company):
    fri = date(2026, 5, 22)
    assert fri.weekday() == 4
    t1 = CompanyTask.objects.create(
        company=company,
        title="Human 1",
        assignee_type=CompanyTask.AssigneeType.HUMAN,
        target_date=fri,
        status=CompanyTask.Status.TODO,
    )
    from apps.ideas.schedule_optimizer import _pack_human_dates

    packed = _pack_human_dates([t1], fri)
    assert packed[t1.pk].weekday() < 5


@pytest.mark.django_db
def test_enforce_respects_dependency(company):
    anchor = date(2026, 5, 20)
    a = CompanyTask.objects.create(
        company=company,
        title="First",
        assignee_type=CompanyTask.AssigneeType.AGENT,
        target_date=anchor + timedelta(days=14),
        status=CompanyTask.Status.TODO,
    )
    b = CompanyTask.objects.create(
        company=company,
        title="Second",
        assignee_type=CompanyTask.AssigneeType.AGENT,
        target_date=anchor + timedelta(days=30),
        status=CompanyTask.Status.TODO,
    )
    CompanyTaskDependency.objects.create(task=b, depends_on=a)
    final = enforce_schedule_rules([a, b], anchor, {})
    assert final[b.pk] > final[a.pk]


@pytest.mark.django_db
def test_optimize_company_schedule_moves_tasks(company, full_agent_fleet, user):
    del full_agent_fleet
    anchor = date.today()
    t1 = CompanyTask.objects.create(
        company=company,
        title="Agent early",
        assignee_type=CompanyTask.AssigneeType.AGENT,
        target_date=anchor + timedelta(days=1),
        status=CompanyTask.Status.TODO,
    )
    t2 = CompanyTask.objects.create(
        company=company,
        title="Agent late",
        assignee_type=CompanyTask.AssigneeType.AGENT,
        target_date=anchor + timedelta(days=20),
        status=CompanyTask.Status.TODO,
    )
    mock_out = ScheduleOptimizationOutput(
        summary="Closed gap between agent tasks.",
        moves=[
            ScheduleTaskMove(
                task_index=2,
                new_target_date=(anchor + timedelta(days=2)).isoformat(),
                reason="Fill gap",
            ),
        ],
    )
    with patch("apps.ideas.schedule_optimizer.agent_optimize_task_schedule") as mock_llm:
        mock_llm.return_value = (mock_out, None)
        result = optimize_company_schedule(company, start_date=anchor)

    assert result.ok is True
    assert result.tasks_moved >= 1
    t2.refresh_from_db()
    assert t2.target_date <= anchor + timedelta(days=5)
    assert len(schedulable_tasks(company)) >= 2


@pytest.mark.django_db
def test_calendar_optimize_view_requires_owner(client, user, company):
    anchor = date.today()
    CompanyTask.objects.create(
        company=company,
        title="A",
        assignee_type=CompanyTask.AssigneeType.AGENT,
        target_date=anchor + timedelta(days=1),
        status=CompanyTask.Status.TODO,
    )
    CompanyTask.objects.create(
        company=company,
        title="B",
        assignee_type=CompanyTask.AssigneeType.AGENT,
        target_date=anchor + timedelta(days=15),
        status=CompanyTask.Status.TODO,
    )
    url = reverse("company_calendar_optimize", kwargs={"company_pk": company.pk})
    with patch("apps.ideas.schedule_optimizer.optimize_company_schedule") as mock_opt:
        mock_opt.return_value = type(
            "R",
            (),
            {"ok": True, "tasks_moved": 2, "summary": "Done", "error": ""},
        )()
        client.force_login(user)
        resp = client.post(url, {"year": anchor.year, "month": anchor.month})
    assert resp.status_code == 302
    mock_opt.assert_called_once()
