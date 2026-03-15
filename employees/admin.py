from django import forms
from django.contrib import admin

from .models import Employee


class EmployeeAdminForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = "__all__"

    def clean_full_name(self):
        full_name = (self.cleaned_data.get("full_name") or "").strip()
        if not full_name:
            return full_name

        duplicate_qs = Employee.all_objects.filter(
            full_name__iexact=full_name,
            is_deleted=False,
        )
        if self.instance and self.instance.pk:
            duplicate_qs = duplicate_qs.exclude(pk=self.instance.pk)

        if duplicate_qs.exists():
            raise forms.ValidationError(
                "Ja existe um usuario cadastrado com este nome."
            )

        return full_name


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
        """Filtra employees baseado na role do usuário"""
        queryset = super().get_queryset(request)
        # SUPER users can only see their own employees
        return request.user.scope_employee_queryset(queryset)

    # Admin delete must respect soft-delete semantics from Employee model/queryset.
    # The default admin collector checks protected relations as if it were a hard
    # delete, which blocks valid soft deletions.
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
