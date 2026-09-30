"""Testes RED da task REL-02 (fonte da verdade: docs/superpowers/specs/2026-09-22-reports-hub-design.md).

Cobrem apenas a aba inicial de Relatorios: rota reports_home, autorizacao
exclusiva ADMIN, entrada de menu e composicao estatica da pagina (dropdown
de relatorio + campos de periodo). Nenhum motor de relatorio e testado aqui.
"""

import re
from urllib.parse import urlencode

from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from core.services.allocation_service import AllocationService
from dashboard.services.query_service import get_pending_action_counts_for_user
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser

NON_ADMIN_ROLES = [
    SystemUser.Role.DEV,
    SystemUser.Role.SUPER,
    SystemUser.Role.BACKOFFICE,
    SystemUser.Role.GERENTE,
    SystemUser.Role.OPERATOR,
]

# Tabelas cuja consulta na renderizacao da aba indicaria motor de relatorio
# prematuro (fora do escopo desta entrega). Corrigido em REL-04 (correcao de
# cobertura): a entrada da tabela de pendencias estava com o nome errado
# ("pendencies_pendency", que nao corresponde a nenhuma tabela real — o
# db_table de AllocationPendency e "pendencies_allocationpendency") e por
# isso nunca capturava uma consulta feita so contra essa tabela.
REPORT_ENTITY_TABLES = [
    "telecom_phoneline",
    "telecom_simcard",
    "allocations_lineallocation",
    "pendencies_allocationpendency",
]

PASSWORD = "StrongPass123"


def _create_user(email, role, **extra):
    return SystemUser.objects.create_user(
        email=email, password=PASSWORD, role=role, **extra
    )


def _report_table_queries(captured_queries):
    """Isola, de uma lista de consultas capturadas, as que tocam alguma
    REPORT_ENTITY_TABLES. Usado tanto pelo teste real de renderizacao quanto
    pelos testes de sensibilidade que provam que o criterio de comparacao
    (baseline exata + multiplicidade) detecta consulta indevida."""
    return [
        query["sql"]
        for query in captured_queries
        if any(table in query["sql"] for table in REPORT_ENTITY_TABLES)
    ]


def _link_operator_to_line(operator, admin):
    """Vincula uma linha ativa ao operator, replicando o fixture real usado
    em telecom/tests.py para que telecom:operator_lines retorne 200 (a view
    responde 403 "sem linha vinculada" para operator sem alocacao ativa,
    independente do menu de Relatorios)."""
    employee = Employee.objects.create(
        full_name="Operator Menu Test",
        corporate_email=f"corp.{operator.pk}@test.com",
        email=operator.email,
        employee_id=f"EMP-MENU-{operator.pk}",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )
    sim_card = SIMcard.objects.create(
        iccid=f"8900000000000{operator.pk:07d}",
        carrier="CarrierMenuTest",
        status=SIMcard.Status.AVAILABLE,
    )
    phone_line = PhoneLine.objects.create(
        phone_number=f"+55119898{operator.pk:06d}",
        sim_card=sim_card,
        status=PhoneLine.Status.AVAILABLE,
        origem=PhoneLine.Origem.SRVMEMU_01,
    )
    AllocationService.allocate_line(
        employee=employee, phone_line=phone_line, allocated_by=admin
    )


