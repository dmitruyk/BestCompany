"""Environment for child processes (pipeline, fleet, etc.)."""
from __future__ import annotations

import os
from typing import MutableMapping


def enrich_subprocess_env(env: MutableMapping[str, str] | None = None) -> dict[str, str]:
    """
    Copy parent env and inject database settings so spawned manage.py commands
    use the same database as the web server.
    """
    from django.conf import settings

    from apps.agents.llm_settings import apply_llm_env_to_mapping, get_service_llm_settings

    result = dict(env if env is not None else os.environ)
    result = apply_llm_env_to_mapping(get_service_llm_settings(), result)
    db = settings.DATABASES["default"]
    for env_key, db_key in (
        ("DB_NAME", "NAME"),
        ("DB_USER", "USER"),
        ("DB_PASSWORD", "PASSWORD"),
        ("DB_HOST", "HOST"),
        ("DB_PORT", "PORT"),
    ):
        value = db.get(db_key)
        if value not in (None, ""):
            result[env_key] = str(value)
    return result
