"""UVI-04 (conferencia corretiva) - SystemUserAdmin.supervisor_email/
manager_email sao campos de texto livre (sem <select>) no proprio
cadastro de contas -- caminho de associacao operacional nao coberto por
UVI-03/UVI-04 original (ficou registrado como "ambiguidade", retificado
nesta conferencia: o contrato UVI-02 (U04) exige explicitamente "validar
conta proposta" para estes dois campos, nao e uma decisao de produto em
aberto).

Fonte de verdade: docs/superpowers/specs/2026-10-14-inactive-system-user-visibility-design.md

Superficie real: unico caminho de edicao de SystemUser e SystemUserAdmin
(confirmado em UVI-02/UVI-03, sem rota de auto-edicao de perfil em
accounts/*). SystemUser.clean() so valida supervisor_email para role=
BACKOFFICE (existencia + role=SUPER, sem is_active) -- mantido
INALTERADO (nao e afrouxado nem apertado neste arquivo: a correcao vive
no FORM do Admin, nao no model, para nao alterar consumidores fora do
escopo do Admin). manager_email nao tem validacao de existencia alguma
hoje (qualquer e-mail, de qualquer role) -- tambem mantido inalterado;
apenas a ATIVIDADE de uma conta CORRESPONDENTE passa a ser verificada
quando ela de fato existe e e proposta como NOVA associacao.

Cinco cenarios distintos cobertos (pedido explicito desta conferencia):
1. manutencao de vinculo inativo ja persistido (inalterado) -- preservado;
2. nova associacao/troca para OUTRO inativo -- recusada;
3. associacao a ativo elegivel -- aceita;
4. valor sem conta correspondente -- tratamento legado preservado;
5. ADMIN/DEV versus papeis restritos com permissao tecnica suficiente.
"""

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from users.models import SystemUser


def _grant_full_systemuser_perms(user):
    perms = Permission.objects.filter(content_type__app_label="users")
    user.user_permissions.set(perms)
    user.is_staff = True
    user.save(update_fields=["is_staff"])


