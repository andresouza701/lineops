from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import TemplateView, View

from core.mixins import RoleRequiredMixin
from core.exceptions.domain_exceptions import BusinessRuleException
from core.services.allocation_service import AllocationService
from employees.forms import EmployeeForm
from employees.models import Employee
from telecom.forms import SIMcardForm, PhoneLineForm, CombinedSimLineForm
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser

from .models import LineAllocation
from .forms import AllocationForm


class RegistrationHubView(RoleRequiredMixin, TemplateView):
    allowed_roles = [SystemUser.Role.ADMIN, SystemUser.Role.OPERATOR]
    template_name = 'allocations/allocation_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['employee_form'] = kwargs.get(
            'employee_form') or EmployeeForm()
        context['simcard_form'] = kwargs.get('simcard_form') or SIMcardForm()
        context['phoneline_form'] = kwargs.get(
            'phoneline_form') or PhoneLineForm()
        context['allocation_form'] = kwargs.get(
            'allocation_form') or AllocationForm()
        context['combined_sim_line_form'] = kwargs.get(
            'combined_sim_line_form') or CombinedSimLineForm()
        context['allocations'] = self._allocations_qs()
        context['available_lines'] = self._available_lines_qs()
        context['available_simcards'] = self._available_simcards_qs()
        context['active_employees'] = self._active_employees_qs()
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get('action')
        handlers = {
            'employee': self._handle_employee,
            'simcard': self._handle_simcard,
            'phoneline': self._handle_phoneline,
            'allocation': self._handle_allocation,
            'simcard_line': self._handle_simcard_line,
        }

        handler = handlers.get(action)
        if not handler:
            messages.error(request, 'Ação inválida.')
            return redirect('allocations:allocation_list')

        response = handler(request)
        return response or redirect('allocations:allocation_list')

    def _handle_employee(self, request):
        self._ensure_roles(request, [SystemUser.Role.ADMIN])
        form = EmployeeForm(request.POST)

        if form.is_valid():
            form.save()
            messages.success(request, 'Usuário cadastrado com sucesso.')
            return None

        messages.error(request, 'Corrija os erros no cadastro de usuário.')
        return self._render_with_forms(employee_form=form)

    def _handle_simcard(self, request):
        self._ensure_roles(request, [SystemUser.Role.ADMIN])
        form = SIMcardForm(request.POST)

        if form.is_valid():
            form.save()
            messages.success(request, 'SIM card cadastrado com sucesso.')
            return None

        messages.error(request, 'Corrija os erros no cadastro de SIM card.')
        return self._render_with_forms(simcard_form=form)

    def _handle_phoneline(self, request):
        self._ensure_roles(request, [SystemUser.Role.ADMIN])
        form = PhoneLineForm(request.POST)

        if form.is_valid():
            phone_line = form.save()
            messages.success(
                request, f'Linha {phone_line.phone_number} criada com sucesso.')
            return None

        messages.error(request, 'Corrija os erros no cadastro de linha.')
        return self._render_with_forms(phoneline_form=form)

    def _handle_simcard_line(self, request):
        self._ensure_roles(request, [SystemUser.Role.ADMIN])
        form = CombinedSimLineForm(request.POST)

        if not form.is_valid():
            messages.error(
                request, 'Corrija os erros para salvar linha e SIM card.')
            return self._render_with_forms(combined_sim_line_form=form)

        with transaction.atomic():
            sim = SIMcard.objects.create(
                iccid=form.cleaned_data['iccid'],
                carrier=form.cleaned_data['carrier'],
                status=SIMcard.Status.AVAILABLE,
            )
            phone_line = PhoneLine.objects.create(
                phone_number=form.cleaned_data['phone_number'],
                sim_card=sim,
                status=PhoneLine.Status.AVAILABLE,
            )

        messages.success(
            request, f'SIM card e linha {phone_line.phone_number} cadastrados com sucesso.')
        return None

    def _handle_allocation(self, request):
        form = AllocationForm(request.POST)

        if not form.is_valid():
            messages.error(
                request, 'Preencha os campos obrigatórios para alocar uma linha.')
            return self._render_with_forms(allocation_form=form)

        employee = form.cleaned_data['employee']
        phone_line = form.cleaned_data['phone_line']

        try:
            AllocationService.allocate_line(
                employee, phone_line, allocated_by=request.user)
        except BusinessRuleException as exc:
            messages.error(request, str(exc))
            return self._render_with_forms(allocation_form=form)

        messages.success(request, 'Linha alocada com sucesso.')
        return None

    def _render_with_forms(self, **forms):
        context = self.get_context_data(**forms)
        return self.render_to_response(context)

    def _ensure_roles(self, request, allowed_roles):
        current_role = (request.user.role or '').lower()
        allowed = {role.lower() for role in allowed_roles}
        if current_role not in allowed:
            raise PermissionDenied('Acesso negado: função insuficiente.')

    def _allocations_qs(self):
        return LineAllocation.objects.select_related('employee', 'phone_line').order_by('-allocated_at')

    def _available_lines_qs(self):
        return PhoneLine.objects.filter(
            is_deleted=False, status=PhoneLine.Status.AVAILABLE
        ).select_related('sim_card')

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
        ).order_by('full_name')


class LineAllocationReleaseView(RoleRequiredMixin, View):
    allowed_roles = [SystemUser.Role.ADMIN, SystemUser.Role.OPERATOR]

    def post(self, request, pk):
        allocation = get_object_or_404(
            LineAllocation.objects.select_related('phone_line'), pk=pk, is_active=True)
        AllocationService.release_line(allocation, released_by=request.user)
        messages.success(request, 'Linha liberada com sucesso.')
        return redirect('allocations:allocation_list')
