"""Forms for core app."""
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from apps.core.llm_choices import OLLAMA_MODELS, OPENAI_MODELS
from apps.core.models import ServiceLLMConfig, UserProfile
from apps.ideas.models import CompanyTeamMember

User = get_user_model()

_TEAM_MEMBER_WIDGET = forms.CheckboxSelectMultiple(
    attrs={"class": "space-y-2 text-sm text-slate-700"}
)


def unlinked_team_members_queryset():
    return (
        CompanyTeamMember.objects.filter(is_active=True, user__isnull=True)
        .select_related("company")
        .order_by("company__name", "name")
    )


def link_team_members_to_user(user: User, members) -> None:
    """Attach team member records to a user; clears previous links for those rows."""
    if not members:
        return
    for member in members:
        if member.user_id and member.user_id != user.pk:
            raise ValueError(
                f"Team member {member.name} is already linked to another user."
            )
    CompanyTeamMember.objects.filter(pk__in=[m.pk for m in members]).update(user=user)


def sync_user_team_members(user: User, selected_members) -> None:
    """Set user's team memberships to exactly the selected active members."""
    selected_ids = {m.pk for m in selected_members}
    CompanyTeamMember.objects.filter(user=user).exclude(pk__in=selected_ids).update(
        user=None
    )
    if selected_ids:
        CompanyTeamMember.objects.filter(pk__in=selected_ids).update(user=user)

_INPUT_CLASS = (
    "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 "
    "shadow-sm focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500"
)
_CHECKBOX_CLASS = (
    "h-4 w-4 rounded border border-slate-300 text-indigo-600 "
    "focus:ring-2 focus:ring-indigo-500"
)


class AppLoginForm(AuthenticationForm):
    """Login form for the main Idea Factory UI."""

    username = forms.CharField(
        widget=forms.TextInput(
            attrs={"class": _INPUT_CLASS, "autocomplete": "username"}
        )
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={"class": _INPUT_CLASS, "autocomplete": "current-password"}
        )
    )


