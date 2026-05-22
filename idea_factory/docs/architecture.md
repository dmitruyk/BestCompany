# Idea Factory - Architecture

## Overview

Idea Factory is a Django web app that runs a multi-agent pipeline using [Strands Agents](https://strandsagents.com/latest/) to generate and validate business ideas.

## Repository Structure

```
idea_factory/
├── idea_factory/          # Django project
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── apps/
│   ├── core/              # Shared utilities
│   ├── ideas/             # IdeaRequest, AgentRun, AgentMessage, IdeaConclusion
│   ├── agents/            # Strands integration, agent definitions, orchestration
│   └── web/               # Templates, views, URLs
├── docs/
├── scripts/
└── manage.py
```

## Data Model

- **IdeaRequest**: User's initial request (title, prompt, status, provider)
- **AgentRun**: Per-agent execution record (agent_name, role, confidence, cycles, duration_ms, output_json)
- **AgentMessage**: Per-message trace (for future traceability)
- **IdeaConclusion**: Saved final summary + result JSON

## Agent Pipeline

Primary agents run in sequence. After each (except Overviewer), **EvaluatorAgent** assesses quality.

1. **InternetExplorerAgent**: Fetches URLs, web search (if ddgs/duckduckgo_search installed)
2. **EvaluatorAgent**: Scores output, sets is_acceptable. If bad → **PromptGeneratorAgent** → retry (max 2x)
3. **IdeaGeneratorAgent**: Generates 5–10 ideas, selects top 3
4. **EvaluatorAgent** → retry if needed
5. **EstimatorAgent**: Cost, timeline, risks, KPIs
6. **EvaluatorAgent** → retry if needed
7. **CriticAgent**: Weak points, failure modes, improvements
8. **EvaluatorAgent** → retry if needed
9. **ExecutorAgent**: MVP backlog, milestones, GTM steps
10. **EvaluatorAgent** → retry if needed
11. **OverviewerAgent**: Executive summary, go/no-go, confidence
12. **Orchestrator** (code): Composes final IdeaConclusion

**PromptGeneratorAgent**: When Evaluator rejects, produces improved_instructions for retry.

## Autonomous Company Loop

When a company has `autonomous_mode=True` (default), the system runs without user action:

1. **Plans**: Directors discuss and propose actions (Agent pipeline).
2. **Selection**: Selector agent picks best 1–2 actions from proposals.
3. **Scheduling**: Scheduler agent assigns actions to calendar dates.
4. **Execution**: On due date, executor agent completes actions (notes, marks DONE).
5. **Improvement**: Checker agent evaluates completed actions; spawns improvement discussion if needed.
6. **Cycle**: When idle, auto-starts "Next steps" discussion; loop repeats.

Run the autonomous loop via cron:
```bash
0 9 * * * cd /path/to/idea_factory && python manage.py run_autonomous_loop
```

Toggle autonomous mode per company from the company detail page (🤖 Self-Run / 👤 Manual).

## Weekly Planning & Tasks

Companies use structured planning separate from the calendar:

1. **Strategic direction** (`CompanyStrategicDirection`): Where the company is heading; mark founder-verified after agreement.
2. **Planning sessions** (`PlanningSession`): Weekly (Monday) via `run_weekly_planning` or on-demand from the UI. The planner agent reads **high-level context** only (`build_strategic_planning_context`) — direction, milestone summaries, completed task outcomes, open work one-liners.
3. **Tasks** (`CompanyTask`): Scope from planning with assignee (AI agent or human), status, progress %, dependencies (`CompanyTaskDependency`), and **results** (`result_summary`, `result_notes`) for the next session.
4. **History** (`CompanyHistoryEntry`): Compact timeline of direction, planning, and task events.
5. **Progress**: `compute_progress_metrics` on the company detail and task board (completion % and weighted progress).

**Docker ticker** (`idea-factory-ticker` in `docker-compose.yml`) runs `run_company_ticker --loop` each `TICKER_INTERVAL_SECONDS` (default 1h):

1. Activity checks (overdue tasks, stale planning sessions)
2. `run_autonomous_loop` for Self-Run companies
3. **Automatic task execution** (`run_company_task_execution`): for each ACTIVE company, up to `TICKER_TASK_MAX_PER_COMPANY` agent-assigned `TODO` tasks that are not blocked by dependencies. On start, `target_date` is set to today (manual **Run agent tasks now** uses the same rule). Sets `IN_PROGRESS`, runs the assigned agent’s LLM, then `DONE` (with `result_summary`) or escalates to human if `needs_human`.
4. `run_weekly_planning` on Mondays after `TICKER_WEEKLY_PLANNING_HOUR`

**Manual task run:** Tasks board → **Run agent tasks now**, or `python manage.py run_company_tasks <company_uuid>` (up to 10 tasks per run).

Host cron alternative: `scripts/run_company_ticker.sh` or `make ticker-once`.

UI routes: `/companies/<id>/planning/`, `/tasks/`, `/direction/`, `/history/`.

## Confidence Scoring

- Base: from model's structured output
- +0.05 if internet exploration found sources
- -0.1 if 3+ assumptions marked "unknown"
- -0.1 if agent hit max cycles
- Clamped to 0..1

## LLM Provider Abstraction

`apps/agents/providers.py`:
- `LLM_PROVIDER=ollama` (default): Uses OLLAMA_HOST, OLLAMA_MODEL_ID
- `LLM_PROVIDER=openai`: Uses OPENAI_API_KEY, OPENAI_MODEL

Provider can be overridden per request via the form dropdown.
