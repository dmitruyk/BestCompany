"""Tests for company planning, tasks, and context."""
import pytest
from django.urls import reverse

from apps.ideas.company_history import record_history
from apps.ideas.models import (
    CompanyHistoryEntry,
    CompanyStrategicDirection,
    CompanyTask,
    CompanyTaskDependency,
    PlanningSession,
)
from apps.ideas.planning import monday_of_week, resolve_assignee, start_planning_session
from apps.ideas.planning_context import build_strategic_planning_context, compute_progress_metrics


@pytest.mark.django_db
def test_monday_of_week():
    from datetime import date

    assert monday_of_week(date(2026, 5, 20)).isoformat() == "2026-05-18"


@pytest.mark.django_db
def test_build_strategic_context_includes_direction(company, full_agent_fleet):
    del full_agent_fleet
    CompanyStrategicDirection.objects.create(
        company=company,
        statement="Grow bakery SaaS in EU",
        founder_verified=True,
        is_active=True,
    )
    ctx = build_strategic_planning_context(company)
    assert "Grow bakery SaaS" in ctx
    assert "founder-verified" in ctx


@pytest.mark.django_db
def test_progress_metrics(company):
    CompanyTask.objects.create(company=company, title="A", status=CompanyTask.Status.DONE, progress_percent=100)
    CompanyTask.objects.create(company=company, title="B", status=CompanyTask.Status.IN_PROGRESS, progress_percent=50)
    m = compute_progress_metrics(company)
    assert m["done_count"] == 1
    assert m["active_tasks"] == 2
    assert m["weighted_progress_percent"] == 75


@pytest.mark.django_db
def test_task_dependency_blocked(company):
    a = CompanyTask.objects.create(company=company, title="First", status=CompanyTask.Status.TODO)
    b = CompanyTask.objects.create(company=company, title="Second", status=CompanyTask.Status.TODO)
    CompanyTaskDependency.objects.create(task=b, depends_on=a)
    assert b.is_blocked_by_dependencies is True
    a.status = CompanyTask.Status.DONE
    a.save()
    b.refresh_from_db()
    assert b.is_blocked_by_dependencies is False


@pytest.mark.django_db
def test_resolve_assignee_agent(company, full_agent_fleet):
    del full_agent_fleet
    atype, agent, human = resolve_assignee(company, "planner")
    assert atype == CompanyTask.AssigneeType.AGENT
    assert agent is not None
    assert human is None


@pytest.mark.django_db
def test_start_planning_session(company, user):
    session = start_planning_session(company, user=user)
    assert session.trigger == PlanningSession.Trigger.MANUAL
    assert session.week_start == monday_of_week()


@pytest.mark.django_db
def test_record_history(company):
    entry = record_history(
        company,
        CompanyHistoryEntry.EntryType.DIRECTION_CREATED,
        "Test",
        summary="Summary line",
    )
    assert entry.company_id == company.pk


@pytest.mark.django_db
def test_company_tasks_run_now(client, user, company, full_agent_fleet):
    del full_agent_fleet
    from unittest.mock import patch

    from apps.ideas.models import CompanyAgent
    from apps.ideas.task_execution import TaskExecutionResult

    agent = company.agents.filter(role=CompanyAgent.Role.PLANNER).first()
    CompanyTask.objects.create(
        company=company,
        title="Runnable",
        status=CompanyTask.Status.TODO,
        assignee_type=CompanyTask.AssigneeType.AGENT,
        assigned_agent=agent,
    )
    client.force_login(user)
    with patch(
        "apps.web.company_planning_views.run_task_execution_for_company",
        return_value=TaskExecutionResult(tasks_completed=1, tasks_started=1),
    ):
        resp = client.post(
            reverse("company_tasks_run_now", kwargs={"company_pk": company.pk})
        )
    assert resp.status_code == 302
    assert resp.url.endswith(f"/companies/{company.pk}/tasks/")


@pytest.mark.django_db
def test_company_tasks_view(client, user, company, full_agent_fleet):
    del full_agent_fleet
    client.force_login(user)
    CompanyTask.objects.create(company=company, title="Ship MVP")
    url = reverse("company_tasks", kwargs={"company_pk": company.pk})
    resp = client.get(url)
    assert resp.status_code == 200
    assert b"Ship MVP" in resp.content


@pytest.mark.django_db
def test_company_direction_post(client, user, company):
    client.force_login(user)
    url = reverse("company_direction", kwargs={"company_pk": company.pk})
    resp = client.post(url, {"action": "save", "statement": "Focus on B2B"})
    assert resp.status_code == 302
    assert CompanyStrategicDirection.objects.filter(company=company, is_active=True).exists()
