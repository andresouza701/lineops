"""
UVI-03 - Testes RED/GREEN da visibilidade de contas de acesso inativas em
EmployeeForm, EmployeeListView/AJAX, EmployeeUpdateView e EmployeeDetailView.

Fonte de verdade: docs/superpowers/specs/2026-10-14-inactive-system-user-visibility-design.md
(UVI-01/UVI-02). Node IDs T05/T06/T08/T09 do checklist derivado em UVI-02.

Revisado na conferencia corretiva (ver secao "UVI-03a" da spec): esta versao
substitui a anterior, que (a) rotulava incorretamente um cenario de UM
supervisor inativo como "fallback de texto livre" quando na verdade o
codigo toma o ramo <select> (mesma causa de T05/T06, nao uma rota
distinta), e (b) nao distinguia a rota real (EmployeeUpdateView, alcancavel
por SUPER/BACKOFFICE/GERENTE) do uso isolado do form sem contexto HTTP.

employees/forms.py::EmployeeForm.__init__ consulta SystemUser por role sem
filtrar is_active (U05) e EmployeeUpdateView.get_form_kwargs nao propaga
nenhum "viewer" ao form (confirmado em employees/views.py): SUPER/
BACKOFFICE/GERENTE que realmente acessam essa rota (EMPLOYEE_ACCESS_ROLES)
recebem exatamente o mesmo formulario sem filtro, nao um caminho hipotetico.
employees/employee_list.html e employee_detail.html (U08/U09) imprimem
corporate_email/manager_email em texto puro. Nenhuma politica foi
implementada ainda (UVI-04/UVI-05): as falhas abaixo documentam a lacuna
real.
"""

from django.test import TestCase
from django.urls import reverse

from employees.forms import EmployeeForm
from employees.models import Employee
from users.models import SystemUser