class ForcePasswordChangeForm(forms.Form):
    """Require a new password on first login (or when flagged by admin)."""

    new_password1 = forms.CharField(
        label="New password",
        widget=forms.PasswordInput(
            attrs={"class": _INPUT_CLASS, "autocomplete": "new-password"}
        ),
    )
    new_password2 = forms.CharField(
        label="Confirm new password",
        widget=forms.PasswordInput(
            attrs={"class": _INPUT_CLASS, "autocomplete": "new-password"}
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

    can_create_ideas = forms.BooleanField(initial=True, required=False)
    can_create_companies = forms.BooleanField(initial=True, required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "first_name", "last_name")

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            profile = user.profile
            profile.must_change_password = True
            profile.can_create_ideas = self.cleaned_data.get("can_create_ideas", True)
            profile.can_create_companies = self.cleaned_data.get(
                "can_create_companies", True
            )
            profile.save(
                update_fields=[
                    "must_change_password",
                    "can_create_ideas",
                    "can_create_companies",
                    "updated_at",
                ]
            )
        return user


class AppUserCreationForm(forms.Form):
    """Staff UI: create a user with a default password (must change on first login)."""

    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": _INPUT_CLASS, "autocomplete": "username"}),
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={"class": _INPUT_CLASS, "autocomplete": "email"}),
    )
    first_name = forms.CharField(
        required=False,
        max_length=150,
        widget=forms.TextInput(attrs={"class": _INPUT_CLASS}),
    )
    last_name = forms.CharField(
        required=False,
        max_length=150,
        widget=forms.TextInput(attrs={"class": _INPUT_CLASS}),
    )
    initial_password = forms.CharField(
        label="Default password",
        help_text="User must change this password on first login.",
        widget=forms.PasswordInput(
            attrs={"class": _INPUT_CLASS, "autocomplete": "new-password"}
        ),
    )
    can_create_ideas = forms.BooleanField(
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={"class": _CHECKBOX_CLASS}),
    )
    can_create_companies = forms.BooleanField(
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={"class": _CHECKBOX_CLASS}),
    )
    is_staff = forms.BooleanField(
        label="Application admin",
        required=False,
        help_text="Admins see all ideas and companies and can manage users.",
        widget=forms.CheckboxInput(attrs={"class": _CHECKBOX_CLASS}),
    )
    link_team_members = forms.ModelMultipleChoiceField(
        queryset=CompanyTeamMember.objects.none(),
        required=False,
        label="Link to existing humans (team members)",
        help_text=(
            "Select company humans to connect to this login. "
            "The user will see those companies and tasks assigned to them. "
            "Typically disable “Create ideas/companies” for linked-only users."
        ),
        widget=_TEAM_MEMBER_WIDGET,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["link_team_members"].queryset = unlinked_team_members_queryset()

    def clean_link_team_members(self):
        members = self.cleaned_data.get("link_team_members") or []
        for member in members:
            if member.user_id:
                raise forms.ValidationError(
                    f"{member.name} ({member.company.name}) is already linked to a user."
                )
        return members

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username

    def clean_initial_password(self):
        password = self.cleaned_data["initial_password"]
        from django.contrib.auth.password_validation import validate_password

        validate_password(password)
        return password

    def save(self) -> User:
        user = User.objects.create_user(
            username=self.cleaned_data["username"],
            password=self.cleaned_data["initial_password"],
            email=self.cleaned_data.get("email") or "",
            first_name=self.cleaned_data.get("first_name") or "",
            last_name=self.cleaned_data.get("last_name") or "",
            is_staff=self.cleaned_data.get("is_staff") or False,
        )
        profile = user.profile
        profile.must_change_password = True
        profile.can_create_ideas = self.cleaned_data.get("can_create_ideas", False)
        profile.can_create_companies = self.cleaned_data.get("can_create_companies", False)
        profile.save(
            update_fields=[
                "must_change_password",
                "can_create_ideas",
                "can_create_companies",
                "updated_at",
            ]
        )
        members = self.cleaned_data.get("link_team_members") or []
        if members:
            link_team_members_to_user(user, members)
        return user


class AppUserEditForm(forms.Form):
    """Staff UI: update permissions and optional password reset."""

    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={"class": _INPUT_CLASS}),
    )
    first_name = forms.CharField(
        required=False,
        max_length=150,
        widget=forms.TextInput(attrs={"class": _INPUT_CLASS}),
    )
    last_name = forms.CharField(
        required=False,
        max_length=150,
        widget=forms.TextInput(attrs={"class": _INPUT_CLASS}),
    )
    is_active = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": _CHECKBOX_CLASS}),
    )
    is_staff = forms.BooleanField(
        label="Application admin",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": _CHECKBOX_CLASS}),
    )
    can_create_ideas = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": _CHECKBOX_CLASS}),
    )
    can_create_companies = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": _CHECKBOX_CLASS}),
    )
    must_change_password = forms.BooleanField(
        label="Require password change on next login",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": _CHECKBOX_CLASS}),
    )
    new_password = forms.CharField(
        required=False,
        label="Set new password (optional)",
        widget=forms.PasswordInput(attrs={"class": _INPUT_CLASS, "autocomplete": "new-password"}),
    )
    link_team_members = forms.ModelMultipleChoiceField(
        queryset=CompanyTeamMember.objects.none(),
        required=False,
        label="Linked humans (team members)",
        help_text=(
            "Humans linked to this user can log in and access their companies "
            "and assigned tasks."
        ),
        widget=_TEAM_MEMBER_WIDGET,
    )

    def __init__(self, *args, user: User, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        linked = CompanyTeamMember.objects.filter(user=user, is_active=True)
        unlinked = unlinked_team_members_queryset()
        self.fields["link_team_members"].queryset = (
            linked | unlinked
        ).distinct().order_by("company__name", "name")
        self.fields["link_team_members"].initial = linked
        profile = user.profile
        self.fields["email"].initial = user.email
        self.fields["first_name"].initial = user.first_name
        self.fields["last_name"].initial = user.last_name
        self.fields["is_active"].initial = user.is_active
        self.fields["is_staff"].initial = user.is_staff
        self.fields["can_create_ideas"].initial = profile.can_create_ideas
        self.fields["can_create_companies"].initial = profile.can_create_companies
        self.fields["must_change_password"].initial = profile.must_change_password

    def clean_new_password(self):
        password = self.cleaned_data.get("new_password")
        if password:
            from django.contrib.auth.password_validation import validate_password

            validate_password(password, self.user)
        return password

    def clean_link_team_members(self):
        members = self.cleaned_data.get("link_team_members") or []
        for member in members:
            if member.user_id and member.user_id != self.user.pk:
                raise forms.ValidationError(
                    f"{member.name} ({member.company.name}) is already linked to another user."
                )
        return members

    def save(self) -> User:
        user = self.user
        user.email = self.cleaned_data.get("email") or ""
        user.first_name = self.cleaned_data.get("first_name") or ""
        user.last_name = self.cleaned_data.get("last_name") or ""
        user.is_active = self.cleaned_data.get("is_active", False)
        user.is_staff = self.cleaned_data.get("is_staff", False)
        new_password = self.cleaned_data.get("new_password")
        if new_password:
            user.set_password(new_password)
        user.save()
        profile = user.profile
        profile.can_create_ideas = self.cleaned_data.get("can_create_ideas", False)
        profile.can_create_companies = self.cleaned_data.get("can_create_companies", False)
        profile.must_change_password = self.cleaned_data.get("must_change_password", False)
        profile.save(
            update_fields=[
                "can_create_ideas",
                "can_create_companies",
                "must_change_password",
                "updated_at",
            ]
        )
        sync_user_team_members(
            user, self.cleaned_data.get("link_team_members") or []
        )
        return user


_ASSISTANT_INHERIT = ("", "— same as service default —")


class ServiceLLMConfigForm(forms.ModelForm):
    """Edit service-wide LLM provider (OpenAI ↔ Ollama) and company Assistant LLM."""

    ollama_model_id = forms.ChoiceField(
        choices=OLLAMA_MODELS,
        help_text="Local model name as shown by Ollama (e.g. llama3.2, qwen3).",
        widget=forms.Select(attrs={"class": _INPUT_CLASS}),
    )
    openai_model_id = forms.ChoiceField(
        choices=OPENAI_MODELS,
        help_text="Used for idea pipelines and agents when OpenAI is the default provider.",
        widget=forms.Select(attrs={"class": _INPUT_CLASS}),
    )
    assistant_provider = forms.ChoiceField(
        choices=[_ASSISTANT_INHERIT, *ServiceLLMConfig.Provider.choices],
        required=False,
        help_text="Leave as “same as service default” unless the company Assistant should use a different provider.",
        widget=forms.Select(attrs={"class": _INPUT_CLASS}),
    )
    assistant_ollama_model_id = forms.ChoiceField(
        choices=[_ASSISTANT_INHERIT, *OLLAMA_MODELS],
        required=False,
        help_text="Leave inherited to use the service default Ollama model.",
        widget=forms.Select(attrs={"class": _INPUT_CLASS}),
    )
    assistant_openai_model_id = forms.ChoiceField(
        choices=[_ASSISTANT_INHERIT, *OPENAI_MODELS],
        required=False,
        help_text="Leave inherited to use the service default OpenAI model.",
        widget=forms.Select(attrs={"class": _INPUT_CLASS}),
    )

    class Meta:
        model = ServiceLLMConfig
        fields = (
            "default_provider",
            "ollama_host",
            "ollama_model_id",
            "openai_model_id",
            "assistant_provider",
            "assistant_ollama_model_id",
            "assistant_openai_model_id",
        )
        widgets = {
            "default_provider": forms.Select(attrs={"class": _INPUT_CLASS}),
            "ollama_host": forms.URLInput(
                attrs={"class": _INPUT_CLASS, "placeholder": "http://localhost:11434"}
            ),
        }
        help_texts = {
            "default_provider": "Default for new idea requests, agent pipelines, and background jobs.",
            "ollama_host": "Base URL of your Ollama server (include http:// or https://).",
        }


class GoogleCalendarSettingsForm(forms.ModelForm):
    """Per-user Google Calendar sync preferences."""

    class Meta:
        model = UserProfile
        fields = (
            "google_calendar_sync_enabled",
            "google_calendar_remove_events_on_disconnect",
            "google_calendar_id",
            "google_calendar_reminder_minutes",
        )
        widgets = {
            "google_calendar_sync_enabled": forms.CheckboxInput(
                attrs={"class": _CHECKBOX_CLASS}
            ),
            "google_calendar_remove_events_on_disconnect": forms.CheckboxInput(
                attrs={"class": _CHECKBOX_CLASS}
            ),
            "google_calendar_id": forms.TextInput(
                attrs={"class": _INPUT_CLASS, "placeholder": "Auto: dedicated Idea Factory calendar"}
            ),
            "google_calendar_reminder_minutes": forms.TextInput(
                attrs={"class": _INPUT_CLASS, "placeholder": "60,1440"}
            ),
        }
        help_texts = {
            "google_calendar_reminder_minutes": (
                "Minutes before the action date. Example: 60,1440 = 1 hour and 1 day before."
            ),
        }
