from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from employees.models import Employee
from telecom.models import PhoneLine, SIMcard
from allocations.models import LineAllocation

class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_employees'] = Employee.objects.filter(is_active=True).count()
        context['total_phone_lines'] = PhoneLine.objects.count()
        context['allocated_lines'] = LineAllocation.objects.filter(end_date__isnull=True).count()
        context['available_lines'] = (
            context['total_phone_lines'] - context['allocated_lines']
        )
        return context