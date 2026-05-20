"""Tests for subprocess environment propagation."""
import os

import pytest


@pytest.mark.django_db
def test_enrich_subprocess_env_injects_db_settings(settings) -> None:
    from apps.core.subprocess_env import enrich_subprocess_env

    env = enrich_subprocess_env({})
    assert env.get("DB_NAME") == settings.DATABASES["default"]["NAME"]
    assert env.get("DB_HOST") == settings.DATABASES["default"]["HOST"]
    if settings.DATABASES["default"].get("PASSWORD"):
        assert "DB_PASSWORD" in env
