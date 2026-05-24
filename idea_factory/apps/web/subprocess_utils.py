"""Shared helpers for spawning manage.py child processes."""
from __future__ import annotations

import os
import sys

from apps.core.subprocess_env import enrich_subprocess_env


def get_project_root() -> str:
    """Absolute path to project root (idea_factory/)."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_subprocess_env() -> dict[str, str]:
    """Env for subprocess — same database and PYTHONPATH as the Django server."""
    root = get_project_root()
    env = enrich_subprocess_env()
    env["PYTHONPATH"] = root + os.pathsep + env.get("PYTHONPATH", "")
    return env


def manage_py_argv(*args: str) -> list[str]:
    """Command argv: python manage.py <args>."""
    root = get_project_root()
    return [sys.executable, os.path.join(root, "manage.py"), *args]
