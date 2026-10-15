"""
FVI-03 - Testes RED da matriz de excecao de acesso a pendencias para
funcionario inativo (requisito 7 do checklist desta etapa).

Fonte de verdade: docs/superpowers/specs/2026-10-14-inactive-system-user-visibility-design.md
(FVI-02 "Fechamento apos respostas explicitas", decisao A). Node IDs
FT25-FT27 derivados nesta etapa (FVI-03).

Contrato: funcionario inativo SEM pendencia nem alocacao elegivel
(employee_id forjado) deve ser recusado ANTES de criar
registro/notificacao. Com pendencia OU alocacao ativa EXISTENTE
(qualquer uma das duas, independente de formar o par exato solicitado),
o acesso, abertura e reabertura continuam permitidos pelas regras
anteriores -- inclusive podendo chegar a um par (employee, allocation)
AINDA AUSENTE (get_or_create cria um registro novo legitimamente; o
contrato explicita que "nenhum registro novo" NAO e prometido nesse
caso). allocation_id explicito continua exigindo pertencer ao
funcionario e estar ativo (validacao ja existente, nao tocada aqui).

PendencyDetailView.get hoje (F18) resolve employee_id so por
scope_employee_queryset, sem nenhuma verificacao de elegibilidade por
status; os testes que exercitam a lacuna (acesso forjado sem pendencia
nem alocacao) falham de verdade (RED).
"""

from django.test import TestCase
from django.urls import reverse

from allocations.models import LineAllocation
from employees.models import Employee
from pendencies.models import AllocationPendency
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser


class PendencyAccessExceptionTestBase(TestCase):
    def setUp(self):
        self.supervisor = SystemUser.objects.create_user(
            email="super.fvi03.pend.exc@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.admin = SystemUser.objects.create_user(
            email="admin.fvi03.pend.exc@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self._line_counter = 0

    def _make_employee(self, suffix, *, status):
        return Employee.objects.create(
            full_name=f"Funcionario Pend Exc {suffix}",
            corporate_email=self.supervisor.email,
            employee_id=f"EMP-FVI03-PE-{suffix}",
            teams=Employee.UnitChoices.JOINVILLE,
            status=status,
        )

    def _make_active_allocation(self, employee):
        self._line_counter += 1
        sim = SIMcard.objects.create(
            iccid=f"9999000011{self._line_counter:010d}",
            carrier="CarrierPendExc",
            status=SIMcard.Status.AVAILABLE,
        )
        phone_line = PhoneLine.objects.create(
            phone_number=f"+551190000{self._line_counter:04d}",
            sim_card=sim,
            status=PhoneLine.Status.ALLOCATED,
        )
        return LineAllocation.objects.create(
            employee=employee, phone_line=phone_line, is_active=True
        )

    def _get_detail(self, employee_id, allocation_id=None):
        params = {"employee_id": employee_id}
        if allocation_id is not None:
            params["allocation_id"] = allocation_id
        return self.client.get(reverse("pendencies:detail"), params)


class FT25_NoEligibilityForgedAccessIsRejected(PendencyAccessExceptionTestBase):
    """FT25: funcionario inativo sem pendencia nem alocacao elegivel
    deve ser recusado antes de criar qualquer registro."""

    def test_no_pendency_no_allocation_inactive_employee_is_rejected(self):
        employee = self._make_employee("A", status=Employee.Status.INACTIVE)
        self.client.force_login(self.supervisor)

        response = self._get_detail(employee.pk)

        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            AllocationPendency.objects.filter(employee=employee).exists()
        )

    def test_released_allocation_alone_does_not_grant_eligibility(self):
        employee = self._make_employee("B", status=Employee.Status.INACTIVE)
        allocation = self._make_active_allocation(employee)
        allocation.is_active = False
        allocation.released_at = allocation.allocated_at
        allocation.save(update_fields=["is_active", "released_at"])

        self.client.force_login(self.supervisor)
        response = self._get_detail(employee.pk)

        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            AllocationPendency.objects.filter(employee=employee).exists()
        )

    def test_admin_viewer_bypasses_eligibility_gate_as_control(self):
        """Controle positivo: ADMIN e excecao de ROLE (sempre visivel),
        nao sujeito ao portao de elegibilidade -- acesso forjado a
        funcionario totalmente inelegivel ainda funciona para ADMIN."""
        employee = self._make_employee("C", status=Employee.Status.INACTIVE)
        self.client.force_login(self.admin)

        response = self._get_detail(employee.pk)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            AllocationPendency.objects.filter(employee=employee).exists()
        )

    def test_active_employee_without_any_record_succeeds_as_control(self):
        """Controle positivo: o portao de elegibilidade e exclusivo de
        funcionario INATIVO -- um funcionario ativo sem pendencia nem
        alocacao continua acessivel normalmente (comportamento
        preexistente, sem relacao com FVI)."""
        employee = self._make_employee("D", status=Employee.Status.ACTIVE)
        self.client.force_login(self.supervisor)

        response = self._get_detail(employee.pk)

        self.assertEqual(response.status_code, 200)


