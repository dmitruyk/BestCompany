"""ASGI config for idea_factory project."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "idea_factory.settings")

application = get_asgi_application()
