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

    def get_queryset(self, request):
        """Filtra employees baseado na role do usuário"""
        queryset = super().get_queryset(request)
        # SUPER users can only see their own employees
        if request.user.role == "super":
            queryset = queryset.filter(corporate_email=request.user.email)
        return queryset
