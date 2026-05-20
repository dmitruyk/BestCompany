"""Tests for manual autonomous loop trigger and helpers."""
from unittest.mock import patch

import pytest
from django.urls import reverse

from apps.ideas.autonomous_loop import count_unscheduled_selected
from apps.ideas.models import ActionProposal, CompanyAgent, DirectorDiscussion


@pytest.mark.django_db
def test_count_unscheduled_selected(company) -> None:
    director = CompanyAgent.objects.create(
        company=company,
        role=CompanyAgent.Role.DIRECTOR,
        name="Dir",
        system_prompt="Lead",
        priority=90,
    )
    disc = DirectorDiscussion.objects.create(company=company, topic="Plan")
    ActionProposal.objects.create(
        discussion=disc,
        proposed_by=director,
        action_type="build",
        description="Build MVP",
        status=ActionProposal.ActionStatus.SELECTED,
    )
    ActionProposal.objects.create(
        discussion=disc,
        proposed_by=director,
        action_type="skip",
        description="Not chosen",
        status=ActionProposal.ActionStatus.PROPOSED,
    )
    assert count_unscheduled_selected(company) == 1


@pytest.mark.django_db
def test_run_autonomous_loop_now_requires_selected(client, user, company) -> None:
    company.owner = user
    company.save()
    client.force_login(user)
    url = reverse("run_autonomous_loop_now", kwargs={"pk": company.pk})
    response = client.post(url, follow=True)
    assert response.status_code == 200
    assert b"No selected actions waiting" in response.content


@pytest.mark.django_db
def test_run_autonomous_loop_now_schedules(client, user, company) -> None:
    director = CompanyAgent.objects.create(
        company=company,
        role=CompanyAgent.Role.DIRECTOR,
        name="Dir",
        system_prompt="Lead",
        priority=90,
    )
    disc = DirectorDiscussion.objects.create(company=company, topic="Plan")
    ActionProposal.objects.create(
        discussion=disc,
        proposed_by=director,
        action_type="build",
        description="Build MVP",
        status=ActionProposal.ActionStatus.SELECTED,
    )
    company.owner = user
    company.save()
    client.force_login(user)
    url = reverse("run_autonomous_loop_now", kwargs={"pk": company.pk})

    with patch("apps.ideas.autonomous_loop.agent_schedule_action") as mock_schedule:
        from datetime import date

        mock_schedule.return_value = date(2026, 5, 21)
        with patch("apps.ideas.autonomous_loop.agent_execute_calendar_action"):
            response = client.post(url, follow=True)

    assert response.status_code == 200
    assert b"Scheduled 1 action" in response.content
