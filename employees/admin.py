from django.contrib import admin

from .models import Employee

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'corporate_email', 'employee_id', 'department', 'status', 'is_deleted', 'created_at', 'updated_at')
    search_fields = ('full_name', 'corporate_email', 'employee_id', 'department')
    list_filter = ('status', 'is_deleted', 'department')