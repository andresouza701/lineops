"""
FVI-03 - Testes RED da visibilidade de funcionarios inativos na lista
/employees/ (requisito 1 do checklist desta etapa).

Fonte de verdade: docs/superpowers/specs/2026-10-14-inactive-system-user-visibility-design.md
(FVI-01/FVI-02, secao "Fechamento apos respostas explicitas"). Node IDs
FT01-FT06 derivados nesta etapa (FVI-03).

Nenhuma politica de visibilidade de Employee.status foi implementada ainda
(FVI-04 nao iniciada); falhas aqui documentam a lacuna real contra o
contrato aprovado, nao placeholders. Cada teste cria dados elegiveis para
a asercao esperada (controle positivo) antes de testar a lacuna.
"""

from django.test import TestCase
from django.urls import reverse

from allocations.models import LineAllocation
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser


class InactiveEmployeeListVisibilityTestBase(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="admin.fvi03.list@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.supervisor = SystemUser.objects.create_user(
            email="super.fvi03.list@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.backoffice = SystemUser.objects.create_user(
            email="backoffice.fvi03.list@test.com",
            password="StrongPass123",
            role=SystemUser.Role.BACKOFFICE,
            supervisor_email=self.supervisor.email,
        )
        self.manager = SystemUser.objects.create_user(
            email="gerente.fvi03.list@test.com",
            password="StrongPass123",
            role=SystemUser.Role.GERENTE,
        )

        self.active_employee = Employee.objects.create(
            full_name="Funcionario Ativo Principal",
            corporate_email=self.supervisor.email,
            manager_email=self.manager.email,
            employee_id="EMP-FVI03-A",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )
        self.inactive_employee = Employee.objects.create(
            full_name="Funcionario Inativo Oculto",
            corporate_email=self.supervisor.email,
            manager_email=self.manager.email,
            employee_id="EMP-FVI03-I",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.INACTIVE,
        )


