"""Tests for automatic company task execution."""
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.ideas.models import (
    CompanyAgent,
    CompanyTask,
    CompanyTaskDependency,
    CompanyTeamMember,
)
from apps.ideas.task_execution import (
    execute_company_task,
    explain_task_skip,
    get_runnable_tasks,
    is_task_runnable,
    run_company_task_execution,
    sync_task_target_date_to_run_day,
)


@pytest.mark.django_db
def test_is_task_runnable_respects_dependencies(company, full_agent_fleet):
    del full_agent_fleet
    agent = company.agents.filter(role=CompanyAgent.Role.PLANNER).first()
    a = CompanyTask.objects.create(
        company=company,
        title="First",
        status=CompanyTask.Status.TODO,
        assignee_type=CompanyTask.AssigneeType.AGENT,
        assigned_agent=agent,
    )
    b = CompanyTask.objects.create(
        company=company,
        title="Second",
        status=CompanyTask.Status.TODO,
        assignee_type=CompanyTask.AssigneeType.AGENT,
        assigned_agent=agent,
    )
    CompanyTaskDependency.objects.create(task=b, depends_on=a)
    assert is_task_runnable(a) is True
    assert is_task_runnable(b) is False
    a.status = CompanyTask.Status.DONE
    a.save()
    b.refresh_from_db()
    assert is_task_runnable(b) is True


@pytest.mark.django_db
def test_is_task_runnable_ignores_future_target_date(company, full_agent_fleet):
    del full_agent_fleet
    agent = company.agents.first()
    today = timezone.localdate()
    task = CompanyTask.objects.create(
        company=company,
        title="Later",
        status=CompanyTask.Status.TODO,
        assignee_type=CompanyTask.AssigneeType.AGENT,
        assigned_agent=agent,
        target_date=today + timedelta(days=30),
    )
    assert is_task_runnable(task) is True
    assert "eligible" in explain_task_skip(task)


@pytest.mark.django_db
def test_sync_task_target_date_to_run_day(company, full_agent_fleet):
    del full_agent_fleet
    agent = company.agents.first()
    today = timezone.localdate()
    task = CompanyTask.objects.create(
        company=company,
        title="Planned later",
        status=CompanyTask.Status.TODO,
        assignee_type=CompanyTask.AssigneeType.AGENT,
        assigned_agent=agent,
        target_date=today + timedelta(days=30),
    )
    assert sync_task_target_date_to_run_day(task, today=today) is True
    assert task.target_date == today
    assert sync_task_target_date_to_run_day(task, today=today) is False


@pytest.mark.django_db
def test_execute_company_task_updates_target_date(company, full_agent_fleet):
    del full_agent_fleet
    agent = company.agents.filter(role=CompanyAgent.Role.PLANNER).first()
    today = timezone.localdate()
    task = CompanyTask.objects.create(
        company=company,
        title="Future due",
        status=CompanyTask.Status.TODO,
        assignee_type=CompanyTask.AssigneeType.AGENT,
        assigned_agent=agent,
        target_date=today + timedelta(days=14),
    )
    mock_out = MagicMock(
        result_summary="Done.",
        progress_percent=100,
        outcome_assessment="success",
        needs_human=False,
    )
    with patch("apps.agents.agents._run_agent", return_value=(mock_out, None)), patch(
        "apps.agents.providers.validate_provider_config", return_value=None
    ), patch("apps.agents.providers.get_model_for_idea", return_value=MagicMock()):
        execute_company_task(task, manual_trigger=True)
    task.refresh_from_db()
    assert task.target_date == today


@pytest.mark.django_db
def test_get_runnable_tasks_skips_human(company, full_agent_fleet):
    del full_agent_fleet
    CompanyTask.objects.create(
        company=company,
        title="Human work",
        status=CompanyTask.Status.TODO,
        assignee_type=CompanyTask.AssigneeType.HUMAN,
    )
    agent = company.agents.first()
    CompanyTask.objects.create(
        company=company,
        title="Agent work",
        status=CompanyTask.Status.TODO,
        assignee_type=CompanyTask.AssigneeType.AGENT,
        assigned_agent=agent,
    )
    runnable = get_runnable_tasks(company, limit=5)
    assert len(runnable) == 1
    assert runnable[0].title == "Agent work"


@pytest.mark.django_db
def test_execute_company_task_completes(company, full_agent_fleet):
    del full_agent_fleet
    agent = company.agents.filter(role=CompanyAgent.Role.PLANNER).first()
    task = CompanyTask.objects.create(
        company=company,
        title="Write brief",
        description="Draft one-pager",
        status=CompanyTask.Status.TODO,
        assignee_type=CompanyTask.AssigneeType.AGENT,
        assigned_agent=agent,
    )
    mock_out = MagicMock(
        result_summary="One-pager drafted.",
        result_notes="See appendix",
        progress_percent=100,
        outcome_assessment="success",
        needs_human=False,
    )
    with patch("apps.agents.agents._run_agent", return_value=(mock_out, None)), patch(
        "apps.agents.providers.validate_provider_config", return_value=None
    ), patch("apps.agents.providers.get_model_for_idea", return_value=MagicMock()):
        outcome = execute_company_task(task)
    assert outcome == "completed"
    task.refresh_from_db()
    assert task.status == CompanyTask.Status.DONE
    assert task.result_summary == "One-pager drafted."
    assert task.progress_percent == 100
    assert task.completed_at is not None


@pytest.mark.django_db
def test_execute_company_task_escalates(company, full_agent_fleet):
    del full_agent_fleet
    CompanyTeamMember.objects.create(
        company=company,
        name="Founder",
        role=CompanyTeamMember.Role.FOUNDER,
        is_active=True,
    )
    agent = company.agents.first()
    task = CompanyTask.objects.create(
        company=company,
        title="Sign contract",
        status=CompanyTask.Status.TODO,
        assignee_type=CompanyTask.AssigneeType.AGENT,
        assigned_agent=agent,
    )
    mock_out = MagicMock(
        result_summary="Needs founder signature.",
        needs_human=True,
        outcome_assessment="blocked",
    )
    with patch("apps.agents.agents._run_agent", return_value=(mock_out, None)), patch(
        "apps.agents.providers.validate_provider_config", return_value=None
    ), patch("apps.agents.providers.get_model_for_idea", return_value=MagicMock()):
        outcome = execute_company_task(task)
    assert outcome == "escalated"
    task.refresh_from_db()
    assert task.status == CompanyTask.Status.BLOCKED
    assert task.escalated_to_human is True
    assert task.assigned_human is not None


@pytest.mark.django_db
def test_run_company_task_execution_dry_run(company, full_agent_fleet, monkeypatch):
    del full_agent_fleet
    agent = company.agents.first()
    CompanyTask.objects.create(
        company=company,
        title="Auto task",
        status=CompanyTask.Status.TODO,
        assignee_type=CompanyTask.AssigneeType.AGENT,
        assigned_agent=agent,
    )
    monkeypatch.setenv("TICKER_TASK_EXECUTION", "true")
    result = run_company_task_execution(dry_run=True)
    assert result.companies_processed == 1
    assert any("Would run" in m for m in result.messages)
