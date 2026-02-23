# Idea Factory - Quickstart

## Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai/) (for local LLM) or OpenAI API key

## Installation

### Using pip

```bash
cd idea_factory
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Using uv

```bash
cd idea_factory
uv sync
```

## Database Setup

```bash
python manage.py migrate
```

## Run the Server

**Run from the idea_factory directory** so the database path resolves correctly:

```bash
cd idea_factory
python manage.py runserver
```

Open http://127.0.0.1:8000/

## First-Time Setup

1. Create an admin user for login:
   ```bash
   python manage.py createsuperuser
   ```
2. Log in at http://127.0.0.1:8000/admin/
3. Navigate to http://127.0.0.1:8000/ (home)

## Using Ollama (Local)

1. Install Ollama: https://ollama.ai/
2. Pull a tool-capable model: `ollama pull gpt-oss:20b` or `ollama pull qwen3` (see https://ollama.com/search?c=tools; llama3 does NOT support tools)
3. Start Ollama: `ollama serve` (or it may run automatically)
4. Set env (optional): `LLM_PROVIDER=ollama OLLAMA_HOST=http://localhost:11434`

## Using OpenAI

1. Set environment variables:
   ```bash
   export LLM_PROVIDER=openai
   export OPENAI_API_KEY=sk-your-key
   ```
2. Or use the provider dropdown in the "New Request" form (overrides current env for that run).

## Architecture

See [docs/architecture.md](architecture.md).
