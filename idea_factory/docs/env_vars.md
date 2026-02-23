# Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `ollama` | `ollama` or `openai` |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL_ID` | `gpt-oss:20b` | Tool-capable Ollama model (qwen3, gpt-oss, mistral-small3.2, etc.) |
| `OPENAI_API_KEY` | (required if openai) | OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model ID |
| `DJANGO_SECRET_KEY` | (dev default) | Django secret |
| `DJANGO_DEBUG` | `true` | Set `false` in production |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated hosts |
| `IDEA_FACTORY_LOG_FILE` | `idea_factory/logs/idea_factory.log` | Path to log file |
| `IDEA_FACTORY_LOG_LEVEL` | `INFO` | Log level (DEBUG, INFO, WARNING, ERROR) |

Copy `.env.example` to `.env` and load with `python-dotenv` or your preferred method.
