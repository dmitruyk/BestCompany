"""Tests for multi-agent panel discussions."""
from unittest.mock import patch

import pytest
from django.urls import reverse

from apps.agents.schemas import AgentPanelContributionOutput, AgentPanelSynthesisOutput
from apps.ideas.agent_panel_discussion import run_agent_panel_discussion
from apps.ideas.models import (
    AgentPanelDiscussion,
    AgentPanelMessage,
    AgentPanelParticipant,
    CompanyAgent,
)


@pytest.mark.django_db
def test_run_agent_panel_discussion_completes(company, user, full_agent_fleet):
    cpa = next(a for a in full_agent_fleet if a.role == CompanyAgent.Role.CPA)
    marketer = next(a for a in full_agent_fleet if a.role == CompanyAgent.Role.MARKETER)
    discussion = AgentPanelDiscussion.objects.create(
        company=company,
        user=user,
        question="Should we increase marketing spend this quarter?",
        status=AgentPanelDiscussion.Status.ACTIVE,
    )
    AgentPanelParticipant.objects.create(discussion=discussion, agent=cpa, sort_order=0)
    AgentPanelParticipant.objects.create(
        discussion=discussion, agent=marketer, sort_order=1
    )

    contribution = AgentPanelContributionOutput(message="From my perspective…")
    synthesis = AgentPanelSynthesisOutput(synthesis="Agreed: proceed cautiously.")

    with patch("apps.ideas.agent_panel_discussion._get_provider_model_for_company", return_value=object()), patch(
        "apps.agents.agents._run_agent"
    ) as mock_run:
        mock_run.side_effect = [
            (contribution, None),
            (contribution, None),
            (synthesis, None),
        ]
        run_agent_panel_discussion(discussion)

    discussion.refresh_from_db()
    assert discussion.status == AgentPanelDiscussion.Status.COMPLETED
    assert discussion.synthesis == "Agreed: proceed cautiously."
    assert AgentPanelMessage.objects.filter(discussion=discussion).count() == 2


@pytest.mark.django_db
def test_run_agent_panel_fails_with_one_agent(company, user, full_agent_fleet):
    cpa = next(a for a in full_agent_fleet if a.role == CompanyAgent.Role.CPA)
    discussion = AgentPanelDiscussion.objects.create(
        company=company,
        user=user,
        question="Budget question",
        status=AgentPanelDiscussion.Status.ACTIVE,
    )
    AgentPanelParticipant.objects.create(discussion=discussion, agent=cpa, sort_order=0)

    run_agent_panel_discussion(discussion)

    discussion.refresh_from_db()
    assert discussion.status == AgentPanelDiscussion.Status.FAILED


@pytest.mark.django_db
def test_start_agent_panel_requires_two_agents(client, user, company, full_agent_fleet):
    client.force_login(user)
    cpa = next(a for a in full_agent_fleet if a.role == CompanyAgent.Role.CPA)
    url = reverse("start_agent_panel", kwargs={"company_pk": company.pk})
    response = client.post(
        url,
        {"question": "Test?", "agent_ids": [str(cpa.pk)]},
        follow=True,
    )
    assert response.status_code == 200
    assert AgentPanelDiscussion.objects.count() == 0


@pytest.mark.django_db
@patch("apps.web.agent_panel_views._spawn_agent_panel_process")
def test_start_agent_panel_creates_discussion(
    mock_spawn, client, user, company, full_agent_fleet
):
    client.force_login(user)
    cpa = next(a for a in full_agent_fleet if a.role == CompanyAgent.Role.CPA)
    marketer = next(a for a in full_agent_fleet if a.role == CompanyAgent.Role.MARKETER)
    url = reverse("start_agent_panel", kwargs={"company_pk": company.pk})
    response = client.post(
        url,
        {
            "question": "Launch freemium first?",
            "agent_ids": [str(cpa.pk), str(marketer.pk)],
        },
    )
    assert response.status_code == 302
    discussion = AgentPanelDiscussion.objects.get()
    assert discussion.question == "Launch freemium first?"
    assert discussion.participants.count() == 2
    mock_spawn.assert_called_once()
