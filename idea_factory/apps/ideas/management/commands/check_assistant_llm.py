"""Verify LLM connectivity for the company assistant."""
from django.core.management.base import BaseCommand

from apps.agents.llm_settings import get_llm_settings_for_assistant, validate_llm_settings
from apps.agents.providers import get_model_for_assistant
from apps.agents.schemas import ChatResponse
from apps.agents.agents import _run_structured_output_direct


class Command(BaseCommand):
    help = "Test LLM provider used by the company assistant (manage.py check_assistant_llm)"

    def handle(self, *args, **options):
        cfg = get_llm_settings_for_assistant()
        err = validate_llm_settings(cfg)
        if err:
            self.stderr.write(self.style.ERROR(f"Config: {err}"))
            return
        self.stdout.write(
            f"Assistant LLM — provider: {cfg.provider} | model: {cfg.model_id_for_provider()}"
        )
        try:
            model = get_model_for_assistant()
            out, metrics = _run_structured_output_direct(
                model,
                "assistant_check",
                "You are a test assistant.",
                "Reply with exactly: OK",
                ChatResponse,
            )
            text = out.response if out and hasattr(out, "response") else str(out)
            self.stdout.write(self.style.SUCCESS(f"LLM OK: {text!r} ({metrics.get('latency_ms')}ms)"))
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"LLM call failed: {type(exc).__name__}: {exc}"))
