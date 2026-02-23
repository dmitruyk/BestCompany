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
