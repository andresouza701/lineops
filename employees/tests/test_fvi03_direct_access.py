"""
FVI-03 - Testes RED de acesso direto GET/POST a funcionario inativo via
/employees/<pk>/edit/ (requisitos 2, 8 e parte do 9 do checklist desta
etapa).

Fonte de verdade: docs/superpowers/specs/2026-10-14-inactive-system-user-visibility-design.md
(FVI-01 contrato itens 3/6/9/10; FVI-02 fechamento). Node IDs FT07-FT11
derivados nesta etapa (FVI-03).

Nenhuma politica foi implementada ainda (FVI-04). Os testes que exercitam
a lacuna (404 generico para inativo) falham hoje porque
EmployeeUpdateView.get_queryset nao filtra por status -- documentado como
RED real, nao placeholder. Testes de controle (escopo, exclusao logica,
ADMIN, historico) confirmam que comportamento preexistente permanece
intacto.
"""

from django.test import TestCase
from django.urls import reverse

from employees.models import Employee, EmployeeHistory
from users.models import SystemUser


class DirectAccessTestBase(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="admin.fvi03.direct@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.supervisor = SystemUser.objects.create_user(
            email="super.fvi03.direct@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.other_supervisor = SystemUser.objects.create_user(
            email="super.outro.fvi03.direct@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.backoffice = SystemUser.objects.create_user(
            email="backoffice.fvi03.direct@test.com",
            password="StrongPass123",
            role=SystemUser.Role.BACKOFFICE,
            supervisor_email=self.supervisor.email,
        )
        self.manager = SystemUser.objects.create_user(
            email="gerente.fvi03.direct@test.com",
            password="StrongPass123",
            role=SystemUser.Role.GERENTE,
        )
        self.operator = SystemUser.objects.create_user(
            email="operator.fvi03.direct@test.com",
            password="StrongPass123",
            role=SystemUser.Role.OPERATOR,
        )

        self.inactive_employee = Employee.objects.create(
            full_name="Funcionario Inativo Editavel",
            corporate_email=self.supervisor.email,
            manager_email=self.manager.email,
            employee_id="EMP-FVI03-DIR-I",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.INACTIVE,
        )
        self.active_employee = Employee.objects.create(
            full_name="Funcionario Ativo Editavel",
            corporate_email=self.supervisor.email,
            manager_email=self.manager.email,
            employee_id="EMP-FVI03-DIR-A",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )
        self.out_of_scope_employee = Employee.objects.create(
            full_name="Funcionario Fora De Escopo",
            corporate_email=self.other_supervisor.email,
            employee_id="EMP-FVI03-DIR-O",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )

    def _edit_url(self, employee):
        return reverse("employees:employee_update", args=[employee.pk])


class FT07_GetDirectAccessToInactiveMustBe404(DirectAccessTestBase):
    """FT07: GET em /employees/<pk>/edit/ para funcionario inativo deve
    retornar 404 generico (sem identidade) para papel com permissao de
    rota, mas sem visibilidade do objeto."""

    def test_super_get_inactive_employee_edit_is_404(self):
        self.client.force_login(self.supervisor)
        response = self.client.get(self._edit_url(self.inactive_employee))

        self.assertEqual(response.status_code, 404)
        self.assertNotContains(
            response, "Funcionario Inativo Editavel", status_code=404
        )

    def test_backoffice_get_inactive_employee_edit_is_404(self):
        self.client.force_login(self.backoffice)
        response = self.client.get(self._edit_url(self.inactive_employee))

        self.assertEqual(response.status_code, 404)

    def test_manager_get_inactive_employee_edit_is_404(self):
        self.client.force_login(self.manager)
        response = self.client.get(self._edit_url(self.inactive_employee))

        self.assertEqual(response.status_code, 404)

    def test_super_get_active_employee_edit_still_200_as_control(self):
        self.client.force_login(self.supervisor)
        response = self.client.get(self._edit_url(self.active_employee))

        self.assertEqual(response.status_code, 200)

    def test_admin_get_inactive_employee_edit_still_200_as_control(self):
        self.client.force_login(self.admin)
        response = self.client.get(self._edit_url(self.inactive_employee))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Funcionario Inativo Editavel")

    def test_operator_still_denied_before_activity_check_as_control(self):
        """Controle: quem nao tem permissao de rota alguma continua
        negado por 403 (RoleRequiredMixin), nunca confundido com o 404
        de visibilidade."""
        self.client.force_login(self.operator)
        response = self.client.get(self._edit_url(self.inactive_employee))

        self.assertEqual(response.status_code, 403)

    def test_scope_denial_for_active_out_of_scope_employee_preserved(self):
        """Controle: a negacao por ESCOPO organizacional (nao por
        status) para um funcionario ativo fora do escopo do SUPER
        continua 404, independente da nova regra de atividade."""
        self.client.force_login(self.supervisor)
        response = self.client.get(self._edit_url(self.out_of_scope_employee))

        self.assertEqual(response.status_code, 404)


