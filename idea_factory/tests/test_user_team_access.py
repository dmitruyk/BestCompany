"""Tests for linking CompanyTeamMember records to User accounts."""
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.core.models import UserProfile
from apps.ideas.models import Company, CompanyTask, CompanyTeamMember

User = get_user_model()


@pytest.fixture
def member_user(db):
    user = User.objects.create_user(username="member", password="pass12345!")
    UserProfile.objects.filter(user=user).update(
        can_create_ideas=False,
        can_create_companies=False,
        must_change_password=False,
    )
    return user


@pytest.mark.django_db
def test_team_member_can_access_linked_company(client, company, member_user) -> None:
    CompanyTeamMember.objects.create(
        company=company,
        name="Alex QA",
        role=CompanyTeamMember.Role.QA,
        user=member_user,
    )
    client.force_login(member_user)
    response = client.get(reverse("company_detail", kwargs={"pk": company.pk}))
    assert response.status_code == 200


@pytest.mark.django_db
def test_team_member_cannot_access_unlinked_company(
    client, company, member_user
) -> None:
    client.force_login(member_user)
    response = client.get(reverse("company_detail", kwargs={"pk": company.pk}))
    assert response.status_code == 404


@pytest.mark.django_db
def test_my_tasks_lists_assigned_human_tasks(
    client, company, member_user, user
) -> None:
    member = CompanyTeamMember.objects.create(
        company=company,
        name="Alex QA",
        role=CompanyTeamMember.Role.QA,
        user=member_user,
    )
    task = CompanyTask.objects.create(
        company=company,
        title="Review release",
        assignee_type=CompanyTask.AssigneeType.HUMAN,
        assigned_human=member,
    )
    CompanyTask.objects.create(
        company=company,
        title="Someone else's task",
        assignee_type=CompanyTask.AssigneeType.HUMAN,
        assigned_human=CompanyTeamMember.objects.create(
            company=company,
            name="Other Human",
            role=CompanyTeamMember.Role.OPERATIONS,
        ),
    )
    client.force_login(member_user)
    response = client.get(reverse("my_tasks"))
    assert response.status_code == 200
    assert task.title.encode() in response.content
    assert b"Someone else's task" not in response.content


@pytest.mark.django_db
def test_member_can_update_own_task(client, company, member_user) -> None:
    member = CompanyTeamMember.objects.create(
        company=company,
        name="Alex",
        role=CompanyTeamMember.Role.QA,
        user=member_user,
    )
    task = CompanyTask.objects.create(
        company=company,
        title="Fix bug",
        assignee_type=CompanyTask.AssigneeType.HUMAN,
        assigned_human=member,
        status=CompanyTask.Status.TODO,
    )
    client.force_login(member_user)
    response = client.post(
        reverse(
            "company_task_detail",
            kwargs={"company_pk": company.pk, "task_pk": task.pk},
        ),
        {"status": CompanyTask.Status.IN_PROGRESS, "progress_percent": "50"},
    )
    assert response.status_code == 302
    task.refresh_from_db()
    assert task.status == CompanyTask.Status.IN_PROGRESS
    assert task.progress_percent == 50


@pytest.mark.django_db
def test_member_cannot_update_unassigned_task(client, company, member_user) -> None:
    CompanyTeamMember.objects.create(
        company=company,
        name="Alex",
        role=CompanyTeamMember.Role.QA,
        user=member_user,
    )
    task = CompanyTask.objects.create(
        company=company,
        title="Not mine",
        assignee_type=CompanyTask.AssigneeType.HUMAN,
        assigned_human=CompanyTeamMember.objects.create(
            company=company,
            name="Bob",
            role=CompanyTeamMember.Role.OPERATIONS,
        ),
    )
    client.force_login(member_user)
    response = client.post(
        reverse(
            "company_task_detail",
            kwargs={"company_pk": company.pk, "task_pk": task.pk},
        ),
        {"status": CompanyTask.Status.DONE},
    )
    assert response.status_code == 302
    task.refresh_from_db()
    assert task.status != CompanyTask.Status.DONE


@pytest.mark.django_db
def test_staff_can_link_team_member_on_user_create(client, user, company) -> None:
    human = CompanyTeamMember.objects.create(
        company=company,
        name="Pat",
        role=CompanyTeamMember.Role.FOUNDER,
    )
    user.is_staff = True
    user.save()
    UserProfile.objects.filter(user=user).update(must_change_password=False)
    client.force_login(user)
    response = client.post(
        reverse("user_create"),
        {
            "username": "patlogin",
            "email": "pat@example.com",
            "initial_password": "TempPass123!",
            "link_team_members": [str(human.pk)],
        },
        follow=True,
    )
    assert response.status_code == 200
    created = User.objects.get(username="patlogin")
    human.refresh_from_db()
    assert human.user_id == created.pk
    created.profile.must_change_password = False
    created.profile.save(update_fields=["must_change_password", "updated_at"])
    client.logout()
    client.login(username="patlogin", password="TempPass123!")
    assert (
        client.get(reverse("company_detail", kwargs={"pk": company.pk})).status_code
        == 200
    )


@pytest.mark.django_db
def test_team_member_login_redirects_to_my_tasks(client, company, member_user) -> None:
    CompanyTeamMember.objects.create(
        company=company,
        name="Alex",
        role=CompanyTeamMember.Role.QA,
        user=member_user,
    )
    response = client.post(
        reverse("app_login"),
        {"username": "member", "password": "pass12345!"},
    )
    assert response.status_code == 302
    assert response.url == reverse("my_tasks")