class SystemUserAdminTextFieldAssociationFixture(TestCase):
    def setUp(self):
        self.inactive_super = SystemUser.objects.create_user(
            email="super.inativo.textfield.uvi04b@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.inactive_super.is_active = False
        self.inactive_super.save(update_fields=["is_active"])

        self.other_inactive_super = SystemUser.objects.create_user(
            email="super.inativo2.textfield.uvi04b@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.other_inactive_super.is_active = False
        self.other_inactive_super.save(update_fields=["is_active"])

        self.active_super = SystemUser.objects.create_user(
            email="super.ativo.textfield.uvi04b@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )

        self.active_backoffice = SystemUser.objects.create_user(
            email="backoffice.ativo.textfield.uvi04b@test.com",
            password="StrongPass123",
            role=SystemUser.Role.BACKOFFICE,
            supervisor_email=self.inactive_super.email,
        )

    def _post_change(self, viewer, *, supervisor_email, manager_email="", role=None):
        self.client.force_login(viewer)
        url = reverse(
            "admin:users_systemuser_change", args=[self.active_backoffice.pk]
        )
        return self.client.post(
            url,
            {
                "email": self.active_backoffice.email,
                "role": role or self.active_backoffice.role,
                "supervisor_email": supervisor_email,
                "manager_email": manager_email,
                "is_active": "on",
                "is_staff": "",
                "is_superuser": "",
                "_continue": "Save",
            },
        )

    def _make_restricted_viewer(self, role):
        viewer = SystemUser.objects.create_user(
            email=f"viewer.textfield.{role}.uvi04b@test.com",
            password="StrongPass123",
            role=role,
        )
        _grant_full_systemuser_perms(viewer)
        return viewer


class RestrictedViewerCannotCreateNewHiddenAssociationTest(
    SystemUserAdminTextFieldAssociationFixture
):
    """Cenario 2: nova associacao/troca para OUTRO inativo -- recusada
    para papel restrito, mesmo com permissao tecnica suficiente para
    alcancar a rota (o registro editado -- active_backoffice -- e ATIVO
    e portanto alcancavel por get_queryset; o que muda e o CONTEUDO
    proposto do campo texto, nao o alcance ao objeto)."""

    def test_backoffice_viewer_cannot_point_supervisor_email_to_unrelated_inactive(
        self,
    ):
        viewer = self._make_restricted_viewer(SystemUser.Role.BACKOFFICE)

        response = self._post_change(
            viewer, supervisor_email=self.other_inactive_super.email
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.context["adminform"].form.errors.get("supervisor_email")
        )
        self.active_backoffice.refresh_from_db()
        self.assertEqual(
            self.active_backoffice.supervisor_email, self.inactive_super.email
        )

    def test_operator_viewer_cannot_point_supervisor_email_to_unrelated_inactive(self):
        """Mesma recusa para outro papel restrito (nao e exclusivo de
        BACKOFFICE)."""
        viewer = self._make_restricted_viewer(SystemUser.Role.OPERATOR)

        response = self._post_change(
            viewer, supervisor_email=self.other_inactive_super.email
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.context["adminform"].form.errors.get("supervisor_email")
        )

    def test_restricted_viewer_cannot_point_manager_email_to_inactive_account(self):
        """manager_email nao tem validacao de EXISTENCIA hoje (qualquer
        papel, qualquer e-mail) -- mas quando o e-mail proposto CORRESPONDE
        a uma conta de fato inativa, a nova associacao tambem e recusada
        (contrato: "validar conta proposta", ambos os campos)."""
        inactive_manager = SystemUser.objects.create_user(
            email="gerente.inativo.textfield.uvi04b@test.com",
            password="StrongPass123",
            role=SystemUser.Role.GERENTE,
        )
        inactive_manager.is_active = False
        inactive_manager.save(update_fields=["is_active"])
        viewer = self._make_restricted_viewer(SystemUser.Role.GERENTE)

        response = self._post_change(
            viewer,
            supervisor_email=self.inactive_super.email,
            manager_email=inactive_manager.email,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.context["adminform"].form.errors.get("manager_email")
        )


class RestrictedViewerPreservesPersistedLinkTest(
    SystemUserAdminTextFieldAssociationFixture
):
    """Cenario 1: manutencao de vinculo inativo JA persistido -- o
    registro ja tinha supervisor_email apontando para self.inactive_super
    antes desta requisicao; reenviar o MESMO valor (sem mudanca) nao pode
    ser tratado como nova associacao."""

    def test_unchanged_hidden_supervisor_email_is_preserved_on_unrelated_save(self):
        viewer = self._make_restricted_viewer(SystemUser.Role.BACKOFFICE)

        response = self._post_change(
            viewer, supervisor_email=self.inactive_super.email
        )

        self.assertEqual(response.status_code, 302)
        self.active_backoffice.refresh_from_db()
        self.assertEqual(
            self.active_backoffice.supervisor_email, self.inactive_super.email
        )


class RestrictedViewerCanSwitchToActiveAccountTest(
    SystemUserAdminTextFieldAssociationFixture
):
    """Cenario 3: associacao a ativo elegivel continua funcionando --
    a recusa nao e um bloqueio generico do campo."""

    def test_switching_supervisor_email_to_active_account_is_accepted(self):
        viewer = self._make_restricted_viewer(SystemUser.Role.BACKOFFICE)

        response = self._post_change(
            viewer, supervisor_email=self.active_super.email
        )

        self.assertEqual(response.status_code, 302)
        self.active_backoffice.refresh_from_db()
        self.assertEqual(
            self.active_backoffice.supervisor_email, self.active_super.email
        )


class RestrictedViewerLegacyValueWithoutMatchingAccountTest(
    SystemUserAdminTextFieldAssociationFixture
):
    """Cenario 4: e-mail sem NENHUMA conta correspondente mantem
    tratamento legado (nenhuma restricao nova de existencia) -- so a
    ATIVIDADE de uma conta que de fato existe e verificada."""

    def test_email_without_any_matching_account_is_still_accepted(self):
        """role=OPERATOR, nao BACKOFFICE: SystemUser.clean() so exige
        existencia de supervisor_email para role=BACKOFFICE (inalterado
        por esta etapa) -- usar BACKOFFICE aqui disparia essa validacao
        pre-existente e nao exercitaria o cenario pretendido (e-mail
        livre sem conta, tratamento legado do campo em si)."""
        viewer = self._make_restricted_viewer(SystemUser.Role.BACKOFFICE)

        response = self._post_change(
            viewer,
            supervisor_email="sem.conta.textfield.uvi04b@corp.com",
            role=SystemUser.Role.OPERATOR,
        )

        self.assertEqual(response.status_code, 302)
        self.active_backoffice.refresh_from_db()
        self.assertEqual(
            self.active_backoffice.supervisor_email,
            "sem.conta.textfield.uvi04b@corp.com",
        )


class AdminAndDevExceptionPreservedTest(SystemUserAdminTextFieldAssociationFixture):
    """Cenario 5: ADMIN/DEV preservam a excecao de role -- podem apontar
    para uma conta inativa diferente da persistida, dentro das permissoes
    ja existentes (controle positivo, nao uma concessao nova)."""

    def test_admin_can_point_supervisor_email_to_a_different_inactive_account(self):
        admin_viewer = SystemUser.objects.create_user(
            email="admin.textfield.uvi04b@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        _grant_full_systemuser_perms(admin_viewer)

        response = self._post_change(
            admin_viewer, supervisor_email=self.other_inactive_super.email
        )

        self.assertEqual(response.status_code, 302)
        self.active_backoffice.refresh_from_db()
        self.assertEqual(
            self.active_backoffice.supervisor_email, self.other_inactive_super.email
        )

    def test_dev_can_point_supervisor_email_to_a_different_inactive_account(self):
        dev_viewer = SystemUser.objects.create_user(
            email="dev.textfield.uvi04b@test.com",
            password="StrongPass123",
            role=SystemUser.Role.DEV,
        )
        _grant_full_systemuser_perms(dev_viewer)

        response = self._post_change(
            dev_viewer, supervisor_email=self.other_inactive_super.email
        )

        self.assertEqual(response.status_code, 302)
        self.active_backoffice.refresh_from_db()
        self.assertEqual(
            self.active_backoffice.supervisor_email, self.other_inactive_super.email
        )


class ErrorMessageDoesNotLeakIdentityTest(SystemUserAdminTextFieldAssociationFixture):
    """Vazamento de identidade em mensagens de erro (achado real da etapa
    anterior com ChoiceField.invalid_choice, que interpolava o valor
    FORJADO de volta na mensagem). Aqui o campo e um CharField/EmailField
    de texto livre: o proprio viewer digitou o valor rejeitado, entao o
    <input value="..."> redisplay o ecoa de volta -- isso NAO e vazamento
    (mesmo raciocinio da caixa de busca do Admin, UVI-04 original): o
    viewer ja sabe o que digitou. O vazamento real a evitar e a mensagem
    de erro em si citar o valor (como o ChoiceField fazia) ou o estado
    persistido mudar -- nenhum dos dois ocorre aqui."""

    def test_rejection_message_is_generic_and_does_not_cite_the_value(self):
        viewer = self._make_restricted_viewer(SystemUser.Role.BACKOFFICE)

        response = self._post_change(
            viewer, supervisor_email=self.other_inactive_super.email
        )

        self.assertEqual(response.status_code, 200)
        errors = response.context["adminform"].form.errors.get("supervisor_email")
        self.assertEqual(errors, ["Selecione uma conta ativa."])
        self.active_backoffice.refresh_from_db()
        self.assertEqual(
            self.active_backoffice.supervisor_email, self.inactive_super.email
        )
