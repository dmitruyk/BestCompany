#!/usr/bin/env python
"""Check LLM provider configuration."""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "idea_factory.settings")

import django
django.setup()

from apps.agents.providers import get_provider, get_model


def main() -> int:
    provider = get_provider()
    print(f"LLM_PROVIDER: {provider}")
    try:
        model = get_model()
        print(f"Model: {model}")
        print("OK - provider configured successfully")
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
