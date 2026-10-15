"""
UVI-03 - Testes RED da visibilidade de contas de acesso inativas no Admin
de SystemUser.

Fonte de verdade: docs/superpowers/specs/2026-10-14-inactive-system-user-visibility-design.md
(UVI-01/UVI-02). Node IDs T01/T02/T03/T04 do checklist derivado em UVI-02.

Estes testes codificam o CONTRATO (ADMIN/DEV podem continuar vendo contas
inativas; SUPER/BACKOFFICE/GERENTE/OPERATOR nao podem, mesmo com permissao
tecnica suficiente para alcancar a rota) contra o comportamento REAL e atual
de users/admin.py::SystemUserAdmin (UserAdmin padrao, sem filtro por role
sobre o queryset de contas). Nenhuma politica foi implementada ainda
(UVI-04); falhas aqui sao esperadas e documentam a lacuna real, nao
placeholders.
"""

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from users.models import SystemUser

RESTRICTED_ROLES = [
    SystemUser.Role.SUPER,
    SystemUser.Role.BACKOFFICE,
    SystemUser.Role.GERENTE,
    SystemUser.Role.OPERATOR,
]
EXEMPT_ROLES = [SystemUser.Role.ADMIN, SystemUser.Role.DEV]


def _grant_full_systemuser_perms(user):
    """Permissao tecnica suficiente para alcancar a rota do Admin de
    SystemUser (view/change/delete/add), isolando o eixo "permissao" do
    eixo "atividade da conta" (regra 5 do contrato UVI-02)."""
    perms = Permission.objects.filter(content_type__app_label="users")
    user.user_permissions.set(perms)
    user.is_staff = True
    user.save(update_fields=["is_staff"])


class SystemUserAdminInactiveVisibilityTestBase(TestCase):
    def setUp(self):
        self.inactive_account = SystemUser.objects.create_user(
            email="inativo.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.OPERATOR,
            first_name="Inativo",
            last_name="UVI03",
        )
        self.inactive_account.is_active = False
        self.inactive_account.save(update_fields=["is_active"])

        self.active_account = SystemUser.objects.create_user(
            email="ativo.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.OPERATOR,
        )

    def _make_viewer(self, role, *, is_staff=True, is_superuser=False):
        viewer = SystemUser.objects.create_user(
            email=f"viewer.{role}.uvi03@test.com",
            password="StrongPass123",
            role=role,
        )
        if is_superuser:
            viewer.is_superuser = True
        viewer.is_staff = is_staff
        viewer.save(update_fields=["is_staff", "is_superuser"])
        if is_staff:
            _grant_full_systemuser_perms(viewer)
        return viewer