class FT26_ExistingPendencyOrAllocationPreservesAccess(
    PendencyAccessExceptionTestBase
):
    """FT26: pendencia OU alocacao ativa existente preserva o acesso do
    funcionario inativo, inclusive quando o par (employee, allocation)
    solicitado ainda nao existe (get_or_create cria legitimamente)."""

    def test_existing_pendency_record_preserves_access_without_new_row(self):
        employee = self._make_employee("E", status=Employee.Status.INACTIVE)
        existing = AllocationPendency.objects.create(
            employee=employee,
            allocation=None,
            action=AllocationPendency.ActionType.NO_ACTION,
        )
        self.client.force_login(self.supervisor)

        response = self._get_detail(employee.pk)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            AllocationPendency.objects.filter(employee=employee).count(), 1
        )
        payload = response.json()
        self.assertEqual(payload["id"], existing.pk)

    def test_existing_active_allocation_preserves_access_for_matching_pair(self):
        employee = self._make_employee("F", status=Employee.Status.INACTIVE)
        allocation = self._make_active_allocation(employee)
        self.client.force_login(self.supervisor)

        response = self._get_detail(employee.pk, allocation.pk)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            AllocationPendency.objects.filter(
                employee=employee, allocation=allocation
            ).count(),
            1,
        )

    def test_existing_active_allocation_grants_eligibility_for_absent_pair(self):
        """Caso explicito do contrato: elegibilidade por alocacao ativa
        (sem allocation_id no pedido) pode levar a criacao de um par
        (employee, allocation=None) AINDA AUSENTE -- nao se promete
        "nenhum registro novo" aqui."""
        employee = self._make_employee("G", status=Employee.Status.INACTIVE)
        self._make_active_allocation(employee)
        self.client.force_login(self.supervisor)

        response = self._get_detail(employee.pk)

        self.assertEqual(response.status_code, 200)
        created = AllocationPendency.objects.get(employee=employee, allocation=None)
        self.assertIsNotNone(created)


class FT27_ExplicitAllocationIdValidationIsPreserved(
    PendencyAccessExceptionTestBase
):
    """FT27: validacoes ja existentes sobre allocation_id explicito
    (pertencer ao funcionario e estar ativo) nao sao tocadas -- controles
    positivos de nao-regressao, nao uma lacuna nova desta etapa."""

    def test_allocation_id_belonging_to_another_employee_is_rejected(self):
        employee = self._make_employee("H", status=Employee.Status.INACTIVE)
        other_employee = self._make_employee(
            "H2", status=Employee.Status.ACTIVE
        )
        other_allocation = self._make_active_allocation(other_employee)
        self.client.force_login(self.supervisor)

        response = self._get_detail(employee.pk, other_allocation.pk)

        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            AllocationPendency.objects.filter(employee=employee).exists()
        )

    def test_allocation_id_referencing_released_allocation_is_rejected(self):
        employee = self._make_employee("I", status=Employee.Status.INACTIVE)
        allocation = self._make_active_allocation(employee)
        allocation.is_active = False
        allocation.released_at = allocation.allocated_at
        allocation.save(update_fields=["is_active", "released_at"])
        self.client.force_login(self.supervisor)

        response = self._get_detail(employee.pk, allocation.pk)

        self.assertEqual(response.status_code, 404)
