"""UVI-06c (correção): mesmo achado 2 de SystemUserAdmin, confirmado
também em EmployeeAdminForm.corporate_email/manager_email -- redisplay de
POST recusado continua ecoando o e-mail oculto no `<input value="...">`.

Fonte de verdade: docs/superpowers/specs/2026-10-14-inactive-system-user-visibility-design.md
"""

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from employees.models import Employee
from users.models import SystemUser


def _grant_full_employee_admin_perms(user):
    perms = Permission.objects.filter(content_type__app_label="employees")
    user.user_permissions.set(perms)
    user.is_staff = True
    user.save(update_fields=["is_staff"])


class RedisplayGuardFixture(TestCase):
    def setUp(self):
        self.inactive_super = SystemUser.objects.create_user(
            email="super.inativo.empredisplay.uvi06c@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.inactive_super.is_active = False
        self.inactive_super.save(update_fields=["is_active"])

        self.active_super = SystemUser.objects.create_user(
            email="super.ativo.empredisplay.uvi06c@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )

        # Começa VISÍVEL (ativo) -- cenário geral, independe de o campo
        # já estar mascarado.
        self.employee = Employee.objects.create(
            full_name="Funcionario EmpRedisplay Uvi06c",
            corporate_email=self.active_super.email,
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )

    def _make_restricted_viewer(self, role=SystemUser.Role.BACKOFFICE):
        viewer = SystemUser.objects.create_user(
            email=f"viewer.empredisplay.{role}.uvi06c@test.com",
            password="StrongPass123",
            role=role,
            supervisor_email=self.active_super.email,
        )
        _grant_full_employee_admin_perms(viewer)
        return viewer

    def _change_url(self):
        return reverse("admin:employees_employee_change", args=[self.employee.pk])

    def _post_change(self, viewer, *, corporate_email, manager_email="", email=""):
        self.client.force_login(viewer)
        return self.client.post(
            self._change_url(),
            {
                "full_name": self.employee.full_name,
                "email": email,
                "corporate_email": corporate_email,
                "manager_email": manager_email,
                "employee_id": self.employee.employee_id,
                "teams": self.employee.teams,
                "status": self.employee.status,
                "pa": "",
                "line_status": self.employee.line_status,
                "is_deleted": "",
                "_continue": "Save",
            },
        )


class ForgedInactiveRedisplayDoesNotLeakTest(RedisplayGuardFixture):
    def test_rejected_post_does_not_echo_the_hidden_email_in_input_value(self):
        viewer = self._make_restricted_viewer()

        response = self._post_change(
            viewer, corporate_email=self.inactive_super.email
        )

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertNotIn(f'value="{self.inactive_super.email}"', html)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.corporate_email, self.active_super.email)


class ValidActiveValuePreservedOnUnrelatedErrorTest(RedisplayGuardFixture):
    def test_valid_active_corporate_email_still_shown_when_other_field_errors(self):
        viewer = self._make_restricted_viewer()
        self.client.force_login(viewer)

        other_employee = Employee.objects.create(
            full_name="Outro Funcionario Uvi06c",
            email="duplicado.uvi06c@negociador.com",
            corporate_email=self.active_super.email,
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )

        response = self._post_change(
            viewer,
            corporate_email=self.active_super.email,
            email="duplicado.uvi06c@negociador.com",  # dispara erro alheio
        )

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(f'value="{self.active_super.email}"', html)


class AdminExceptionPreservedTest(RedisplayGuardFixture):
    def test_admin_rejected_post_not_restricted(self):
        admin_viewer = SystemUser.objects.create_user(
            email="admin.empredisplay.uvi06c@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        _grant_full_employee_admin_perms(admin_viewer)

        response = self._post_change(
            admin_viewer, corporate_email=self.inactive_super.email
        )

        self.assertEqual(response.status_code, 302)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.corporate_email, self.inactive_super.email)
