from django.contrib import admin

from .models import AllocationPendency


@admin.register(AllocationPendency)
class AllocationPendencyAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "allocation",
        "action",
        "technical_responsible",
        "pendency_submitted_at",
        "resolved_at",
        "updated_at",
    )
    list_filter = ("action",)
    search_fields = ("employee__full_name",)
    readonly_fields = (
        "created_at",
        "updated_at",
        "last_action_changed_at",
        "pendency_submitted_at",
        "resolved_at",
    )
