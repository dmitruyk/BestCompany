"""Pydantic output schemas for agent structured outputs."""
from pydantic import BaseModel, Field


class IdeaItem(BaseModel):
    """A single business idea variant."""

    name: str = Field(default="", description="Short name for the idea")
    description: str = Field(default="", description="Brief description")
    target_users: str = Field(default="", description="Who would use this")
    differentiation: str = Field(default="", description="What makes it unique")
    feasibility_score: float = Field(default=0.5, ge=0, le=1, description="0-1 feasibility")


class IdeaSetOutput(BaseModel):
    """Output from IdeaGeneratorAgent."""

    ideas: list[IdeaItem] = Field(default_factory=list, description="List of 5-10 business ideas")
    top_3_indices: list[int] = Field(
        description="Indices (0-based) of the top 3 ideas",
        min_length=3,
        max_length=3,
    )
    target_users_summary: str = Field(default="", description="Overall target user segment")
    differentiation_summary: str = Field(default="", description="Key differentiators")
    confidence: float = Field(default=0.5, ge=0, le=1, description="Confidence 0-1")


class EstimateAssumptions(BaseModel):
    """Explicit assumptions in the estimate."""

    assumption: str = Field(default="", description="The assumption made")
    confidence: str = Field(default="medium", description="high/medium/low/unknown")


class EstimateOutput(BaseModel):
    """Output from EstimatorAgent."""

    cost_range_min_usd: float = Field(default=0, ge=0)
    cost_range_max_usd: float = Field(default=0, ge=0)
    timeline_weeks: int = Field(default=0, ge=0)
    risks: list[str] = Field(default_factory=list, description="Key risks")
    assumptions: list[EstimateAssumptions] = Field(
        default_factory=list, description="Assumptions made"
    )
    mvp_plan_summary: str = Field(default="", description="Brief MVP plan")
    kpis: list[str] = Field(default_factory=list, description="Key performance indicators")
    confidence: float = Field(default=0.5, ge=0, le=1)


class CritiqueOutput(BaseModel):
    """Output from CriticAgent."""

    weak_points: list[str] = Field(default_factory=list, description="Identified weak points")
    failure_modes: list[str] = Field(default_factory=list, description="Potential failure modes")
    missing_assumptions: list[str] = Field(default_factory=list, description="What might be missing")
    legal_ops_risks: list[str] = Field(default_factory=list, description="Legal/operational risks")
    improvements: list[str] = Field(default_factory=list, description="Proposed improvements")
    alternative_hypotheses: list[str] = Field(
        default_factory=list, description="Alternative approaches"
    )
    confidence: float = Field(default=0.5, ge=0, le=1)


class ExecutorOutput(BaseModel):
    """Output from ExecutorAgent."""

    mvp_backlog: list[str] = Field(default_factory=list, description="MVP backlog items")
    milestones: list[str] = Field(default_factory=list, description="Key milestones")
    stack_suggestions: list[str] = Field(
        default_factory=list, description="Suggested tech stack"
    )
    gtm_steps: list[str] = Field(default_factory=list, description="Go-to-market steps")
    next_steps_immediate: list[str] = Field(
        default_factory=list, description="Immediate next steps"
    )
    confidence: float = Field(default=0.5, ge=0, le=1)


class InternetExplorerOutput(BaseModel):
    """Output from InternetExplorerAgent."""

    sources_checked: list[str] = Field(
        default_factory=list, description="URLs or sources consulted"
    )
    market_insights: str = Field(default="", description="Market-related findings")
    competitor_notes: str = Field(default="", description="Competitor observations")
    pricing_trends: str = Field(default="", description="Pricing/trend observations")
    search_available: bool = Field(default=True, description="Whether web search was available")
    confidence: float = Field(default=0.0, ge=0, le=1)


class OverviewOutput(BaseModel):
    """Output from OverviewerAgent."""

    executive_summary: str = Field(default="", description="Decision-ready summary")
    go_no_go: str = Field(default="", description="GO or NO-GO recommendation")
    key_metrics: list[str] = Field(default_factory=list, description="Key metrics to track")
    confidence: float = Field(default=0.5, ge=0, le=1)


class EvaluatorOutput(BaseModel):
    """Output from EvaluatorAgent - quality assessment of another agent's response."""

    score: float = Field(default=0.5, ge=0, le=1, description="Quality score 0-1")
    is_acceptable: bool = Field(default=True, description="Whether the response meets quality bar")
    feedback: str = Field(default="", description="Brief feedback on quality")
    improvement_suggestions: list[str] = Field(
        default_factory=list, description="Specific suggestions for improvement"
    )


class SearchQueriesOutput(BaseModel):
    """Output for extracting web search queries from a business idea (Ollama workaround)."""

    queries: list[str] = Field(
        default_factory=list,
        min_length=2,
        max_length=5,
        description="2-5 specific web search queries for market/competitor/pricing research",
    )


class PromptGeneratorOutput(BaseModel):
    """Output from PromptGeneratorAgent - improved prompt for retry."""

    improved_instructions: str = Field(
        default="",
        description="Instructions to append to the user prompt for a retry",
    )
    changes_summary: str = Field(
        default="", description="Brief summary of what was changed"
    )


