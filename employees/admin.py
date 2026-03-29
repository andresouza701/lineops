from django import forms
from django.contrib import admin

from core.normalization import normalize_email_address, normalize_full_name

from .models import Employee


class EmployeeAdminForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = "__all__"

    def clean_full_name(self):
        full_name = normalize_full_name(self.cleaned_data.get("full_name"))
        if not full_name:
            return full_name

        if Employee.has_active_full_name_conflict(
            full_name,
            exclude_id=self.instance.pk if self.instance and self.instance.pk else None,
        ):
            raise forms.ValidationError(
                "Ja existe um usuario cadastrado com este nome."
            )

        return full_name

    def clean_corporate_email(self):
        return normalize_email_address(self.cleaned_data.get("corporate_email"))

    def clean_manager_email(self):
        return normalize_email_address(self.cleaned_data.get("manager_email")) or None


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    form = EmployeeAdminForm
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
        queryset = super().get_queryset(request)
        return request.user.scope_employee_queryset(queryset)

    def get_deleted_objects(self, objs, request):
        deleted_objects = [str(obj) for obj in objs]
        model_count = {self.model._meta.verbose_name: len(deleted_objects)}
        perms_needed = set()
        protected = []
        return deleted_objects, model_count, perms_needed, protected

    def delete_model(self, request, obj):
        obj.delete()

    def delete_queryset(self, request, queryset):
        queryset.delete()
