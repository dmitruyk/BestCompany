"""Tests for human accounts and forced password change."""
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.core.models import UserProfile

User = get_user_model()


@pytest.mark.django_db
def test_ensure_default_admin_creates_admin() -> None:
    from django.core.management import call_command

    call_command("ensure_default_admin")
    user = User.objects.get(username="admin")
    assert user.is_superuser is True
    assert user.is_staff is True
    assert user.check_password("1234")
    assert user.profile.must_change_password is True


@pytest.mark.django_db
def test_ensure_default_admin_idempotent() -> None:
    from django.core.management import call_command

    call_command("ensure_default_admin")
    user = User.objects.get(username="admin")
    user.set_password("changed-secret")
    user.save()
    user.profile.must_change_password = False
    user.profile.save()
    call_command("ensure_default_admin")
    user.refresh_from_db()
    assert user.check_password("changed-secret")
    assert user.profile.must_change_password is False


@pytest.mark.django_db
def test_login_redirects_to_password_change(client) -> None:
    user = User.objects.create_user(username="human1", password="temp1234")
    UserProfile.objects.filter(user=user).update(must_change_password=True)
    response = client.post(
        reverse("app_login"),
        {"username": "human1", "password": "temp1234"},
    )
    assert response.status_code == 302
    assert response.url == reverse("force_password_change")


@pytest.mark.django_db
def test_force_password_change_clears_flag(client) -> None:
    user = User.objects.create_user(username="human2", password="temp1234")
    UserProfile.objects.filter(user=user).update(must_change_password=True)
    client.force_login(user)
    response = client.post(
        reverse("force_password_change"),
        {"new_password1": "NewSecurePass99!", "new_password2": "NewSecurePass99!"},
    )
    assert response.status_code == 302
    user.refresh_from_db()
    assert user.profile.must_change_password is False
    assert user.check_password("NewSecurePass99!")


@pytest.mark.django_db
def test_middleware_blocks_home_until_password_changed(client) -> None:
    user = User.objects.create_user(username="human3", password="temp1234")
    UserProfile.objects.filter(user=user).update(must_change_password=True)
    client.force_login(user)
    response = client.get(reverse("home"))
    assert response.status_code == 302
    assert response.url == reverse("force_password_change")
