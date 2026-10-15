"""
UVI-05 - Complemento aos RED de apresentacao em
employees/tests/test_uvi03_inactive_account_visibility.py (lista/AJAX/
detalhe). Cobre lacunas reais: string legada sem conta correspondente (nao
deve ser mascarada por suposicao), custo de consulta sem crescimento linear
por item, e alternancia de viewers sem reuso indevido de resultado.

RETIFICADO na conferencia corretiva de UVI-05 (desvio relatado pelo
usuario): a entrega original desta etapa fazia a neutralizacao valer para
QUALQUER viewer, inclusive ADMIN/DEV -- contradizendo o contrato aprovado
(Spec Summary/UVI-01: "ADMIN e DEV podem continuar vendo contas inativas em
listas, buscas ou seletores de contas") e uma justificativa escrita na
spec nao substitui aprovacao do usuario. Corrigido: a neutralizacao agora
depende do viewer (reutilizando users.visibility.viewer_is_exempt), e os
testes abaixo que antes usavam ADMIN para exercitar o rotulo neutro foram
trocados para um viewer genuinamente restrito (GERENTE, com escopo real
via manager_email -- EMPLOYEE_ACCESS_ROLES inclui GERENTE). Testes que
provam a excecao ADMIN/DEV ficam em
employees/tests/test_uvi03_inactive_account_visibility.py (classe T08,
retificada na mesma conferencia) e em
employees/tests/test_uvi05b_role_scoped_neutralization.py (novo).

Fonte de verdade: docs/superpowers/specs/2026-10-14-inactive-system-user-visibility-design.md
"""

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from employees.models import Employee
from users.models import SystemUser
from users.visibility import INACTIVE_ACCOUNT_LABEL


