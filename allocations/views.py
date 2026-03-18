from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import TemplateView, View

from core.exceptions.domain_exceptions import BusinessRuleException
from core.mixins import RoleRequiredMixin
from core.services.allocation_service import AllocationService
from core.services.telephony_use_case import TelephonyUseCase
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser

from .forms import CombinedRegistrationForm, TelephonyAssignmentForm
from .models import LineAllocation

DUPLICATE_EMPLOYEE_NAME_CONSTRAINT = "employees_employee_unique_active_full_name_ci"


def _is_duplicate_full_name_error(exc: IntegrityError) -> bool:
    if DUPLICATE_EMPLOYEE_NAME_CONSTRAINT in str(exc):
        return True

    cause = getattr(exc, "__cause__", None)
    if not cause:
        return False

    if DUPLICATE_EMPLOYEE_NAME_CONSTRAINT in str(cause):
        return True

    diag = getattr(cause, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None)
    return constraint_name == DUPLICATE_EMPLOYEE_NAME_CONSTRAINT


class RegistrationHubView(RoleRequiredMixin, TemplateView):
    allowed_roles = [SystemUser.Role.ADMIN, SystemUser.Role.OPERATOR]
    template_name = "allocations/allocation_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["employee_form"] = (
            kwargs.get("employee_form") or CombinedRegistrationForm()
        )
        context["telephony_form"] = (
            kwargs.get("telephony_form") or TelephonyAssignmentForm()
        )
        context["allocations"] = self._allocations_qs()
        context["available_lines"] = self._available_lines_qs()
        context["available_simcards"] = self._available_simcards_qs()
        context["active_employees"] = self._active_employees_qs()
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action")

        if action == "employee":
            return self._handle_employee(request)
        if action == "telephony":
            return self._handle_telephony(request)

        messages.error(request, "Ação inválida.")
        return redirect("allocations:allocation_list")

    def _handle_employee(self, request):
        self._ensure_roles(request, [SystemUser.Role.ADMIN])
        form = CombinedRegistrationForm(request.POST)

        if form.is_valid():
            try:
                Employee.objects.create(
                    full_name=form.cleaned_data["full_name"],
                    corporate_email=form.cleaned_data["corporate_email"],
                    manager_email=form.cleaned_data["manager_email"] or None,
                    employee_id=form.cleaned_data["employee_id"],
                    teams=form.cleaned_data["teams"],
                    status=form.cleaned_data["status"],
                )
            except IntegrityError as exc:
                if not _is_duplicate_full_name_error(exc):
                    raise
                form.add_error(
                    "full_name",
                    "Ja existe um usuario cadastrado com este nome.",
                )
                messages.error(request, "Corrija os erros do usuário.")
                return self._render_with_forms(employee_form=form)

            messages.success(request, "Usuário cadastrado com sucesso!")
            return redirect("allocations:allocation_list")

        messages.error(request, "Corrija os erros do usuário.")
        return self._render_with_forms(employee_form=form)

    def _handle_telephony(self, request):
        self._ensure_roles(request, [SystemUser.Role.ADMIN])
        form = TelephonyAssignmentForm(request.POST)

        if not form.is_valid():
            messages.error(request, "Corrija os erros de telefonia.")
            return self._render_with_forms(telephony_form=form)

        line_action = form.cleaned_data["line_action"]

        try:
            if line_action == "change_status":
                result = TelephonyUseCase.change_line_status(
                    phone_line_id=form.cleaned_data["phone_line_status"].pk,
                    new_status=form.cleaned_data["status_line"],
                    actor=request.user,
                )
            elif line_action == "existing":
                result = TelephonyUseCase.allocate_existing_line(
                    phone_line=form.cleaned_data["phone_line"],
                    employee=form.cleaned_data["employee"],
                    actor=request.user,
                )
            else:  # new line
                result = TelephonyUseCase.create_new_line_with_allocation(
                    line_data={
                        "phone_number": form.cleaned_data["phone_number"],
                        "iccid": form.cleaned_data["iccid"],
                        "carrier": form.cleaned_data["carrier"],
                        "origem": form.cleaned_data["origem"],
                    },
                    employee=form.cleaned_data.get("employee"),
                    actor=request.user,
                )

            messages.success(request, result.message)
        except BusinessRuleException as exc:
            messages.error(request, str(exc))
            return self._render_with_forms(telephony_form=form)

        return redirect("allocations:allocation_list")

    def _render_with_forms(self, **forms):
        context = self.get_context_data(**forms)
        return self.render_to_response(context)

    def _ensure_roles(self, request, allowed_roles):
        current_role = (request.user.role or "").lower()
        allowed = {role.lower() for role in allowed_roles}
        if current_role not in allowed:
            raise PermissionDenied("Acesso negado: Permissão insuficiente!")

    def _allocations_qs(self):
        # Atualiza para buscar phone_line com sim_card e status atualizado
        return LineAllocation.objects.select_related(
            "employee", "phone_line__sim_card", "phone_line"
        ).order_by("-allocated_at")

    def _available_lines_qs(self):
        return PhoneLine.objects.filter(
            is_deleted=False, status=PhoneLine.Status.AVAILABLE
        ).select_related("sim_card")

    def _available_simcards_qs(self):
        return SIMcard.objects.filter(
            is_deleted=False,
            phone_line__isnull=True,
            status=SIMcard.Status.AVAILABLE,
        )

    def _active_employees_qs(self):
        return Employee.objects.filter(
            is_deleted=False,
            status=Employee.Status.ACTIVE,
        ).order_by("full_name")


