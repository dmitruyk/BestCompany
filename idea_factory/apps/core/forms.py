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


_INPUT_CLASS = (
    "w-full rounded-lg border-slate-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
)
_CHECKBOX_CLASS = "rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"


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

    def __init__(self, *args, user: User, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
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
