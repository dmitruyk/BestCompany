"""Pytest configuration for idea_factory."""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "idea_factory.settings")
django.setup()
