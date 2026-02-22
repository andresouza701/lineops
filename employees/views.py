from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Prefetch
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView, DetailView
from django.views import View
from django.shortcuts import get_object_or_404, redirect
from allocations.models import LineAllocation
from core.mixins import RoleRequiredMixin
from users.models import SystemUser

from .models import Employee


class EmployeeListView(LoginRequiredMixin, ListView):
    model = Employee
    template_name = 'employees/employee_list.html'
    context_object_name = 'employees'
    paginate_by = 10

    def get_queryset(self):
        self.queryset = Employee.objects.all().order_by('full_name')

        search = self.request.GET.get('search')
        search_by = self.request.GET.get('search_by')

        if search:
            if search_by == 'linha':
                self.queryset = self.queryset.filter(
                    Q(allocations__phone_line__phone_number__icontains=search)
                )
            elif search_by == 'todos':
                self.queryset = self.queryset.filter(
                    Q(full_name__icontains=search) |
                    Q(employee_id__icontains=search) |
                    Q(allocations__phone_line__phone_number__icontains=search)
                )
            else:
                # default search by name (and matricula for convenience)
                self.queryset = self.queryset.filter(
                    Q(full_name__icontains=search) |
                    Q(employee_id__icontains=search)
                )

        return (
            self.queryset.distinct()
            .prefetch_related(
                Prefetch(
                    'allocations',
                    queryset=LineAllocation.objects.filter(
                        is_active=True).select_related('phone_line')
                )
            )
        )


class EmployeeCreateView(RoleRequiredMixin, CreateView):
    allowed_roles = [SystemUser.Role.ADMIN]
    model = Employee
    template_name = 'employees/employee_form.html'
    fields = ['full_name', 'corporate_email',
              'employee_id', 'department', 'status']
    success_url = reverse_lazy('employees:employee_list')

    def form_valid(self, form):
        messages.success(self.request, 'Funcionário criado com sucesso.')
        return super().form_valid(form)


class EmployeeUpdateView(RoleRequiredMixin, UpdateView):
    allowed_roles = [SystemUser.Role.ADMIN]
    model = Employee
    template_name = 'employees/employee_form.html'
    fields = ['full_name', 'corporate_email',
              'employee_id', 'department', 'status']
    success_url = reverse_lazy('employees:employee_list')

    def form_valid(self, form):
        messages.success(self.request, 'Funcionário atualizado com sucesso.')
        return super().form_valid(form)


class EmployeeDeactivateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        employee = get_object_or_404(Employee, pk=pk)
        employee.delete()
        messages.success(request, 'Funcionário desativado com sucesso.')
        return redirect('employees:employee_list')


class EmployeeDetailView(LoginRequiredMixin, DetailView):
    model = Employee
    template_name = 'employees/employee_detail.html'
    context_object_name = 'employee'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['allocations'] = (
            LineAllocation.objects
            .filter(employee=self.get_object())
            .select_related('phone_line__sim_card')
            .order_by('-allocated_at'))
        return context
