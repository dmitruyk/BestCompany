"""Admin for user accounts and human access."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User

from apps.core.forms import AdminHumanUserCreationForm
from apps.core.models import ServiceLLMConfig, UserProfile


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    extra = 0
    fields = (
        "must_change_password",
        "can_create_ideas",
        "can_create_companies",
    )
    readonly_fields = ()


@admin.register(ServiceLLMConfig)
class ServiceLLMConfigAdmin(admin.ModelAdmin):
    list_display = (
        "default_provider",
        "ollama_host",
        "ollama_model_id",
        "openai_model_id",
        "updated_at",
    )

    def has_add_permission(self, request):
        return not ServiceLLMConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "must_change_password",
        "can_create_ideas",
        "can_create_companies",
        "updated_at",
    )
    list_filter = ("must_change_password", "can_create_ideas", "can_create_companies")
    search_fields = ("user__username", "user__email")
    raw_id_fields = ("user",)


class CustomUserAdmin(DjangoUserAdmin):
    """
    Let staff create human accounts with login access.
    New users created here must change password on first login by default.
    """

    inlines = (UserProfileInline,)
    add_form = AdminHumanUserCreationForm
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "password1", "password2"),
                "description": (
                    "Create a human account for Idea Factory. "
                    "The user must change their password on first login."
                ),
            },
        ),
        (
            "Personal info",
            {"fields": ("first_name", "last_name", "email")},
        ),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        profile, _ = UserProfile.objects.get_or_create(user=obj)
        if not change:
            profile.must_change_password = True
            profile.save(update_fields=["must_change_password", "updated_at"])


# Registered from AppConfig.ready() to replace default User admin