class EmployeeFormInactiveSupervisorFixture(TestCase):
    def setUp(self):
        self.inactive_super = SystemUser.objects.create_user(
            email="super.inativo.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.inactive_super.is_active = False
        self.inactive_super.save(update_fields=["is_active"])

        self.active_super = SystemUser.objects.create_user(
            email="super.ativo.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.active_manager = SystemUser.objects.create_user(
            email="gerente.ativo.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.GERENTE,
        )

    def _valid_payload(self, corporate_email):
        return {
            "full_name": "Funcionario UVI03",
            "email": "",
            "corporate_email": corporate_email,
            "manager_email": self.active_manager.email,
            "employee_id": "Alimentos",
            "teams": "Joinville",
            "status": Employee.Status.ACTIVE,
            "pa": "",
        }


class T05_EmployeeFormChoicesLeakInactiveSupervisorTest(
    EmployeeFormInactiveSupervisorFixture
):
    """Nivel de unidade (form isolado). Reforcado por
    T05b_EmployeeUpdateViewRealRouteLeaksInactiveSupervisorTest abaixo, que
    exercita a MESMA logica pela rota HTTP real alcancavel por papel
    restrito -- este teste prova a causa no form; aquele prova o alcance."""

    def test_corporate_email_choices_must_not_include_inactive_supervisor(self):
        form = EmployeeForm()

        rendered_values = [value for value, _label in form.fields["corporate_email"].widget.choices]

        self.assertNotIn(self.inactive_super.email, rendered_values)

    def test_corporate_email_choices_still_include_active_supervisor(self):
        """Controle positivo: o supervisor ativo continua disponivel -- a
        ausencia do inativo nao e um efeito colateral de lista vazia."""
        form = EmployeeForm()

        rendered_values = [value for value, _label in form.fields["corporate_email"].widget.choices]

        self.assertIn(self.active_super.email, rendered_values)


class T06_ForgedInactiveSupervisorSelectionTest(
    EmployeeFormInactiveSupervisorFixture
):
    def test_form_must_reject_forged_inactive_supervisor_email(self):
        """POST forjado com o e-mail da conta inativa (fora das opcoes
        exibidas) nao pode ser aceito pelo servidor."""
        form = EmployeeForm(data=self._valid_payload(self.inactive_super.email))

        self.assertFalse(form.is_valid())

    def test_form_accepts_active_supervisor_email_as_control(self):
        """Controle positivo: o mesmo payload com e-mail ativo e aceito --
        a rejeicao anterior nao e por outro campo invalido."""
        form = EmployeeForm(data=self._valid_payload(self.active_super.email))

        self.assertTrue(form.is_valid(), form.errors)


class T05b_EmployeeUpdateViewRealRouteLeaksInactiveSupervisorTest(TestCase):
    """Mesma causa de T05/T06, mas exercitada pela rota HTTP REAL alcancada
    por um papel restrito (BACKOFFICE, dentro de EMPLOYEE_ACCESS_ROLES),
    nao apenas pelo form instanciado isoladamente -- responde diretamente
    ao ponto de conferencia 3 (nao apresentar politica de form isolado como
    se fosse rota acessivel sem prova de alcance real).

    O backoffice.supervisor_email aponta para o MESMO supervisor inativo
    que o funcionario editado tem em corporate_email: e exatamente o
    cenario real em que scope_employee_queryset (SUPERVISOR_SCOPE_ROLES)
    libera o acesso (U11 -- escopo nao filtra por atividade), tornando a
    rota get_object alcancavel sem depender de permissao ADMIN.
    """

    def setUp(self):
        self.inactive_super = SystemUser.objects.create_user(
            email="super.inativo.rota.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.inactive_super.is_active = False
        self.inactive_super.save(update_fields=["is_active"])

        self.active_super = SystemUser.objects.create_user(
            email="super.ativo.rota.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.backoffice = SystemUser.objects.create_user(
            email="backoffice.rota.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.BACKOFFICE,
            supervisor_email=self.inactive_super.email,
        )
        self.employee = Employee.objects.create(
            full_name="Funcionario Rota UVI03",
            corporate_email=self.inactive_super.email,
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        self.client.force_login(self.backoffice)

    def test_backoffice_can_reach_the_employee_update_route_as_control(self):
        """Controle de alcance: a rota existe e responde 200 para este
        viewer -- sem isso, um RED abaixo poderia ser falso-positivo por
        negacao de rota, nao pela ausencia de filtro de visibilidade."""
        response = self.client.get(
            reverse("employees:employee_update", args=[self.employee.pk])
        )

        self.assertEqual(response.status_code, 200)

    def test_edit_form_get_must_not_render_inactive_supervisor_email_as_option(self):
        response = self.client.get(
            reverse("employees:employee_update", args=[self.employee.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.inactive_super.email)

    def test_invalid_post_redisplay_must_not_leak_inactive_supervisor_email(self):
        """Erro em OUTRO campo (employee_id invalido -- nao full_name, que
        fica desabilitado/sem validacao para viewer sem can_edit_full_name,
        confirmado empiricamente na primeira execucao: full_name="" nao
        gerava erro algum, pois campo disabled ignora o POST e usa o
        initial, validando a troca como sucesso/302) preserva a tentativa
        de corporate_email mas nao pode reexibir a identidade da conta
        inativa no HTML redisplayado."""
        response = self.client.post(
            reverse("employees:employee_update", args=[self.employee.pk]),
            {
                "full_name": "Funcionario Rota UVI03",
                "email": "",
                "corporate_email": self.inactive_super.email,
                "manager_email": "",
                "employee_id": "Carteira-Invalida-UVI03",
                "teams": "Joinville",
                "status": Employee.Status.ACTIVE,
                "pa": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.context["form"].errors.get("employee_id"),
            "esperado erro de campo em employee_id (locale pt-br altera o "
            "texto exato da mensagem, por isso nao comparado literalmente)",
        )
        self.assertNotContains(response, self.inactive_super.email)

    def test_switching_to_active_supervisor_on_update_is_accepted_as_control(self):
        """Controle positivo ("trocar por ativo"): a rejeicao do inativo
        nao e um bloqueio generico do formulario -- trocar para um
        supervisor ativo continua funcionando na mesma rota."""
        response = self.client.post(
            reverse("employees:employee_update", args=[self.employee.pk]),
            {
                "full_name": "Funcionario Rota UVI03",
                "email": "",
                "corporate_email": self.active_super.email,
                "manager_email": "",
                "employee_id": "Alimentos",
                "teams": "Joinville",
                "status": Employee.Status.ACTIVE,
                "pa": "",
            },
            follow=False,
        )

        self.employee.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.employee.corporate_email, self.active_super.email)


class T06b_SingleInactiveSupervisorIsStillTheOnlySelectChoiceTest(TestCase):
    """UVI-04 (politica implementada): com UM unico supervisor cadastrado e
    ele inativo, o campo permanece <select> (nao cai para TextInput -- "ha
    conta(s), so que nenhuma visivel" e diferente de "zero contas", ver
    T06c), mas a UNICA opcao real (o e-mail do inativo) nao pode mais ser
    oferecida nem aceita para um viewer sem a excecao de role: contrato
    item 9, "coleção sem candidatos ativos não pode virar TextInput livre
    que permita selecionar conta inativa" -- aqui generalizado para
    tambem nao virar <select> que ofereça esse unico inativo. O campo
    mostra o estado "Nenhum usuario ativo disponivel" e rejeita o e-mail
    forjado no POST (sem vinculo persistido a preservar, pois trata-se de
    uma CRIACAO nova, nao edicao de um funcionario ja vinculado)."""

    def setUp(self):
        self.only_super = SystemUser.objects.create_user(
            email="unico.super.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.only_super.is_active = False
        self.only_super.save(update_fields=["is_active"])

    def test_sole_inactive_supervisor_is_not_offered_as_a_real_choice(self):
        from django import forms as djforms

        form = EmployeeForm()
        self.assertIsInstance(form.fields["corporate_email"].widget, djforms.Select)
        rendered_values = [
            value for value, _label in form.fields["corporate_email"].widget.choices
        ]
        self.assertNotIn(self.only_super.email, rendered_values)

    def test_sole_inactive_supervisor_email_is_rejected_on_forged_post(self):
        payload = {
            "full_name": "Funcionario Unico Super Inativo",
            "email": "",
            "corporate_email": self.only_super.email,
            "manager_email": "",
            "employee_id": "Alimentos",
            "teams": "Joinville",
            "status": Employee.Status.ACTIVE,
            "pa": "",
        }
        bound_form = EmployeeForm(data=payload)
        self.assertFalse(bound_form.is_valid())
        self.assertIn("corporate_email", bound_form.errors)


class T06c_ZeroSupervisorRowsFreeTextFallbackPreservesLegacyBehaviorTest(TestCase):
    """Contrato item 9, cenario REAL de hoje: zero linhas de SystemUser com
    role=SUPER no banco (nao "zero ativas com inativas existindo" -- essa
    distincao so passara a existir depois que UVI-04 filtrar por
    is_active; hoje qualquer linha, ativa ou inativa, já forca o ramo
    <select> -- ver T06b). Neste cenario verdadeiramente vazio o campo cai
    para TextInput e aceita e-mail SEM conta correspondente (categoria "b"
    do ponto 2 da conferencia): e comportamento legado documentado no
    contrato ("valores sem conta correspondente conservam tratamento
    anterior"), NAO um defeito novo desta feature. GREEN esperado."""

    def test_free_text_accepts_email_without_any_matching_account(self):
        from django import forms as djforms

        form = EmployeeForm()
        self.assertIsInstance(
            form.fields["corporate_email"].widget, djforms.TextInput
        )

        payload = {
            "full_name": "Funcionario Sem Supervisor Cadastrado",
            "email": "",
            "corporate_email": "email.sem.conta.uvi03@corp.com",
            "manager_email": "",
            "employee_id": "Alimentos",
            "teams": "Joinville",
            "status": Employee.Status.ACTIVE,
            "pa": "",
        }
        bound_form = EmployeeForm(data=payload)

        self.assertTrue(bound_form.is_valid(), bound_form.errors)


class T08_EmployeeListAndDetailAdminPreservesIdentityTest(TestCase):
    """T08 -- RETIFICADO na conferencia corretiva de UVI-05 (viewer ADMIN).

    Classificacao original (UVI-03/03a/04/04b) registrava esta classe como
    "ambiguidade nao resolvida": o RED com viewer ADMIN era aceito como
    valido sob a leitura "hoje nao existe mascara para ninguem", sem
    decidir se a mascara deveria valer tambem para ADMIN. A entrega de
    UVI-05 decidiu unilateralmente que sim (neutralizacao universal,
    inclusive ADMIN/DEV) -- desvio relatado pelo usuario e retificado
    nesta conferencia: o contrato aprovado (Spec Summary/UVI-01) e
    explicito -- "ADMIN e DEV podem continuar vendo contas inativas em
    listas, buscas ou seletores de contas"; aqui ADMIN acessa
    employee_list (EMPLOYEE_ACCESS_ROLES inclui ADMIN) e
    employee_detail (allowed_roles = [ADMIN], unica role que alcanca essa
    rota) -- autorizacao previa real, nao uma concessao nova. ADMIN deve
    ver a identidade integral; a neutralizacao vale apenas para as quatro
    roles restritas (T08b, abaixo, com BACKOFFICE)."""

    def setUp(self):
        self.inactive_super = SystemUser.objects.create_user(
            email="super.inativo.lista.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.inactive_super.is_active = False
        self.inactive_super.save(update_fields=["is_active"])

        self.admin_viewer = SystemUser.objects.create_user(
            email="admin.lista.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )

        self.employee = Employee.objects.create(
            full_name="Funcionario Com Supervisor Inativo",
            corporate_email=self.inactive_super.email,
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        self.client.force_login(self.admin_viewer)

    def test_employee_list_page_preserves_inactive_supervisor_email_for_admin(self):
        response = self.client.get(reverse("employees:employee_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.inactive_super.email)
        # Controle: o funcionario em si continua presente na lista.
        self.assertContains(response, "Funcionario Com Supervisor Inativo")

    def test_employee_list_ajax_payload_preserves_inactive_supervisor_email_for_admin(self):
        response = self.client.get(
            reverse("employees:employee_list"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        emails_in_payload = {row["corporate_email"] for row in payload["data"]}
        self.assertIn(self.inactive_super.email, emails_in_payload)
        full_names_in_payload = {row["full_name"] for row in payload["data"]}
        self.assertIn("Funcionario Com Supervisor Inativo", full_names_in_payload)

    def test_employee_detail_page_preserves_inactive_supervisor_email_for_admin(self):
        response = self.client.get(
            reverse("employees:employee_detail", args=[self.employee.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.inactive_super.email)


class T08b_EmployeeListUnambiguouslyRestrictedViewerTest(TestCase):
    """Repete a lista (nao o detalhe, que e ADMIN-only por allowed_roles e
    por isso nao alcancavel por BACKOFFICE) com um viewer inequivocamente
    restrito. Inalterado pela conferencia corretiva de UVI-05: a mascara
    SEMPRE valeu (e continua valendo) para BACKOFFICE -- a retificacao
    afetou apenas a classe T08 acima (viewer ADMIN)."""

    def setUp(self):
        self.inactive_super = SystemUser.objects.create_user(
            email="super.inativo.restrito.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.inactive_super.is_active = False
        self.inactive_super.save(update_fields=["is_active"])

        self.backoffice_viewer = SystemUser.objects.create_user(
            email="backoffice.restrito.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.BACKOFFICE,
            supervisor_email=self.inactive_super.email,
        )
        self.employee = Employee.objects.create(
            full_name="Funcionario Restrito Com Supervisor Inativo",
            corporate_email=self.inactive_super.email,
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        self.client.force_login(self.backoffice_viewer)

    def test_backoffice_can_reach_list_as_control(self):
        response = self.client.get(reverse("employees:employee_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Funcionario Restrito Com Supervisor Inativo")

    def test_restricted_viewer_employee_list_must_not_reveal_inactive_supervisor_email(self):
        response = self.client.get(reverse("employees:employee_list"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.inactive_super.email)


class T09_ScopePreservedWhenLinkedSupervisorBecomesInactiveTest(TestCase):
    """T09: desativar o supervisor NAO pode reduzir o escopo de
    funcionarios/linhas (U11 -- decisao explicita de nao filtrar
    scope_employee_queryset/get_managed_supervisor_emails por atividade).

    Corrige a entrega anterior, que citava
    dashboard/tests/test_manager_dashboard_removed_supervisor.py como
    controle equivalente: aquele teste cobre supervisor REMOVIDO (e-mail
    sem SystemUser correspondente, nunca existiu um vinculo real), nao
    supervisor DESATIVADO (conta existe, is_active=False) -- precondicoes
    diferentes, referencia retificada aqui com um teste real e novo para o
    cenario de desativacao."""

    def test_gerente_scope_still_includes_employees_of_deactivated_supervisor(self):
        manager = SystemUser.objects.create_user(
            email="gerente.t09.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.GERENTE,
        )
        supervisor = SystemUser.objects.create_user(
            email="super.t09.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
            manager_email=manager.email,
        )
        employee = Employee.objects.create(
            full_name="Funcionario T09 UVI03",
            corporate_email=supervisor.email,
            manager_email=manager.email,
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )

        supervisor.is_active = False
        supervisor.save(update_fields=["is_active"])

        managed_emails = manager.get_managed_supervisor_emails()
        self.assertIn(supervisor.email, managed_emails)

        scoped_queryset = manager.scope_employee_queryset()
        self.assertIn(employee, list(scoped_queryset))

    def test_backoffice_scope_still_includes_employees_of_deactivated_supervisor(self):
        supervisor = SystemUser.objects.create_user(
            email="super.t09b.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        backoffice = SystemUser.objects.create_user(
            email="backoffice.t09b.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.BACKOFFICE,
            supervisor_email=supervisor.email,
        )
        employee = Employee.objects.create(
            full_name="Funcionario T09b UVI03",
            corporate_email=supervisor.email,
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )

        supervisor.is_active = False
        supervisor.save(update_fields=["is_active"])

        scoped_queryset = backoffice.scope_employee_queryset()
        self.assertIn(employee, list(scoped_queryset))
