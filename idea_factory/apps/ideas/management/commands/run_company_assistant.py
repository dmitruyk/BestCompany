"""Management command to generate company assistant response in background."""
import sys

from django.core.management.base import BaseCommand

from apps.agents.llm_settings import get_llm_settings_for_assistant, llm_env
from apps.ideas.models import CompanyAssistantMessage


class Command(BaseCommand):
    help = "Generate assistant response (run_company_assistant <message_uuid>)"

    def add_arguments(self, parser):
        parser.add_argument("message_id", type=str)

    def handle(self, *args, **options):
        message_id = options["message_id"]
        try:
            message = CompanyAssistantMessage.objects.select_related(
                "conversation",
                "company",
                "company__idea_request",
                "user",
            ).get(pk=message_id)
        except CompanyAssistantMessage.DoesNotExist:
            self.stderr.write(f"Message {message_id} not found")
            sys.exit(1)

        from apps.web.company_assistant_views import _run_company_assistant_message

        cfg = get_llm_settings_for_assistant(message.company.idea_request)
        with llm_env(cfg):
            _run_company_assistant_message(message)
        self.stdout.write(f"Company assistant response saved for message {message_id}")
