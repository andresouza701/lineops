"""Testes RED da task REL-02 (fonte da verdade: docs/superpowers/specs/2026-09-22-reports-hub-design.md).

Cobrem apenas a aba inicial de Relatorios: rota reports_home, autorizacao
exclusiva ADMIN, entrada de menu e composicao estatica da pagina (dropdown
de relatorio + campos de periodo). Nenhum motor de relatorio e testado aqui.
"""

import re

from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import NoReverseMatch, reverse

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
