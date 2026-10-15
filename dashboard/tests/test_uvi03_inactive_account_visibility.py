"""
UVI-03 - Teste RED da visibilidade de identidade de supervisor inativo no
painel por gerente (ManagerDashboardView).

Fonte de verdade: docs/superpowers/specs/2026-10-14-inactive-system-user-visibility-design.md
(UVI-01/UVI-02). Node ID T08 do checklist derivado em UVI-02 (U10).

dashboard/views.py::ManagerDashboardView agrupa funcionarios pelo proprio
e-mail do supervisor (get_managed_supervisor_emails, sem filtro de
atividade por design -- escopo de dados, U11) e o template
manager_dashboard.html imprime esse e-mail como rotulo do grupo. Um
supervisor SUPER inativo, mas ainda gerenciado pelo gerente, continua
aparecendo com o proprio e-mail como identidade, violando o contrato de
rotulo neutro "Usuario inativo" -- sem perder funcionarios/vinculos/totais,
que devem ser preservados (U10/U11).
"""

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from dashboard.models import DailyUserAction
from employees.models import Employee
from users.models import SystemUser


class T08_ManagerDashboardRevealsInactiveSupervisorEmailTest(TestCase):
    def setUp(self):
        self.manager = SystemUser.objects.create_user(
            email="gerente.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.GERENTE,
        )
        self.inactive_supervisor = SystemUser.objects.create_user(
            email="super.inativo.painel.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
            manager_email=self.manager.email,
        )
        self.inactive_supervisor.is_active = False
        self.inactive_supervisor.save(update_fields=["is_active"])

        self.employee = Employee.objects.create(
            full_name="Funcionario Painel UVI03",
            corporate_email=self.inactive_supervisor.email,
            manager_email=self.manager.email,
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        self.client.force_login(self.manager)

    def test_manager_dashboard_must_not_reveal_inactive_supervisor_email(self):
        response = self.client.get(reverse("manager_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.inactive_supervisor.email)

    def test_manager_dashboard_preserves_employee_and_group_totals(self):
        """Controle positivo: a ocultacao da identidade nao pode zerar os
        totais do grupo nem remover a carteira do funcionario -- inativacao
        de conta e escopo de dados sao preocupacoes distintas (U11). O
        template agrega por carteira (nao lista nome de funcionario), por
        isso o controle verifica a carteira "Alimentos" e os totais, nao o
        full_name (corrigido apos observar o HTML real na primeira
        execucao: nenhum full_name de funcionario e impresso nesta pagina)."""
        response = self.client.get(reverse("manager_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alimentos")
        supervisor_dashboards = response.context["supervisor_dashboards"]
        group = next(
            (
                item
                for item in supervisor_dashboards
                if item["supervisor"] == self.inactive_supervisor.email
            ),
            None,
        )
        self.assertIsNotNone(
            group,
            "grupo do supervisor inativo deve existir (escopo preservado); "
            "se a rotulagem mudar o rotulo nao sera mais o e-mail cru",
        )
        self.assertEqual(group["total_logged"], 1)

    def test_manager_dashboard_actions_also_reveal_inactive_supervisor_email(self):
        DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=self.employee,
            action_type=DailyUserAction.ActionType.NEW_NUMBER,
            is_resolved=False,
        )

        response = self.client.get(reverse("manager_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.inactive_supervisor.email)
