"""UVI-06 (correcao da revisao final): SystemUserAdmin.supervisor_email/
manager_email validam NOVAS associacoes (UVI-04/04b), mas o GET de edicao
e a changelist continuam expondo a identidade de um vinculo JA PERSISTIDO
quando esse vinculo esta oculto para o viewer -- achado real desta
conferencia, nao coberto por UVI-04b (que so cobria o POST/validacao).

Fonte de verdade: docs/superpowers/specs/2026-10-14-inactive-system-user-visibility-design.md

Cobertura:
- GET de edicao com vinculo inativo persistido: identidade ausente do
  HTML; marcador neutro "Manter vinculo atual" presente.
- changelist: manager_email/supervisor_email projetados (rotulo neutro),
  nao o e-mail cru.
- POST reenviando o marcador (sem alteracao real): vinculo preservado no
  banco (mesmo e-mail oculto de antes).
- POST com o marcador em contexto invalido (campo sem vinculo oculto,
  valor ja visivel): recusado, erro generico.
- Redisplay apos erro em OUTRO campo: continua sem a identidade, marcador
  preservado.
- ADMIN/DEV: identidade real no GET e na changelist (excecao preservada).
"""

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from users.models import SystemUser
from users.visibility import KEEP_CURRENT_LABEL, KEEP_CURRENT_TOKEN


def _grant_full_systemuser_perms(user):
    perms = Permission.objects.filter(content_type__app_label="users")
    user.user_permissions.set(perms)
    user.is_staff = True
    user.save(update_fields=["is_staff"])


class SystemUserAdminKeepCurrentFixture(TestCase):
    def setUp(self):
        self.inactive_super = SystemUser.objects.create_user(
            email="super.inativo.keepcurrent.uvi06@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.inactive_super.is_active = False
        self.inactive_super.save(update_fields=["is_active"])

        self.active_super = SystemUser.objects.create_user(
            email="super.ativo.keepcurrent.uvi06@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )

        self.active_backoffice = SystemUser.objects.create_user(
            email="backoffice.ativo.keepcurrent.uvi06@test.com",
            password="StrongPass123",
            role=SystemUser.Role.BACKOFFICE,
            supervisor_email=self.inactive_super.email,
        )

    def _make_restricted_viewer(self, role):
        viewer = SystemUser.objects.create_user(
            email=f"viewer.keepcurrent.{role}.uvi06@test.com",
            password="StrongPass123",
            role=role,
        )
        _grant_full_systemuser_perms(viewer)
        return viewer

    def _change_url(self, obj=None):
        return reverse(
            "admin:users_systemuser_change",
            args=[(obj or self.active_backoffice).pk],
        )


class RestrictedViewerGetEditFormDoesNotLeakIdentityTest(
    SystemUserAdminKeepCurrentFixture
):
    def test_get_edit_form_must_not_contain_hidden_supervisor_email(self):
        viewer = self._make_restricted_viewer(SystemUser.Role.BACKOFFICE)
        self.client.force_login(viewer)

        response = self.client.get(self._change_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.inactive_super.email)

    def test_get_edit_form_must_show_keep_current_label(self):
        viewer = self._make_restricted_viewer(SystemUser.Role.BACKOFFICE)
        self.client.force_login(viewer)

        response = self.client.get(self._change_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, KEEP_CURRENT_LABEL)


class ChangelistProjectsSupervisorEmailTest(SystemUserAdminKeepCurrentFixture):
    def test_changelist_must_not_reveal_inactive_supervisor_email_to_restricted_viewer(
        self,
    ):
        viewer = self._make_restricted_viewer(SystemUser.Role.BACKOFFICE)
        self.client.force_login(viewer)

        response = self.client.get(reverse("admin:users_systemuser_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.inactive_super.email)

    def test_changelist_still_shows_real_identity_to_admin(self):
        admin_viewer = SystemUser.objects.create_user(
            email="admin.keepcurrent.uvi06@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        _grant_full_systemuser_perms(admin_viewer)
        self.client.force_login(admin_viewer)

        response = self.client.get(reverse("admin:users_systemuser_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.inactive_super.email)


class KeepCurrentTokenPreservesHiddenLinkTest(SystemUserAdminKeepCurrentFixture):
    def test_submitting_keep_current_token_preserves_hidden_link(self):
        viewer = self._make_restricted_viewer(SystemUser.Role.BACKOFFICE)
        self.client.force_login(viewer)

        response = self.client.post(
            self._change_url(),
            {
                "email": self.active_backoffice.email,
                "role": self.active_backoffice.role,
                "supervisor_email": KEEP_CURRENT_TOKEN,
                "manager_email": "",
                "is_active": "on",
                "is_staff": "",
                "is_superuser": "",
                "_continue": "Save",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.active_backoffice.refresh_from_db()
        self.assertEqual(
            self.active_backoffice.supervisor_email, self.inactive_super.email
        )


class KeepCurrentTokenInvalidContextTest(SystemUserAdminKeepCurrentFixture):
    def test_token_rejected_on_field_without_hidden_link(self):
        """manager_email nao tem vinculo persistido algum -- o marcador
        aqui nao tem contexto valido para ser resolvido."""
        viewer = self._make_restricted_viewer(SystemUser.Role.BACKOFFICE)
        self.client.force_login(viewer)

        response = self.client.post(
            self._change_url(),
            {
                "email": self.active_backoffice.email,
                "role": self.active_backoffice.role,
                "supervisor_email": self.inactive_super.email,
                "manager_email": KEEP_CURRENT_TOKEN,
                "is_active": "on",
                "is_staff": "",
                "is_superuser": "",
                "_continue": "Save",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.context["adminform"].form.errors.get("manager_email")
        )

    def test_token_rejected_on_creation(self):
        admin_viewer = SystemUser.objects.create_user(
            email="admin.creator.keepcurrent.uvi06@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        viewer = self._make_restricted_viewer(SystemUser.Role.BACKOFFICE)
        self.client.force_login(viewer)

        response = self.client.post(
            reverse("admin:users_systemuser_add"),
            {
                "email": "novo.usuario.keepcurrent.uvi06@test.com",
                "password1": "StrongPass123",
                "password2": "StrongPass123",
                "role": SystemUser.Role.BACKOFFICE,
                "supervisor_email": KEEP_CURRENT_TOKEN,
                "manager_email": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            SystemUser.objects.filter(
                email="novo.usuario.keepcurrent.uvi06@test.com"
            ).exists()
        )


class RedisplayAfterUnrelatedErrorPreservesStateTest(
    SystemUserAdminKeepCurrentFixture
):
    def test_error_in_role_field_does_not_leak_identity_nor_lose_keep_current(self):
        """BACKOFFICE exige supervisor_email -- forcar role invalido para
        outro campo (email duplicado) dispara erro sem tocar
        supervisor_email; o redisplay nao pode vazar a identidade oculta
        nem perder o estado 'manter vinculo'."""
        viewer = self._make_restricted_viewer(SystemUser.Role.BACKOFFICE)
        self.client.force_login(viewer)

        response = self.client.post(
            self._change_url(),
            {
                "email": self.active_super.email,  # duplicado -> erro
                "role": self.active_backoffice.role,
                "supervisor_email": KEEP_CURRENT_TOKEN,
                "manager_email": "",
                "is_active": "on",
                "is_staff": "",
                "is_superuser": "",
                "_continue": "Save",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["adminform"].form.errors)
        self.assertNotContains(response, self.inactive_super.email)
        self.active_backoffice.refresh_from_db()
        self.assertEqual(
            self.active_backoffice.supervisor_email, self.inactive_super.email
        )
