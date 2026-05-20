"""Forms for core app."""
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from apps.core.models import ServiceLLMConfig

User = get_user_model()


class AppLoginForm(AuthenticationForm):
    """Login form for the main Idea Factory UI."""

    username = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "class": "w-full rounded-lg border-slate-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500",
                "autocomplete": "username",
            }
        )
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "w-full rounded-lg border-slate-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500",
                "autocomplete": "current-password",
            }
        )
    )


class ForcePasswordChangeForm(forms.Form):
    """Require a new password on first login (or when flagged by admin)."""

    new_password1 = forms.CharField(
        label="New password",
        widget=forms.PasswordInput(
            attrs={
                "class": "w-full rounded-lg border-slate-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500",
                "autocomplete": "new-password",
            }
        ),
    )
    new_password2 = forms.CharField(
        label="Confirm new password",
        widget=forms.PasswordInput(
            attrs={
                "class": "w-full rounded-lg border-slate-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500",
                "autocomplete": "new-password",
            }
        ),
    )

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("new_password1")
        p2 = cleaned.get("new_password2")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Passwords do not match.")
        if p1:
            from django.contrib.auth.password_validation import validate_password

            validate_password(p1)
        return cleaned


class AdminHumanUserCreationForm(UserCreationForm):
    """Admin form: create a human user who must change password on first login."""

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "first_name", "last_name")

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            profile = user.profile
            profile.must_change_password = True
            profile.save(update_fields=["must_change_password", "updated_at"])
        return user


class ServiceLLMConfigForm(forms.ModelForm):
    """Edit service-wide LLM provider (OpenAI ↔ Ollama)."""

    class Meta:
        model = ServiceLLMConfig
        fields = (
            "default_provider",
            "ollama_host",
            "ollama_model_id",
            "openai_model_id",
        )
        widgets = {
            "default_provider": forms.Select(
                attrs={
                    "class": "w-full rounded-lg border-slate-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
                }
            ),
            "ollama_host": forms.URLInput(
                attrs={
                    "class": "w-full rounded-lg border-slate-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500",
                    "placeholder": "http://localhost:11434",
                }
            ),
            "ollama_model_id": forms.TextInput(
                attrs={
                    "class": "w-full rounded-lg border-slate-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500",
                    "placeholder": "gpt-oss:20b",
                }
            ),
            "openai_model_id": forms.TextInput(
                attrs={
                    "class": "w-full rounded-lg border-slate-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500",
                    "placeholder": "gpt-4o-mini",
                }
            ),
        }
