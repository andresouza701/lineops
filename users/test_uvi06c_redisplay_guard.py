"""UVI-06c (correção): achado confirmado na revisão do diff UVI --
SystemUserAdmin: POST de ``manager_email``/``supervisor_email`` apontando
para conta inativa é recusado com mensagem genérica, mas o ``<input
value="...">`` do redisplay continua contendo o e-mail recusado --
exposição de identidade oculta mesmo com a validação correta. A correção
deve neutralizar a REPRESENTAÇÃO sem alterar a validação da entrada
original (não limpar o POST antes de validar).

Fonte de verdade: docs/superpowers/specs/2026-10-14-inactive-system-user-visibility-design.md
"""

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from users.models import SystemUser
from users.visibility import KEEP_CURRENT_TOKEN


def _grant_full_systemuser_perms(user):
    perms = Permission.objects.filter(content_type__app_label="users")
    user.user_permissions.set(perms)
    user.is_staff = True
    user.save(update_fields=["is_staff"])


class RedisplayGuardFixture(TestCase):
    def setUp(self):
        self.inactive_super = SystemUser.objects.create_user(
            email="super.inativo.redisplay.uvi06c@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.inactive_super.is_active = False
        self.inactive_super.save(update_fields=["is_active"])

        self.active_super = SystemUser.objects.create_user(
            email="super.ativo.redisplay.uvi06c@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )

        # active_backoffice.supervisor_email comeca VISIVEL (ativo) --
        # cenario geral do achado, nao depende do campo ja estar mascarado.
        self.active_backoffice = SystemUser.objects.create_user(
            email="backoffice.ativo.redisplay.uvi06c@test.com",
            password="StrongPass123",
            role=SystemUser.Role.BACKOFFICE,
            supervisor_email=self.active_super.email,
        )

    def _make_restricted_viewer(self, role=SystemUser.Role.BACKOFFICE):
        viewer = SystemUser.objects.create_user(
            email=f"viewer.redisplay.{role}.uvi06c@test.com",
            password="StrongPass123",
            role=role,
        )
        _grant_full_systemuser_perms(viewer)
        return viewer

    def _change_url(self):
        return reverse(
            "admin:users_systemuser_change", args=[self.active_backoffice.pk]
        )

    def _post_change(self, viewer, *, supervisor_email, manager_email=""):
        self.client.force_login(viewer)
        return self.client.post(
            self._change_url(),
            {
                "email": self.active_backoffice.email,
                "role": self.active_backoffice.role,
                "supervisor_email": supervisor_email,
                "manager_email": manager_email,
                "is_active": "on",
                "is_staff": "",
                "is_superuser": "",
                "_continue": "Save",
            },
        )


class ForgedInactiveRedisplayDoesNotLeakTest(RedisplayGuardFixture):
    def test_rejected_post_does_not_echo_the_hidden_email_in_input_value(self):
        viewer = self._make_restricted_viewer()

        response = self._post_change(
            viewer, supervisor_email=self.inactive_super.email
        )

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertNotIn(f'value="{self.inactive_super.email}"', html)
        self.active_backoffice.refresh_from_db()
        self.assertEqual(
            self.active_backoffice.supervisor_email, self.active_super.email
        )

    def test_rejection_error_still_fires_and_is_generic(self):
        viewer = self._make_restricted_viewer()

        response = self._post_change(
            viewer, supervisor_email=self.inactive_super.email
        )

        errors = response.context["adminform"].form.errors.get("supervisor_email")
        self.assertEqual(errors, ["Selecione uma conta ativa."])


class ValidActiveValuePreservedOnUnrelatedErrorTest(RedisplayGuardFixture):
    def test_valid_active_supervisor_email_still_shown_when_other_field_errors(self):
        """Campo alheio (email duplicado) dispara erro; supervisor_email
        foi submetido com um valor ATIVO valido -- deve continuar visivel
        no redisplay (nao revertido para o marcador neutro)."""
        viewer = self._make_restricted_viewer()
        self.client.force_login(viewer)

        other_active = SystemUser.objects.create_user(
            email="outro.ativo.redisplay.uvi06c@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )

        response = self.client.post(
            self._change_url(),
            {
                "email": other_active.email,  # duplicado -> erro alheio
                "role": self.active_backoffice.role,
                "supervisor_email": other_active.email,
                "manager_email": "",
                "is_active": "on",
                "is_staff": "",
                "is_superuser": "",
                "_continue": "Save",
            },
        )

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(f'value="{other_active.email}"', html)


class RedisplayAfterHiddenPersistedLinkTest(RedisplayGuardFixture):
    """Cenario em que o campo JA estava mascarado (persistido oculto) --
    forjar outro inativo tambem nao pode vazar, e reenviar o token
    continua preservando o vinculo."""

    def setUp(self):
        super().setUp()
        self.active_backoffice.supervisor_email = self.inactive_super.email
        self.active_backoffice.save(update_fields=["supervisor_email"])
        self.other_inactive = SystemUser.objects.create_user(
            email="super.outro.inativo.redisplay.uvi06c@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.other_inactive.is_active = False
        self.other_inactive.save(update_fields=["is_active"])

    def test_forged_other_inactive_over_masked_field_does_not_leak(self):
        viewer = self._make_restricted_viewer()

        response = self._post_change(
            viewer, supervisor_email=self.other_inactive.email
        )

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertNotIn(f'value="{self.other_inactive.email}"', html)
        self.active_backoffice.refresh_from_db()
        self.assertEqual(
            self.active_backoffice.supervisor_email, self.inactive_super.email
        )

    def test_token_resubmission_still_shown_as_token(self):
        viewer = self._make_restricted_viewer()

        response = self._post_change(viewer, supervisor_email=KEEP_CURRENT_TOKEN)

        self.assertEqual(response.status_code, 302)
        self.active_backoffice.refresh_from_db()
        self.assertEqual(
            self.active_backoffice.supervisor_email, self.inactive_super.email
        )


class AdminExceptionPreservedTest(RedisplayGuardFixture):
    def test_admin_rejected_post_still_echoes_value_no_restriction_applies(self):
        """ADMIN tem excecao de role -- account_is_hidden_for_viewer
        sempre False para ADMIN, entao a guarda de redisplay nunca
        interfere (nao ha identidade oculta do ponto de vista do ADMIN)."""
        admin_viewer = SystemUser.objects.create_user(
            email="admin.redisplay.uvi06c@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        _grant_full_systemuser_perms(admin_viewer)

        response = self._post_change(
            admin_viewer, supervisor_email=self.inactive_super.email
        )

        self.assertEqual(response.status_code, 302)
        self.active_backoffice.refresh_from_db()
        self.assertEqual(
            self.active_backoffice.supervisor_email, self.inactive_super.email
        )
