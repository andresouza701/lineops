"""UVI-06d (correção): mesmo achado 2 (SystemUserAdmin), confirmado
também em EmployeeAdmin.manager_email (campo opcional, pode ser None --
mesma lacuna: redisplay usa __keep_current__ mesmo sem vínculo
persistido oculto preservável naquele campo).

Fonte de verdade: docs/superpowers/specs/2026-10-14-inactive-system-user-visibility-design.md
"""

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from employees.models import Employee
from users.models import SystemUser
from users.visibility import KEEP_CURRENT_TOKEN


def _grant_full_employee_admin_perms(user):
    perms = Permission.objects.filter(content_type__app_label="employees")
    user.user_permissions.set(perms)
    user.is_staff = True
    user.save(update_fields=["is_staff"])


def _field_input_html(response, field_name):
    form = response.context["adminform"].form
    return str(form[field_name])


class Fixture(TestCase):
    def setUp(self):
        self.inactive_super = SystemUser.objects.create_user(
            email="super.inativo.empnolink.uvi06d@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.inactive_super.is_active = False
        self.inactive_super.save(update_fields=["is_active"])

        self.active_super = SystemUser.objects.create_user(
            email="super.ativo.empnolink.uvi06d@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )

    def _make_restricted_viewer(self, role=SystemUser.Role.BACKOFFICE):
        viewer = SystemUser.objects.create_user(
            email=f"viewer.empnolink.{role}.uvi06d@test.com",
            password="StrongPass123",
            role=role,
            supervisor_email=self.active_super.email,
        )
        _grant_full_employee_admin_perms(viewer)
        return viewer

    def _change_url(self, employee):
        return reverse("admin:employees_employee_change", args=[employee.pk])

    def _post_change(self, viewer, employee, *, manager_email="", email=""):
        self.client.force_login(viewer)
        return self.client.post(
            self._change_url(employee),
            {
                "full_name": employee.full_name,
                "email": email,
                "corporate_email": self.active_super.email,
                "manager_email": manager_email,
                "employee_id": employee.employee_id,
                "teams": employee.teams,
                "status": employee.status,
                "pa": "",
                "line_status": employee.line_status,
                "is_deleted": "",
                "_continue": "Save",
            },
        )


class FieldWithoutAnyPersistedLinkTest(Fixture):
    """Cenario (a): manager_email=None."""

    def setUp(self):
        super().setUp()
        self.employee = Employee.objects.create(
            full_name="Funcionario SemGerente Uvi06d",
            corporate_email=self.active_super.email,
            manager_email=None,
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )

    def test_rejected_post_banco_intacto(self):
        viewer = self._make_restricted_viewer()

        response = self._post_change(
            viewer, self.employee, manager_email=self.inactive_super.email
        )

        self.assertEqual(response.status_code, 200)
        self.employee.refresh_from_db()
        self.assertIsNone(self.employee.manager_email)

    def test_redisplay_is_empty_not_the_hidden_email_and_not_the_token(self):
        viewer = self._make_restricted_viewer()

        response = self._post_change(
            viewer, self.employee, manager_email=self.inactive_super.email
        )

        input_html = _field_input_html(response, "manager_email")
        self.assertNotIn(self.inactive_super.email, input_html)
        self.assertNotIn(KEEP_CURRENT_TOKEN, input_html)
        # Django TextInput omite o atributo value por completo quando o
        # valor e string vazia (comportamento padrao do widget).
        self.assertNotIn("value=", input_html)


class FieldWithActivePersistedLinkTest(Fixture):
    """Cenario (b): manager_email aponta para conta ATIVA."""

    def setUp(self):
        super().setUp()
        self.another_active = SystemUser.objects.create_user(
            email="super.ativo2.empnolink.uvi06d@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.employee = Employee.objects.create(
            full_name="Funcionario GerenteAtivo Uvi06d",
            corporate_email=self.active_super.email,
            manager_email=self.another_active.email,
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )

    def test_rejected_post_preserves_active_link(self):
        viewer = self._make_restricted_viewer()

        response = self._post_change(
            viewer, self.employee, manager_email=self.inactive_super.email
        )

        self.assertEqual(response.status_code, 200)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.manager_email, self.another_active.email)

    def test_redisplay_does_not_use_keep_current_token(self):
        viewer = self._make_restricted_viewer()

        response = self._post_change(
            viewer, self.employee, manager_email=self.inactive_super.email
        )

        input_html = _field_input_html(response, "manager_email")
        self.assertNotIn(KEEP_CURRENT_TOKEN, input_html)
        self.assertNotIn(self.inactive_super.email, input_html)


class FieldWithHiddenPreservableLinkTest(Fixture):
    """Cenario (c): manager_email oculto preservavel -- reconfirmado sem
    regressao."""

    def setUp(self):
        super().setUp()
        self.employee = Employee.objects.create(
            full_name="Funcionario GerenteOculto Uvi06d",
            corporate_email=self.active_super.email,
            manager_email=self.inactive_super.email,
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )

    def test_get_shows_neutral_token(self):
        viewer = self._make_restricted_viewer()
        self.client.force_login(viewer)

        response = self.client.get(self._change_url(self.employee))

        input_html = _field_input_html(response, "manager_email")
        self.assertIn(f'value="{KEEP_CURRENT_TOKEN}"', input_html)
        self.assertNotIn(self.inactive_super.email, input_html)

    def test_resubmitting_token_preserves_real_hidden_link(self):
        viewer = self._make_restricted_viewer()

        response = self._post_change(
            viewer, self.employee, manager_email=KEEP_CURRENT_TOKEN
        )

        self.assertEqual(response.status_code, 302)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.manager_email, self.inactive_super.email)