class LegacySupervisorStringWithoutMatchingAccountTest(TestCase):
    """Valor legado (corporate_email sem SystemUser correspondente) nao
    pode ser classificado como inativo por suposicao -- deve continuar
    aparecendo em texto puro na lista (viewer restrito GERENTE, onde a
    politica de mascaramento realmente atua) e no detalhe (unica rota
    alcancavel e ADMIN-only, usado aqui so como controle de alcance)."""

    def setUp(self):
        self.admin_viewer = SystemUser.objects.create_user(
            email="admin.legado.uvi05@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.gerente_viewer = SystemUser.objects.create_user(
            email="gerente.legado.uvi05@test.com",
            password="StrongPass123",
            role=SystemUser.Role.GERENTE,
        )
        self.employee = Employee.objects.create(
            full_name="Funcionario Com Supervisor Legado",
            corporate_email="supervisor.legado.sem.conta.uvi05@test.com",
            manager_email=self.gerente_viewer.email,
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )

    def test_employee_list_does_not_mask_legacy_string_without_account_for_restricted_viewer(self):
        self.client.force_login(self.gerente_viewer)
        response = self.client.get(reverse("employees:employee_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "supervisor.legado.sem.conta.uvi05@test.com")
        self.assertNotContains(response, INACTIVE_ACCOUNT_LABEL)

    def test_employee_detail_does_not_mask_legacy_string_without_account(self):
        self.client.force_login(self.admin_viewer)
        response = self.client.get(
            reverse("employees:employee_detail", args=[self.employee.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "supervisor.legado.sem.conta.uvi05@test.com")
        self.assertNotContains(response, INACTIVE_ACCOUNT_LABEL)


class TwoDistinctInactiveSupervisorsDoNotCollapseTest(TestCase):
    """Dois funcionarios com DOIS supervisores inativos distintos, vistos
    por um viewer GENUINAMENTE RESTRITO (GERENTE, escopo real via
    manager_email dos supervisores): ambos sao mascarados com o mesmo
    rotulo neutro, mas cada funcionario/linha permanece distinto --
    rotulo igual nao significa identidade igual, e nenhum dado e perdido
    na projecao em lote."""

    def setUp(self):
        self.gerente_viewer = SystemUser.objects.create_user(
            email="gerente.dois.uvi05@test.com",
            password="StrongPass123",
            role=SystemUser.Role.GERENTE,
        )
        self.inactive_super_a = SystemUser.objects.create_user(
            email="super.a.inativo.uvi05@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
            manager_email=self.gerente_viewer.email,
        )
        self.inactive_super_a.is_active = False
        self.inactive_super_a.save(update_fields=["is_active"])

        self.inactive_super_b = SystemUser.objects.create_user(
            email="super.b.inativo.uvi05@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
            manager_email=self.gerente_viewer.email,
        )
        self.inactive_super_b.is_active = False
        self.inactive_super_b.save(update_fields=["is_active"])

        self.employee_a = Employee.objects.create(
            full_name="Funcionario Alfa Supervisor A",
            corporate_email=self.inactive_super_a.email,
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        self.employee_b = Employee.objects.create(
            full_name="Funcionario Beta Supervisor B",
            corporate_email=self.inactive_super_b.email,
            employee_id="Bebidas",
            teams="Araquari",
            status=Employee.Status.ACTIVE,
        )
        self.client.force_login(self.gerente_viewer)

    def test_both_inactive_supervisors_are_masked_without_losing_either_employee(self):
        response = self.client.get(reverse("employees:employee_list"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.inactive_super_a.email)
        self.assertNotContains(response, self.inactive_super_b.email)
        self.assertContains(response, "Funcionario Alfa Supervisor A")
        self.assertContains(response, "Funcionario Beta Supervisor B")
        # Controle: o rotulo neutro aparece duas vezes (uma por funcionario
        # distinto), nao colapsado em uma unica linha.
        self.assertContains(response, INACTIVE_ACCOUNT_LABEL, count=2)

    def test_both_inactive_supervisors_are_masked_in_ajax_payload(self):
        response = self.client.get(
            reverse("employees:employee_list"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        full_name_by_label = {
            row["full_name"]: row["corporate_email"] for row in payload["data"]
        }
        self.assertEqual(
            full_name_by_label["Funcionario Alfa Supervisor A"],
            INACTIVE_ACCOUNT_LABEL,
        )
        self.assertEqual(
            full_name_by_label["Funcionario Beta Supervisor B"],
            INACTIVE_ACCOUNT_LABEL,
        )
        emails_in_payload = {row["corporate_email"] for row in payload["data"]}
        self.assertNotIn(self.inactive_super_a.email, emails_in_payload)
        self.assertNotIn(self.inactive_super_b.email, emails_in_payload)


class QueryCostAndViewerIsolationTest(TestCase):
    """Custo de consulta da projecao em lote (viewer restrito GERENTE, onde
    a mascara realmente executa a consulta de resolucao) nao cresce
    linearmente com o numero de funcionarios/identidades distintas. E
    alternancia de viewers DIFERENTES (ADMIN -> BACKOFFICE -> ADMIN) nao
    reusa resultado indevido: ADMIN sempre ve a identidade real (excecao
    de role, autorizacao previa), BACKOFFICE sempre ve o rotulo neutro --
    nenhum dos dois contamina o outro por ordem de execucao."""

    def _create_employees(self, count, *, inactive_supervisors, batch, manager_email):
        for index in range(count):
            supervisor = SystemUser.objects.create_user(
                email=f"super.cost.{batch}.{index}.uvi05@test.com",
                password="StrongPass123",
                role=SystemUser.Role.SUPER,
                manager_email=manager_email,
            )
            if index < inactive_supervisors:
                supervisor.is_active = False
                supervisor.save(update_fields=["is_active"])
            Employee.objects.create(
                full_name=f"Funcionario Custo {batch} {index}",
                corporate_email=supervisor.email,
                employee_id="Alimentos",
                teams="Joinville",
                status=Employee.Status.ACTIVE,
            )

    def setUp(self):
        self.admin_viewer = SystemUser.objects.create_user(
            email="admin.custo.uvi05@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.gerente_viewer = SystemUser.objects.create_user(
            email="gerente.custo.uvi05@test.com",
            password="StrongPass123",
            role=SystemUser.Role.GERENTE,
        )

    def test_list_rendering_query_count_is_constant_regardless_of_row_count(self):
        self.client.force_login(self.gerente_viewer)

        self._create_employees(
            2, inactive_supervisors=1, batch="small", manager_email=self.gerente_viewer.email
        )
        with CaptureQueriesContext(connection) as small_ctx:
            response_small = self.client.get(reverse("employees:employee_list"))
        self.assertEqual(response_small.status_code, 200)
        small_count = len(small_ctx.captured_queries)

        self._create_employees(
            20, inactive_supervisors=10, batch="large", manager_email=self.gerente_viewer.email
        )
        with CaptureQueriesContext(connection) as large_ctx:
            response_large = self.client.get(reverse("employees:employee_list"))
        self.assertEqual(response_large.status_code, 200)
        large_count = len(large_ctx.captured_queries)

        self.assertEqual(
            small_count,
            large_count,
            "custo de consulta da lista nao pode crescer com o numero de "
            "funcionarios/supervisores distintos (sem N+1 por item)",
        )

    def test_alternating_viewers_do_not_leak_or_reuse_each_others_result(self):
        inactive_super = SystemUser.objects.create_user(
            email="super.isolamento.uvi05@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
            manager_email=self.gerente_viewer.email,
        )
        inactive_super.is_active = False
        inactive_super.save(update_fields=["is_active"])
        Employee.objects.create(
            full_name="Funcionario Isolamento",
            corporate_email=inactive_super.email,
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )

        backoffice_viewer = SystemUser.objects.create_user(
            email="backoffice.isolamento.uvi05@test.com",
            password="StrongPass123",
            role=SystemUser.Role.BACKOFFICE,
            supervisor_email=inactive_super.email,
        )

        # Primeira requisicao: ADMIN -- excecao de role, deve ver a
        # identidade real (autorizacao previa, nao concessao nova).
        self.client.force_login(self.admin_viewer)
        response_admin = self.client.get(reverse("employees:employee_list"))
        self.assertEqual(response_admin.status_code, 200)
        self.assertContains(response_admin, inactive_super.email)

        # Segunda requisicao, viewer restrito: deve ver o rotulo neutro,
        # nao contaminado pelo resultado real que o ADMIN acabou de ver.
        self.client.force_login(backoffice_viewer)
        response_backoffice = self.client.get(reverse("employees:employee_list"))
        self.assertEqual(response_backoffice.status_code, 200)
        self.assertNotContains(response_backoffice, inactive_super.email)
        self.assertContains(response_backoffice, INACTIVE_ACCOUNT_LABEL)

        # Terceira requisicao, volta para ADMIN: identidade real de novo,
        # sem ter sido "contaminado" pelo mascaramento da requisicao
        # anterior (nenhum estado de viewer em cache compartilhado).
        self.client.force_login(self.admin_viewer)
        response_admin_again = self.client.get(reverse("employees:employee_list"))
        self.assertEqual(response_admin_again.status_code, 200)
        self.assertContains(response_admin_again, inactive_super.email)
