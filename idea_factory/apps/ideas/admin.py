"""Django admin for ideas app."""
from django.contrib import admin
from .models import (
    ActionProposal,
    AgentMessage,
    AgentRun,
    Company,
    CompanyAgent,
    CompanyCalendarAction,
    DirectorDiscussion,
    DiscussionMessage,
    IdeaConclusion,
    IdeaRequest,
    UserAgentMessage,
)


@admin.register(IdeaRequest)
class IdeaRequestAdmin(admin.ModelAdmin):
    """Admin for IdeaRequest."""

    list_display = (
        "title",
        "status",
        "development_status",
        "provider",
        "model_id",
        "owner",
        "created_at",
    )
    list_filter = ("status", "development_status", "provider")
    search_fields = ("title", "prompt")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(AgentRun)
class AgentRunAdmin(admin.ModelAdmin):
    """Admin for AgentRun."""

    list_display = (
        "agent_name",
        "idea_request",
        "role",
        "confidence",
        "cycles",
        "status",
        "started_at",
    )
    list_filter = ("role", "status")
    readonly_fields = (
        "id",
        "started_at",
        "finished_at",
        "output_json",
    )


@admin.register(AgentMessage)
class AgentMessageAdmin(admin.ModelAdmin):
    """Admin for AgentMessage."""

    list_display = ("agent_run", "sequence", "kind", "created_at")
    list_filter = ("kind",)


@admin.register(IdeaConclusion)
class IdeaConclusionAdmin(admin.ModelAdmin):
    """Admin for IdeaConclusion."""

    list_display = ("idea_request", "created_at")
    readonly_fields = ("id", "created_at")


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "idea_request", "owner", "status", "created_at")
    list_filter = ("status",)


@admin.register(CompanyAgent)
class CompanyAgentAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "role", "priority", "created_at")
    list_filter = ("role",)


@admin.register(DirectorDiscussion)
class DirectorDiscussionAdmin(admin.ModelAdmin):
    list_display = ("topic", "company", "status", "created_at")
    list_filter = ("status",)


@admin.register(DiscussionMessage)
class DiscussionMessageAdmin(admin.ModelAdmin):
    list_display = ("discussion", "sender_type", "sender_agent", "created_at")
    list_filter = ("sender_type",)


@admin.register(ActionProposal)
class ActionProposalAdmin(admin.ModelAdmin):
    list_display = ("action_type", "discussion", "proposed_by", "status", "created_at")
    list_filter = ("status",)


@admin.register(UserAgentMessage)
class UserAgentMessageAdmin(admin.ModelAdmin):
    list_display = ("user", "agent", "created_at")


@admin.register(CompanyCalendarAction)
class CompanyCalendarActionAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "action_date", "status", "created_at")
    list_filter = ("status", "action_date")