class FT08_PostDirectAccessToInactiveMustNotMutate(DirectAccessTestBase):
    """FT08: POST forjado para funcionario inativo oculto nao pode
    alterar nenhum campo persistido, mesmo que o papel tenha permissao
    de rota e os dados do formulario sejam validos."""

    def _valid_payload(self, *, full_name):
        return {
            "full_name": full_name,
            "email": "negociador.forjado@test.com",
            "corporate_email": self.supervisor.email,
            "manager_email": self.manager.email,
            "employee_id": "Ambiental",
            "teams": Employee.UnitChoices.ARAQUARI,
            "status": Employee.Status.ACTIVE,
            "pa": "",
        }

    def test_super_post_to_inactive_employee_is_404_and_does_not_mutate(self):
        self.client.force_login(self.supervisor)
        original_status = self.inactive_employee.status
        original_email = self.inactive_employee.email

        response = self.client.post(
            self._edit_url(self.inactive_employee),
            self._valid_payload(full_name="Nome Forjado Pelo Super"),
        )

        self.assertEqual(response.status_code, 404)
        self.inactive_employee.refresh_from_db()
        self.assertEqual(self.inactive_employee.status, original_status)
        self.assertEqual(self.inactive_employee.email, original_email)
        self.assertEqual(
            self.inactive_employee.full_name, "Funcionario Inativo Editavel"
        )

    def test_admin_post_to_inactive_employee_still_succeeds_as_control(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            self._edit_url(self.inactive_employee),
            self._valid_payload(full_name="Reativado Pelo Admin"),
        )

        self.assertEqual(response.status_code, 302)
        self.inactive_employee.refresh_from_db()
        self.assertEqual(self.inactive_employee.status, Employee.Status.ACTIVE)


class FT09_StatusChangeBetweenGetAndPostIsReevaluated(DirectAccessTestBase):
    """FT09 (requisito 8): o status e relido a cada requisicao -- se o
    funcionario ficou inativo entre o GET e o POST, o POST deve ser
    recusado pela mesma regra, sem depender de qualquer garantia de
    concorrencia de banco (apenas o fato de get_queryset/get_object
    serem chamados a cada requisicao)."""

    def test_employee_deactivated_between_get_and_post_rejects_post(self):
        self.client.force_login(self.supervisor)

        get_response = self.client.get(self._edit_url(self.active_employee))
        self.assertEqual(get_response.status_code, 200)

        self.active_employee.status = Employee.Status.INACTIVE
        self.active_employee.save(update_fields=["status"])

        post_response = self.client.post(
            self._edit_url(self.active_employee),
            {
                "full_name": "Nome Apos Inativacao",
                "email": "",
                "corporate_email": self.supervisor.email,
                "manager_email": self.manager.email,
                "employee_id": "Ambiental",
                "teams": Employee.UnitChoices.JOINVILLE,
                "status": Employee.Status.ACTIVE,
                "pa": "",
            },
        )

        self.assertEqual(post_response.status_code, 404)
        self.active_employee.refresh_from_db()
        self.assertEqual(
            self.active_employee.full_name, "Funcionario Ativo Editavel"
        )


class FT10_LogicalDeletionAndHistoryArePreserved(DirectAccessTestBase):
    """FT10 (requisito 9): exclusao logica (is_deleted) e historico sao
    conceitos distintos do status de atividade e nao devem regredir com
    a FVI. Controles positivos (comportamento ja existente, nao uma
    lacuna nova)."""

    def test_soft_deleted_employee_edit_route_is_404_for_admin_too(self):
        self.inactive_employee.delete()  # soft delete (is_deleted=True)

        self.client.force_login(self.admin)
        response = self.client.get(self._edit_url(self.inactive_employee))

        self.assertEqual(response.status_code, 404)

    def test_admin_history_view_still_shows_inactive_employee_history(self):
        EmployeeHistory.objects.create(
            employee=self.inactive_employee,
            action=EmployeeHistory.ActionType.STATUS_CHANGED,
            old_value="active",
            new_value="inactive",
            description="Teste FVI-03",
        )

        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("employees:employee_history", args=[self.inactive_employee.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Funcionario Inativo Editavel")


class FT11_ScopeAndStatusAreIndependentDenialReasons(DirectAccessTestBase):
    """FT11 (requisito 9): a negacao por escopo organizacional (super
    sem vinculo) e a negacao por status inativo nao devem ser
    confundidas -- ambas resultam em 404, mas por causas diferentes.
    Garante que a nova regra de status nao enfraquece nem substitui a
    de escopo (ela deve continuar valendo mesmo se o funcionario de
    outro escopo estiver ATIVO, como ja comprovado em FT07)."""

    def test_backoffice_without_linked_supervisor_gets_scope_denial_regardless_of_status(
        self,
    ):
        isolated_backoffice = SystemUser.objects.create_user(
            email="backoffice.isolado.fvi03.direct@test.com",
            password="StrongPass123",
            role=SystemUser.Role.BACKOFFICE,
        )
        self.client.force_login(isolated_backoffice)

        response = self.client.get(self._edit_url(self.active_employee))

        self.assertEqual(response.status_code, 404)
