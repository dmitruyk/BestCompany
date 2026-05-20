"""Shared pytest fixtures."""
import json

import pytest
from django.contrib.auth import get_user_model

from apps.ideas.models import (
    Company,
    CompanyAgent,
    CompanyCalendarAction,
    CompanyTeamMember,
    DirectorDiscussion,
    IdeaConclusion,
    IdeaRequest,
)

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="owner", password="test-pass-123")


@pytest.fixture
def idea_request(db, user):
    return IdeaRequest.objects.create(
        title="Test SaaS",
        prompt="Build a bakery ordering platform",
        status=IdeaRequest.Status.SUCCEEDED,
        owner=user,
        provider=IdeaRequest.Provider.OPENAI,
    )


@pytest.fixture
def idea_conclusion(db, idea_request):
    result = {
        "final_summary": "Strong GO for local bakeries.",
        "agent_outputs": {
            "estimator": {
                "kpis": ["Monthly active bakeries", "Order conversion rate"],
                "mvp_plan_summary": "Launch MVP in 8 weeks",
            },
            "executor": {
                "milestones": ["MVP beta", "First 10 customers"],
                "mvp_backlog": ["Auth", "Orders", "Payments"],
            },
            "overviewer": {
                "go_no_go": "GO",
                "executive_summary": "Proceed with focused MVP.",
                "key_metrics": ["Revenue", "Retention"],
            },
        },
    }
    return IdeaConclusion.objects.create(
        idea_request=idea_request,
        final_summary=result["final_summary"],
        result_json=json.dumps(result),
    )


@pytest.fixture
def company(db, user, idea_request, idea_conclusion):
    del idea_conclusion
    return Company.objects.create(
        idea_request=idea_request,
        name="Test Bakery Co",
        owner=user,
        status=Company.Status.ACTIVE,
    )


@pytest.fixture
def full_agent_fleet(db, company):
    """Minimal fleet matching best-practice requirements."""
    roles = [
        (CompanyAgent.Role.FOUNDER, "AI Founder", 95),
        (CompanyAgent.Role.FOUNDER_ASSISTANT, "AI Assistant", 70),
        (CompanyAgent.Role.CPA, "Finance Lead", 60),
        (CompanyAgent.Role.MARKETER, "Growth Lead", 60),
        (CompanyAgent.Role.PLANNER, "Roadmap Lead", 65),
        (CompanyAgent.Role.QA, "Quality Lead", 55),
        (CompanyAgent.Role.DEVELOPER, "Tech Lead", 50),
    ]
    agents = []
    for role, name, priority in roles:
        agents.append(
            CompanyAgent.objects.create(
                company=company,
                role=role,
                name=name,
                system_prompt=f"You are {name}.",
                priority=priority,
            )
        )
    for i, name in enumerate(
        ("Strategy Director", "Operations Director", "Growth Director")
    ):
        agents.append(
            CompanyAgent.objects.create(
                company=company,
                role=CompanyAgent.Role.DIRECTOR,
                name=name,
                system_prompt=f"You are {name}.",
                priority=90 - i,
            )
        )
    return agents
