"""Data models for idea requests and agent runs."""
import os
import uuid

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models


def idea_attachment_upload_to(instance: "IdeaAttachment", filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower() or ".pdf"
    return f"idea_attachments/{instance.idea_request_id}/{uuid.uuid4()}{ext}"


class IdeaRequest(models.Model):
    """A user's business idea request that triggers the agent pipeline."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RUNNING = "RUNNING", "Running"
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"

    class DevelopmentStatus(models.TextChoices):
        NOT_STARTED = "NOT_STARTED", "Not Started"
        GENERATING_FLEET = "GENERATING_FLEET", "Generating Agent Fleet"
        READY = "READY", "Ready"
        DEVELOPING = "DEVELOPING", "Developing"
        COMPLETED = "COMPLETED", "Completed"

    class Provider(models.TextChoices):
        OLLAMA = "ollama", "Ollama (local)"
        OPENAI = "openai", "OpenAI"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    prompt = models.TextField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    provider = models.CharField(
        max_length=20, choices=Provider.choices, default=Provider.OLLAMA
    )
    model_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Ollama model (e.g. gpt-oss:20b, qwen3) or OpenAI model; Ollama requires tool-capable model",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="idea_requests",
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    development_status = models.CharField(
        max_length=30,
        choices=DevelopmentStatus.choices,
        default=DevelopmentStatus.NOT_STARTED,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.title} ({self.status})"


class IdeaAttachment(models.Model):
    """PDF document attached to an idea for additional LLM context."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    idea_request = models.ForeignKey(
        IdeaRequest, on_delete=models.CASCADE, related_name="attachments"
    )
    file = models.FileField(
        upload_to=idea_attachment_upload_to,
        validators=[FileExtensionValidator(allowed_extensions=["pdf"])],
    )
    original_filename = models.CharField(max_length=255)
    extracted_text = models.TextField(
        blank=True,
        default="",
        help_text="Plain text extracted from the PDF for agent context",
    )
    file_size = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return self.original_filename


class AgentRun(models.Model):
    """Records a single agent execution within the pipeline."""

    class Role(models.TextChoices):
        ORCHESTRATOR = "orchestrator", "Orchestrator"
        INTERNET_EXPLORER = "internet_explorer", "Internet Explorer"
        IDEA_GENERATOR = "idea_generator", "Idea Generator"
        ESTIMATOR = "estimator", "Estimator"
        EXECUTOR = "executor", "Executor"
        CRITIC = "critic", "Critic"
        OVERVIEWER = "overviewer", "Overviewer"
        EVALUATOR = "evaluator", "Evaluator"
        PROMPT_GENERATOR = "prompt_generator", "Prompt Generator"

    class RunStatus(models.TextChoices):
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    idea_request = models.ForeignKey(
        IdeaRequest, on_delete=models.CASCADE, related_name="agent_runs"
    )
    agent_name = models.CharField(max_length=100)
    role = models.CharField(max_length=50, choices=Role.choices)
    confidence = models.FloatField(null=True, blank=True)
    cycles = models.IntegerField(default=0)
    duration_ms = models.IntegerField(null=True, blank=True)
    input_tokens = models.IntegerField(null=True, blank=True)
    output_tokens = models.IntegerField(null=True, blank=True)
    total_tokens = models.IntegerField(null=True, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=RunStatus.choices, default=RunStatus.SUCCEEDED
    )
    error = models.TextField(null=True, blank=True)
    output_json = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ["started_at"]

    def __str__(self) -> str:
        return f"{self.agent_name} for {self.idea_request_id}"


class AgentMessage(models.Model):
    """Individual message within an agent run (for traceability)."""

    class Kind(models.TextChoices):
        SYSTEM = "SYSTEM", "System"
        USER = "USER", "User"
        ASSISTANT = "ASSISTANT", "Assistant"
        TOOL_RESULT = "TOOL_RESULT", "Tool Result"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent_run = models.ForeignKey(
        AgentRun, on_delete=models.CASCADE, related_name="messages"
    )
    sequence = models.IntegerField(default=0)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sequence"]

    def __str__(self) -> str:
        return f"{self.agent_run.agent_name} #{self.sequence} ({self.kind})"


