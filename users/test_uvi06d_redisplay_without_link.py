"""UVI-06d (correção): achado confirmado na revisão focada do diff UVI --
``should_mask_submitted_value_for_redisplay`` troca QUALQUER valor
submetido que resolva para conta oculta pelo token ``__keep_current__``,
mesmo quando NÃO existe vínculo persistido oculto preservável naquele
campo (``manager_email=None``, ou vínculo persistido ATIVO). O contrato
exige: ``__keep_current__`` só representa um vínculo persistido, oculto
e preservável NAQUELE campo -- sem isso, o redisplay deve usar
representação vazia, nunca o token (que o campo nem sequer suporta
nesses casos, pois não foi trocado para CharField -- o widget continua
``type="email"``, e o token vira um "e-mail" inválido).

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


class Fixture(TestCase):
    def setUp(self):
        self.inactive_super = SystemUser.objects.create_user(
            email="super.inativo.nolink.uvi06d@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.inactive_super.is_active = False
        self.inactive_super.save(update_fields=["is_active"])

        self.active_super = SystemUser.objects.create_user(
            email="super.ativo.nolink.uvi06d@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )

    def _make_restricted_viewer(self, role=SystemUser.Role.BACKOFFICE):
        viewer = SystemUser.objects.create_user(
            email=f"viewer.nolink.{role}.uvi06d@test.com",
            password="StrongPass123",
            role=role,
        )
        _grant_full_systemuser_perms(viewer)
        return viewer

    def _change_url(self, target):
        return reverse("admin:users_systemuser_change", args=[target.pk])

    def _post_change(self, viewer, target, *, supervisor_email="", manager_email=""):
        self.client.force_login(viewer)
        return self.client.post(
            self._change_url(target),
            {
                "email": target.email,
                "role": target.role,
                "supervisor_email": supervisor_email,
                "manager_email": manager_email,
                "is_active": "on",
                "is_staff": "",
                "is_superuser": "",
                "_continue": "Save",
            },
        )


class FieldWithoutAnyPersistedLinkTest(Fixture):
    """Cenario (a): manager_email=None -- nao ha vinculo algum a manter."""

    def setUp(self):
        super().setUp()
        self.target = SystemUser.objects.create_user(
            email="backoffice.semgerente.uvi06d@test.com",
            password="StrongPass123",
            role=SystemUser.Role.BACKOFFICE,
            supervisor_email=self.active_super.email,
        )
        self.assertIsNone(self.target.manager_email)

    def test_rejected_post_banco_intacto(self):
        viewer = self._make_restricted_viewer()

        response = self._post_change(
            viewer,
            self.target,
            supervisor_email=self.active_super.email,
            manager_email=self.inactive_super.email,
        )

        self.assertEqual(response.status_code, 200)
        self.target.refresh_from_db()
        self.assertIsNone(self.target.manager_email)

    def test_redisplay_is_empty_not_the_hidden_email_and_not_the_token(self):
        viewer = self._make_restricted_viewer()

        response = self._post_change(
            viewer,
            self.target,
            supervisor_email=self.active_super.email,
            manager_email=self.inactive_super.email,
        )

        input_html = _field_input_html(response, "manager_email")
        self.assertNotIn(self.inactive_super.email, input_html)
        self.assertNotIn(KEEP_CURRENT_TOKEN, input_html)
        # Django TextInput omite o atributo value por completo quando o
        # valor e string vazia (comportamento padrao do widget) -- a
        # representacao vazia exigida pelo contrato e exatamente isso,
        # nao um value="" literal.
        self.assertNotIn("value=", input_html)

    def test_explicit_field_error_present(self):
        viewer = self._make_restricted_viewer()

        response = self._post_change(
            viewer,
            self.target,
            supervisor_email=self.active_super.email,
            manager_email=self.inactive_super.email,
        )

        errors = response.context["adminform"].form.errors.get("manager_email")
        self.assertEqual(errors, ["Selecione uma conta ativa."])


class FieldWithActivePersistedLinkTest(Fixture):
    """Cenario (b): vinculo persistido existe e esta ATIVO -- nao pode ser
    substituido pelo marcador reservado a vinculos INATIVOS."""

    def setUp(self):
        super().setUp()
        self.another_active = SystemUser.objects.create_user(
            email="super.ativo2.nolink.uvi06d@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.target = SystemUser.objects.create_user(
            email="backoffice.gerenteativo.uvi06d@test.com",
            password="StrongPass123",
            role=SystemUser.Role.BACKOFFICE,
            supervisor_email=self.active_super.email,
            manager_email=self.another_active.email,
        )

    def test_rejected_post_preserves_active_link(self):
        viewer = self._make_restricted_viewer()

        response = self._post_change(
            viewer,
            self.target,
            supervisor_email=self.active_super.email,
            manager_email=self.inactive_super.email,
        )

        self.assertEqual(response.status_code, 200)
        self.target.refresh_from_db()
        self.assertEqual(self.target.manager_email, self.another_active.email)

    def test_redisplay_does_not_use_keep_current_token(self):
        viewer = self._make_restricted_viewer()

        response = self._post_change(
            viewer,
            self.target,
            supervisor_email=self.active_super.email,
            manager_email=self.inactive_super.email,
        )

        input_html = _field_input_html(response, "manager_email")
        self.assertNotIn(KEEP_CURRENT_TOKEN, input_html)
        self.assertNotIn(self.inactive_super.email, input_html)


class FieldWithHiddenPreservableLinkTest(Fixture):
    """Cenario (c): vinculo persistido existe e esta OCULTO -- comportamento
    ja corrigido em UVI-06c, reconfirmado aqui sem regressao."""

    def setUp(self):
        super().setUp()
        self.target = SystemUser.objects.create_user(
            email="backoffice.gerenteoculto.uvi06d@test.com",
            password="StrongPass123",
            role=SystemUser.Role.BACKOFFICE,
            supervisor_email=self.active_super.email,
            manager_email=self.inactive_super.email,
        )

    def test_get_shows_neutral_token(self):
        viewer = self._make_restricted_viewer()
        self.client.force_login(viewer)

        response = self.client.get(self._change_url(self.target))

        input_html = _field_input_html(response, "manager_email")
        self.assertIn(f'value="{KEEP_CURRENT_TOKEN}"', input_html)
        self.assertNotIn(self.inactive_super.email, input_html)

    def test_resubmitting_token_preserves_real_hidden_link(self):
        viewer = self._make_restricted_viewer()

        response = self._post_change(
            viewer,
            self.target,
            supervisor_email=self.active_super.email,
            manager_email=KEEP_CURRENT_TOKEN,
        )

        self.assertEqual(response.status_code, 302)
        self.target.refresh_from_db()
        self.assertEqual(self.target.manager_email, self.inactive_super.email)


class RecoveryAfterErrorTest(Fixture):
    """Cenario (d): usuario corrige e reenvia com um ativo valido."""

    def setUp(self):
        super().setUp()
        self.target = SystemUser.objects.create_user(
            email="backoffice.recovery.uvi06d@test.com",
            password="StrongPass123",
            role=SystemUser.Role.BACKOFFICE,
            supervisor_email=self.active_super.email,
        )

    def test_second_submission_with_active_email_saves(self):
        viewer = self._make_restricted_viewer()

        first = self._post_change(
            viewer,
            self.target,
            supervisor_email=self.active_super.email,
            manager_email=self.inactive_super.email,
        )
        self.assertEqual(first.status_code, 200)

        second = self._post_change(
            viewer,
            self.target,
            supervisor_email=self.active_super.email,
            manager_email="",
        )

        self.assertEqual(second.status_code, 302)
        self.target.refresh_from_db()
        self.assertIsNone(self.target.manager_email)


class UnrelatedFieldErrorPreservesValidChoiceTest(Fixture):
    """Cenario (e): erro em OUTRO campo preserva o valor ativo valido
    submetido neste campo (ja coberto por UVI-06c, reconfirmado)."""

    def setUp(self):
        super().setUp()
        self.target = SystemUser.objects.create_user(
            email="backoffice.unrelated.uvi06d@test.com",
            password="StrongPass123",
            role=SystemUser.Role.BACKOFFICE,
            supervisor_email=self.active_super.email,
        )

    def test_valid_active_manager_email_preserved_on_unrelated_error(self):
        viewer = self._make_restricted_viewer()
        self.client.force_login(viewer)

        other_active = SystemUser.objects.create_user(
            email="super.outro.ativo.uvi06d@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        response = self.client.post(
            self._change_url(self.target),
            {
                "email": other_active.email,  # duplicado -> erro alheio
                "role": self.target.role,
                "supervisor_email": self.active_super.email,
                "manager_email": other_active.email,
                "is_active": "on",
                "is_staff": "",
                "is_superuser": "",
                "_continue": "Save",
            },
        )

        self.assertEqual(response.status_code, 200)
        input_html = _field_input_html(response, "manager_email")
        self.assertIn(f'value="{other_active.email}"', input_html)


class AdminExceptionUnaffectedTest(Fixture):
    """Cenario (f): ADMIN/DEV sem restricao -- a guarda de redisplay
    nunca intervem (account_is_hidden_for_viewer sempre False)."""

    def setUp(self):
        super().setUp()
        self.target = SystemUser.objects.create_user(
            email="backoffice.adminctl.uvi06d@test.com",
            password="StrongPass123",
            role=SystemUser.Role.BACKOFFICE,
            supervisor_email=self.active_super.email,
        )

    def test_admin_can_assign_inactive_manager_without_restriction(self):
        admin_viewer = SystemUser.objects.create_user(
            email="admin.nolink.uvi06d@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        _grant_full_systemuser_perms(admin_viewer)

        response = self._post_change(
            admin_viewer,
            self.target,
            supervisor_email=self.active_super.email,
            manager_email=self.inactive_super.email,
        )

        self.assertEqual(response.status_code, 302)
        self.target.refresh_from_db()
        self.assertEqual(self.target.manager_email, self.inactive_super.email)


def _field_input_html(response, field_name):
    form = response.context["adminform"].form
    return str(form[field_name])
