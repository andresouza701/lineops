from django.contrib import messages
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from allocations.models import LineAllocation
from core.mixins import RoleRequiredMixin
from users.models import SystemUser

from .models import Employee


class EmployeeListView(RoleRequiredMixin, ListView):
    allowed_roles = [SystemUser.Role.ADMIN]
    model = Employee
    template_name = "employees/employee_list.html"
    context_object_name = "employees"
    paginate_by = 10

    def get_queryset(self):
        queryset = Employee.objects.all().order_by("full_name")

        name = self.request.GET.get("name", "").strip()
        team = self.request.GET.get("team", "").strip()
        teams = self.request.GET.get("teams", "").strip()
        line = self.request.GET.get("line", "").strip()
        if name:
            queryset = queryset.filter(full_name__icontains=name)
        if team:
            queryset = queryset.filter(teams__icontains=team)
        if teams:
            queryset = queryset.filter(teams__icontains=teams)
        if line:
            queryset = queryset.filter(
                allocations__phone_line__phone_number__icontains=line
            )

        return queryset.distinct().prefetch_related(
            Prefetch(
                "allocations",
                queryset=LineAllocation.objects.filter(is_active=True).select_related(
                    "phone_line"
                ),
            )
        )


class EmployeeCreateView(RoleRequiredMixin, CreateView):
    allowed_roles = [SystemUser.Role.ADMIN]
    model = Employee
    template_name = "employees/employee_form.html"
    from .forms import EmployeeForm

    form_class = EmployeeForm
    success_url = reverse_lazy("employees:employee_list")

    def form_valid(self, form):
        messages.success(self.request, "Funcionário criado com sucesso.")
        return super().form_valid(form)


class EmployeeUpdateView(RoleRequiredMixin, UpdateView):
    allowed_roles = [SystemUser.Role.ADMIN]
    model = Employee
    template_name = "employees/employee_form.html"
    from .forms import EmployeeForm

    form_class = EmployeeForm
    success_url = reverse_lazy("employees:employee_list")

    def form_valid(self, form):
        messages.success(self.request, "Funcionário atualizado com sucesso.")
        return super().form_valid(form)


class EmployeeDeactivateView(RoleRequiredMixin, View):
    allowed_roles = [SystemUser.Role.ADMIN]

    def post(self, request, pk):
        employee = get_object_or_404(Employee, pk=pk)
        employee.delete()
        messages.success(request, "Funcionário desativado com sucesso.")
        return redirect("employees:employee_list")


class EmployeeDetailView(RoleRequiredMixin, DetailView):
    allowed_roles = [SystemUser.Role.ADMIN]
    model = Employee
    template_name = "employees/employee_detail.html"
    context_object_name = "employee"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = self.get_object()
        allocations = LineAllocation.objects.filter(employee=employee)
        # Date filter
        start_date = self.request.GET.get("start_date")
        end_date = self.request.GET.get("end_date")
        if start_date:
            allocations = allocations.filter(allocated_at__date__gte=start_date)
        if end_date:
            allocations = allocations.filter(allocated_at__date__lte=end_date)
        context["allocations"] = allocations.select_related(
            "phone_line__sim_card"
        ).order_by("-allocated_at")
        context["start_date"] = start_date
        context["end_date"] = end_date
        return context
