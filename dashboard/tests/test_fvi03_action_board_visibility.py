"""
FVI-03 - Testes RED da visibilidade de funcionarios inativos em Acoes do
Dia e no resumo de responsaveis (requisitos 5 e 6 do checklist desta
etapa, com paridade entre os dois consumidores do mesmo helper).

Fonte de verdade: docs/superpowers/specs/2026-10-14-inactive-system-user-visibility-design.md
(FVI-02 F22; fechamento "Acoes do Dia e resumo"). Node IDs FT29-FT33
derivados nesta etapa (FVI-03).

dashboard/views.py::daily_user_action_board (linha ~1943) chama
get_supervised_employees_queryset SEM o .filter(status=ACTIVE) que as
outras quatro chamadas do mesmo helper ja aplicam (F22); o resumo
(action_board_metrics_service.py::summarize_action_board_responsibles)
faz a MESMA chamada de forma independente, sem herdar filtro da view.
Os dois consumidores sao testados separadamente, pois a correcao de um
nao propaga automaticamente para o outro.
"""

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from allocations.models import LineAllocation
from dashboard.models import DailyUserAction
from dashboard.services.action_board_metrics_service import (
    summarize_action_board_responsibles,
)
from employees.models import Employee
from pendencies.models import AllocationPendency
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser

BOARD_URL = "daily_user_action_board"


