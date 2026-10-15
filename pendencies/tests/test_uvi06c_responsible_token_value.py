"""UVI-06c (correção): achado confirmado na revisão do diff UVI --
AllocationPendencyAdmin.technical_responsible neutraliza apenas o RÓTULO
(``label_from_instance``) da opção preservável; o ``<option value="...">``
continua carregando o PK real da conta oculta (``<option value="1"
selected>Manter vínculo atual</option>``). O contrato exige o token
``__keep_current__`` como VALOR da opção, sem transportar o ID da conta
oculta -- não apenas o texto.

Fonte de verdade: docs/superpowers/specs/2026-10-14-inactive-system-user-visibility-design.md
"""

import re

from django.contrib.auth.models import Permission


def _extract_technical_responsible_select(html):
    match = re.search(
        r'<select name="technical_responsible"[^>]*>(.*?)</select>',
        html,
        re.DOTALL,
    )
    assert match is not None, "select technical_responsible nao encontrado no HTML"
    return match.group(1)

from django.test import TestCase
from django.urls import reverse

from employees.models import Employee
from pendencies.models import AllocationPendency
from users.models import SystemUser
from users.visibility import KEEP_CURRENT_LABEL, KEEP_CURRENT_TOKEN


def _grant_full_pendency_perms(user):
    perms = Permission.objects.filter(content_type__app_label="pendencies")
    user.user_permissions.set(perms)
    user.is_staff = True
    user.save(update_fields=["is_staff"])


