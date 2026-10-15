"""UVI-06 (correcao da revisao final): EmployeeAdminForm.corporate_email/
manager_email validam NOVAS associacoes (UVI-04, U07), mas o GET de
edicao e a changelist continuam expondo a identidade de um vinculo JA
PERSISTIDO quando esse vinculo esta oculto para o viewer -- achado real
desta conferencia, nao coberto pela entrega original de U07.

Fonte de verdade: docs/superpowers/specs/2026-10-14-inactive-system-user-visibility-design.md
"""

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from employees.models import Employee
from users.models import SystemUser
from users.visibility import KEEP_CURRENT_LABEL, KEEP_CURRENT_TOKEN


def _grant_full_employee_admin_perms(user):
    perms = Permission.objects.filter(content_type__app_label="employees")
    user.user_permissions.set(perms)
    user.is_staff = True
    user.save(update_fields=["is_staff"])


class EmployeeAdminKeepCurrentFixture(TestCase):
    def setUp(self):
        self.inactive_super = SystemUser.objects.create_user(
            email="super.inativo.empadmin.uvi06@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.inactive_super.is_active = False
        self.inactive_super.save(update_fields=["is_active"])

        self.active_super = SystemUser.objects.create_user(
            email="super.ativo.empadmin.uvi06@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )

        self.employee = Employee.objects.create(
            full_name="Funcionario EmpAdmin KeepCurrent UVI06",
            corporate_email=self.inactive_super.email,
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )

    def _make_restricted_viewer(self, role=SystemUser.Role.BACKOFFICE):
        """BACKOFFICE.scope_employee_queryset exige supervisor_email
        proprio correspondente ao corporate_email do funcionario (escopo
        de dados, U11, fora do dominio de visibilidade) -- sem isto o
        Admin nao alcancaria o registro por um motivo alheio a esta
        politica (escopo, nao visibilidade de conta), mesmo cuidado
        documentado em test_uvi04_admin_free_text_association.py."""
        viewer = SystemUser.objects.create_user(
            email=f"viewer.empadmin.{role}.uvi06@test.com",
            password="StrongPass123",
            role=role,
            supervisor_email=self.inactive_super.email,
        )
        _grant_full_employee_admin_perms(viewer)
        return viewer

    def _change_url(self):
        return reverse("admin:employees_employee_change", args=[self.employee.pk])


class RestrictedViewerGetEditFormDoesNotLeakIdentityTest(
    EmployeeAdminKeepCurrentFixture
):
    def test_get_edit_form_must_not_contain_hidden_corporate_email(self):
        viewer = self._make_restricted_viewer()
        self.client.force_login(viewer)

        response = self.client.get(self._change_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.inactive_super.email)

    def test_get_edit_form_must_show_keep_current_label(self):
        viewer = self._make_restricted_viewer()
        self.client.force_login(viewer)

        response = self.client.get(self._change_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, KEEP_CURRENT_LABEL)


class ChangelistProjectsCorporateEmailTest(EmployeeAdminKeepCurrentFixture):
    def test_changelist_must_not_reveal_inactive_supervisor_email_to_restricted_viewer(
        self,
    ):
        viewer = self._make_restricted_viewer()
        self.client.force_login(viewer)

        response = self.client.get(reverse("admin:employees_employee_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.inactive_super.email)

    def test_changelist_still_shows_real_identity_to_admin(self):
        admin_viewer = SystemUser.objects.create_user(
            email="admin.empadmin.keepcurrent.uvi06@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        _grant_full_employee_admin_perms(admin_viewer)
        self.client.force_login(admin_viewer)

        response = self.client.get(reverse("admin:employees_employee_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.inactive_super.email)


class KeepCurrentTokenPreservesHiddenLinkTest(EmployeeAdminKeepCurrentFixture):
    def _post_change(self, viewer, *, corporate_email, manager_email=""):
        self.client.force_login(viewer)
        return self.client.post(
            self._change_url(),
            {
                "full_name": self.employee.full_name,
                "email": "",
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

    def test_submitting_keep_current_token_preserves_hidden_link(self):
        viewer = self._make_restricted_viewer()

        response = self._post_change(viewer, corporate_email=KEEP_CURRENT_TOKEN)

        self.assertEqual(response.status_code, 302)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.corporate_email, self.inactive_super.email)

    def test_token_rejected_on_field_without_hidden_link(self):
        viewer = self._make_restricted_viewer()

        response = self._post_change(
            viewer,
            corporate_email=self.active_super.email,
            manager_email=KEEP_CURRENT_TOKEN,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.context["adminform"].form.errors.get("manager_email")
        )

    def test_switching_to_active_account_still_works(self):
        viewer = self._make_restricted_viewer()

        response = self._post_change(viewer, corporate_email=self.active_super.email)

        self.assertEqual(response.status_code, 302)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.corporate_email, self.active_super.email)

    def test_forged_other_inactive_account_rejected_without_leaking_identity(self):
        other_inactive = SystemUser.objects.create_user(
            email="super.outro.inativo.empadmin.uvi06@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        other_inactive.is_active = False
        other_inactive.save(update_fields=["is_active"])
        viewer = self._make_restricted_viewer()

        response = self._post_change(viewer, corporate_email=other_inactive.email)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.context["adminform"].form.errors.get("corporate_email")
        )
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.corporate_email, self.inactive_super.email)
