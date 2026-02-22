from core.mixins import AuthenticadView
from django.views.generic import ListView

from .models import Employee


class EmployeeListView(AuthenticadView, ListView):
    model = Employee
    template_name = 'employees/employee_list.html'
    context_object_name = 'employees'
    ordering = ['full_name']