class ResponsibleTokenValueFixture(TestCase):
    def setUp(self):
        self.inactive_responsible = SystemUser.objects.create_user(
            email="responsavel.inativo.uvi06c@test.com",
            password="StrongPass123",
            role=SystemUser.Role.OPERATOR,
        )
        self.inactive_responsible.is_active = False
        self.inactive_responsible.save(update_fields=["is_active"])

        self.other_inactive = SystemUser.objects.create_user(
            email="responsavel.outro.inativo.uvi06c@test.com",
            password="StrongPass123",
            role=SystemUser.Role.OPERATOR,
        )
        self.other_inactive.is_active = False
        self.other_inactive.save(update_fields=["is_active"])

        self.active_operator = SystemUser.objects.create_user(
            email="responsavel.ativo.uvi06c@test.com",
            password="StrongPass123",
            role=SystemUser.Role.OPERATOR,
        )

        self.employee = Employee.objects.create(
            full_name="Funcionario PendResponsavel Uvi06c",
            corporate_email="super.pendresp.uvi06c@corp.com",
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        self.pendency = AllocationPendency.objects.create(
            employee=self.employee,
            allocation=None,
            technical_responsible=self.inactive_responsible,
        )

    def _make_restricted_viewer(self, role=SystemUser.Role.GERENTE):
        viewer = SystemUser.objects.create_user(
            email=f"viewer.pendresp.{role}.uvi06c@test.com",
            password="StrongPass123",
            role=role,
        )
        _grant_full_pendency_perms(viewer)
        return viewer

    def _change_url(self):
        return reverse(
            "admin:pendencies_allocationpendency_change", args=[self.pendency.pk]
        )

    def _post_change(self, viewer, technical_responsible_value):
        self.client.force_login(viewer)
        return self.client.post(
            self._change_url(),
            {
                "employee": self.employee.pk,
                "action": AllocationPendency.ActionType.NO_ACTION,
                "observation": "",
                "technical_responsible": technical_responsible_value,
                "_continue": "Save",
            },
        )


class SelectedOptionValueMustBeTokenNotPkTest(ResponsibleTokenValueFixture):
    """Achado 1: o <option> selecionado para o vínculo oculto deve usar
    __keep_current__ como VALOR, nunca o pk real da conta oculta."""

    def test_selected_option_value_is_not_the_hidden_account_pk(self):
        viewer = self._make_restricted_viewer()
        self.client.force_login(viewer)

        response = self.client.get(self._change_url())

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        select_html = _extract_technical_responsible_select(html)
        leaked = re.search(
            rf'<option value="{self.inactive_responsible.pk}"[^>]*selected',
            select_html,
        )
        self.assertIsNone(
            leaked,
            f"PK oculto {self.inactive_responsible.pk} exposto como value da opcao selecionada",
        )

    def test_selected_option_value_is_the_keep_current_token(self):
        viewer = self._make_restricted_viewer()
        self.client.force_login(viewer)

        response = self.client.get(self._change_url())

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertRegex(
            html,
            rf'<option value="{KEEP_CURRENT_TOKEN}"[^>]*selected[^>]*>{KEEP_CURRENT_LABEL}',
        )

    def test_hidden_account_pk_does_not_appear_anywhere_in_select_options(self):
        viewer = self._make_restricted_viewer()
        self.client.force_login(viewer)

        response = self.client.get(self._change_url())

        html = response.content.decode()
        select_match = re.search(
            r'<select name="technical_responsible"[^>]*>(.*?)</select>',
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(select_match)
        select_html = select_match.group(1)
        self.assertNotIn(f'value="{self.inactive_responsible.pk}"', select_html)
        self.assertNotIn(self.inactive_responsible.email, select_html)


class TokenPostPreservesPersistedResponsibleTest(ResponsibleTokenValueFixture):
    def test_submitting_token_keeps_the_originally_persisted_responsible(self):
        viewer = self._make_restricted_viewer()

        response = self._post_change(viewer, KEEP_CURRENT_TOKEN)

        self.assertEqual(response.status_code, 302)
        self.pendency.refresh_from_db()
        self.assertEqual(
            self.pendency.technical_responsible_id, self.inactive_responsible.pk
        )

    def test_token_is_never_the_value_written_to_the_fk(self):
        viewer = self._make_restricted_viewer()

        self._post_change(viewer, KEEP_CURRENT_TOKEN)

        self.pendency.refresh_from_db()
        # FK real, nunca a string literal do token.
        self.assertIsInstance(self.pendency.technical_responsible_id, int)


class TokenInvalidContextRejectedTest(ResponsibleTokenValueFixture):
    def test_token_rejected_when_pendency_has_no_hidden_responsible(self):
        other_employee = Employee.objects.create(
            full_name="Funcionario Sem Pendencia Oculta Uvi06c",
            corporate_email="super.pendresp2.uvi06c@corp.com",
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        pendency_no_hidden = AllocationPendency.objects.create(
            employee=other_employee,
            allocation=None,
            technical_responsible=self.active_operator,
        )
        viewer = self._make_restricted_viewer()
        self.client.force_login(viewer)

        response = self.client.post(
            reverse(
                "admin:pendencies_allocationpendency_change",
                args=[pendency_no_hidden.pk],
            ),
            {
                "employee": other_employee.pk,
                "action": AllocationPendency.ActionType.NO_ACTION,
                "observation": "",
                "technical_responsible": KEEP_CURRENT_TOKEN,
                "_continue": "Save",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.context["adminform"].form.errors.get("technical_responsible")
        )

    def test_token_rejected_on_creation(self):
        viewer = self._make_restricted_viewer()
        self.client.force_login(viewer)
        new_employee = Employee.objects.create(
            full_name="Funcionario Novo Uvi06c",
            corporate_email="super.pendresp3.uvi06c@corp.com",
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )

        response = self.client.post(
            reverse("admin:pendencies_allocationpendency_add"),
            {
                "employee": new_employee.pk,
                "action": AllocationPendency.ActionType.NO_ACTION,
                "observation": "",
                "technical_responsible": KEEP_CURRENT_TOKEN,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            AllocationPendency.objects.filter(employee=new_employee).exists()
        )


class ForgedOtherInactiveStillRejectedTest(ResponsibleTokenValueFixture):
    def test_forged_other_inactive_pk_rejected(self):
        viewer = self._make_restricted_viewer()

        response = self._post_change(viewer, self.other_inactive.pk)

        self.assertEqual(response.status_code, 200)
        self.pendency.refresh_from_db()
        self.assertEqual(
            self.pendency.technical_responsible_id, self.inactive_responsible.pk
        )


class SwitchToActiveWorksTest(ResponsibleTokenValueFixture):
    def test_switching_to_active_responsible_persists(self):
        viewer = self._make_restricted_viewer()

        response = self._post_change(viewer, self.active_operator.pk)

        self.assertEqual(response.status_code, 302)
        self.pendency.refresh_from_db()
        self.assertEqual(self.pendency.technical_responsible_id, self.active_operator.pk)


class RedisplayAfterUnrelatedErrorTest(ResponsibleTokenValueFixture):
    def test_invalid_action_redisplay_preserves_keep_current_without_leaking_pk(self):
        viewer = self._make_restricted_viewer()
        self.client.force_login(viewer)

        response = self.client.post(
            self._change_url(),
            {
                "employee": self.employee.pk,
                "action": "not_a_real_action",
                "observation": "",
                "technical_responsible": KEEP_CURRENT_TOKEN,
                "_continue": "Save",
            },
        )

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        select_html = _extract_technical_responsible_select(html)
        self.assertNotIn(f'value="{self.inactive_responsible.pk}"', select_html)
        self.assertIn(KEEP_CURRENT_LABEL, select_html)
        self.pendency.refresh_from_db()
        self.assertEqual(
            self.pendency.technical_responsible_id, self.inactive_responsible.pk
        )


class AdminExceptionPreservedTest(ResponsibleTokenValueFixture):
    def test_admin_sees_real_identity_and_can_reassign(self):
        admin_viewer = SystemUser.objects.create_user(
            email="admin.pendresp.uvi06c@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        _grant_full_pendency_perms(admin_viewer)
        self.client.force_login(admin_viewer)

        response = self.client.get(self._change_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.inactive_responsible.email)
        self.assertContains(response, self.other_inactive.email)
