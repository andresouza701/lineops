"""
UVI-05 - Conferencia corretiva: controles de que a excecao ADMIN/DEV na
politica de neutralizacao (users.visibility) nao concede acesso novo a
rota nenhuma, e de que DEV mantem a mesma negacao de rota que tinha antes
desta feature (EMPLOYEE_ACCESS_ROLES/allowed_roles inalterados).

Desvio relatado pelo usuario: a entrega original desta etapa neutralizava
employee_list/employee_detail/manager_dashboard para QUALQUER viewer,
inclusive ADMIN/DEV -- contradizendo o contrato aprovado. Corrigido em
users/visibility.py::resolve_inactive_email_labels (agora recebe o
viewer e reutiliza viewer_is_exempt, a MESMA excecao central de UVI-04).
Este arquivo prova a fronteira correta: excecao de POLITICA (ve
identidade onde JA tem acesso) nao e excecao de ROTA (nao abre tela nova).

Fonte de verdade: docs/superpowers/specs/2026-10-14-inactive-system-user-visibility-design.md
"""

from django.test import TestCase
from django.urls import reverse

from employees.models import Employee
from users.models import SystemUser
from users.visibility import viewer_is_exempt


class DevExemptInPolicyButNoNewRouteAccessTest(TestCase):
    """DEV e excecao de ROLE na politica (viewer_is_exempt == True), mas
    nao esta em EMPLOYEE_ACCESS_ROLES nem em
    ManagerDashboardView.allowed_roles -- a excecao na politica de
    apresentacao nao pode abrir rota antes negada."""

    def setUp(self):
        self.dev_viewer = SystemUser.objects.create_user(
            email="dev.rota.uvi05.correcao@test.com",
            password="StrongPass123",
            role=SystemUser.Role.DEV,
        )
        self.inactive_super = SystemUser.objects.create_user(
            email="super.inativo.rota.uvi05.correcao@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.inactive_super.is_active = False
        self.inactive_super.save(update_fields=["is_active"])
        self.employee = Employee.objects.create(
            full_name="Funcionario Rota DEV",
            corporate_email=self.inactive_super.email,
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        self.client.force_login(self.dev_viewer)

    def test_dev_is_exempt_in_the_policy_itself(self):
        # Controle de fronteira: a politica central concede a excecao de
        # role a DEV (mesma condicao de ADMIN) -- o que falta e a rota.
        self.assertTrue(viewer_is_exempt(self.dev_viewer))

    def test_dev_still_denied_on_employee_list_route(self):
        response = self.client.get(reverse("employees:employee_list"))
        self.assertEqual(response.status_code, 403)

    def test_dev_still_denied_on_employee_detail_route(self):
        response = self.client.get(
            reverse("employees:employee_detail", args=[self.employee.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_dev_still_denied_on_manager_dashboard_route(self):
        response = self.client.get(reverse("manager_dashboard"))
        self.assertEqual(response.status_code, 403)


class AdminExemptMatchesPreviouslyAuthorizedRoutesOnlyTest(TestCase):
    """ADMIN e excecao de role, e JA tinha acesso a employee_list e
    employee_detail (EMPLOYEE_ACCESS_ROLES/allowed_roles inalterados por
    esta feature) -- a excecao na politica de apresentacao apenas
    preserva identidade onde a rota ja era alcancavel, nao abre nada
    novo. Controle negativo: GERENTE (restrito) continua sem acesso a
    employee_detail (ADMIN-only), com ou sem a excecao de politica."""

    def setUp(self):
        self.gerente_viewer = SystemUser.objects.create_user(
            email="gerente.sem.detalhe.uvi05.correcao@test.com",
            password="StrongPass123",
            role=SystemUser.Role.GERENTE,
        )
        self.employee = Employee.objects.create(
            full_name="Funcionario Controle Rota",
            corporate_email="qualquer.supervisor@test.com",
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        self.client.force_login(self.gerente_viewer)

    def test_gerente_still_denied_on_employee_detail_admin_only_route(self):
        response = self.client.get(
            reverse("employees:employee_detail", args=[self.employee.pk])
        )
        self.assertEqual(response.status_code, 403)
