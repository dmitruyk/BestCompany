"""Tests for fleet role mapping and director minimums."""
import pytest

from apps.agents.fleet import ROLE_MAP, MIN_DIRECTORS, _ensure_min_directors
from apps.ideas.models import Company, CompanyAgent, IdeaRequest


@pytest.mark.django_db
def test_role_map_includes_team_roles() -> None:
    assert ROLE_MAP["founder"] == CompanyAgent.Role.FOUNDER
    assert ROLE_MAP["planner"] == CompanyAgent.Role.PLANNER
    assert ROLE_MAP["qa"] == CompanyAgent.Role.QA
    assert ROLE_MAP["accountant"] == CompanyAgent.Role.CPA


@pytest.mark.django_db
def test_ensure_min_directors_adds_defaults(user, idea_request) -> None:
    company = Company.objects.create(
        idea_request=idea_request,
        name="Co",
        owner=user,
    )
    _ensure_min_directors(company, "Test context")
    assert company.agents.filter(role=CompanyAgent.Role.DIRECTOR).count() >= MIN_DIRECTORS
