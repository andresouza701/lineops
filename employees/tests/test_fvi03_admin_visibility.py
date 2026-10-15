"""
FVI-03 - Testes RED da visibilidade de funcionarios inativos no Admin de
Employee (requisito 3 do checklist desta etapa).

Fonte de verdade: docs/superpowers/specs/2026-10-14-inactive-system-user-visibility-design.md
(FVI-02, "EmployeeAdmin.get_queryset" -- F14/F15). Node IDs FT12-FT15
derivados nesta etapa (FVI-03). Nenhum teste HTTP de Admin existia para
Employee antes desta etapa (confirmado em FVI-02); criados do zero no
padrao de users/test_uvi03_admin_inactive_visibility.py.

EmployeeAdmin.get_queryset aplica hoje somente scope_employee_queryset,
sem filtro de status (F14); os testes que exercitam essa lacuna falham
de verdade (RED), nao sao placeholders.
"""

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from employees.models import Employee
from users.models import SystemUser

RESTRICTED_ROLES = [
    SystemUser.Role.SUPER,
    SystemUser.Role.BACKOFFICE,
    SystemUser.Role.GERENTE,
]
EXEMPT_ROLES = [SystemUser.Role.ADMIN, SystemUser.Role.DEV]


def _grant_full_employee_perms(user):
    """Permissao tecnica suficiente para alcancar a rota do Admin de
    Employee (view/change/delete/add), isolando o eixo "permissao" do
    eixo "status do funcionario" (mesmo padrao de UVI-03 para
    SystemUser)."""
    perms = Permission.objects.filter(content_type__app_label="employees")
    user.user_permissions.set(perms)
    user.is_staff = True
    user.save(update_fields=["is_staff"])


class EmployeeAdminInactiveVisibilityTestBase(TestCase):
    """Escopo organizacional (scope_employee_queryset) e um eixo
    independente do status de atividade: para SUPER/BACKOFFICE/GERENTE
    nao ficarem vazios de forma vacua (o que tornaria "nao lista o
    inativo" verdadeiro so porque NADA e listado), os dois funcionarios
    fixos sao vinculados a um supervisor/gerente fixo, e cada viewer
    restrito e criado DENTRO desse mesmo vinculo (_make_viewer)."""

    FIXED_SUPERVISOR_EMAIL = "supervisor.fvi03.admin@test.com"
    FIXED_MANAGER_EMAIL = "gerente.fvi03.admin@test.com"

    def setUp(self):
        self.inactive_employee = Employee.objects.create(
            full_name="Funcionario Inativo Admin",
            corporate_email=self.FIXED_SUPERVISOR_EMAIL,
            manager_email=self.FIXED_MANAGER_EMAIL,
            employee_id="EMP-FVI03-ADM-I",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.INACTIVE,
        )
        self.active_employee = Employee.objects.create(
            full_name="Funcionario Ativo Admin",
            corporate_email=self.FIXED_SUPERVISOR_EMAIL,
            manager_email=self.FIXED_MANAGER_EMAIL,
            employee_id="EMP-FVI03-ADM-A",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )

    def _make_viewer(self, role, *, is_staff=True, is_superuser=False):
        extra = {}
        if role == SystemUser.Role.SUPER:
            email = self.FIXED_SUPERVISOR_EMAIL
        elif role == SystemUser.Role.GERENTE:
            email = self.FIXED_MANAGER_EMAIL
        elif role == SystemUser.Role.BACKOFFICE:
            email = f"viewer.{role}.fvi03.admin@test.com"
            extra["supervisor_email"] = self.FIXED_SUPERVISOR_EMAIL
        else:
            email = f"viewer.{role}.fvi03.admin@test.com"

        viewer = SystemUser.objects.create_user(
            email=email,
            password="StrongPass123",
            role=role,
            **extra,
        )
        if is_superuser:
            viewer.is_superuser = True
        viewer.is_staff = is_staff
        viewer.save(update_fields=["is_staff", "is_superuser"])
        if is_staff:
            _grant_full_employee_perms(viewer)
        return viewer


