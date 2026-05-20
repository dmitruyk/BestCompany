"""Tests for autonomous loop helpers (mocked LLM)."""
from datetime import date
from unittest.mock import patch

import pytest

from apps.agents.autonomous import agent_select_actions, _build_calendar_context
from apps.agents.schemas import ActionSelectionOutput
from apps.ideas.models import ActionProposal, CompanyAgent, CompanyCalendarAction, DirectorDiscussion


@pytest.mark.django_db
def test_build_calendar_context_empty(company) -> None:
    text = _build_calendar_context(company, date.today())
    assert "No calendar actions" in text


@pytest.mark.django_db
def test_build_calendar_context_lists_entries(company) -> None:
    CompanyCalendarAction.objects.create(
        company=company,
        action_date=date.today(),
        title="Ship MVP",
        status=CompanyCalendarAction.ActionStatus.PLANNED,
    )
    text = _build_calendar_context(company, date.today())
    assert "Ship MVP" in text


@pytest.mark.django_db
def test_agent_select_actions_marks_selected(company, idea_request) -> None:
    director = CompanyAgent.objects.create(
        company=company,
        role=CompanyAgent.Role.DIRECTOR,
        name="Dir",
        system_prompt="Lead",
        priority=90,
    )
    disc = DirectorDiscussion.objects.create(
        company=company,
        topic="Test",
        status=DirectorDiscussion.Status.AWAITING_SELECTION,
    )
    a1 = ActionProposal.objects.create(
        discussion=disc,
        proposed_by=director,
        action_type="build",
        description="Build feature A",
    )
    ActionProposal.objects.create(
        discussion=disc,
        proposed_by=director,
        action_type="market",
        description="Launch campaign",
    )
    mock_out = ActionSelectionOutput(selected_action_ids=[1], rationale="Best impact")

    with patch("apps.agents.autonomous._get_provider_model") as mock_model:
        with patch("apps.agents.autonomous._run_agent") as mock_run:
            mock_model.return_value = object()
            mock_run.return_value = (mock_out, {})
            ok = agent_select_actions(disc)

    assert ok is True
    a1.refresh_from_db()
    assert a1.status == ActionProposal.ActionStatus.SELECTED