class ReportsHomeAccessTests(TestCase):
    """Contrato de acesso e apresentacao da tabela da spec (secao 'Contrato de acesso e apresentacao')."""

    def setUp(self):
        self.admin = _create_user("admin.reports@test.com", SystemUser.Role.ADMIN)
        self.url = reverse("reports_home")

    def test_admin_gets_200(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_non_admin_roles_get_403(self):
        for index, role in enumerate(NON_ADMIN_ROLES):
            with self.subTest(role=role):
                user = _create_user(f"role{index}.reports@test.com", role)
                self.client.force_login(user)
                response = self.client.get(self.url)
                self.assertEqual(response.status_code, 403)

    def test_anonymous_gets_403(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_staff_superuser_without_admin_role_gets_403(self):
        user = _create_user(
            "staffsuper.reports@test.com",
            SystemUser.Role.OPERATOR,
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)


class ReportsHomeMenuTests(TestCase):
    """Entrada de menu real (.rail-nav), visivel somente para ADMIN, apos Telecom e antes de Cadastro."""

    def setUp(self):
        self.admin = _create_user("admin.menu@test.com", SystemUser.Role.ADMIN)
        self.reports_url = reverse("reports_home")
        self.telecom_url = reverse("telecom:overview")
        self.allocations_url = reverse("allocations:allocation_list")

    def test_menu_shows_reports_link_for_admin(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.telecom_url)
        self.assertContains(response, f'href="{self.reports_url}"')
        self.assertContains(response, "Relatórios")

    def test_menu_hides_reports_link_for_non_admin_roles(self):
        role_pages = {
            SystemUser.Role.DEV: reverse("telecom:blip_configuration_list"),
            SystemUser.Role.SUPER: reverse("telecom:overview"),
            SystemUser.Role.BACKOFFICE: reverse("telecom:overview"),
            SystemUser.Role.GERENTE: reverse("telecom:overview"),
            SystemUser.Role.OPERATOR: reverse("telecom:operator_lines"),
        }
        for index, (role, page_url) in enumerate(role_pages.items()):
            with self.subTest(role=role):
                user = _create_user(f"menu{index}.reports@test.com", role)
                if role == SystemUser.Role.OPERATOR:
                    _link_operator_to_line(user, self.admin)
                self.client.force_login(user)
                response = self.client.get(page_url)
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, f'href="{self.reports_url}"')

    def test_reports_link_positioned_after_telecom_before_cadastro(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.telecom_url)
        content = response.content.decode()

        telecom_index = content.index(f'href="{self.telecom_url}"')
        reports_index = content.index(f'href="{self.reports_url}"')
        cadastro_index = content.index(f'href="{self.allocations_url}"')

        self.assertLess(telecom_index, reports_index)
        self.assertLess(reports_index, cadastro_index)

    def test_reports_link_active_only_on_reports_page(self):
        self.client.force_login(self.admin)

        on_reports_page = self.client.get(self.reports_url)
        self.assertContains(
            on_reports_page,
            f'href="{self.reports_url}" class="rail-link is-active"',
        )

        on_other_page = self.client.get(self.telecom_url)
        self.assertContains(
            on_other_page,
            f'href="{self.reports_url}" class="rail-link "',
        )

    def _reports_link_tag(self, content):
        """Extrai a tag <a> exata do link de Relatorios, para inspecionar
        seus proprios atributos (nao apenas a presenca de aria-current em
        algum lugar do HTML renderizado)."""
        match = re.search(
            rf'<a href="{re.escape(self.reports_url)}"[^>]*>', content
        )
        self.assertIsNotNone(
            match, "tag <a> do link de Relatorios nao encontrada no HTML"
        )
        return match.group(0)

    def test_reports_link_has_aria_current_only_on_reports_page(self):
        self.client.force_login(self.admin)

        on_reports_page = self.client.get(self.reports_url)
        reports_tag = self._reports_link_tag(on_reports_page.content.decode())
        self.assertIn('aria-current="page"', reports_tag)
        self.assertIn("is-active", reports_tag)

        on_other_page = self.client.get(self.telecom_url)
        other_tag = self._reports_link_tag(on_other_page.content.decode())
        self.assertNotIn("aria-current", other_tag)
        self.assertNotIn("is-active", other_tag)

    def test_menu_hides_reports_link_for_anonymous_via_real_template(self):
        """Renderiza o template real (reports/home.html, que estende
        base/base.html) com AnonymousUser via RequestFactory, sem passar
        pela view/URL (RoleRequiredMixin bloquearia o anonimo com 403 antes
        de qualquer renderizacao). 403 isolado nao comprova ocultacao do
        menu; aqui a navegacao real e efetivamente renderizada e inspecionada
        para o usuario anonimo, sem copiar a condicao do template para um
        template artificial."""
        factory = RequestFactory()
        request = factory.get(self.reports_url)
        request.user = AnonymousUser()

        html = render_to_string("reports/home.html", request=request)

        self.assertNotIn(f'href="{self.reports_url}"', html)
        self.assertIsNone(
            re.search(rf'<a href="{re.escape(self.reports_url)}"[^>]*>', html),
            "link de Relatorios nao deve aparecer na navegacao para anonimo",
        )


class ReportsHomeContentTests(TestCase):
    """Composicao aprovada: titulo, subtitulo, dropdown de 6 relatorios e campos de periodo separados vazios."""

    def setUp(self):
        self.admin = _create_user("admin.content@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)
        self.url = reverse("reports_home")

    def test_page_shows_title_and_subtitle(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Relatórios")
        self.assertContains(response, "Consulte os relatórios disponíveis do LineOps.")

    def test_page_shows_report_dropdown_with_six_options(self):
        response = self.client.get(self.url)
        content = response.content.decode()

        self.assertIn('<select', content)
        for label in [
            "Selos WhatsApp",
            "Inventário de linhas",
            "Alocações",
            "Pendências",
            "Histórico da linha",
            "Indicadores diários",
        ]:
            self.assertIn(label, content)

    def test_page_shows_separate_empty_date_fields(self):
        response = self.client.get(self.url)
        content = response.content.decode()

        self.assertIn('name="data_inicial"', content)
        self.assertIn('name="data_final"', content)
        self.assertNotIn('name="data_inicial" value="20', content)
        self.assertNotIn('name="data_final" value="20', content)

    def test_page_loads_with_empty_dates_without_premature_error(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn("obrigat", content.lower())
        self.assertNotIn("erro", content.lower())

    def test_page_states_generation_unavailable_without_functional_export(self):
        response = self.client.get(self.url)
        content = response.content.decode()

        self.assertTrue(
            "não está disponível" in content.lower()
            or "ainda não" in content.lower()
            or "indisponível" in content.lower(),
            "pagina deve comunicar por texto que a geracao ainda nao esta disponivel",
        )
        self.assertNotIn(".xlsx", content)
        self.assertNotIn("/exportar", content)
        self.assertNotIn("Gerar relatório\"", content)

    def test_rendering_does_not_query_report_entities(self):
        """Contrato (spec, secao 'Contrato de acesso e apresentacao'): a aba nao
        pode consultar entidades de relatorio para produzir conteudo, mas a
        consulta agregada, ja existente, do context processor global
        pending_actions_count e permitida — nao equivale a consulta de motor
        de relatorio.

        Correcao de cobertura (REL-04): a versao anterior aceitava qualquer
        consulta que apenas mencionasse a assinatura da tabela de pendencias
        (substring), o que nao prova que seja *a* consulta legitima — uma
        consulta totalmente diferente, porem tocando a mesma tabela, teria
        passado. Agora comparamos a consulta capturada, texto a texto, com um
        baseline obtido chamando a mesma funcao de producao
        (get_pending_action_counts_for_user, dashboard/services/query_service.py)
        isoladamente, e exigimos exatamente uma ocorrencia identica a ela —
        cobrindo tanto a identidade da consulta quanto a multiplicidade."""
        with CaptureQueriesContext(connection) as baseline_ctx:
            get_pending_action_counts_for_user(self.admin)
        self.assertEqual(
            len(baseline_ctx.captured_queries),
            1,
            "premissa do teste: a funcao de producao do context processor "
            "deve gerar exatamente 1 consulta isolada, usada como baseline",
        )
        baseline_sql = baseline_ctx.captured_queries[0]["sql"]

        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

        report_table_queries = _report_table_queries(captured.captured_queries)
        self.assertEqual(
            report_table_queries,
            [baseline_sql],
            "renderizacao da aba deve produzir exatamente a consulta baseline "
            "do context processor pending_actions_count as entidades de "
            "relatorio — nem uma consulta diferente, nem mais de uma "
            "ocorrencia (duplicacao)",
        )


class ReportQueryCheckSensitivityTests(TestCase):
    """Prova de sensibilidade (REL-04, correcao de cobertura) do criterio usado
    em test_rendering_does_not_query_report_entities: baseline exata +
    multiplicidade. As perturbacoes abaixo executam SQL real dentro do
    ambiente isolado de teste (nunca mockam a consulta indevida nem alteram
    codigo de aplicacao); provam que o criterio de comparacao detectaria uma
    consulta indevida, caso ela existisse — nao testam a view em si, ja
    coberta pelo teste GREEN acima."""

    def setUp(self):
        self.admin = _create_user("admin.querycheck@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)
        self.url = reverse("reports_home")
        with CaptureQueriesContext(connection) as baseline_ctx:
            get_pending_action_counts_for_user(self.admin)
        self.baseline_sql = baseline_ctx.captured_queries[0]["sql"]

    def test_detects_unrelated_query_on_a_different_report_table(self):
        """Uma consulta real, porem indevida, a uma entidade de relatorio
        diferente (telecom_phoneline) executada durante a mesma renderizacao
        deve fazer a comparacao com o baseline falhar."""
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(self.url)
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM telecom_phoneline")
        self.assertEqual(response.status_code, 200)

        report_table_queries = _report_table_queries(captured.captured_queries)
        self.assertNotEqual(
            report_table_queries,
            [self.baseline_sql],
            "consulta real a outra entidade de relatorio deve divergir do "
            "baseline e ser detectada",
        )

    def test_detects_different_query_on_the_same_permitted_table(self):
        """Uma consulta real, mas com SQL diferente do baseline, contra a
        MESMA tabela permitida (pendencies_allocationpendency) deve ser
        detectada. Isso comprova que mencionar a tabela permitida, por si so,
        nao basta — a versao anterior do teste (substring da tabela + limite
        de 1 ocorrencia) teria aceitado esta consulta indevida por engano,
        pois ela contem a assinatura da tabela e ocorre uma unica vez."""
        rogue_sql = "SELECT COUNT(*) FROM pendencies_allocationpendency"
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(self.url)
            with connection.cursor() as cursor:
                cursor.execute(rogue_sql)
        self.assertEqual(response.status_code, 200)

        report_table_queries = _report_table_queries(captured.captured_queries)
        self.assertIn(
            rogue_sql,
            report_table_queries,
            "premissa do teste: a consulta indevida precisa ter sido capturada",
        )
        self.assertNotEqual(
            report_table_queries,
            [self.baseline_sql],
            "consulta diferente contra a mesma tabela permitida deve ser "
            "detectada como divergente do baseline exato",
        )

    def test_detects_duplicate_of_the_permitted_query(self):
        """Repetir a propria consulta legitima (mesmo codigo de producao,
        chamado uma segunda vez) durante a mesma renderizacao deve fazer a
        comparacao falhar por multiplicidade, mesmo com as duas ocorrencias
        sendo textualmente identicas ao baseline."""
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(self.url)
            get_pending_action_counts_for_user(self.admin)
        self.assertEqual(response.status_code, 200)

        report_table_queries = _report_table_queries(captured.captured_queries)
        self.assertEqual(len(report_table_queries), 2)
        self.assertTrue(all(sql == self.baseline_sql for sql in report_table_queries))
        self.assertNotEqual(
            report_table_queries,
            [self.baseline_sql],
            "duplicacao da propria consulta permitida deve ser detectada "
            "pela checagem de multiplicidade (lista de 2 difere da lista de 1)",
        )


class ExistingNavigationPreservedTests(TestCase):
    """Regressao: links/permissoes existentes continuam intactos nos caminhos afetados pelo menu."""

    def setUp(self):
        self.admin = _create_user("admin.regressao@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_admin_still_sees_telecom_and_cadastro_links(self):
        response = self.client.get(reverse("telecom:overview"))
        self.assertContains(response, f'href="{reverse("telecom:overview")}"')
        self.assertContains(
            response, f'href="{reverse("allocations:allocation_list")}"'
        )

    def test_allocation_list_still_admin_only(self):
        operator = _create_user("operator.regressao@test.com", SystemUser.Role.OPERATOR)
        self.client.force_login(operator)
        response = self.client.get(reverse("allocations:allocation_list"))
        self.assertEqual(response.status_code, 403)


class ReportsHomeUrlNameTests(TestCase):
    """Confirma que a rota nomeada reports_home existe, conforme direcao tecnica da spec."""

    def test_reports_home_url_name_is_registered(self):
        try:
            reverse("reports_home")
        except NoReverseMatch as exc:
            self.fail(
                "reverse('reports_home') deve resolver; rota ainda ausente (RED esperado): "
                f"{exc}"
            )


# Espelha, campo a campo, o bloco especifico de cada relatorio em
# templates/reports/home.html (mesmos nomes de <input>/<select> dentro da
# UNICA <form> do hub) -- exatamente o que um navegador real envia ao
# submeter a pagina, nunca uma URL limpa construida so para contornar o
# defeito. "linha" fica de fora: e campo COMUM (REPORT_COMMON_PARAM_NAMES),
# sempre renderizado em todo bloco, nao um campo especifico de relatorio.
REPORT_SPECIFIC_FIELDS_RENDERED = {
    "whatsapp_seal": ["selo", "pagamento", "situacao"],
    "line_inventory": ["status_linha", "operadora", "origem", "canal", "com_selo", "com_vinculo"],
    "allocations": ["situacao_alocacao", "funcionario"],
    "pendencies": ["situacao_pendencia", "motivo_pendencia", "com_responsavel", "funcionario"],
    "line_history": ["tipo_evento", "fonte_evento", "ator"],
}


def _rendered_form_pairs(relatorio, *, data_inicial, data_final, incluir_excluidos="", linha="", **specific_values):
    """Pares (nome, valor) que o FORMULARIO B ('Filtrar e gerar relatorio')
    real renderiza e submeteria quando `raw.relatorio == relatorio` --
    `relatorio` fixo (campo oculto, nao editavel neste form) + comuns +
    so o bloco especifico deste relatorio (nunca o de outro)."""
    pairs = [
        ("relatorio", relatorio),
        ("data_inicial", data_inicial),
        ("data_final", data_final),
    ]
    for name in REPORT_SPECIFIC_FIELDS_RENDERED.get(relatorio, []):
        pairs.append((name, specific_values.get(name, "")))
    pairs.append(("linha", linha))
    if incluir_excluidos:
        pairs.append(("incluir_excluidos", incluir_excluidos))
    return pairs


def _picker_submission(relatorio, *, data_inicial="", data_final="", incluir_excluidos=""):
    """Reproduz a submissao real do FORMULARIO A ('Selecionar relatorio')
    de templates/reports/home.html, o mecanismo de navegacao que resolve o
    defeito de REL-12-V/REL-12-V-2: contem SOMENTE o `<select
    name="relatorio">` + os comuns ja aplicados na pagina atual, espelhados
    como `<input type="hidden">` so quando nao vazios (mesma guarda
    `{% if raw.X %}` do template) -- NUNCA nenhum campo especifico de
    relatorio, nem da origem nem do destino (Form A nao tem nenhum <input>
    desse tipo na sua propria arvore DOM -- ver
    ReportPickerFormNeverContainsSpecificFieldsTests, que prova isso
    inspecionando o HTML real, nao so simulando). Sem parametro `linha`:
    REL-14 corrigiu o picker para nunca mais espelhar `linha` (REL-07 linha
    672 da spec so garante datas/incluir_excluidos sobrevivendo a troca de
    relatorio) -- nenhuma requisicao real do form picker o inclui mais,
    para nenhum relatorio de origem, entao esta funcao tambem nao o aceita."""
    pairs = [("relatorio", relatorio)]
    if data_inicial:
        pairs.append(("data_inicial", data_inicial))
    if data_final:
        pairs.append(("data_final", data_final))
    if incluir_excluidos:
        pairs.append(("incluir_excluidos", incluir_excluidos))
    return pairs


ALL_SPECIFIC_FIELD_NAMES = set().union(*REPORT_SPECIFIC_FIELDS_RENDERED.values())


def _form_body(html, aria_label):
    match = re.search(
        rf'<form[^>]*aria-label="{re.escape(aria_label)}"[^>]*>(.*?)</form>',
        html, re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"<form aria-label={aria_label!r}> nao encontrado no HTML")
    return match.group(1)


def _form_field_names(html, aria_label):
    return set(re.findall(r'name="([^"]+)"', _form_body(html, aria_label)))


def _make_inventory_line(phone_number, *, operadora):
    sim = SIMcard.objects.create(iccid=f"890000{phone_number[-12:]}", carrier=operadora)
    return PhoneLine.objects.create(
        phone_number=phone_number,
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        origem=PhoneLine.Origem.SRVMEMU_01,
    )


def _make_allocation(phone_number, *, employee_name, admin):
    sim = SIMcard.objects.create(iccid=f"890001{phone_number[-12:]}", carrier="TIM")
    line = PhoneLine.objects.create(
        phone_number=phone_number,
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        origem=PhoneLine.Origem.SRVMEMU_01,
    )
    employee = Employee.objects.create(
        full_name=employee_name,
        corporate_email=f"corp.{phone_number[-6:]}@test.com",
        employee_id=f"EMP-{phone_number[-6:]}",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )
    AllocationService.allocate_line(employee=employee, phone_line=line, allocated_by=admin)
    return line, employee


class ReportQueryStrictWhitelistRegressionTests(TestCase):
    """REL-12-V-2 (2a rodada, correcao da correcao): a entrega anterior de
    REL-12-V-2 resolveu a navegacao de troca de relatorio adicionando
    `tolerate_other_report_params` a `_validate_report_query_params`,
    usado por `ReportsHomeView` — isso afrouxou a validacao da CONSULTA:
    um parametro especifico de OUTRO relatorio ja implementado (ex.:
    `selo`, campo real de whatsapp_seal) parava de ser rejeitado como
    "parametro desconhecido" ao consultar outro relatorio (ex.:
    line_history), mesmo numa requisicao DIRETA sem nenhuma troca de
    dropdown envolvida — violando o contrato aprovado ("Consulta e
    exportacao mantem whitelist estrita por relatorio"). Esta classe
    prova a REGRESSAO da validacao estrita da CONSULTA (o teste
    equivalente de EXPORTACAO ja existia e sempre passou, pois
    `ReportsExportView` nunca recebeu a tolerancia)."""

    def setUp(self):
        self.admin = _create_user("admin.strictwhitelist@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)
        self.today = timezone.localdate().isoformat()
        self.url = reverse("reports_home")

    def test_direct_query_with_foreign_specific_param_is_rejected(self):
        """Requisicao DIRETA (nao uma troca de dropdown — nenhum campo do
        relatorio anterior no payload, so um campo alheio isolado) com
        `selo` (campo real de whatsapp_seal) ao consultar `line_history`
        deve continuar 400 "Parametro desconhecido: selo" — a mesma
        garantia que ja vale para um nome totalmente inexistente."""
        response = self.client.get(
            f"{self.url}?{urlencode([('relatorio', 'line_history'), ('data_inicial', self.today), ('data_final', self.today), ('selo', 'META_ONE')])}"
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Parâmetro desconhecido: selo", status_code=400)

    def test_direct_query_with_foreign_specific_param_from_allocations_is_rejected(self):
        response = self.client.get(
            f"{self.url}?{urlencode([('relatorio', 'pendencies'), ('data_inicial', self.today), ('data_final', self.today), ('situacao_alocacao', 'ativa')])}"
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Parâmetro desconhecido: situacao_alocacao", status_code=400)


class ReportPickerFormNeverContainsSpecificFieldsTests(TestCase):
    """Prova ESTRUTURAL (nao so comportamental) da correcao real de
    REL-12-V-2 (2a rodada): `templates/reports/home.html` foi dividido em
    dois <form> GET independentes — 'Selecionar relatorio' (so `relatorio`
    + comuns ja aplicados, espelhados como <input type=hidden> quando nao
    vazios) e 'Filtrar e gerar relatorio' (`relatorio` fixo em <input
    type=hidden>, nao editavel aqui, + comuns + bloco especifico do
    relatorio EXIBIDO). Nenhuma tolerancia foi adicionada a
    `_validate_report_query_params` (permanece identica a antes de
    REL-12-V: `unknown_params = set(get_params.keys()) - allowed_names`,
    sem excecao para ReportsHomeView) — em vez disso, o formulario que
    troca de relatorio simplesmente NUNCA contem, na sua propria arvore
    DOM, nenhum campo especifico de relatorio algum (nem do exibido, nem
    de nenhum outro), entao a requisicao que ele envia numa troca ja e,
    por construcao, valida para o whitelist estrito original.

    Estes testes inspecionam o HTML REAL renderizado (nao simulam a
    submissao) para provar essa garantia diretamente na fonte, para os 5
    relatorios, cada um com seus proprios filtros especificos preenchidos
    — differencia "nao enviado" (provado aqui) de "enviado e ignorado"
    (o que a tentativa anterior, revertida, fazia)."""

    def setUp(self):
        self.admin = _create_user("admin.pickerstruct@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)
        self.today = timezone.localdate().isoformat()
        self.url = reverse("reports_home")

    def _get(self, pairs):
        return self.client.get(f"{self.url}?{urlencode(pairs)}")

    def test_picker_form_field_set_is_exactly_relatorio_plus_present_commons(self):
        for relatorio, specific in [
            ("whatsapp_seal", {"selo": "META_ONE", "pagamento": "CREDIT_CARD", "situacao": "expired"}),
            ("line_inventory", {"status_linha": "AVAILABLE", "operadora": "X", "origem": "SRVMEMU-01", "canal": "WEB", "com_selo": "com", "com_vinculo": "com"}),
            ("allocations", {"situacao_alocacao": "ativa", "funcionario": "Fulano"}),
            ("pendencies", {"situacao_pendencia": "aberta", "motivo_pendencia": "new_number", "com_responsavel": "com", "funcionario": "Fulano"}),
            ("line_history", {"tipo_evento": "CREATED", "fonte_evento": "PHONE_LINE_HISTORY", "ator": "Fulano"}),
        ]:
            with self.subTest(relatorio=relatorio):
                pairs = _rendered_form_pairs(
                    relatorio, data_inicial=self.today, data_final=self.today,
                    incluir_excluidos="1", linha="9999", **specific,
                )
                response = self._get(pairs)
                self.assertEqual(response.status_code, 200)
                content = response.content.decode()

                picker_fields = _form_field_names(content, "Selecionar relatório")
                self.assertEqual(
                    picker_fields,
                    {"relatorio", "data_inicial", "data_final", "incluir_excluidos"},
                    f"form picker de {relatorio} tem campo(s) inesperado(s) ou ausente(s): "
                    f"{picker_fields ^ {'relatorio', 'data_inicial', 'data_final', 'incluir_excluidos'}}",
                )
                # `linha` continua um filtro real do form "Filtrar e gerar
                # relatorio" deste relatorio (valor "9999" aplicado acima),
                # mas nunca sobrevive a uma troca de relatorio pelo picker —
                # REL-07 (linha 672 da spec) so garante datas/incluir_excluidos
                # na troca; REL-14 corrigiu o picker para nao mais espelhar
                # `linha`, unico jeito sem JS de nao enviar um filtro que o
                # destino pode rejeitar (ex.: daily_indicators).
                self.assertNotIn("linha", picker_fields)
                self.assertFalse(
                    picker_fields & ALL_SPECIFIC_FIELD_NAMES,
                    "form picker nunca pode conter nenhum campo especifico de nenhum relatorio",
                )

    def test_picker_form_omits_empty_common_fields_on_first_use(self):
        """Antes de qualquer consulta bem-sucedida (datas ainda vazias), o
        form picker nao inclui `data_inicial`/`data_final` — evita
        disparar `attempted=True` prematuramente (mesma UX de hoje, sem
        erro de campo obrigatorio so por trocar o dropdown)."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        picker_fields = _form_field_names(response.content.decode(), "Selecionar relatório")
        self.assertEqual(picker_fields, {"relatorio"})

    def test_filters_form_relatorio_field_is_hidden_and_fixed(self):
        """O <select> visivel de relatorio pertence SO ao form picker; o
        form de filtros fixa `relatorio` num <input type=hidden>, nao
        editavel ali — trocar de relatorio so pelo form de filtros e
        estruturalmente impossivel."""
        response = self._get(_rendered_form_pairs(
            "allocations", data_inicial=self.today, data_final=self.today,
        ))
        body = _form_body(response.content.decode(), "Filtrar e gerar relatório")
        self.assertIn('<input type="hidden" name="relatorio" value="allocations">', body)
        self.assertNotIn("<select", body[: body.index('name="relatorio"') + 50])
        self.assertNotIn('id="id_relatorio"', body)


class ReportSwitchViaFormSubmissionTests(TestCase):
    """REL-12-V registrou o defeito (nao especifico de Historico da linha,
    hub inteiro): trocar o dropdown "Relatorio" e submeter uma unica vez,
    sem reload intermediario, reenviava os campos especificos do relatorio
    ANTERIOR ainda presentes no DOM (quando so havia UM <form>) —
    `_validate_report_query_params` rejeitava isso como "parametro
    desconhecido", corretamente (o whitelist estrito por relatorio SEMPRE
    esteve certo).

    2a rodada (REL-12-V-2, correcao da correcao): uma primeira tentativa
    de resolver isso relaxou o proprio validador
    (`tolerate_other_report_params`) — violava "consulta mantem whitelist
    estrita" mesmo para requisicoes diretas sem nenhuma troca envolvida
    (ver ReportQueryStrictWhitelistRegressionTests, que prova essa
    regressao contra o codigo que chegou a ficar no repositorio
    temporariamente). Revertido integralmente: `_validate_report_query_
    params` nao tem mais nenhum parametro/ramo de tolerancia, identica ao
    comportamento anterior a qualquer tentativa de correcao.

    A correcao real esta na ESTRUTURA do template (ver
    ReportPickerFormNeverContainsSpecificFieldsTests): dois <form>
    separados. Esta classe testa o COMPORTAMENTO fim-a-fim da troca via
    `_picker_submission` (que reproduz exatamente o que o form picker
    real envia — nunca uma URL limpa inventada para contornar o defeito,
    ver a prova estrutural acima)."""

    def setUp(self):
        self.admin = _create_user("admin.switch2@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)
        self.today = timezone.localdate().isoformat()
        self.url = reverse("reports_home")

    def _get(self, pairs):
        return self.client.get(f"{self.url}?{urlencode(pairs)}")

    def test_switch_single_submission_succeeds_with_common_params_applied(self):
        """Cenario central do defeito original: origem (line_inventory)
        consultada de verdade com filtro especifico preenchido; troca para
        allocations via UMA unica submissao do form picker; comuns
        (datas) aplicados ao destino; resultado e do destino, nao da
        origem."""
        _make_inventory_line("+5511900010001", operadora="OperadoraOrigemXYZ")
        _, employee = _make_allocation(
            "+5511900010002", employee_name="Funcionario Destino Teste", admin=self.admin
        )

        origem = self._get(_rendered_form_pairs(
            "line_inventory", data_inicial=self.today, data_final=self.today,
            status_linha="AVAILABLE", operadora="OperadoraOrigemXYZ",
        ))
        self.assertEqual(origem.status_code, 200)
        self.assertContains(origem, "OperadoraOrigemXYZ")

        switch_pairs = _picker_submission("allocations", data_inicial=self.today, data_final=self.today)
        self.assertEqual(
            dict(switch_pairs), {"relatorio": "allocations", "data_inicial": self.today, "data_final": self.today},
            "query string efetiva do form picker: so relatorio + comuns aplicados",
        )
        switched = self._get(switch_pairs)

        self.assertEqual(switched.status_code, 200)
        content = switched.content.decode()
        self.assertNotIn("Parâmetro desconhecido", content)
        self.assertNotIn("status_linha", content)
        self.assertNotIn("OperadoraOrigemXYZ", content)
        self.assertContains(switched, "Funcionario Destino Teste")
        # query string efetivamente processada pela view (nao so o que o teste enviou)
        self.assertEqual(set(switched.wsgi_request.GET.keys()), {"relatorio", "data_inicial", "data_final"})

    def test_switch_ignores_stale_specific_because_it_is_never_sent(self):
        """Comparacao direta: consultar allocations direto x via troca do
        picker (saindo de line_inventory com status_linha=CANCELLED, valor
        que zeraria o resultado SE vazasse) produz o MESMO resultado —
        porque o form picker nunca envia `status_linha` para começar,
        nao porque o valor enviado foi descartado."""
        _, employee = _make_allocation(
            "+5511900010003", employee_name="Funcionario Comparacao", admin=self.admin
        )

        direct = self._get(_rendered_form_pairs(
            "allocations", data_inicial=self.today, data_final=self.today,
        ))
        switched = self._get(_picker_submission("allocations", data_inicial=self.today, data_final=self.today))

        self.assertEqual(direct.status_code, 200)
        self.assertEqual(switched.status_code, 200)
        self.assertContains(direct, "Funcionario Comparacao")
        self.assertContains(switched, "Funcionario Comparacao")
        self.assertEqual(
            direct.content.decode().count("Funcionario Comparacao"),
            switched.content.decode().count("Funcionario Comparacao"),
        )

    def test_switch_from_page_greater_than_one_resets_to_page_one(self):
        """Origem (line_inventory) navegada ate a pagina 2 de verdade (55
        linhas reais, PAGE_SIZE=50, link de paginacao real); trocar para
        allocations via picker nunca inclui `page` — reseta implicitamente
        para a pagina 1."""
        for i in range(55):
            _make_inventory_line(f"+551190002{i:04d}", operadora="OperadoraPaginacao")
        origem_pagina_2 = self._get(_rendered_form_pairs(
            "line_inventory", data_inicial=self.today, data_final=self.today,
        ) + [("page", "2")])
        self.assertEqual(origem_pagina_2.status_code, 200)
        self.assertEqual(origem_pagina_2.context["result"].page_number, 2)

        _make_allocation("+5511900010004", employee_name="Funcionario Pagina Um", admin=self.admin)
        switch_pairs = _picker_submission("allocations", data_inicial=self.today, data_final=self.today)
        self.assertNotIn("page", dict(switch_pairs))
        switched = self._get(switch_pairs)

        self.assertEqual(switched.status_code, 200)
        self.assertEqual(switched.context["result"].page_number, 1)

    def test_switch_to_report_with_zero_results_shows_empty_state(self):
        past = "2000-01-01"
        response = self._get(_picker_submission("allocations", data_inicial=past, data_final=past))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nenhum resultado para os filtros selecionados.")

    def test_switch_to_daily_indicators_now_available_succeeds_without_param_error(self):
        """Repropositado em REL-13-Q (2026-09-30): "daily_indicators" era o
        ultimo relatorio do catalogo sem nenhum motor, entao trocar para
        ele via picker (que so envia relatorio+comuns) caia no ramo de
        indisponibilidade total. Agora que a consulta existe, a mesma
        troca em UMA submissao (sem nenhum campo especifico no payload,
        porque este relatorio nao tem nenhum) deve suceder normalmente —
        mesmo mecanismo ja provado para os outros 5 relatorios nesta
        classe, resultado invertido porque o relatorio de destino mudou de
        estado. Nao remove a garantia original (nunca erro de parametro
        numa troca de relatorio via picker), so o pathway generico usado
        para demonstra-la deixou de existir (ver
        config/tests/test_daily_indicators_report.py::
        DailyIndicatorsCatalogClosureNote)."""
        response = self._get(_picker_submission("daily_indicators", data_inicial=self.today, data_final=self.today))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn("Parâmetro desconhecido", content)
        self.assertNotIn("Este relatório ainda não está disponível.", content)

    def test_staying_on_same_report_still_applies_its_own_filter(self):
        """Regressao: usar o form de FILTROS (nao o picker) sem trocar
        relatorio continua filtrando normalmente."""
        _make_inventory_line("+5511900010005", operadora="OperadoraFiltroProprio")
        _make_inventory_line("+5511900010006", operadora="OutraOperadora")

        pairs = _rendered_form_pairs(
            "line_inventory", data_inicial=self.today, data_final=self.today,
            operadora="OperadoraFiltroProprio",
        )
        response = self._get(pairs)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "+5511900010005")
        self.assertNotContains(response, "+5511900010006")

    def test_direct_request_with_genuinely_unknown_parameter_still_rejected(self):
        pairs = _rendered_form_pairs(
            "line_history", data_inicial=self.today, data_final=self.today,
        ) + [("campo_totalmente_inexistente", "x")]
        response = self._get(pairs)
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Parâmetro desconhecido: campo_totalmente_inexistente", status_code=400)

    def test_repeated_common_parameter_rejected_via_picker_form(self):
        pairs = _picker_submission("line_history", data_inicial=self.today, data_final=self.today) + [("data_inicial", "2026-01-01")]
        response = self._get(pairs)
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Parâmetro repetido não é permitido: data_inicial", status_code=400)

    def test_invalid_common_value_rejected_via_picker_form(self):
        """Datas invertidas enviadas pelo PROPRIO form picker (final <
        inicial, ambas comuns) continuam rejeitadas — trocar relatorio nao
        contorna a validacao de valor invalido de campo comum."""
        pairs = _picker_submission("line_inventory", data_inicial=self.today, data_final="2000-01-01")
        response = self._get(pairs)
        self.assertEqual(response.status_code, 400)
        self.assertContains(
            response, "Data final não pode ser anterior à data inicial.", status_code=400
        )

    def test_export_endpoint_still_rejects_foreign_specific_param(self):
        """Exportacao nunca teve nem tem qualquer tolerancia — continua
        estrita, mesmo com um nome que e campo real de outro relatorio."""
        export_url = reverse("reports_export", kwargs={"formato": "csv"})
        pairs = [
            ("relatorio", "line_history"),
            ("data_inicial", self.today),
            ("data_final", self.today),
            ("selo", "META_ONE"),  # campo real de whatsapp_seal, alheio a line_history
        ]
        response = self.client.get(f"{export_url}?{urlencode(pairs)}")
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Parâmetro desconhecido: selo", status_code=400)

    def test_download_links_after_switch_reference_only_destination_report(self):
        """Os links de exportacao pos-troca sao montados a partir de `raw`
        (eco do que foi efetivamente submetido/aceito pelo picker), nunca
        dos valores antigos da origem."""
        _make_inventory_line("+5511900010007", operadora="OperadoraQueNaoDeveVazar")
        origem = self._get(_rendered_form_pairs(
            "line_inventory", data_inicial=self.today, data_final=self.today,
            operadora="OperadoraQueNaoDeveVazar",
        ))
        self.assertEqual(origem.status_code, 200)

        switched = self._get(_picker_submission("line_history", data_inicial=self.today, data_final=self.today))

        self.assertEqual(switched.status_code, 200)
        content = switched.content.decode()
        self.assertIn("/relatorios/exportar/csv/?relatorio=line_history", content)
        self.assertNotIn("OperadoraQueNaoDeveVazar", content)
        self.assertNotIn("status_linha=", content)
