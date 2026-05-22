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

    def try_complete_selection(self) -> bool:
        """Mark COMPLETED when owner (or agent) resolved every proposed action."""
        if self.status != self.Status.AWAITING_SELECTION:
            return False
        if self.actions.filter(status=ActionProposal.ActionStatus.PROPOSED).exists():
            return False
        self.status = self.Status.COMPLETED
        self.save(update_fields=["status", "updated_at"])
        return True


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
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="team_memberships",
        help_text="Login account linked to this human; grants company access and task assignment.",
    )
    name = models.CharField(max_length=120)
    email = models.EmailField(blank=True, default="")
    role = models.CharField(max_length=30, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["role", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "user"],
                condition=models.Q(user__isnull=False),
                name="unique_company_user_team_member",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_role_display()})"


class CompanyStrategicDirection(models.Model):
    """Company development direction — agreed or verified with founders."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="strategic_directions"
    )
    statement = models.TextField(
        help_text="Where the company is heading; used in weekly planning.",
    )
    founder_verified = models.BooleanField(
        default=False,
        help_text="True when founders have agreed or clarified this direction.",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_directions",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Only one direction should be active per company.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        preview = (self.statement[:60] + "…") if len(self.statement) > 60 else self.statement
        return f"{preview} ({'verified' if self.founder_verified else 'draft'})"


class PlanningSession(models.Model):
    """Weekly (Monday) or on-demand planning that produces a task scope."""

    class Trigger(models.TextChoices):
        WEEKLY = "weekly", "Weekly (Monday)"
        MANUAL = "manual", "User Request"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="planning_sessions"
    )
    trigger = models.CharField(max_length=20, choices=Trigger.choices)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    week_start = models.DateField(
        null=True,
        blank=True,
        help_text="Monday of the planning week, when applicable.",
    )
    summary = models.TextField(
        blank=True,
        default="",
        help_text="Outcome summary for directors/managers.",
    )
    context_snapshot = models.TextField(
        blank=True,
        default="",
        help_text="High-level context fed into planning (task results, direction).",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="planning_sessions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Planning {self.week_start or self.created_at.date()} ({self.get_status_display()})"


class CompanyTask(models.Model):
    """Assignable work item from planning — agent or human."""

    class Status(models.TextChoices):
        TODO = "TODO", "To Do"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        BLOCKED = "BLOCKED", "Blocked"
        DONE = "DONE", "Done"
        CANCELLED = "CANCELLED", "Cancelled"

    class AssigneeType(models.TextChoices):
        UNASSIGNED = "unassigned", "Unassigned"
        AGENT = "agent", "AI Agent"
        HUMAN = "human", "Human"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="tasks"
    )
    planning_session = models.ForeignKey(
        PlanningSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.TODO
    )
    progress_percent = models.PositiveSmallIntegerField(
        default=0,
        help_text="0–100 completion estimate.",
    )
    assignee_type = models.CharField(
        max_length=20,
        choices=AssigneeType.choices,
        default=AssigneeType.UNASSIGNED,
    )
    assigned_agent = models.ForeignKey(
        CompanyAgent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tasks",
    )
    assigned_human = models.ForeignKey(
        CompanyTeamMember,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tasks",
    )
    escalated_to_human = models.BooleanField(
        default=False,
        help_text="Agent could not complete; reassigned or needs human.",
    )
    target_date = models.DateField(null=True, blank=True)
    google_event_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Google Calendar event ID when synced for the company owner.",
    )
    google_calendar_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last successful sync to Google Calendar.",
    )
    calendar_action = models.ForeignKey(
        CompanyCalendarAction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="linked_tasks",
    )
    result_summary = models.TextField(
        blank=True,
        default="",
        help_text="Outcome when done; feeds next planning context.",
    )
    result_notes = models.TextField(
        blank=True,
        default="",
        help_text="Attachments, links, or extra detail for the result.",
    )
    sort_order = models.PositiveIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self) -> str:
        return f"{self.title} ({self.get_status_display()})"

    @property
    def is_blocked_by_dependencies(self) -> bool:
        """True if any prerequisite task is not done."""
        deps = self.dependencies.select_related("depends_on").all()
        return any(
            d.depends_on.status not in (self.Status.DONE, self.Status.CANCELLED)
            for d in deps
        )


class CompanyTaskDependency(models.Model):
    """Task B depends on task A (A must complete before B can proceed)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(
        CompanyTask,
        on_delete=models.CASCADE,
        related_name="dependencies",
    )
    depends_on = models.ForeignKey(
        CompanyTask,
        on_delete=models.CASCADE,
        related_name="dependents",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["task", "depends_on"],
                name="unique_task_dependency",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.task.title} depends on {self.depends_on.title}"


class CompanyHistoryEntry(models.Model):
    """Compact audit trail for company actions and task lifecycle."""

    class EntryType(models.TextChoices):
        DIRECTION_CREATED = "direction_created", "Direction Set"
        DIRECTION_VERIFIED = "direction_verified", "Direction Verified"
        PLANNING_STARTED = "planning_started", "Planning Started"
        PLANNING_COMPLETED = "planning_completed", "Planning Completed"
        TASK_CREATED = "task_created", "Task Created"
        TASK_UPDATED = "task_updated", "Task Updated"
        TASK_COMPLETED = "task_completed", "Task Completed"
        TASK_ESCALATED = "task_escalated", "Task Escalated to Human"
        CALENDAR_LINKED = "calendar_linked", "Calendar Linked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="history_entries"
    )
    entry_type = models.CharField(max_length=30, choices=EntryType.choices)
    title = models.CharField(max_length=255)
    summary = models.TextField(blank=True, default="")
    related_task = models.ForeignKey(
        CompanyTask,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="history_entries",
    )
    related_planning_session = models.ForeignKey(
        PlanningSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="history_entries",
    )
    metadata_json = models.TextField(blank=True, default="{}")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Company history entries"

    def __str__(self) -> str:
        return f"{self.get_entry_type_display()}: {self.title}"