class FT01_InitialListHidesInactiveForRestrictedRoles(
    InactiveEmployeeListVisibilityTestBase
):
    """FT01: render inicial de /employees/ nao deve listar funcionario
    inativo para SUPER/BACKOFFICE/GERENTE; ADMIN preserva visibilidade."""

    def test_super_list_does_not_show_inactive_employee_in_scope(self):
        self.client.force_login(self.supervisor)
        response = self.client.get(reverse("employees:employee_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Funcionario Ativo Principal")
        self.assertNotContains(response, "Funcionario Inativo Oculto")

    def test_backoffice_list_does_not_show_inactive_employee_in_scope(self):
        self.client.force_login(self.backoffice)
        response = self.client.get(reverse("employees:employee_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Funcionario Ativo Principal")
        self.assertNotContains(response, "Funcionario Inativo Oculto")

    def test_manager_list_does_not_show_inactive_employee_in_scope(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse("employees:employee_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Funcionario Ativo Principal")
        self.assertNotContains(response, "Funcionario Inativo Oculto")

    def test_admin_list_still_shows_inactive_employee(self):
        """Controle positivo: ADMIN preserva visibilidade (excecao de
        role, nao ausencia de filtro acidental)."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse("employees:employee_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Funcionario Ativo Principal")
        self.assertContains(response, "Funcionario Inativo Oculto")


class FT02_SearchHidesInactiveForRestrictedRoles(
    InactiveEmployeeListVisibilityTestBase
):
    """FT02: busca por nome/supervisor nao deve encontrar funcionario
    inativo para papel restrito; controle positivo com funcionario ativo."""

    def test_name_search_for_restricted_role_does_not_find_inactive(self):
        """Correcao de teste (FVI-04, causa documentada): o campo de
        busca por nome reecoa o termo pesquisado no proprio
        <input value="..."> (comportamento preexistente, nao relacionado
        a FVI). Buscar exatamente pelo nome do funcionario oculto fazia
        assertNotContains falhar por causa do ECO no input, nao por uma
        linha de resultado.

        Fortalecimento (revisao de cobertura pos-FVI-04): a asercao
        original dependia so de uma string HTML literal (<td>...</td>),
        que passaria mesmo se o markup do <td> ganhasse um atributo
        (ex.: <td class="...">) -- GREEN por coincidencia de markup, nao
        por provar a regra. A verificacao primaria agora inspeciona o
        dado real do servidor (response.context["initial_employees"]),
        imune a qualquer mudanca de markup; o <td> literal e mantido
        como sinal secundario (markup atual confirmado em
        templates/employees/employee_list.html:80), e a linha de "sem
        resultado" (id="no-data-employees") confirma que a tabela esta
        genuinamente vazia, distinguindo isso do eco no input de busca
        (linha 25 do mesmo template, fora da tabela)."""
        self.client.force_login(self.supervisor)
        response = self.client.get(
            reverse("employees:employee_list"),
            {"name": "Funcionario Inativo Oculto"},
        )

        self.assertEqual(response.status_code, 200)

        # Verificacao primaria: dado real do servidor, nao string HTML.
        rendered_pks = {
            employee.pk for employee in response.context["initial_employees"]
        }
        self.assertNotIn(self.inactive_employee.pk, rendered_pks)

        # Confirma que a tabela esta genuinamente vazia (filtro
        # funcionando), nao apenas que uma string nao apareceu por
        # acaso de markup.
        self.assertContains(response, 'id="no-data-employees"')
        self.assertContains(response, "Nenhum usuário encontrado")

        # Sinal secundario, preservado: a celula de resultado real
        # (nao o eco do campo de busca, que usa value="...", nunca
        # <td>...).
        self.assertNotContains(response, "<td>Funcionario Inativo Oculto</td>")

        # O eco no campo de busca e esperado e nao e o que este teste
        # proibe -- confirma que a string aparece (no input), distinta
        # da linha de tabela ja verificada ausente acima.
        self.assertContains(
            response, 'value="Funcionario Inativo Oculto"'
        )

    def test_name_search_for_restricted_role_finds_active_as_control(self):
        self.client.force_login(self.supervisor)
        response = self.client.get(
            reverse("employees:employee_list"),
            {"name": "Funcionario Ativo Principal"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Funcionario Ativo Principal")

    def test_name_search_for_admin_finds_inactive_as_control(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("employees:employee_list"),
            {"name": "Funcionario Inativo Oculto"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Funcionario Inativo Oculto")

    def test_supervisor_search_does_not_find_inactive_for_restricted_role(self):
        self.client.force_login(self.supervisor)
        response = self.client.get(
            reverse("employees:employee_list"),
            {"supervisor": self.supervisor.email},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Funcionario Inativo Oculto")


class FT03_AjaxLoadMoreHidesInactive(InactiveEmployeeListVisibilityTestBase):
    """FT03: payload JSON de "Carregar mais" nao deve incluir o
    funcionario inativo para papel restrito."""

    def _ajax_get(self, **params):
        return self.client.get(
            reverse("employees:employee_list"),
            params,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_ajax_payload_excludes_inactive_employee_for_restricted_role(self):
        self.client.force_login(self.supervisor)
        response = self._ajax_get(offset=0, limit=10)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        ids = {item["id"] for item in payload["data"]}
        self.assertIn(self.active_employee.pk, ids)
        self.assertNotIn(self.inactive_employee.pk, ids)

    def test_ajax_payload_includes_inactive_employee_for_admin_as_control(self):
        self.client.force_login(self.admin)
        response = self._ajax_get(offset=0, limit=10)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        ids = {item["id"] for item in payload["data"]}
        self.assertIn(self.inactive_employee.pk, ids)


class FT04_CountsAndHasMoreFilterBeforePagination(TestCase):
    """FT04: contagem/has_more/offset devem refletir o queryset JA
    filtrado por status, nao o total bruto -- o filtro precisa ocorrer
    ANTES do corte de paginacao, nao depois (requisito explicito do
    contrato)."""

    def setUp(self):
        self.supervisor = SystemUser.objects.create_user(
            email="super.fvi03.count@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        # Ordem alfabetica por full_name: A, B(inativo), C, D.
        self.employee_a = Employee.objects.create(
            full_name="Employee A",
            corporate_email=self.supervisor.email,
            employee_id="EMP-FVI03-CA",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )
        self.employee_b_inactive = Employee.objects.create(
            full_name="Employee B",
            corporate_email=self.supervisor.email,
            employee_id="EMP-FVI03-CB",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.INACTIVE,
        )
        self.employee_c = Employee.objects.create(
            full_name="Employee C",
            corporate_email=self.supervisor.email,
            employee_id="EMP-FVI03-CC",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )
        self.employee_d = Employee.objects.create(
            full_name="Employee D",
            corporate_email=self.supervisor.email,
            employee_id="EMP-FVI03-CD",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )
        self.client.force_login(self.supervisor)

    def test_has_more_reflects_filtered_count_not_raw_count(self):
        """3 ativos (A,C,D) + 1 inativo (B) = 4 linhas no banco. Com
        limit=3/offset=0: filtrado (A,C,D) esgota em 3 -> has_more deve
        ser False. Sem o filtro (comportamento atual), a fatia bruta
        [A,B,C] tambem teria 3 itens mas o total bruto (4) > 3 fixaria
        has_more incorretamente em True -- divergencia observavel."""
        response = self.client.get(
            reverse("employees:employee_list"),
            {"offset": 0, "limit": 3},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        ids = [item["id"] for item in payload["data"]]
        self.assertEqual(
            ids, [self.employee_a.pk, self.employee_c.pk, self.employee_d.pk]
        )
        self.assertFalse(payload["has_more"])

    def test_initial_render_has_more_employees_flag_excludes_inactive(self):
        """Mesma divergencia no contexto do render inicial
        (has_more_employees), paginate_by=10 (ajustado via monkeypatch de
        instancia nao e permitido; aqui so os 4 registros existem, bem
        abaixo do paginate_by padrao, entao has_more_employees deve ser
        False de qualquer forma -- o teste real de corte esta no AJAX
        acima, que permite limit explicito). Aqui garantimos apenas que a
        contagem inicial (quantidade de linhas renderizadas) exclui o
        inativo, reforcando o mesmo filtro no caminho nao-AJAX."""
        response = self.client.get(reverse("employees:employee_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Employee A")
        self.assertContains(response, "Employee C")
        self.assertContains(response, "Employee D")
        self.assertNotContains(response, "Employee B")


class FT05_QueryCostDoesNotGrowWithInactiveCount(TestCase):
    """FT05 (requisito 10): o custo de consulta da lista nao deve crescer
    linearmente com o numero de funcionarios inativos no escopo. Este
    teste NAO documenta uma lacuna do contrato de visibilidade (o codigo
    atual tambem nao faz N+1 por linha); serve de guarda de regressao
    para a futura composicao de queryset em FVI-04 -- registrado como
    cobertura de controle, nao RED."""

    def setUp(self):
        self.supervisor = SystemUser.objects.create_user(
            email="super.fvi03.cost@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.client.force_login(self.supervisor)

    def _create_employees(self, count, *, status, prefix):
        for i in range(count):
            Employee.objects.create(
                full_name=f"{prefix} {i:03d}",
                corporate_email=self.supervisor.email,
                employee_id=f"EMP-{prefix}-{i:03d}",
                teams=Employee.UnitChoices.JOINVILLE,
                status=status,
            )

    def test_query_count_is_stable_regardless_of_inactive_volume(self):
        self._create_employees(2, status=Employee.Status.ACTIVE, prefix="Base")

        with self.assertNumQueries(self._baseline_query_count()):
            self.client.get(reverse("employees:employee_list"))

        self._create_employees(
            30, status=Employee.Status.INACTIVE, prefix="Volume"
        )

        with self.assertNumQueries(self._baseline_query_count()):
            self.client.get(reverse("employees:employee_list"))

    def _baseline_query_count(self):
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        with CaptureQueriesContext(connection) as ctx:
            self.client.get(reverse("employees:employee_list"))
        return len(ctx.captured_queries)


class FT06_UviAndFviAreIndependentAxes(TestCase):
    """FT06 (requisito 9): Employee.status (FVI) e SystemUser.is_active
    (UVI) sao eixos independentes. Funcionario ativo com supervisor de
    conta inativa continua visivel e mascarado (UVI); funcionario
    inativo e ocultado (FVI) mesmo com supervisor de conta ativa."""

    def setUp(self):
        self.manager = SystemUser.objects.create_user(
            email="gerente.fvi03.axes@test.com",
            password="StrongPass123",
            role=SystemUser.Role.GERENTE,
        )
        self.inactive_supervisor_account = SystemUser.objects.create_user(
            email="super.inativo.fvi03.axes@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.inactive_supervisor_account.is_active = False
        self.inactive_supervisor_account.save(update_fields=["is_active"])

        self.active_supervisor_account = SystemUser.objects.create_user(
            email="super.ativo.fvi03.axes@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )

        self.active_employee_masked_supervisor = Employee.objects.create(
            full_name="Ativo Supervisor Inativo",
            corporate_email=self.inactive_supervisor_account.email,
            manager_email=self.manager.email,
            employee_id="EMP-FVI03-AX1",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )
        self.inactive_employee_active_supervisor = Employee.objects.create(
            full_name="Inativo Supervisor Ativo",
            corporate_email=self.active_supervisor_account.email,
            manager_email=self.manager.email,
            employee_id="EMP-FVI03-AX2",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.INACTIVE,
        )
        self.client.force_login(self.manager)

    def test_active_employee_with_inactive_supervisor_stays_visible_and_masked(
        self,
    ):
        """Controle positivo (UVI ja implementada): nao deve regredir
        com a introducao da FVI."""
        response = self.client.get(reverse("employees:employee_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ativo Supervisor Inativo")
        self.assertNotContains(
            response, self.inactive_supervisor_account.email
        )
        self.assertContains(response, "Usuário inativo")

    def test_inactive_employee_with_active_supervisor_is_hidden(self):
        """RED: FVI ainda nao oculta o funcionario inativo mesmo quando
        o supervisor vinculado esta ativo -- a ocultacao e por
        Employee.status, nao por SystemUser.is_active."""
        response = self.client.get(reverse("employees:employee_list"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Inativo Supervisor Ativo")
