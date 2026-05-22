"""Django admin for ideas app."""
from django.contrib import admin
from .models import (
    ActionProposal,
    AgentMessage,
    AgentRun,
    Company,
    CompanyAgent,
    CompanyCalendarAction,
    CompanyHistoryEntry,
    CompanyStrategicDirection,
    CompanyTask,
    CompanyTaskDependency,
    CompanyTeamMember,
    DirectorDiscussion,
    DiscussionMessage,
    IdeaAttachment,
    IdeaConclusion,
    IdeaRequest,
    PlanningSession,
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


@admin.register(IdeaAttachment)
class IdeaAttachmentAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "idea_request", "file_size", "created_at")
    search_fields = ("original_filename",)
    readonly_fields = ("id", "extracted_text", "created_at")


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


@admin.register(CompanyTeamMember)
class CompanyTeamMemberAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "role", "user", "is_active", "email", "created_at")
    list_filter = ("role", "is_active")
    search_fields = ("name", "email", "company__name", "user__username")
    raw_id_fields = ("user",)


@admin.register(CompanyCalendarAction)
class CompanyCalendarActionAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "action_date", "status", "created_at")
    list_filter = ("status", "action_date")


@admin.register(CompanyStrategicDirection)
class CompanyStrategicDirectionAdmin(admin.ModelAdmin):
    list_display = ("company", "founder_verified", "is_active", "created_at")
    list_filter = ("founder_verified", "is_active")


@admin.register(PlanningSession)
class PlanningSessionAdmin(admin.ModelAdmin):
    list_display = ("company", "trigger", "week_start", "status", "created_at")
    list_filter = ("trigger", "status")


@admin.register(CompanyTask)
class CompanyTaskAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "status", "assignee_type", "progress_percent", "target_date")
    list_filter = ("status", "assignee_type")


@admin.register(CompanyTaskDependency)
class CompanyTaskDependencyAdmin(admin.ModelAdmin):
    list_display = ("task", "depends_on")


@admin.register(CompanyHistoryEntry)
class CompanyHistoryEntryAdmin(admin.ModelAdmin):
    list_display = ("company", "entry_type", "title", "created_at")
    list_filter = ("entry_type",)
