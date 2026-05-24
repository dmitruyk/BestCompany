"""Custom template tags for web app."""
from __future__ import annotations

from django import template

from apps.core.assistant_markdown import render_assistant_markdown

register = template.Library()

# Example prompts shown on agent chat to guide the owner.
AGENT_CHAT_EXAMPLES: dict[str, list[str]] = {
    "cpa": [
        "What is our estimated burn rate and runway for the next 6 months?",
        "Which budget line items should we cut or defer first?",
        "Summarize financial risks from the current development plan.",
    ],
    "director": [
        "What are the top three strategic priorities for this quarter?",
        "What go/no-go criteria should we use before scaling?",
        "Which director-level risks are not yet covered by an action?",
    ],
    "marketer": [
        "Draft a one-paragraph positioning statement for our target customer.",
        "What channels should we test first with a limited budget?",
        "What messaging should we A/B test in the next launch?",
    ],
    "developer": [
        "What is the critical path for an MVP in the next 4 weeks?",
        "Which technical debts block launch and how should we sequence fixes?",
        "What should we automate first in CI/CD?",
    ],
    "product": [
        "What is the smallest viable feature set for a first release?",
        "Which user jobs are underserved by competitors?",
        "What metrics should define product-market fit for us?",
    ],
    "planner": [
        "Break the next milestone into weekly deliverables with owners.",
        "What dependencies could delay the roadmap?",
        "Suggest a 30/60/90-day plan from our current readiness score.",
    ],
    "qa": [
        "What should be in our release checklist before going live?",
        "Which flows need regression tests first?",
        "What quality risks should block launch?",
    ],
    "operations": [
        "What operational processes should we document before scale?",
        "Which vendor or tooling gaps create the most downtime risk?",
        "What weekly ops cadence do you recommend?",
    ],
    "founder": [
        "What should I decide this week as owner and main investor?",
        "Where are we off-track versus the original idea?",
        "What is the single highest-leverage action right now?",
    ],
    "founder_assistant": [
        "Summarize status across agents and open discussions.",
        "What needs my approval today?",
        "Draft a short investor update from current company state.",
    ],
}

AGENT_CHAT_EXAMPLES_DEFAULT = [
    "What should we prioritize this week?",
    "Summarize current status, risks, and recommended next steps.",
    "What open items need my decision as owner?",
]

COMPANY_STEPS_MANUAL = [
    "Open the Assistant tab for a read-only summary of company state, plans, and recommendations (with links to tasks and pages).",
    "Chat with an agent (CPA, Product, Marketer, etc.) using Ask — ask about status, risks, or priorities.",
    "Ask multiple agents together (e.g. CPA + Product Manager) to debate a question and get a combined recommendation.",
    "Start a director discussion (e.g. “Next steps”, “Launch plan”) and wait for action proposals.",
    "Select actions you agree with, then click Schedule selected to add them to the calendar.",
    "Open Calendar to mark items in progress or done and add completion notes.",
]

COMPANY_ASSISTANT_EXAMPLES = [
    "Do I have any tasks assigned to me?",
    "Fix the development plan readiness failure",
    "What is going on in this company right now?",
    "Summarize open tasks, blockers, and what needs my attention.",
    "What did the last planning session decide and what is still open?",
    "Explain director recommendations and which actions are awaiting my decision.",
    "What is on the calendar this week and what is overdue?",
]

COMPANY_STEPS_AUTONOMOUS = [
    "Agents may auto-select and schedule actions — review the calendar regularly.",
    "Start discussions or chat with agents anytime to steer strategy.",
    "Toggle to Manual mode if you want to approve every action yourself.",
    "Use Regenerate Agents only when the fleet should reflect a major company change.",
]

NEW_IDEA_EXAMPLES = [
    "B2B SaaS for independent bakeries: inventory, online orders, and delivery routing under $200/mo.",
    "Mobile app for pet owners in urban areas: vet booking, reminders, and insurance comparison.",
    "Internal tool for a 50-person sales team: lead scoring from CRM data with GDPR constraints in EU.",
]

DISCUSSION_TOPIC_EXAMPLES = [
    "Next steps for the next 30 days",
    "Marketing launch plan and budget",
    "Budget review and runway",
    "Product MVP scope and timeline",
    "Hiring and team structure",
]

AGENT_PANEL_QUESTION_EXAMPLES = [
    "Should we launch a freemium tier before paid marketing spend?",
    "What is the minimum viable feature set for our first release?",
    "How should we allocate budget between development and marketing this quarter?",
    "Which risks should block launch vs. which can we accept?",
    "What pricing model fits our target customer and runway?",
]


@register.filter
def get_item(d, key):
    """Get item from dict by key. Returns [] if key not found."""
    if d is None:
        return []
    return d.get(key, [])


@register.filter
def date_lt(d, other):
    """Return True if d < other (for date comparison)."""
    if d is None or other is None:
        return False
    return d < other


@register.filter
def date_gte(d, other):
    """Return True if d >= other (for date comparison)."""
    if d is None or other is None:
        return False
    return d >= other


@register.filter
def date_eq(d, other):
    """Return True if d == other (for date comparison)."""
    if d is None or other is None:
        return False
    return d == other


@register.inclusion_tag("web/includes/guide_hint.html")
def guide_hint(
    title="",
    body="",
    steps=None,
    examples=None,
    examples_label="",
    fill_input_id="",
):
    """Render a guidance box with optional steps and example prompts."""
    return {
        "title": title,
        "body": body,
        "steps": steps or [],
        "examples": examples or [],
        "examples_label": examples_label,
        "fill_input_id": fill_input_id,
    }


@register.simple_tag
def agent_chat_examples(agent):
    """Return role-specific example questions for agent chat."""
    role = getattr(agent, "role", "") or ""
    return AGENT_CHAT_EXAMPLES.get(role, AGENT_CHAT_EXAMPLES_DEFAULT)


@register.simple_tag
def discussion_topic_examples():
    """Return example director discussion topics."""
    return DISCUSSION_TOPIC_EXAMPLES


@register.simple_tag
def agent_panel_question_examples():
    """Return example questions for multi-agent panel discussions."""
    return AGENT_PANEL_QUESTION_EXAMPLES


@register.simple_tag
def new_idea_examples():
    """Return example idea request prompts."""
    return NEW_IDEA_EXAMPLES


@register.simple_tag
def company_steps_manual():
    return COMPANY_STEPS_MANUAL


@register.simple_tag
def company_steps_autonomous():
    return COMPANY_STEPS_AUTONOMOUS


@register.simple_tag
def company_assistant_examples():
    return COMPANY_ASSISTANT_EXAMPLES


@register.filter
def assistant_response_html(text: str) -> str:
    """Render assistant markdown (links, lists, bold) as safe HTML."""
    return render_assistant_markdown(text)
