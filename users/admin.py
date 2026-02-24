from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import SystemUser


@admin.register(SystemUser)
class SystemUserAdmin(UserAdmin):
    model = SystemUser
    list_display = ("email", "role", "is_staff", "is_active")
    ordering = ("email",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Permissions", {"fields": ("is_staff", "is_active", "role", "is_superuser")}),
        ("Important dates", {"fields": ("last_login",)}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2", "role"),
            },
        ),
    )
