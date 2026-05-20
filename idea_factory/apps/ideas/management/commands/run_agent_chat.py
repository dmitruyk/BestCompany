"""Management command to generate agent chat response in background."""
import sys

from django.core.management.base import BaseCommand

from apps.ideas.models import UserAgentMessage


class Command(BaseCommand):
    help = "Generate agent response for a user chat message (run_agent_chat <message_uuid>)"

    def add_arguments(self, parser):
        parser.add_argument("message_id", type=str)

    def handle(self, *args, **options):
        message_id = options["message_id"]
        try:
            message = UserAgentMessage.objects.select_related(
                "agent", "agent__company", "user"
            ).get(pk=message_id)
        except UserAgentMessage.DoesNotExist:
            self.stderr.write(f"Message {message_id} not found")
            sys.exit(1)

        from apps.web.views import _run_agent_chat_message

        _run_agent_chat_message(message)
        self.stdout.write(f"Agent chat response saved for message {message_id}")
