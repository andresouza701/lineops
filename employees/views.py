from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from allocations.models import LineAllocation
from core.integrity import (
    is_duplicate_employee_email_error,
    is_duplicate_employee_name_error,
)
from core.mixins import RoleRequiredMixin
from core.services.allocation_service import AllocationService
from core.validation import parse_non_negative_int
from users.models import SystemUser
from users.visibility import mask_inactive_email, resolve_inactive_email_labels

from telecom.seal_indicator import seal_indicator_for_phone_line

from .models import Employee, EmployeeHistory

DUPLICATE_EMPLOYEE_NAME_MESSAGE = "Já existe um usuário cadastrado com este nome."
DUPLICATE_EMPLOYEE_EMAIL_MESSAGE = "Já existe um negociador cadastrado com este email."


class EmployeeListView(RoleRequiredMixin, ListView):
    allowed_roles = list(SystemUser.EMPLOYEE_ACCESS_ROLES)
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
        offset = parse_non_negative_int(request.GET.get("offset", 0), default=0)
        limit = max(
            parse_non_negative_int(request.GET.get("limit", self.paginate_by), 10), 1
        )

        queryset = self._build_queryset(request)
        employees = list(queryset[offset : offset + limit])
        has_more = queryset.count() > (offset + limit)

        # UVI-05 (retificado): neutraliza o supervisor de conta inativa no
        # payload JSON apenas para viewer sem a excecao de role (mesma
        # projecao do render inicial, resolvida em lote); ADMIN/DEV
        # recebem set vazio e veem a identidade real.
        inactive_emails = resolve_inactive_email_labels(
            request.user, (emp.corporate_email for emp in employees)
        )

        # Formatar dados para JSON
        data = []
        for emp in employees:
            lines = self._get_employee_lines(emp)
            data.append(
                {
                    "id": emp.pk,
                    "email": emp.email or "",
                    "corporate_email": mask_inactive_email(
                        emp.corporate_email, inactive_emails
                    ),
                    "full_name": emp.full_name,
                    "line": lines,
                    "lines": self._get_employee_lines_with_seal(emp),
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

    @staticmethod
    def _get_employee_lines(employee):
        """Extract phone numbers (+ situação textual do selo, SVI-05) from
        prefetched allocations to avoid N+1. Mesma regra usada pelo render
        inicial (template) e pelo AJAX (campo "line"), reaproveitando
        PhoneLine.seal_status ja carregado na instancia (sem query extra)."""
        allocations = employee.allocations.all()
        parts = []
        for allocation in allocations:
            phone_line = allocation.phone_line
            if not (phone_line and phone_line.phone_number):
                continue
            if phone_line.whatsapp_seal:
                parts.append(f"{phone_line.phone_number} ({phone_line.seal_status['label']})")
            else:
                parts.append(phone_line.phone_number)
        return ", ".join(parts) if parts else "-"

    @staticmethod
    def _get_employee_lines_with_seal(employee):
        """Mesma identidade de linha do método acima, estruturada por linha
        (não string concatenada) para o render dinâmico seguro (JS usa
        createElement/textContent, não concatenação de HTML — I08 AJAX)."""
        return [
            {
                "phone_number": allocation.phone_line.phone_number,
                "seal_indicator": seal_indicator_for_phone_line(allocation.phone_line).as_dict(),
            }
            for allocation in employee.allocations.all()
            if allocation.phone_line and allocation.phone_line.phone_number
        ]

    def _build_queryset(self, request):
        """Constrói o queryset baseado nos filtros"""
        queryset = Employee.objects.all().order_by("full_name")

        # Filtrar por role: SUPER vê apenas seus próprios usuários
        queryset = request.user.scope_employee_queryset(queryset)

        name = request.GET.get("name", "").strip()
        line = request.GET.get("line", "").strip()
        team = request.GET.get("team", "").strip()
        teams = request.GET.get("teams", "").strip()
        supervisor = request.GET.get("supervisor", "").strip()

        if name:
            queryset = queryset.filter(full_name__icontains=name)
        if line:
            queryset = queryset.filter(
                allocations__is_active=True,
                allocations__phone_line__phone_number__icontains=line,
            )
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
        initial_employees = list(queryset[: self.paginate_by])
        # UVI-05 (retificado): neutraliza o supervisor de conta inativa no
        # render inicial apenas para viewer sem a excecao de role, mesma
        # projecao do payload AJAX (resolvida em lote, sem consulta por
        # linha).
        inactive_emails = resolve_inactive_email_labels(
            self.request.user,
            (employee.corporate_email for employee in initial_employees),
        )
        for employee in initial_employees:
            employee.line_display = self._get_employee_lines(employee)
            employee.corporate_email_display = mask_inactive_email(
                employee.corporate_email, inactive_emails
            )

        context["initial_employees"] = initial_employees
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

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["viewer"] = self.request.user
        return kwargs

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
        except IntegrityError as exc:
            if is_duplicate_employee_email_error(exc):
                form.add_error("email", DUPLICATE_EMPLOYEE_EMAIL_MESSAGE)
                messages.error(self.request, "Corrija os erros do usuário.")
                return self.form_invalid(form)
            if not is_duplicate_employee_name_error(exc):
                raise
            form.add_error("full_name", DUPLICATE_EMPLOYEE_NAME_MESSAGE)
            messages.error(self.request, "Corrija os erros do usuário.")
            return self.form_invalid(form)

        messages.success(self.request, "Usuário criado com sucesso.")
        return response


class EmployeeUpdateView(RoleRequiredMixin, UpdateView):
    allowed_roles = list(SystemUser.EMPLOYEE_ACCESS_ROLES)
    model = Employee
    template_name = "employees/employee_form.html"
    from .forms import EmployeeForm

    form_class = EmployeeForm
    success_url = reverse_lazy("employees:employee_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["can_edit_full_name"] = self.request.user.role == SystemUser.Role.ADMIN
        kwargs["viewer"] = self.request.user
        return kwargs

    def get_queryset(self):
        """Filtra usuários baseado na role do usuário"""
        queryset = Employee.objects.all()
        # SUPER users can only access their own users
        return self.request.user.scope_employee_queryset(queryset)

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
        except IntegrityError as exc:
            if is_duplicate_employee_email_error(exc):
                form.add_error("email", DUPLICATE_EMPLOYEE_EMAIL_MESSAGE)
                messages.error(self.request, "Corrija os erros do usuário.")
                return self.form_invalid(form)
            if not is_duplicate_employee_name_error(exc):
                raise
            form.add_error("full_name", DUPLICATE_EMPLOYEE_NAME_MESSAGE)
            messages.error(self.request, "Corrija os erros do usuário.")
            return self.form_invalid(form)

        messages.success(self.request, "Usuário atualizado com sucesso.")
        return response


class EmployeeDeactivateView(RoleRequiredMixin, View):
    allowed_roles = [SystemUser.Role.ADMIN]

    @transaction.atomic
    def post(self, request, pk):
        employee = get_object_or_404(Employee, pk=pk)
        active_allocations = list(
            LineAllocation.objects.filter(employee=employee, is_active=True)
            .select_related("phone_line")
            .order_by("-allocated_at")
        )
        for allocation in active_allocations:
            AllocationService.release_line(allocation, released_by=request.user)
        employee.delete()
        messages.success(request, "Usuário desativado com sucesso.")
        return redirect("employees:employee_list")


class EmployeeDetailView(RoleRequiredMixin, DetailView):
    allowed_roles = [SystemUser.Role.ADMIN]
    model = Employee
    template_name = "employees/employee_detail.html"
    context_object_name = "employee"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = context["employee"]
        # UVI-05 (retificado): neutraliza supervisor/gerente de conta
        # inativa no detalhe apenas para viewer sem a excecao de role
        # (resolvido em lote, uma consulta para os dois campos). Esta
        # rota e ADMIN-only (allowed_roles), entao na pratica o set
        # resolvido aqui e sempre vazio -- ADMIN ve a identidade real.
        inactive_emails = resolve_inactive_email_labels(
            self.request.user, [employee.corporate_email, employee.manager_email]
        )
        employee.corporate_email_display = mask_inactive_email(
            employee.corporate_email, inactive_emails
        )
        employee.manager_email_display = mask_inactive_email(
            employee.manager_email, inactive_emails
        )
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