class LineAllocationReleaseView(RoleRequiredMixin, View):
    allowed_roles = [SystemUser.Role.ADMIN, SystemUser.Role.OPERATOR]

    def post(self, request, pk):
        allocation = get_object_or_404(
            LineAllocation.objects.select_related("phone_line"), pk=pk, is_active=True
        )
        AllocationService.release_line(allocation, released_by=request.user)
        messages.success(request, "Linha liberada com sucesso!")
        next_url = request.POST.get("next")
        if next_url and url_has_allowed_host_and_scheme(
            url=next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect("allocations:allocation_list")


class AllocationEditView(RoleRequiredMixin, View):
    allowed_roles = [SystemUser.Role.ADMIN, SystemUser.Role.OPERATOR]

    def get(self, request, pk):
        allocation = get_object_or_404(
            LineAllocation.objects.select_related("phone_line__sim_card"),
            pk=pk,
        )
        available_lines = PhoneLine.objects.filter(
            is_deleted=False, status=PhoneLine.Status.AVAILABLE
        ).select_related("sim_card")
        employees = Employee.objects.filter(
            is_deleted=False, status=Employee.Status.ACTIVE
        )
        return render(
            request,
            "allocations/allocation_edit.html",
            {
                "allocation": allocation,
                "available_lines": available_lines,
                "employees": employees,
            },
        )

    def post(self, request, pk):
        allocation = get_object_or_404(
            LineAllocation.objects.select_related("phone_line__sim_card"), pk=pk
        )
        action = request.POST.get("action")
        if action == "release":
            if not allocation.is_active:
                messages.error(request, "Apenas alocacoes ativas podem ser liberadas.")
                return redirect(reverse("allocations:allocation_edit", args=[pk]))
            AllocationService.release_line(allocation, released_by=request.user)
            messages.success(request, "Linha liberada com sucesso!")
            return redirect(reverse("telecom:overview"))
        elif action == "save":
            new_status = request.POST.get("status")
            employee_pk = request.POST.get("employee")
            updated = False
            if new_status and new_status != allocation.phone_line.status:
                allocation.phone_line.status = new_status
                allocation.phone_line.save(update_fields=["status"])
                updated = True
            if employee_pk:
                employee = get_object_or_404(
                    Employee.objects.filter(
                        is_deleted=False,
                        status=Employee.Status.ACTIVE,
                    ),
                    pk=employee_pk,
                )
                if allocation.employee != employee:
                    allocation.employee = employee
                    allocation.save(update_fields=["employee"])
                    updated = True
            if updated:
                messages.success(request, "Dados atualizados com sucesso!")
            else:
                messages.info(request, "Nenhuma alteração realizada.")
            return redirect(
                reverse("allocations:allocation_edit", args=[allocation.pk])
            )
        return redirect(reverse("telecom:overview"))
