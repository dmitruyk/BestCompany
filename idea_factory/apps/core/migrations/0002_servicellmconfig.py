# Service-wide LLM configuration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_userprofile"),
    ]

    operations = [
        migrations.CreateModel(
            name="ServiceLLMConfig",
            fields=[
                (
                    "id",
                    models.PositiveSmallIntegerField(
                        default=1, editable=False, primary_key=True, serialize=False
                    ),
                ),
                (
                    "default_provider",
                    models.CharField(
                        choices=[
                            ("ollama", "Ollama (local)"),
                            ("openai", "OpenAI"),
                        ],
                        default="ollama",
                        max_length=20,
                    ),
                ),
                (
                    "ollama_host",
                    models.CharField(default="http://localhost:11434", max_length=255),
                ),
                (
                    "ollama_model_id",
                    models.CharField(
                        default="gpt-oss:20b",
                        help_text="Tool-capable Ollama model",
                        max_length=100,
                    ),
                ),
                (
                    "openai_model_id",
                    models.CharField(default="gpt-4o-mini", max_length=100),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "LLM service configuration",
                "verbose_name_plural": "LLM service configuration",
            },
        ),
    ]
