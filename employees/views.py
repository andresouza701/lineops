from django.contrib import messages
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from allocations.models import LineAllocation
from core.mixins import RoleRequiredMixin
from users.models import SystemUser

from .models import Employee, EmployeeHistory


class EmployeeListView(RoleRequiredMixin, ListView):
    allowed_roles = [SystemUser.Role.ADMIN, SystemUser.Role.SUPER]
    model = Employee
    template_name = "employees/employee_list.html"
    context_object_name = "employees"
    paginate_by = 10

    def get(self, request, *args, **kwargs):
        # Se for requisição AJAX para load more
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return self._handle_ajax_request(request)
        return super().get(request, *args, **kwargs)

    def _handle_ajax_request(self, request):
        """Retorna dados em JSON para load more"""
        offset = int(request.GET.get("offset", 0))
        limit = int(request.GET.get("limit", self.paginate_by))

        queryset = self._build_queryset(request)
        employees = list(queryset[offset : offset + limit])
        has_more = queryset.count() > (offset + limit)

        # Formatar dados para JSON
        data = []
        for emp in employees:
            data.append(
                {
                    "id": emp.pk,
                    "corporate_email": emp.corporate_email,
                    "full_name": emp.full_name,
                    "employee_id": emp.employee_id,
                    "pa": emp.pa or "",
                    "teams": emp.teams,
                    "status": emp.status,
                    "edit_url": f"/employees/{emp.pk}/edit/",
                    "history_url": f"/employees/{emp.pk}/history/",
                }
            )

        return JsonResponse(
            {"data": data, "has_more": has_more, "offset": offset + len(employees)}
        )

    def _build_queryset(self, request):
        """Constrói o queryset baseado nos filtros"""
        queryset = Employee.objects.all().order_by("full_name")

        name = request.GET.get("name", "").strip()
        team = request.GET.get("team", "").strip()
        teams = request.GET.get("teams", "").strip()
        supervisor = request.GET.get("supervisor", "").strip()

        if name:
            queryset = queryset.filter(full_name__icontains=name)
        if team:
            queryset = queryset.filter(teams__icontains=team)
        if teams:
            queryset = queryset.filter(teams__icontains=teams)
        if supervisor:
            queryset = queryset.filter(corporate_email__icontains=supervisor)

        return queryset.distinct().prefetch_related(
            Prefetch(
                "allocations",
                queryset=LineAllocation.objects.filter(is_active=True).select_related(
                    "phone_line"
                ),
            )
        )

    def get_queryset(self):
        return self._build_queryset(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Carregar apenas os primeiros itens baseado em paginate_by
        queryset = self.get_queryset()
        context["initial_employees"] = list(queryset[: self.paginate_by])
        context["has_more_employees"] = queryset.count() > self.paginate_by
        context["items_per_page"] = self.paginate_by
        return context


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
    allowed_roles = [SystemUser.Role.ADMIN, SystemUser.Role.SUPER]
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


class EmployeeHistoryView(RoleRequiredMixin, DetailView):
    allowed_roles = [SystemUser.Role.ADMIN]
    model = Employee
    template_name = "employees/employee_history.html"
    context_object_name = "employee"

    def get_queryset(self):
        return Employee.objects.filter(is_deleted=False)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["history"] = (
            EmployeeHistory.objects.filter(employee=context["employee"])
            .select_related("changed_by")
            .order_by("-changed_at")
        )
        return context
