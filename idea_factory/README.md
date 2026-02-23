# Idea Factory

A **Business Idea Factory** web app that takes a user's initial request, runs a multi-agent pipeline using [Strands Agents](https://strandsagents.com/latest/), and shows results in a UI with full traceability.

## Features

- Multi-agent pipeline: Internet Explorer → Idea Generator → Estimator → Critic → Executor → Overviewer
- Structured outputs via Pydantic (confidence, cycles, token usage)
- LLM providers: Ollama (local) or OpenAI, switchable via env vars
- Full traceability: agent outputs, confidence, cycles, duration, tool usage
- Export as JSON, save as conclusion

## Quick Start

```bash
# Install (Python 3.10+ required)
pip install -r requirements.txt
# or: uv sync

# Migrate
python manage.py migrate

# Create admin user (for login)
python manage.py createsuperuser

# Run
python manage.py runserver
```

Open http://127.0.0.1:8000/ and log in via admin.

## Environment

See [.env.example](.env.example) and [docs/env_vars.md](docs/env_vars.md).

- `LLM_PROVIDER`: `ollama` (default) or `openai`
- Ollama: `OLLAMA_HOST`, `OLLAMA_MODEL_ID`
- OpenAI: `OPENAI_API_KEY`, `OPENAI_MODEL`

## Documentation

- [docs/quickstart.md](docs/quickstart.md)
- [docs/architecture.md](docs/architecture.md)

## Tests

```bash
pip install pytest pytest-django
pytest
```
