"""Tests for company assistant proposed actions."""
import json

import pytest
from django.contrib.auth import get_user_model

from apps.ideas.company_assistant_actions import (
    propose_actions_for_message,
    user_wants_assistant_action,
)
from apps.ideas.development_plan import get_development_plan_summary
from apps.ideas.models import (
    CompanyAssistantConversation,
    CompanyAssistantMessage,
    CompanyAssistantProposedAction,
    IdeaConclusion,
)

User = get_user_model()


def test_user_wants_action_on_fix_readiness():
    assert user_wants_assistant_action("Can you fix the development plan failure?")
    assert user_wants_assistant_action("What is my readiness score?")


@pytest.mark.django_db
def test_propose_planning_when_no_pipeline_plan(company, user):
    plan = get_development_plan_summary(company.idea_request)
    assert plan["has_plan"] is False
    conv = CompanyAssistantConversation.objects.create(company=company, user=user)
    msg = CompanyAssistantMessage.objects.create(
        conversation=conv,
        company=company,
        user=user,
        user_content="Fix the failed development plan check",
    )
    proposals = propose_actions_for_message(msg)
    assert proposals
    assert any(
        p.action_type == CompanyAssistantProposedAction.ActionType.START_PLANNING_SESSION
        for p in proposals
    )