class FleetAgentDefinition(BaseModel):
    """Single agent definition for company fleet generation."""

    role: str = Field(
        description=(
            "One of: founder, founder_assistant, cpa, director, planner, qa, "
            "marketer, developer, product, operations"
        )
    )
    name: str = Field(description="Display name for the agent")
    system_prompt: str = Field(description="System prompt defining agent behavior")
    priority: int = Field(default=0, description="Higher = more priority (for directors)")
    config: dict = Field(default_factory=dict, description="Optional config JSON")


class FleetGenerationOutput(BaseModel):
    """Output from fleet generator - list of agents to create."""

    company_name: str = Field(description="Suggested company name")
    agents: list[FleetAgentDefinition] = Field(
        description="List of agents to create for the company"
    )


class ChatResponse(BaseModel):
    """Simple response for agent chat - single text field."""

    response: str = Field(
        default="",
        description="The agent's response to the user's question or suggestion",
    )


class ProposedAction(BaseModel):
    """Single action proposed by a director."""

    action_type: str = Field(description="Short action type/category")
    description: str = Field(description="Detailed description of the action")
    rationale: str = Field(default="", description="Why this action is recommended")


class DirectorDiscussionOutput(BaseModel):
    """Output from director during discussion - message and proposed actions."""

    message: str = Field(default="", description="Director's discussion contribution")
    proposed_actions: list[ProposedAction] = Field(
        default_factory=list,
        description="1-2 concrete actions the director proposes",
    )


class ActionSelectionOutput(BaseModel):
    """Output from selector agent - which proposed actions to accept."""

    selected_action_ids: list[int] = Field(
        default_factory=list,
        description="1-based indices of actions to select (best first); max 2",
        max_length=2,
    )
    rationale: str = Field(default="", description="Why these actions were selected")


class ScheduleProposalOutput(BaseModel):
    """Output from scheduler agent - when to place action on calendar."""

    action_date: str = Field(
        description="Date in YYYY-MM-DD format for this action",
    )
    rationale: str = Field(default="", description="Why this date was chosen")


class CompanyTaskExecutionOutput(BaseModel):
    """Output when an assigned agent completes a company planning task."""

    result_summary: str = Field(
        description="Concise outcome for next planning (1-3 sentences)",
    )
    result_notes: str = Field(
        default="",
        description="Optional detail: links, metrics, follow-ups",
    )
    progress_percent: int = Field(
        default=100,
        ge=0,
        le=100,
        description="Estimated completion 0-100",
    )
    outcome_assessment: str = Field(
        default="success",
        description="success, partial, or blocked",
    )
    needs_human: bool = Field(
        default=False,
        description="True if a human must take over (escalate task)",
    )


class ExecutionOutput(BaseModel):
    """Output from executor agent - completion of a calendar action."""

    completion_notes: str = Field(
        description="What was accomplished, outcomes, blockers if any",
    )
    outcome_assessment: str = Field(
        default="",
        description="Brief assessment: success, partial, needs_follow_up",
    )
    follow_up_suggested: bool = Field(
        default=False,
        description="Whether to spawn improvement discussion",
    )


class ScheduleTaskMove(BaseModel):
    """One task due-date change from schedule optimization."""

    task_index: int = Field(
        ge=1,
        description="1-based index of the task in the schedulable list provided to the optimizer",
    )
    new_target_date: str = Field(
        description="New due date in YYYY-MM-DD format",
    )
    reason: str = Field(
        default="",
        description="Brief reason for this move (gap closure, dependency, assignee rules)",
    )


class ScheduleOptimizationOutput(BaseModel):
    """Output from schedule optimizer — redistribute task due dates."""

    summary: str = Field(
        default="",
        description="Overall assessment of gaps and what was improved",
    )
    moves: list[ScheduleTaskMove] = Field(
        default_factory=list,
        description="New due dates for tasks that should move",
    )


class ResultCheckOutput(BaseModel):
    """Output from checker agent - evaluation of completed action."""

    quality_score: float = Field(default=0.5, ge=0, le=1, description="0-1 quality")
    needs_improvement: bool = Field(
        default=False,
        description="Whether to spawn improvement discussion",
    )
    improvement_topic: str = Field(
        default="",
        description="Topic for follow-up discussion if needs_improvement",
    )
    summary: str = Field(default="", description="Brief evaluation summary")


class PlannedTaskItem(BaseModel):
    """Single task proposed during a planning session."""

    title: str = Field(description="Short task title")
    description: str = Field(default="", description="What to accomplish")
    suggested_role: str = Field(
        default="planner",
        description=(
            "Agent role to assign: founder, director, planner, qa, cpa, "
            "marketer, developer, product, operations; or 'human' for team"
        ),
    )
    depends_on_indices: list[int] = Field(
        default_factory=list,
        description="0-based indices of other tasks in this plan that must finish first",
    )
    target_days_offset: int = Field(
        default=7,
        ge=0,
        le=90,
        description="Days from week start to target completion",
    )


class PlanningSessionOutput(BaseModel):
    """Output from planner agent for a planning session."""

    session_summary: str = Field(
        default="",
        description="High-level summary for directors and managers",
    )
    progress_assessment: str = Field(
        default="",
        description="Where the company is vs strategic direction and milestones",
    )
    tasks: list[PlannedTaskItem] = Field(
        default_factory=list,
        description="3–12 concrete tasks for the week",
        min_length=1,
        max_length=15,
    )
