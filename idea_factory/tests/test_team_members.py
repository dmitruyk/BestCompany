"""Tests for human team members."""
import pytest
from django.urls import reverse

from apps.ideas.models import CompanyTeamMember


@pytest.mark.django_db
def test_team_member_model(company) -> None:
    m = CompanyTeamMember.objects.create(
        company=company,
        name="Alex",
        role=CompanyTeamMember.Role.FOUNDER_ASSISTANT,
        email="alex@example.com",
    )
    assert "Alex" in str(m)
    assert company.team_members.filter(is_active=True).count() == 1


@pytest.mark.django_db
def test_add_team_member_view(client, user, company) -> None:
    client.force_login(user)
    url = reverse("add_team_member", kwargs={"pk": company.pk})
    response = client.post(
        url,
        {"name": "Sam QA", "role": CompanyTeamMember.Role.QA, "email": ""},
    )
    assert response.status_code == 302
    assert CompanyTeamMember.objects.filter(company=company, name="Sam QA").exists()
