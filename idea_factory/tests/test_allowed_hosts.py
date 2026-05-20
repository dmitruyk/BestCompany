"""ALLOWED_HOSTS / public hostname configuration."""
import importlib
import os

import pytest
from django.http.request import validate_host


@pytest.fixture
def fresh_settings(monkeypatch):
    """Reload settings after env changes (settings are read at import time)."""
    import idea_factory.settings as settings_module

    yield settings_module
    importlib.reload(settings_module)


def test_public_host_added_to_allowed_hosts(monkeypatch, fresh_settings):
    monkeypatch.setenv("DJANGO_PUBLIC_HOST", "manage.addmylegacy.com")
    monkeypatch.setenv("ALLOWED_HOSTS", "localhost")
    settings = importlib.reload(fresh_settings)
    assert "manage.addmylegacy.com" in settings.ALLOWED_HOSTS
    assert "https://manage.addmylegacy.com" in settings.CSRF_TRUSTED_ORIGINS
    assert validate_host("manage.addmylegacy.com", settings.ALLOWED_HOSTS)


def test_manage_host_in_allowed_hosts_list(monkeypatch, fresh_settings):
    monkeypatch.delenv("DJANGO_PUBLIC_HOST", raising=False)
    monkeypatch.setenv(
        "ALLOWED_HOSTS",
        "localhost,manage.addmylegacy.com",
    )
    settings = importlib.reload(fresh_settings)
    assert validate_host("manage.addmylegacy.com", settings.ALLOWED_HOSTS)


def test_local_env_allows_manage_host():
    from django.conf import settings

    assert validate_host("manage.addmylegacy.com", settings.ALLOWED_HOSTS)