class IdeaConclusion(models.Model):
    """Final conclusion saved from a completed idea request."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    idea_request = models.OneToOneField(
        IdeaRequest, on_delete=models.CASCADE, related_name="conclusion"
    )
    final_summary = models.TextField()
    result_json = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Conclusion for {self.idea_request.title}"


class Company(models.Model):
    """Company created when user accepts an idea and starts development."""

    class Status(models.TextChoices):
        INITIALIZING = "INITIALIZING", "Initializing"
        ACTIVE = "ACTIVE", "Active"
        REGENERATING_AGENTS = "REGENERATING_AGENTS", "Regenerating Agents"
        COMPLETED = "COMPLETED", "Completed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    idea_request = models.OneToOneField(
        IdeaRequest, on_delete=models.CASCADE, related_name="company"
    )
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="companies",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.INITIALIZING
    )
    autonomous_mode = models.BooleanField(
        default=True,
        help_text="When True, agents select plans, schedule, execute, and improve without user action",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Companies"

    def __str__(self) -> str:
        return f"{self.name} ({self.status})"


class CompanyAgent(models.Model):
    """Persistent agent in a company fleet - CPA, Director, Marketer, etc."""

    class Role(models.TextChoices):
        FOUNDER = "founder", "Founder (AI)"
        FOUNDER_ASSISTANT = "founder_assistant", "Founder Assistant (AI)"
        DIRECTOR = "director", "Director"
        PLANNER = "planner", "Planner"
        QA = "qa", "QA / Quality"
        CPA = "cpa", "CPA (Budget & Finance)"
        MARKETER = "marketer", "Marketer"
        DEVELOPER = "developer", "Developer"
        PRODUCT = "product", "Product Manager"
        OPERATIONS = "operations", "Operations"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="agents"
    )
    role = models.CharField(max_length=30, choices=Role.choices)
    name = models.CharField(max_length=100)
    system_prompt = models.TextField()
    config_json = models.TextField(blank=True, default="{}")
    priority = models.IntegerField(default=0, help_text="Higher = more priority (for directors)")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-priority", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_role_display()})"


class DirectorDiscussion(models.Model):
    """Discussion among directors that produces action proposals."""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        AWAITING_SELECTION = "AWAITING_SELECTION", "Awaiting Selection"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="discussions"
    )
    topic = models.CharField(max_length=255)
    status = models.CharField(
        max_length=30, choices=Status.choices, default=Status.ACTIVE
    )
    cancelled = models.BooleanField(
        default=False,
        help_text="When True, running discussion process will exit on next check",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.topic} ({self.status})"


class DiscussionMessage(models.Model):
    """Message in a director discussion (from agent or user)."""

    class SenderType(models.TextChoices):
        USER = "user", "User"
        AGENT = "agent", "Agent"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    discussion = models.ForeignKey(
        DirectorDiscussion, on_delete=models.CASCADE, related_name="messages"
    )
    sender_type = models.CharField(max_length=10, choices=SenderType.choices)
    sender_agent = models.ForeignKey(
        CompanyAgent, on_delete=models.SET_NULL, null=True, blank=True
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.sender_type} @ {self.created_at}"


class ActionProposal(models.Model):
    """Action proposed by a director for user to select."""

    class ActionStatus(models.TextChoices):
        PROPOSED = "PROPOSED", "Proposed"
        SELECTED = "SELECTED", "Selected"
        REJECTED = "REJECTED", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    discussion = models.ForeignKey(
        DirectorDiscussion, on_delete=models.CASCADE, related_name="actions"
    )
    proposed_by = models.ForeignKey(
        CompanyAgent, on_delete=models.SET_NULL, null=True, related_name="proposed_actions"
    )
    action_type = models.CharField(max_length=100)
    description = models.TextField()
    status = models.CharField(
        max_length=20, choices=ActionStatus.choices, default=ActionStatus.PROPOSED
    )
    rationale = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action_type} ({self.status})"


class UserAgentMessage(models.Model):
    """Chat message between user (owner) and a company agent."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="agent_messages"
    )
    agent = models.ForeignKey(
        CompanyAgent, on_delete=models.CASCADE, related_name="user_messages"
    )
    user_content = models.TextField()
    agent_response = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"User -> {self.agent.name} @ {self.created_at}"


class CompanyCalendarAction(models.Model):
    """Action scheduled or completed for a specific date in the company calendar."""

    class ActionStatus(models.TextChoices):
        PLANNED = "PLANNED", "Planned"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        DONE = "DONE", "Done"
        DEFERRED = "DEFERRED", "Deferred"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="calendar_actions"
    )
    action_proposal = models.ForeignKey(
        ActionProposal,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="calendar_entries",
    )
    action_date = models.DateField(db_index=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=ActionStatus.choices, default=ActionStatus.PLANNED
    )
    completion_notes = models.TextField(blank=True)
    google_event_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Google Calendar event ID when synced for the company owner.",
    )
    google_calendar_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["action_date", "title"]

    def __str__(self) -> str:
        return f"{self.title} ({self.action_date})"


class CompanyTeamMember(models.Model):
    """Human participant in company development (founders, assistants, QA, etc.)."""

    class Role(models.TextChoices):
        FOUNDER = "founder", "Founder"
        FOUNDER_ASSISTANT = "founder_assistant", "Founder Assistant"
        DIRECTOR = "director", "Director (Human)"
        PLANNER = "planner", "Planner"
        QA = "qa", "QA"
        ACCOUNTANT = "accountant", "Accountant"
        MARKETING = "marketing", "Marketing"
        OPERATIONS = "operations", "Operations"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="team_members"
    )
    name = models.CharField(max_length=120)
    email = models.EmailField(blank=True, default="")
    role = models.CharField(max_length=30, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["role", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_role_display()})"
