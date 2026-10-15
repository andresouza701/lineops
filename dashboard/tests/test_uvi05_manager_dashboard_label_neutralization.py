"""
UVI-05 - Complemento ao RED original de ManagerDashboardView (ver
dashboard/tests/test_uvi03_inactive_account_visibility.py). Cobre dois
supervisores inativos distintos sem colapsar grupos/totais, e custo de
consulta/isolamento entre requisicoes sucessivas da projecao em lote
usada no painel.

Fonte de verdade: docs/superpowers/specs/2026-10-14-inactive-system-user-visibility-design.md
"""

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from employees.models import Employee
from users.models import SystemUser
from users.visibility import INACTIVE_ACCOUNT_LABEL


class TwoDistinctInactiveSupervisorGroupsDoNotCollapseTest(TestCase):
    """Dois supervisores inativos distintos, gerenciados pelo mesmo
    gerente, devem permanecer como DOIS grupos distintos (chave interna =
    e-mail real), cada um com seu proprio total -- o rotulo neutro
    identico nao pode fazer o painel mesclar as carteiras."""

    def setUp(self):
        self.manager = SystemUser.objects.create_user(
            email="gerente.dois.uvi05@test.com",
            password="StrongPass123",
            role=SystemUser.Role.GERENTE,
        )
        self.inactive_supervisor_a = SystemUser.objects.create_user(
            email="super.a.painel.uvi05@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
            manager_email=self.manager.email,
        )
        self.inactive_supervisor_a.is_active = False
        self.inactive_supervisor_a.save(update_fields=["is_active"])

        self.inactive_supervisor_b = SystemUser.objects.create_user(
            email="super.b.painel.uvi05@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
            manager_email=self.manager.email,
        )
        self.inactive_supervisor_b.is_active = False
        self.inactive_supervisor_b.save(update_fields=["is_active"])

        Employee.objects.create(
            full_name="Funcionario Painel A",
            corporate_email=self.inactive_supervisor_a.email,
            manager_email=self.manager.email,
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        Employee.objects.create(
            full_name="Funcionario Painel B1",
            corporate_email=self.inactive_supervisor_b.email,
            manager_email=self.manager.email,
            employee_id="Bebidas",
            teams="Araquari",
            status=Employee.Status.ACTIVE,
        )
        Employee.objects.create(
            full_name="Funcionario Painel B2",
            corporate_email=self.inactive_supervisor_b.email,
            manager_email=self.manager.email,
            employee_id="Bebidas",
            teams="Araquari",
            status=Employee.Status.ACTIVE,
        )
        self.client.force_login(self.manager)

    def test_both_groups_stay_separate_with_correct_totals(self):
        response = self.client.get(reverse("manager_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.inactive_supervisor_a.email)
        self.assertNotContains(response, self.inactive_supervisor_b.email)

        supervisor_dashboards = response.context["supervisor_dashboards"]
        group_a = next(
            item
            for item in supervisor_dashboards
            if item["supervisor"] == self.inactive_supervisor_a.email
        )
        group_b = next(
            item
            for item in supervisor_dashboards
            if item["supervisor"] == self.inactive_supervisor_b.email
        )

        # Controle: grupos distintos (nao mesclados), cada um com rotulo
        # neutro, mas totais e carteiras proprios e intactos.
        self.assertEqual(group_a["supervisor_label"], INACTIVE_ACCOUNT_LABEL)
        self.assertEqual(group_b["supervisor_label"], INACTIVE_ACCOUNT_LABEL)
        self.assertEqual(group_a["total_logged"], 1)
        self.assertEqual(group_b["total_logged"], 2)
        self.assertContains(response, "Alimentos")
        self.assertContains(response, "Bebidas")
        self.assertContains(response, INACTIVE_ACCOUNT_LABEL, count=2)


class ManagerDashboardQueryCostAndIsolationTest(TestCase):
    """Custo de consulta da projecao do painel nao cresce linearmente com
    o numero de supervisores/funcionarios, e requisicoes sucessivas nao
    contaminam uma a outra."""

    def setUp(self):
        self.manager = SystemUser.objects.create_user(
            email="gerente.custo.uvi05@test.com",
            password="StrongPass123",
            role=SystemUser.Role.GERENTE,
        )
        self.client.force_login(self.manager)

    def _create_supervisors_with_employees(self, count, *, inactive, batch):
        for index in range(count):
            supervisor = SystemUser.objects.create_user(
                email=f"super.custo.{batch}.{index}.uvi05@test.com",
                password="StrongPass123",
                role=SystemUser.Role.SUPER,
                manager_email=self.manager.email,
            )
            if index < inactive:
                supervisor.is_active = False
                supervisor.save(update_fields=["is_active"])
            Employee.objects.create(
                full_name=f"Funcionario Custo {batch} {index}",
                corporate_email=supervisor.email,
                manager_email=self.manager.email,
                employee_id="Alimentos",
                teams="Joinville",
                status=Employee.Status.ACTIVE,
            )

    def test_dashboard_query_count_is_constant_regardless_of_supervisor_count(self):
        self._create_supervisors_with_employees(2, inactive=1, batch="small")
        with CaptureQueriesContext(connection) as small_ctx:
            response_small = self.client.get(reverse("manager_dashboard"))
        self.assertEqual(response_small.status_code, 200)
        small_count = len(small_ctx.captured_queries)

        self._create_supervisors_with_employees(15, inactive=8, batch="large")
        with CaptureQueriesContext(connection) as large_ctx:
            response_large = self.client.get(reverse("manager_dashboard"))
        self.assertEqual(response_large.status_code, 200)
        large_count = len(large_ctx.captured_queries)

        self.assertEqual(
            small_count,
            large_count,
            "custo de consulta do painel nao pode crescer com o numero de "
            "supervisores/funcionarios distintos (sem N+1 por item)",
        )

    def test_successive_requests_do_not_leak_label_state(self):
        inactive_supervisor = SystemUser.objects.create_user(
            email="super.isolamento.painel.uvi05@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
            manager_email=self.manager.email,
        )
        inactive_supervisor.is_active = False
        inactive_supervisor.save(update_fields=["is_active"])
        Employee.objects.create(
            full_name="Funcionario Isolamento Painel",
            corporate_email=inactive_supervisor.email,
            manager_email=self.manager.email,
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )

        response_first = self.client.get(reverse("manager_dashboard"))
        self.assertEqual(response_first.status_code, 200)
        self.assertNotContains(response_first, inactive_supervisor.email)

        response_second = self.client.get(reverse("manager_dashboard"))
        self.assertEqual(response_second.status_code, 200)
        self.assertNotContains(response_second, inactive_supervisor.email)