class RecoveryAfterErrorTest(Fixture):
    def setUp(self):
        super().setUp()
        self.employee = Employee.objects.create(
            full_name="Funcionario Recovery Uvi06d",
            corporate_email=self.active_super.email,
            manager_email=None,
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )

    def test_second_submission_with_active_email_saves(self):
        viewer = self._make_restricted_viewer()

        first = self._post_change(
            viewer, self.employee, manager_email=self.inactive_super.email
        )
        self.assertEqual(first.status_code, 200)

        second = self._post_change(viewer, self.employee, manager_email="")

        self.assertEqual(second.status_code, 302)
        self.employee.refresh_from_db()
        self.assertIsNone(self.employee.manager_email)


class UnrelatedFieldErrorPreservesValidChoiceTest(Fixture):
    def setUp(self):
        super().setUp()
        self.employee = Employee.objects.create(
            full_name="Funcionario Unrelated Uvi06d",
            corporate_email=self.active_super.email,
            manager_email=None,
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )

    def test_valid_active_manager_email_preserved_on_unrelated_error(self):
        viewer = self._make_restricted_viewer()
        self.client.force_login(viewer)

        other_employee = Employee.objects.create(
            full_name="Outro Funcionario Uvi06d",
            email="duplicado.uvi06d@negociador.com",
            corporate_email=self.active_super.email,
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        other_active = SystemUser.objects.create_user(
            email="super.outro.ativo.empnolink.uvi06d@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )

        response = self._post_change(
            viewer,
            self.employee,
            manager_email=other_active.email,
            email="duplicado.uvi06d@negociador.com",
        )

        self.assertEqual(response.status_code, 200)
        input_html = _field_input_html(response, "manager_email")
        self.assertIn(f'value="{other_active.email}"', input_html)


class AdminExceptionUnaffectedTest(Fixture):
    def setUp(self):
        super().setUp()
        self.employee = Employee.objects.create(
            full_name="Funcionario AdminCtl Uvi06d",
            corporate_email=self.active_super.email,
            manager_email=None,
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )

    def test_admin_can_assign_inactive_manager_without_restriction(self):
        admin_viewer = SystemUser.objects.create_user(
            email="admin.empnolink.uvi06d@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        _grant_full_employee_admin_perms(admin_viewer)

        response = self._post_change(
            admin_viewer, self.employee, manager_email=self.inactive_super.email
        )

        self.assertEqual(response.status_code, 302)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.manager_email, self.inactive_super.email)
