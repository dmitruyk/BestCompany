from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_google_calendar_disconnect_portal"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicellmconfig",
            name="assistant_provider",
            field=models.CharField(
                blank=True,
                choices=[("ollama", "Ollama (local)"), ("openai", "OpenAI")],
                default="",
                help_text="LLM for the company Assistant tab. Empty = use default provider above.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="servicellmconfig",
            name="assistant_ollama_model_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Ollama model for Assistant when assistant provider is Ollama (or inherited default is Ollama). Empty = use Ollama model above.",
                max_length=100,
            ),
        ),
        migrations.AddField(
            model_name="servicellmconfig",
            name="assistant_openai_model_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="OpenAI model for Assistant when assistant provider is OpenAI (or inherited default is OpenAI). Empty = use OpenAI model above.",
                max_length=100,
            ),
        ),
    ]
