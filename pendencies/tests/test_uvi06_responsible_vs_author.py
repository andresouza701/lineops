"""UVI-06 (correcao da revisao final): AllocationPendencyAdmin trata
technical_responsible (referencia OPERACIONAL -- quem esta tratando a
pendencia agora) e updated_by (AUTORIA/historico -- quem alterou o
registro por ultimo) com o MESMO mecanismo hoje
(`_visible_responsible_queryset`, reinclui o pk persistido no queryset,
expondo a identidade real na <option> quando o vinculo esta oculto para
o viewer). Achado real: technical_responsible precisa de representacao
NEUTRA (como EmployeeForm/__keep_current__); updated_by deve seguir a
excecao historica ja aprovada (mesmo tratamento de LineAllocationAdmin.
allocated_by/released_by -- novas escolhas filtradas, referencia
historica EXIBIDA, sem mascaramento).

Fonte de verdade: docs/superpowers/specs/2026-10-14-inactive-system-user-visibility-design.md
"""

from django.contrib.auth.models import Permission
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


class ResponsibleVsAuthorFixture(TestCase):
    def setUp(self):
        self.inactive_responsible = SystemUser.objects.create_user(
            email="responsavel.inativo.uvi06@test.com",
            password="StrongPass123",
            role=SystemUser.Role.OPERATOR,
        )
        self.inactive_responsible.is_active = False
        self.inactive_responsible.save(update_fields=["is_active"])

        self.inactive_author = SystemUser.objects.create_user(
            email="autor.inativo.uvi06@test.com",
            password="StrongPass123",
            role=SystemUser.Role.OPERATOR,
        )
        self.inactive_author.is_active = False
        self.inactive_author.save(update_fields=["is_active"])

        self.active_operator = SystemUser.objects.create_user(
            email="operador.ativo.uvi06@test.com",
            password="StrongPass123",
            role=SystemUser.Role.OPERATOR,
        )

        self.employee = Employee.objects.create(
            full_name="Funcionario PendResponsavel UVI06",
            corporate_email="super.pendresp.uvi06@corp.com",
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        self.pendency = AllocationPendency.objects.create(
            employee=self.employee,
            allocation=None,
            technical_responsible=self.inactive_responsible,
            updated_by=self.inactive_author,
        )

    def _make_restricted_viewer(self, role=SystemUser.Role.GERENTE):
        viewer = SystemUser.objects.create_user(
            email=f"viewer.pendresp.{role}.uvi06@test.com",
            password="StrongPass123",
            role=role,
        )
        _grant_full_pendency_perms(viewer)
        return viewer

    def _change_url(self):
        return reverse(
            "admin:pendencies_allocationpendency_change", args=[self.pendency.pk]
        )


class TechnicalResponsibleNeutralOptionTest(ResponsibleVsAuthorFixture):
    """technical_responsible e operacional: o vinculo persistido e inativo
    deve aparecer no <select> com rotulo NEUTRO, nunca o e-mail real."""

    def test_get_edit_form_must_not_contain_inactive_responsible_email(self):
        viewer = self._make_restricted_viewer()
        self.client.force_login(viewer)

        response = self.client.get(self._change_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.inactive_responsible.email)

    def test_get_edit_form_must_show_keep_current_label_for_responsible(self):
        viewer = self._make_restricted_viewer()
        self.client.force_login(viewer)

        response = self.client.get(self._change_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, KEEP_CURRENT_LABEL)

    def test_changelist_must_not_reveal_inactive_responsible_email(self):
        viewer = self._make_restricted_viewer()
        self.client.force_login(viewer)

        response = self.client.get(
            reverse("admin:pendencies_allocationpendency_changelist")
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.inactive_responsible.email)

    def test_unchanged_submission_preserves_hidden_responsible(self):
        """UVI-06c (correcao): retificacao deste teste. A entrega anterior
        (UVI-06) reincluia o PK OCULTO no queryset, entao reenviar esse
        pk bruto sem alteracao era aceito -- exatamente o achado real
        corrigido ("label_from_instance neutraliza so o texto... <option
        value> continua com o PK real"). Apos a correcao, o GET nunca
        renderiza o pk oculto como valor selecionado (renderiza o token
        __keep_current__) -- um viewer real reenviando o formulario sem
        alteracao agora envia o TOKEN, nunca o pk bruto. Reenviar o pk
        bruto diretamente passou a ser corretamente recusado (o pk oculto
        nao esta mais no queryset de opcoes validas). Teste corrigido
        para refletir a interacao real: "manter vinculo" via o token."""
        viewer = self._make_restricted_viewer()
        self.client.force_login(viewer)

        response = self.client.post(
            self._change_url(),
            {
                "employee": self.employee.pk,
                "action": AllocationPendency.ActionType.NO_ACTION,
                "observation": "",
                "technical_responsible": KEEP_CURRENT_TOKEN,
                "_continue": "Save",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.pendency.refresh_from_db()
        self.assertEqual(self.pendency.technical_responsible_id, self.inactive_responsible.pk)

    def test_raw_hidden_pk_resubmission_is_now_rejected(self):
        """Controle novo (UVI-06c): o pk oculto bruto, que a entrega
        anterior aceitava por estar reincluido no queryset, agora e
        recusado -- nao esta mais entre as opcoes validas (so o token
        ou uma conta visivel sao aceitos)."""
        viewer = self._make_restricted_viewer()
        self.client.force_login(viewer)

        response = self.client.post(
            self._change_url(),
            {
                "employee": self.employee.pk,
                "action": AllocationPendency.ActionType.NO_ACTION,
                "observation": "",
                "technical_responsible": self.inactive_responsible.pk,
                "_continue": "Save",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.pendency.refresh_from_db()
        self.assertEqual(self.pendency.technical_responsible_id, self.inactive_responsible.pk)

    def test_forged_other_inactive_responsible_is_rejected(self):
        other_inactive = SystemUser.objects.create_user(
            email="outro.responsavel.inativo.uvi06@test.com",
            password="StrongPass123",
            role=SystemUser.Role.OPERATOR,
        )
        other_inactive.is_active = False
        other_inactive.save(update_fields=["is_active"])
        viewer = self._make_restricted_viewer()
        self.client.force_login(viewer)

        response = self.client.post(
            self._change_url(),
            {
                "employee": self.employee.pk,
                "action": AllocationPendency.ActionType.NO_ACTION,
                "observation": "",
                "technical_responsible": other_inactive.pk,
                "_continue": "Save",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.pendency.refresh_from_db()
        self.assertEqual(
            self.pendency.technical_responsible_id, self.inactive_responsible.pk
        )


class UpdatedByHistoricalExceptionUnaffectedTest(ResponsibleVsAuthorFixture):
    """updated_by segue a excecao historica aprovada: identidade do autor
    persistido continua EXIBIDA (nao mascarada), igual a
    LineAllocationAdmin.allocated_by/released_by."""

    def test_get_edit_form_still_shows_real_updated_by_identity(self):
        viewer = self._make_restricted_viewer()
        self.client.force_login(viewer)

        response = self.client.get(self._change_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.inactive_author.email)