class ActionBoardVisibilityTestBase(TestCase):
    def setUp(self):
        self.supervisor = SystemUser.objects.create_user(
            email="super.fvi03.board@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.admin = SystemUser.objects.create_user(
            email="admin.fvi03.board@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )

        self.active_employee = Employee.objects.create(
            full_name="Funcionario Ativo Board",
            corporate_email=self.supervisor.email,
            employee_id="EMP-FVI03-BRD-A",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )
        self.inactive_employee = Employee.objects.create(
            full_name="Funcionario Inativo Board",
            corporate_email=self.supervisor.email,
            employee_id="EMP-FVI03-BRD-I",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.INACTIVE,
        )

        # daily_user_action_board aplica apply_action_board_visibility_rules
        # (regra PRE-EXISTENTE, nao relacionada a FVI): para o viewer ADMIN,
        # uma linha com status ACTIVE e sem pendencia aberta e OCULTADA do
        # board por reducao de ruido (should_hide_row_for_admin). Sem
        # vinculo nenhum, "allocation" e None e a MESMA regra tambem oculta
        # (ver corpo da funcao). Para o controle positivo de ADMIN nao se
        # confundir com essa regra alheia, cada funcionario recebe uma
        # alocacao com line_status=RESTRICTED (nao-ACTIVE), que a regra
        # nunca oculta, independente de pendencia.
        self.active_line = self._make_restricted_allocation(
            self.active_employee, suffix=1
        )
        self.inactive_line = self._make_restricted_allocation(
            self.inactive_employee, suffix=2
        )

    def _make_restricted_allocation(self, employee, *, suffix):
        sim = SIMcard.objects.create(
            iccid=f"666600001111222{suffix:01d}3",
            carrier="CarrierBoardBase",
            status=SIMcard.Status.AVAILABLE,
        )
        phone_line = PhoneLine.objects.create(
            phone_number=f"+55119770000{suffix:03d}",
            sim_card=sim,
            status=PhoneLine.Status.ALLOCATED,
        )
        return LineAllocation.objects.create(
            employee=employee,
            phone_line=phone_line,
            is_active=True,
            line_status=LineAllocation.LineStatus.RESTRICTED,
        )

    def _board_url(self):
        return reverse(BOARD_URL)

    def _rows_for(self, response):
        return response.context["rows"]

    def _employee_ids_in_rows(self, response):
        return {row["employee"].pk for row in self._rows_for(response)}


class FT29_BoardGetHidesInactiveEmployeeRows(ActionBoardVisibilityTestBase):
    """FT29: Acoes do Dia (GET) nao deve listar funcionario inativo do
    escopo para SUPER/BACKOFFICE/GERENTE; ADMIN preserva visibilidade."""

    def test_restricted_role_rows_exclude_inactive_employee(self):
        self.client.force_login(self.supervisor)
        response = self.client.get(self._board_url())

        self.assertEqual(response.status_code, 200)
        ids = self._employee_ids_in_rows(response)
        self.assertIn(self.active_employee.pk, ids)
        self.assertNotIn(self.inactive_employee.pk, ids)

    def test_admin_rows_still_include_inactive_employee_as_control(self):
        self.client.force_login(self.admin)
        response = self.client.get(self._board_url())

        self.assertEqual(response.status_code, 200)
        ids = self._employee_ids_in_rows(response)
        self.assertIn(self.inactive_employee.pk, ids)


class FT30_ForgedPostToInactiveEmployeeMustNotWrite(
    ActionBoardVisibilityTestBase
):
    """FT30: POST forjado com employee_id de funcionario inativo dentro
    do escopo organizacional nao pode criar DailyUserAction nem alterar
    line_status, mesmo com payload valido."""

    def _valid_payload(self, employee):
        return {
            "day": timezone.localdate().isoformat(),
            "employee_id": str(employee.pk),
            "allocation_id": "",
            "action_type": DailyUserAction.ActionType.NEW_NUMBER,
            "note": "",
        }

    def test_restricted_role_post_to_inactive_employee_creates_no_action(self):
        self.client.force_login(self.supervisor)

        response = self.client.post(
            self._board_url(), self._valid_payload(self.inactive_employee)
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            DailyUserAction.objects.filter(employee=self.inactive_employee).exists()
        )

    def test_restricted_role_post_to_active_employee_creates_action_as_control(self):
        self.client.force_login(self.supervisor)

        response = self.client.post(
            self._board_url(), self._valid_payload(self.active_employee)
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            DailyUserAction.objects.filter(employee=self.active_employee).exists()
        )

    def test_admin_post_to_inactive_employee_creates_action_as_control(self):
        """Controle positivo: ADMIN preserva a capacidade de operar
        sobre funcionario inativo em Acoes do Dia."""
        self.client.force_login(self.admin)

        response = self.client.post(
            self._board_url(), self._valid_payload(self.inactive_employee)
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            DailyUserAction.objects.filter(employee=self.inactive_employee).exists()
        )


class FT31_StatusChangeBetweenGetAndPostIsReevaluated(
    ActionBoardVisibilityTestBase
):
    """FT31 (requisito 8): o funcionario e relido a cada requisicao --
    se ficou inativo entre o GET e o POST, o POST deve ser recusado,
    sem depender de garantia de concorrencia de banco."""

    def test_employee_deactivated_between_get_and_post_rejects_post(self):
        self.client.force_login(self.supervisor)

        get_response = self.client.get(self._board_url())
        self.assertEqual(get_response.status_code, 200)

        self.active_employee.status = Employee.Status.INACTIVE
        self.active_employee.save(update_fields=["status"])

        response = self.client.post(
            self._board_url(),
            {
                "day": timezone.localdate().isoformat(),
                "employee_id": str(self.active_employee.pk),
                "allocation_id": "",
                "action_type": DailyUserAction.ActionType.NEW_NUMBER,
                "note": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            DailyUserAction.objects.filter(employee=self.active_employee).exists()
        )


class FT32_SummaryParityWithBoardVisibility(ActionBoardVisibilityTestBase):
    """FT32 (requisito 6): summarize_action_board_responsibles faz
    consulta INDEPENDENTE da view (chama get_supervised_employees_queryset
    por conta propria) -- precisa excluir o funcionario inativo
    separadamente, nao por heranca automatica da correcao da view."""

    def setUp(self):
        super().setUp()
        sim = SIMcard.objects.create(
            iccid="88880000111122223333",
            carrier="CarrierBoard",
            status=SIMcard.Status.AVAILABLE,
        )
        self.phone_line = PhoneLine.objects.create(
            phone_number="+5511977776666",
            sim_card=sim,
            status=PhoneLine.Status.ALLOCATED,
        )
        self.allocation = LineAllocation.objects.create(
            employee=self.inactive_employee,
            phone_line=self.phone_line,
            is_active=True,
        )
        self.pendency = AllocationPendency.objects.create(
            employee=self.inactive_employee,
            allocation=self.allocation,
            action=AllocationPendency.ActionType.NEW_NUMBER,
            technical_responsible=self.admin,
        )
        self.pendency.pendency_submitted_at = timezone.now()
        self.pendency.save(update_fields=["pendency_submitted_at"])

    def test_summary_excludes_inactive_employee_open_pendency(self):
        result = summarize_action_board_responsibles(self.supervisor)

        self.assertEqual(result["summary"]["open_total"], 0)
        self.assertEqual(result["summary"]["assigned_total"], 0)
        self.assertNotIn(self.admin.pk, result["responsibles"])

    def test_summary_still_counts_active_employee_pendency_as_control(self):
        active_allocation = LineAllocation.objects.create(
            employee=self.active_employee,
            phone_line=PhoneLine.objects.create(
                phone_number="+5511977775555",
                sim_card=SIMcard.objects.create(
                    iccid="77770000111122223333",
                    carrier="CarrierBoardActive",
                    status=SIMcard.Status.AVAILABLE,
                ),
                status=PhoneLine.Status.ALLOCATED,
            ),
            is_active=True,
        )
        active_pendency = AllocationPendency.objects.create(
            employee=self.active_employee,
            allocation=active_allocation,
            action=AllocationPendency.ActionType.NEW_NUMBER,
            technical_responsible=self.admin,
        )
        active_pendency.pendency_submitted_at = timezone.now()
        active_pendency.save(update_fields=["pendency_submitted_at"])

        result = summarize_action_board_responsibles(self.supervisor)

        self.assertEqual(result["summary"]["open_total"], 1)
        self.assertEqual(result["summary"]["assigned_total"], 1)
        self.assertIn(self.admin.pk, result["responsibles"])

    def test_admin_summary_still_includes_inactive_employee_as_control(self):
        result = summarize_action_board_responsibles(self.admin)

        self.assertEqual(result["summary"]["open_total"], 1)
        self.assertEqual(result["summary"]["assigned_total"], 1)
        self.assertIn(self.admin.pk, result["responsibles"])
