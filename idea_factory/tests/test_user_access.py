"""Tests for multi-user access control and staff user management."""
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.core.models import UserProfile
from apps.ideas.models import Company, IdeaRequest

User = get_user_model()


@pytest.mark.django_db
def test_regular_user_sees_only_own_ideas(client, user, idea_request) -> None:
    other = User.objects.create_user(username="other", password="pass12345!")
    other_idea = IdeaRequest.objects.create(
        title="Other idea",
        prompt="Secret",
        status=IdeaRequest.Status.SUCCEEDED,
        owner=other,
        provider=IdeaRequest.Provider.OPENAI,
    )
    client.force_login(user)
    response = client.get(reverse("home"))
    assert response.status_code == 200
    assert idea_request.title.encode() in response.content
    assert other_idea.title.encode() not in response.content


@pytest.mark.django_db
def test_staff_sees_all_ideas(client, user, idea_request) -> None:
    user.is_staff = True
    user.save()
    other = User.objects.create_user(username="other2", password="pass12345!")
    other_idea = IdeaRequest.objects.create(
        title="Shared visibility",
        prompt="Visible to admin",
        status=IdeaRequest.Status.SUCCEEDED,
        owner=other,
        provider=IdeaRequest.Provider.OPENAI,
    )
    client.force_login(user)
    response = client.get(reverse("home"))
    assert other_idea.title.encode() in response.content


@pytest.mark.django_db
def test_cannot_create_idea_without_permission(client, user) -> None:
    UserProfile.objects.filter(user=user).update(can_create_ideas=False)
    client.force_login(user)
    response = client.get(reverse("new_idea"))
    assert response.status_code == 302
    assert response.url == reverse("home")


@pytest.mark.django_db
def test_staff_can_create_user(client, user) -> None:
    user.is_staff = True
    user.save()
    UserProfile.objects.filter(user=user).update(must_change_password=False)
    client.force_login(user)
    response = client.post(
        reverse("user_create"),
        {
            "username": "newhuman",
            "email": "new@example.com",
            "first_name": "New",
            "last_name": "Human",
            "initial_password": "TempPass123!",
            "can_create_ideas": "on",
            "can_create_companies": "on",
        },
        follow=True,
    )
    assert response.status_code == 200
    created = User.objects.get(username="newhuman")
    assert created.profile.must_change_password is True
    assert created.profile.can_create_ideas is True
    assert created.check_password("TempPass123!")


@pytest.mark.django_db
def test_non_staff_cannot_access_user_list(client, user) -> None:
    client.force_login(user)
    response = client.get(reverse("user_list"))
    assert response.status_code == 302


@pytest.mark.django_db
def test_regular_user_cannot_view_other_company(client, user, company) -> None:
    other = User.objects.create_user(username="intruder", password="pass12345!")
    client.force_login(other)
    response = client.get(reverse("company_detail", kwargs={"pk": company.pk}))
    assert response.status_code == 404


@pytest.mark.django_db
def test_staff_can_view_any_company(client, user, company) -> None:
    user.is_staff = True
    user.save()
    client.force_login(user)
    response = client.get(reverse("company_detail", kwargs={"pk": company.pk}))
    assert response.status_code == 200
