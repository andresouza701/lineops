"""UVI-04 - EmployeeAdmin/EmployeeAdminForm (U07): corporate_email e
manager_email sao campos de texto livre no Admin de Employee (sem
<select>), caminho alternativo de associacao. Mesma politica de
visibilidade de EmployeeForm (users.visibility), aplicada via
clean_corporate_email/clean_manager_email + EmployeeAdmin.get_form
(injeta o viewer da request no form).

Fonte de verdade: docs/superpowers/specs/2026-10-14-inactive-system-user-visibility-design.md
U07 (UVI-02) / UVI-04 (esta etapa)."""

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from employees.models import Employee
from users.models import SystemUser


def _grant_full_employee_perms(user):
    perms = Permission.objects.filter(content_type__app_label="employees")
    user.user_permissions.set(perms)
    user.is_staff = True
    user.save(update_fields=["is_staff"])


class EmployeeAdminFreeTextAssociationTest(TestCase):
    def setUp(self):
        self.inactive_super = SystemUser.objects.create_user(
            email="super.inativo.adminform.uvi04@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.inactive_super.is_active = False
        self.inactive_super.save(update_fields=["is_active"])

        self.active_super = SystemUser.objects.create_user(
            email="super.ativo.adminform.uvi04@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )

        self.admin_viewer = SystemUser.objects.create_user(
            email="admin.adminform.uvi04@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
            # Irrelevante para ADMIN (scope_employee_queryset nao filtra
            # este role), mas necessario quando o teste reatribui o role
            # para BACKOFFICE (SUPERVISOR_SCOPE_ROLES): sem isto,
            # scope_employee_queryset ficaria vazio e o Admin nao
            # alcancaria o funcionario por um motivo alheio a esta
            # politica (escopo, nao visibilidade de conta).
            supervisor_email=self.active_super.email,
        )
        _grant_full_employee_perms(self.admin_viewer)

        self.employee = Employee.objects.create(
            full_name="Funcionario AdminForm UVI04",
            corporate_email=self.active_super.email,
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )

    def _post_change(self, corporate_email):
        self.client.force_login(self.admin_viewer)
        url = reverse("admin:employees_employee_change", args=[self.employee.pk])
        return self.client.post(
            url,
            {
                "full_name": self.employee.full_name,
                "email": "",
                "corporate_email": corporate_email,
                "manager_email": "",
                "employee_id": "Alimentos",
                "teams": "Joinville",
                "status": Employee.Status.ACTIVE,
                "pa": "",
                "line_status": self.employee.line_status,
                "is_deleted": "",
                "_continue": "Save",
            },
        )

    def test_restricted_role_cannot_point_corporate_email_to_hidden_inactive_account(
        self,
    ):
        self.admin_viewer.role = SystemUser.Role.BACKOFFICE
        self.admin_viewer.save(update_fields=["role"])

        response = self._post_change(self.inactive_super.email)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["adminform"].form.errors.get("corporate_email"))
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.corporate_email, self.active_super.email)

    def test_restricted_role_can_still_switch_to_another_active_account(self):
        self.admin_viewer.role = SystemUser.Role.BACKOFFICE
        self.admin_viewer.save(update_fields=["role"])
        other_active = SystemUser.objects.create_user(
            email="super.ativo2.adminform.uvi04@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )

        response = self._post_change(other_active.email)

        self.assertEqual(response.status_code, 302)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.corporate_email, other_active.email)

    def test_restricted_role_unchanged_hidden_persisted_value_is_preserved(self):
        """Vinculo ja persistido (mesmo que aponte para conta inativa) nao
        e uma NOVA associacao -- salvar outro campo sem alterar
        corporate_email preserva o valor, mesmo que ele corresponda a uma
        conta oculta para este viewer."""
        self.employee.corporate_email = self.inactive_super.email
        self.employee.save(update_fields=["corporate_email"])
        self.admin_viewer.role = SystemUser.Role.BACKOFFICE
        self.admin_viewer.supervisor_email = self.inactive_super.email
        self.admin_viewer.save(update_fields=["role", "supervisor_email"])

        response = self._post_change(self.inactive_super.email)

        self.assertEqual(response.status_code, 302)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.corporate_email, self.inactive_super.email)

    def test_admin_role_can_point_corporate_email_to_inactive_account(self):
        """Controle positivo: ADMIN preserva a excecao de role tambem neste
        caminho de texto livre."""
        response = self._post_change(self.inactive_super.email)

        self.assertEqual(response.status_code, 302)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.corporate_email, self.inactive_super.email)
