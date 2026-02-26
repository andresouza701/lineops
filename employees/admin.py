from django.contrib import admin

from .models import Employee


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "corporate_email",
        "employee_id",
        "teams",
        "status",
        "is_deleted",
        "created_at",
        "updated_at",
    )

    search_fields = ("full_name", "corporate_email", "employee_id", "teams")
    list_filter = ("status", "is_deleted", "teams")
    ordering = ("full_name",)