class T01_ChangelistSearchCountTests(SystemUserAdminInactiveVisibilityTestBase):
    """T01: lista/pesquisa/contagens/filtro is_active/paginacao no Admin."""

    def test_restricted_role_changelist_must_not_list_inactive_account(self):
        viewer = self._make_viewer(SystemUser.Role.SUPER)
        self.client.force_login(viewer)

        response = self.client.get(reverse("admin:users_systemuser_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.inactive_account.email)

    def test_search_feature_is_fixed_and_respects_restricted_role_visibility(self):
        """UVI-04 corrige o defeito pre-existente (achado na conferencia
        corretiva de UVI-03: UserAdmin.search_fields herdado incluia
        "username", campo inexistente em SystemUser, e qualquer busca
        levantava FieldError). A correcao minima (search_fields = ("email",),
        o unico campo real de login do cadastro) e aplicada e testada em
        separado por users/test_admin_search_field_defect.py (RED->GREEN
        dedicado ao defeito). Aqui a busca ja fixa e exercitada junto com a
        POLITICA nova: papel restrito buscando pelo e-mail da conta oculta
        nao a encontra (nem FieldError, nem vazamento)."""
        viewer = self._make_viewer(SystemUser.Role.BACKOFFICE)
        self.client.force_login(viewer)

        response = self.client.get(
            reverse("admin:users_systemuser_changelist"),
            {"q": self.inactive_account.email},
        )

        self.assertEqual(response.status_code, 200)
        # A caixa de busca ecoa de volta o termo digitado pelo proprio
        # viewer (nao e vazamento de identidade: o viewer ja sabia o que
        # digitou) -- a prova real de ocultacao e a AUSENCIA da conta nos
        # resultados/paginador, nao assertNotContains no HTML inteiro.
        cl = response.context["cl"]
        self.assertNotIn(self.inactive_account, list(cl.result_list))
        self.assertEqual(cl.paginator.count, 0)

    def test_search_finds_active_account_for_restricted_role(self):
        """Controle positivo: a busca nao esta simplesmente quebrada ou
        retornando vazio por erro -- uma conta ATIVA e encontrada
        normalmente pelo mesmo papel restrito. Responde diretamente ao
        requisito "nao aceitar 'sem resultados' causado por erro como
        prova de ocultacao"."""
        viewer = self._make_viewer(SystemUser.Role.BACKOFFICE)
        self.client.force_login(viewer)

        response = self.client.get(
            reverse("admin:users_systemuser_changelist"),
            {"q": self.active_account.email},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.active_account.email)
        cl = response.context["cl"]
        self.assertEqual(cl.paginator.count, 1)

    def test_search_finds_inactive_account_for_admin_and_dev(self):
        """Controle positivo: ADMIN/DEV preservam a excecao de role tambem
        na busca -- encontram a conta inativa pelo e-mail normalmente."""
        for role in (SystemUser.Role.ADMIN, SystemUser.Role.DEV):
            with self.subTest(role=role):
                viewer = self._make_viewer(role)
                self.client.force_login(viewer)

                response = self.client.get(
                    reverse("admin:users_systemuser_changelist"),
                    {"q": self.inactive_account.email},
                )

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, self.inactive_account.email)

    def test_restricted_role_changelist_count_excludes_inactive(self):
        viewer = self._make_viewer(SystemUser.Role.GERENTE)
        self.client.force_login(viewer)

        response = self.client.get(reverse("admin:users_systemuser_changelist"))

        self.assertEqual(response.status_code, 200)
        cl = response.context["cl"]
        self.assertNotIn(self.inactive_account, list(cl.result_list))
        # Contagem/paginador: cl.paginator.count alimenta tanto o rodape
        # "N usuarios" quanto o calculo de paginas -- se a conta oculta
        # entra na contagem, paginacao tambem fica errada para o viewer
        # restrito. 3 linhas existem no banco neste ponto (inactive_account,
        # active_account, o proprio viewer GERENTE): excluindo so a
        # inativa, a contagem correta seria 2.
        self.assertEqual(cl.paginator.count, 2)

    def test_admin_role_changelist_still_lists_inactive_account(self):
        """Controle positivo: ADMIN preserva visibilidade (nao houve
        negacao de rota/permissao mascarando o resultado)."""
        viewer = self._make_viewer(SystemUser.Role.ADMIN)
        self.client.force_login(viewer)

        response = self.client.get(reverse("admin:users_systemuser_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.inactive_account.email)

    def test_dev_role_changelist_still_lists_inactive_account(self):
        viewer = self._make_viewer(SystemUser.Role.DEV)
        self.client.force_login(viewer)

        response = self.client.get(reverse("admin:users_systemuser_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.inactive_account.email)


class T02_DirectAccessVsPermissionDenialTests(SystemUserAdminInactiveVisibilityTestBase):
    """T02: acesso direto (change/delete/history/password) deve retornar
    404 generico para papel restrito com permissao suficiente; separa esse
    caso do caso sem permissao alguma (que deve continuar negado antes)."""

    def test_restricted_role_with_permission_gets_change_page_today(self):
        viewer = self._make_viewer(SystemUser.Role.SUPER)
        self.client.force_login(viewer)

        url = reverse(
            "admin:users_systemuser_change", args=[self.inactive_account.pk]
        )
        response = self.client.get(url)

        # Contrato exige 404 generico sem identidade. Hoje o Admin padrao
        # nao filtra por role: a pagina de edicao e exibida normalmente,
        # inclusive com o e-mail da conta oculta no formulario.
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, self.inactive_account.email, status_code=404)

    def test_restricted_role_without_permission_is_denied_before_activity_check(self):
        """Controle: sem permissao alguma, a negacao deve ocorrer por
        autenticacao/permissao (302 para login ou 403), nunca 404 -- nao
        pode ser confundida com o bloqueio por inatividade."""
        viewer = self._make_viewer(SystemUser.Role.SUPER, is_staff=False)
        self.client.force_login(viewer)

        url = reverse(
            "admin:users_systemuser_change", args=[self.inactive_account.pk]
        )
        response = self.client.get(url)

        self.assertIn(response.status_code, (302, 403))

    def test_restricted_role_with_permission_can_open_active_account_change_page(self):
        """Controle positivo: a rota/permissao funcionam normalmente para
        conta ativa -- a falha do teste anterior nao e por rota inalcancavel."""
        viewer = self._make_viewer(SystemUser.Role.SUPER)
        self.client.force_login(viewer)

        url = reverse("admin:users_systemuser_change", args=[self.active_account.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.active_account.email)

    def test_restricted_role_delete_page_must_be_404(self):
        viewer = self._make_viewer(SystemUser.Role.GERENTE)
        self.client.force_login(viewer)

        url = reverse(
            "admin:users_systemuser_delete", args=[self.inactive_account.pk]
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_restricted_role_history_page_must_be_404(self):
        viewer = self._make_viewer(SystemUser.Role.BACKOFFICE)
        self.client.force_login(viewer)

        url = reverse(
            "admin:users_systemuser_history", args=[self.inactive_account.pk]
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_restricted_role_password_change_page_must_be_404(self):
        viewer = self._make_viewer(SystemUser.Role.OPERATOR)
        self.client.force_login(viewer)

        # Nome de rota fixo pelo UserAdmin do Django, independente do
        # app_label do modelo de usuario customizado (confirmado em
        # django/contrib/auth/admin.py::UserAdmin.get_urls, Django 5.2.11).
        url = reverse(
            "admin:auth_user_password_change",
            args=[self.inactive_account.pk],
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_admin_role_change_page_still_reachable(self):
        """Controle positivo: ADMIN preserva acesso direto a conta inativa."""
        viewer = self._make_viewer(SystemUser.Role.ADMIN)
        self.client.force_login(viewer)

        url = reverse(
            "admin:users_systemuser_change", args=[self.inactive_account.pk]
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.inactive_account.email)


class T02b_ForgedPostMustNotMutateHiddenAccountTests(
    SystemUserAdminInactiveVisibilityTestBase
):
    """T02/contrato item 3: POST forjado dirigido ao objeto oculto nao pode
    alterar estado, senha ou vinculo. Comparamos estado persistido, nao
    apenas o status HTTP da resposta."""

    def test_forged_post_must_not_change_role_of_hidden_account(self):
        viewer = self._make_viewer(SystemUser.Role.SUPER)
        self.client.force_login(viewer)
        original_role = self.inactive_account.role

        url = reverse(
            "admin:users_systemuser_change", args=[self.inactive_account.pk]
        )
        response = self.client.post(
            url,
            {
                "email": self.inactive_account.email,
                "role": SystemUser.Role.ADMIN,
                "is_active": "on",
                "is_staff": "on",
                "_continue": "Save",
            },
        )

        self.inactive_account.refresh_from_db()
        self.assertNotEqual(response.status_code, 200)
        self.assertEqual(self.inactive_account.role, original_role)
        self.assertFalse(self.inactive_account.is_active)

    def test_forged_batch_delete_confirmation_page_must_not_list_hidden_account(self):
        """Primeiro passo da acao em lote (sem "post":"yes" ainda nao
        executa a exclusao -- so renderiza a confirmacao). Corrigido na
        conferencia (ponto 4): a versao anterior so fazia este primeiro
        POST e concluia GREEN porque o objeto obviamente ainda existia --
        prova de ausencia de execucao, nao de comportamento (GREEN vacuo).
        Aqui a pagina de confirmacao em si e inspecionada: ela NAO deveria
        listar/identificar a conta oculta para um papel restrito."""
        viewer = self._make_viewer(SystemUser.Role.GERENTE)
        self.client.force_login(viewer)

        url = reverse("admin:users_systemuser_changelist")
        response = self.client.post(
            url,
            {
                "action": "delete_selected",
                "_selected_action": [str(self.inactive_account.pk)],
                "index": "0",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.inactive_account.email)

    def test_forged_batch_delete_second_step_must_not_actually_remove_hidden_account(
        self,
    ):
        """Segundo passo real (POST com "post":"yes") -- e aqui que a
        exclusao de fato ocorreria se a acao nao filtrar por visibilidade.
        Estado persistido comparado antes/depois, nao apenas o status HTTP."""
        viewer = self._make_viewer(SystemUser.Role.GERENTE)
        self.client.force_login(viewer)

        url = reverse("admin:users_systemuser_changelist")
        self.client.post(
            url,
            {
                "action": "delete_selected",
                "_selected_action": [str(self.inactive_account.pk)],
                "post": "yes",
                "index": "0",
            },
        )

        self.assertTrue(
            SystemUser.objects.filter(pk=self.inactive_account.pk).exists()
        )

    def test_batch_delete_second_step_still_removes_visible_active_account_as_control(
        self,
    ):
        """Controle positivo: a acao em lote continua funcionando de
        verdade para uma conta visivel -- a sobrevivencia da conta oculta
        no teste anterior nao e por a acao estar quebrada/sem efeito."""
        viewer = self._make_viewer(SystemUser.Role.GERENTE)
        self.client.force_login(viewer)

        url = reverse("admin:users_systemuser_changelist")
        self.client.post(
            url,
            {
                "action": "delete_selected",
                "_selected_action": [str(self.active_account.pk)],
                "post": "yes",
                "index": "0",
            },
        )

        self.assertFalse(
            SystemUser.objects.filter(pk=self.active_account.pk).exists()
        )


class T04_StaffSuperuserFlagsDoNotGrantRoleExceptionTests(
    SystemUserAdminInactiveVisibilityTestBase
):
    """T04: is_staff/is_superuser nao substituem a excecao de atividade
    por role ADMIN/DEV. Um papel restrito com ambas as flags continua sem
    ver contas inativas."""

    def test_restricted_role_with_is_staff_and_is_superuser_still_blocked(self):
        viewer = self._make_viewer(
            SystemUser.Role.OPERATOR, is_staff=True, is_superuser=True
        )
        self.client.force_login(viewer)

        response = self.client.get(reverse("admin:users_systemuser_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.inactive_account.email)


class U04_BackofficeSupervisorLinkValidationIgnoresActivityTests(TestCase):
    """UVI-02 U04: "Validar conta proposta; ... Nao afrouxar SystemUser.clean
    para backoffice." Verificado na conferencia corretiva (ponto 1): esta
    nao e uma questao de VISIBILIDADE por role (ambos os caminhos abaixo
    sao exercitados pelo unico caminho real de edicao de SystemUser --
    SystemUserAdmin, confirmado sem rota alternativa de auto-edicao em
    accounts/*), e sim de VALIDACAO do vinculo proposto: SystemUser.clean()
    so confere SystemUser.objects.filter(role=SUPER, email__iexact=...)
    .exists() -- sem is_active -- entao um backoffice pode ser vinculado a
    um supervisor INATIVO sem nenhuma rejeicao, tanto no model quanto pela
    rota real do Admin."""

    def setUp(self):
        self.inactive_super = SystemUser.objects.create_user(
            email="super.inativo.u04.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.inactive_super.is_active = False
        self.inactive_super.save(update_fields=["is_active"])

        self.active_super = SystemUser.objects.create_user(
            email="super.ativo.u04.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )

    def test_model_clean_accepts_inactive_supervisor_link_without_restriction(self):
        backoffice = SystemUser(
            email="backoffice.u04.model.uvi03@test.com",
            role=SystemUser.Role.BACKOFFICE,
            supervisor_email=self.inactive_super.email,
        )
        backoffice.set_password("StrongPass123")

        # Nao deveria levantar ValidationError se o contrato exigisse
        # validar a ATIVIDADE da conta proposta, nao so sua existencia com
        # role=SUPER -- hoje nao levanta (RED: ausencia da excecao
        # esperada e a propria violacao, nao uma assercao de excecao).
        backoffice.full_clean()

    def test_model_clean_accepts_active_supervisor_link_as_control(self):
        """Controle positivo: vincular a um supervisor ativo tambem passa
        -- a ausencia de erro no teste anterior nao e por outro motivo."""
        backoffice = SystemUser(
            email="backoffice.u04.control.uvi03@test.com",
            role=SystemUser.Role.BACKOFFICE,
            supervisor_email=self.active_super.email,
        )
        backoffice.set_password("StrongPass123")

        backoffice.full_clean()

    def test_admin_change_route_accepts_inactive_supervisor_link_without_restriction(
        self,
    ):
        """Mesma verificacao pela rota real (unica existente para editar
        SystemUser: SystemUserAdmin). Viewer ADMIN porque nao ha rota de
        auto-edicao de perfil em accounts/* (confirmado por ausencia de
        app/urls correspondente) -- nao e um teste de visibilidade por
        role, e de validacao do vinculo proposto nessa unica rota real."""
        admin_viewer = SystemUser.objects.create_user(
            email="admin.u04.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        _grant_full_systemuser_perms(admin_viewer)
        self.client.force_login(admin_viewer)

        backoffice = SystemUser.objects.create_user(
            email="backoffice.u04.route.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.BACKOFFICE,
            supervisor_email=self.active_super.email,
        )

        url = reverse("admin:users_systemuser_change", args=[backoffice.pk])
        response = self.client.post(
            url,
            {
                "email": backoffice.email,
                "role": SystemUser.Role.BACKOFFICE,
                "supervisor_email": self.inactive_super.email,
                "manager_email": "",
                "is_active": "on",
                "is_staff": "",
                "is_superuser": "",
                "_continue": "Save",
            },
        )

        backoffice.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(backoffice.supervisor_email, self.inactive_super.email)