class FT12_ChangelistSearchCountTests(EmployeeAdminInactiveVisibilityTestBase):
    """FT12: changelist/busca/contagem no Admin de Employee nao devem
    expor o funcionario inativo para papel restrito; ADMIN/DEV
    preservam visibilidade."""

    def test_restricted_role_changelist_must_not_list_inactive_employee(self):
        viewer = self._make_viewer(SystemUser.Role.SUPER)
        self.client.force_login(viewer)

        response = self.client.get(reverse("admin:employees_employee_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Funcionario Inativo Admin")

    def test_restricted_role_changelist_count_excludes_inactive(self):
        viewer = self._make_viewer(SystemUser.Role.GERENTE)
        self.client.force_login(viewer)

        response = self.client.get(reverse("admin:employees_employee_changelist"))

        self.assertEqual(response.status_code, 200)
        cl = response.context["cl"]
        self.assertNotIn(self.inactive_employee, list(cl.result_list))
        self.assertEqual(cl.paginator.count, 1)

    def test_restricted_role_search_does_not_find_inactive_employee(self):
        viewer = self._make_viewer(SystemUser.Role.BACKOFFICE)
        self.client.force_login(viewer)

        response = self.client.get(
            reverse("admin:employees_employee_changelist"),
            {"q": self.inactive_employee.employee_id},
        )

        self.assertEqual(response.status_code, 200)
        cl = response.context["cl"]
        self.assertNotIn(self.inactive_employee, list(cl.result_list))

    def test_restricted_role_search_finds_active_employee_as_control(self):
        viewer = self._make_viewer(SystemUser.Role.BACKOFFICE)
        self.client.force_login(viewer)

        response = self.client.get(
            reverse("admin:employees_employee_changelist"),
            {"q": self.active_employee.employee_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Funcionario Ativo Admin")

    def test_admin_role_changelist_still_lists_inactive_employee(self):
        viewer = self._make_viewer(SystemUser.Role.ADMIN)
        self.client.force_login(viewer)

        response = self.client.get(reverse("admin:employees_employee_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Funcionario Inativo Admin")

    def test_dev_role_changelist_still_lists_inactive_employee(self):
        viewer = self._make_viewer(SystemUser.Role.DEV)
        self.client.force_login(viewer)

        response = self.client.get(reverse("admin:employees_employee_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Funcionario Inativo Admin")


class FT13_DirectAccessVsPermissionDenialTests(
    EmployeeAdminInactiveVisibilityTestBase
):
    """FT13: change/delete/history diretos devem retornar 404 generico
    para papel restrito com permissao suficiente; ADMIN preserva
    acesso."""

    def test_restricted_role_with_permission_change_page_is_404(self):
        viewer = self._make_viewer(SystemUser.Role.SUPER)
        self.client.force_login(viewer)

        url = reverse(
            "admin:employees_employee_change", args=[self.inactive_employee.pk]
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_restricted_role_without_permission_is_denied_before_activity_check(
        self,
    ):
        viewer = self._make_viewer(SystemUser.Role.SUPER, is_staff=False)
        self.client.force_login(viewer)

        url = reverse(
            "admin:employees_employee_change", args=[self.inactive_employee.pk]
        )
        response = self.client.get(url)

        self.assertIn(response.status_code, (302, 403))

    def test_restricted_role_can_open_active_employee_change_page_as_control(self):
        viewer = self._make_viewer(SystemUser.Role.SUPER)
        self.client.force_login(viewer)

        url = reverse(
            "admin:employees_employee_change", args=[self.active_employee.pk]
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Funcionario Ativo Admin")

    def test_restricted_role_delete_page_must_be_404(self):
        viewer = self._make_viewer(SystemUser.Role.GERENTE)
        self.client.force_login(viewer)

        url = reverse(
            "admin:employees_employee_delete", args=[self.inactive_employee.pk]
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_restricted_role_history_page_must_be_404(self):
        viewer = self._make_viewer(SystemUser.Role.BACKOFFICE)
        self.client.force_login(viewer)

        url = reverse(
            "admin:employees_employee_history", args=[self.inactive_employee.pk]
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_admin_role_change_page_still_reachable(self):
        viewer = self._make_viewer(SystemUser.Role.ADMIN)
        self.client.force_login(viewer)

        url = reverse(
            "admin:employees_employee_change", args=[self.inactive_employee.pk]
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Funcionario Inativo Admin")


class FT14_BulkActionMustNotAffectHiddenEmployee(
    EmployeeAdminInactiveVisibilityTestBase
):
    """FT14: acao em lote "Excluir" (que no Admin de Employee executa
    exclusao LOGICA via EmployeeQuerySet.delete -- is_deleted=True, nao
    remocao de linha) nao pode atingir o objeto oculto para papel
    restrito, mesmo com PK forjada na selecao."""

    def test_restricted_role_bulk_delete_does_not_soft_delete_hidden_employee(
        self,
    ):
        viewer = self._make_viewer(SystemUser.Role.GERENTE)
        self.client.force_login(viewer)

        url = reverse("admin:employees_employee_changelist")
        self.client.post(
            url,
            {
                "action": "delete_selected",
                "_selected_action": [str(self.inactive_employee.pk)],
                "post": "yes",
                "index": "0",
            },
        )

        self.inactive_employee.refresh_from_db()
        self.assertFalse(self.inactive_employee.is_deleted)

    def test_bulk_delete_confirmation_page_does_not_list_hidden_employee(self):
        viewer = self._make_viewer(SystemUser.Role.GERENTE)
        self.client.force_login(viewer)

        url = reverse("admin:employees_employee_changelist")
        response = self.client.post(
            url,
            {
                "action": "delete_selected",
                "_selected_action": [str(self.inactive_employee.pk)],
                "index": "0",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Funcionario Inativo Admin")

    def test_restricted_role_bulk_delete_still_soft_deletes_visible_employee_as_control(
        self,
    ):
        viewer = self._make_viewer(SystemUser.Role.GERENTE)
        self.client.force_login(viewer)

        url = reverse("admin:employees_employee_changelist")
        self.client.post(
            url,
            {
                "action": "delete_selected",
                "_selected_action": [str(self.active_employee.pk)],
                "post": "yes",
                "index": "0",
            },
        )

        self.active_employee.refresh_from_db()
        self.assertTrue(self.active_employee.is_deleted)


class FT15_StaffSuperuserFlagsDoNotGrantRoleExceptionTests(
    EmployeeAdminInactiveVisibilityTestBase
):
    """FT15: is_staff/is_superuser nao substituem a excecao de role
    ADMIN/DEV (mesmo controle T04 de UVI-03, adaptado para
    EmployeeAdmin)."""

    def test_restricted_role_with_is_staff_and_is_superuser_still_blocked(self):
        viewer = self._make_viewer(
            SystemUser.Role.OPERATOR, is_staff=True, is_superuser=True
        )
        self.client.force_login(viewer)

        response = self.client.get(reverse("admin:employees_employee_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Funcionario Inativo Admin")
