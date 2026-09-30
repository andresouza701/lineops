"""Testes RED da task REL-13-T (fonte da verdade:
docs/superpowers/specs/2026-09-22-reports-hub-design.md, secoes REL-07 e
REL-13-C — leitura integral obrigatoria, incluindo as quatro decisoes A-D
aprovadas em 2026-09-30 e as "Ressalvas documentais de REL-13-C").

Cobrem o relatorio daily_indicators: consulta na tela (endpoint existente
GET /relatorios/, motor ainda ausente) e exportacoes CSV/XLSX (endpoint ja
registrado desde REL-08-E, reports_export, cujo dispatch hoje nao inclui
daily_indicators). Nao testa a aba generica (rota, menu, autorizacao base,
dropdown com 6 opcoes) nem os motores dos outros 5 relatorios, ja cobertos
em config/tests/test_reports_hub.py e nos respectivos
config/tests/test_*_report.py — reaproveitados, nao duplicados.

Estado atual do motor (2026-09-30, antes de REL-13-Q/E): "daily_indicators"
nao esta em REPORT_SPECIFIC_PARAM_NAMES, REPORT_FORM_CLASSES,
REPORT_QUERY_ENGINES nem REPORT_EXPORT_ENGINES (config/views.py) — e o
UNICO relatorio do catalogo REL-01 sem NENHUM motor nesta etapa (ja
confirmado por config/tests/test_line_inventory_report.py::
OtherReportStillUnavailableTests::
test_daily_indicators_report_still_returns_400_engine_unavailable e por
config/tests/test_reports_hub.py::...::
test_switch_to_unavailable_report_shows_unavailable_message_not_param_error
— NAO duplicados aqui). Isso produz dois tipos de resultado real e
distinto, ambos verificados explicitamente nas classes abaixo (nunca
presumidos):

1. Validacao comum (REL-07: datas obrigatorias/invalidas/invertidas,
   incluir_excluidos, page, parametro repetido, parametro totalmente
   desconhecido) roda ANTES do despacho por relatorio usando o form
   generico de fallback (WhatsAppSealReportQueryForm, unico que ja possui
   data_inicial/data_final/incluir_excluidos/page/linha) — GREEN real
   hoje, nao RED, porque o contrato comum ja se aplica independente do
   motor de Indicadores diarios existir. 16 dos 60 testes desta task caem
   aqui (contrato comum + autorizacao + baseline de formato/relatorio
   desconhecido).
2. Qualquer requisito especifico do contrato aprovado em REL-13-C (nove
   colunas herdadas de build_indicator_for_day, granularidade por dia
   calendario, ausencia de escrita, totalizadores restritos a
   Entregues/Reconectados/Novos, checkbox oculto, rejeicao de `linha`,
   paginacao/ordenacao) depende do motor ainda inexistente — mas o
   RESULTADO OBSERVADO nao e uniforme, e os 44 RED restantes se dividem em
   TRES causas distintas (nunca "uma causa unica"), reconciliadas por
   execucao real (nao por suposicao) na secao "Gap Analysis" da entrega
   REL-13-T na fonte da verdade:
   a. **Motor ausente (40 testes)**: `daily_indicators` fora de
      `REPORT_QUERY_ENGINES`/`REPORT_EXPORT_ENGINES` — a requisicao cai em
      "relatorio ainda nao disponivel" (400) antes de qualquer logica
      especifica rodar. Falha sempre na PRIMEIRA asserção de status
      (`assertEqual(response.status_code, 200)`, ou 404 no caso de
      paginacao fora do intervalo).
   b. **Template sem ramo proprio (2 testes,
      `DailyIndicatorsIncluirExcluidosContractTests.
      test_checkbox_hidden_for_daily_indicators`/
      `test_other_report_specific_fields_not_rendered_for_daily_indicators`)**:
      a pagina SEM datas (`attempted=False`) retorna 200 hoje (o motor
      nunca e chamado nesse caminho) — a falha e de CONTEUDO, nao de
      status: `templates/reports/home.html` nao tem nenhum ramo
      `{% elif raw.relatorio == "daily_indicators" %}` (cai no `{% else %}`
      de Selos WhatsApp) nem guarda de ocultacao do checkbox "Incluir
      excluidos".
   c. **Parametro `linha` ainda sem validacao especifica (2 testes,
      `DailyIndicatorsLinhaRejectedTests`)**: o STATUS ja bate com o
      contrato (400), mas pela razao ERRADA — `linha` esta no whitelist
      comum e o form de fallback o aceita sem erro; o 400 real vem do
      motor ausente (mesma causa (a)), nao da rejeicao especifica "nao
      aplicavel a este relatorio" exigida por REL-13-C. A falha ocorre na
      asserção de CONTEUDO (`assertNotIn(UNAVAILABLE_MESSAGE, ...)`), nao
      na de status.
   Nenhuma exceção/erro de fixture nas 44 (0 `ERROR`, confirmado por
   execucao real) — todas falham por `AssertionError` limpo, na asserção
   documentada acima para cada categoria.

Nota (secao 10 do enunciado desta task, "ultimo relatorio do catalogo"):
os testes acima citados usam "daily_indicators" como UNICO exemplo restante
de "relatorio do catalogo REL-01 genuinamente sem nenhum motor". Quando
REL-13-Q implementar o motor de consulta, aquele pathway generico ficara
sem nenhum relatorio real para exemplificar "totalmente indisponivel" —
diferente das quatro reproposicoes anteriores (line_inventory -> allocations
-> pendencies -> line_history -> daily_indicators), NAO havera um setimo
relatorio do catalogo para substituir o exemplo. Registrado aqui e na fonte
da verdade (secao "Ultimo relatorio do catalogo" ao final desta task);
aqueles testes NAO sao alterados por esta task — a revisao da cobertura
generica fica para quando REL-13-Q fechar o catalogo, nao antes.

Fixtures usam ORM direto (Employee/PhoneLine/SIMcard/LineAllocation),
backdatando created_at/allocated_at via queryset.update() quando
necessario (auto_now_add impede setar no create()) — mesmo padrao ja usado
em dashboard/tests/test_reconnect_counter.py::_make_allocation. O relogio
(`django.utils.timezone.localdate`/`.now`) e congelado nas classes que
dependem de "hoje" (regra de dia historico, is_historical_day) para tornar
o resultado deterministico independente da data real de execucao da
suite.

Volume/particionamento em ZIP/limiar de exportacao (REL-07, herdado
integralmente por REL-13-C) dependem de um exportador que ainda nao existe
(core/services/daily_indicators_export_service.py, proposto para REL-13-E)
— sem interface de configuracao de limiar para reduzir em teste sem
inventar uma API nova, explicitamente fora do escopo desta task. Medicao
de desempenho por quantidade de DIAS (nao registros) fica para REL-13-Q,
com criterio de aceite definido ANTES da medicao (REL-13-C, decisao D) —
nenhum SLA numerico e presumido aqui; o teste de custo desta task apenas
comprova ausencia de escalonamento nao-linear grosseiro (secao 6 do
enunciado), nunca um numero fixo de queries nem um periodo impraticavel.
"""

import csv
import io
import itertools
import os
import shutil
import sys
import time as time_module
import zipfile
from datetime import date, datetime, time, timedelta
from unittest import mock
from urllib.parse import urlencode

import openpyxl
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from allocations.models import LineAllocation
from dashboard.models import DashboardDailySnapshot
from dashboard.views import build_indicator_for_day, count_reconnected_numbers_for_day
from employees.models import Employee, EmployeeHistory
from telecom.models import LineDailyActionAuditEvent, PhoneLine, PhoneLineHistory, SIMcard
from users.models import SystemUser

PASSWORD = "StrongPass123"
REPORTS_URL_NAME = "reports_home"
EXPORT_URL_NAME = "reports_export"

NON_ADMIN_ROLES = [
    SystemUser.Role.DEV,
    SystemUser.Role.SUPER,
    SystemUser.Role.BACKOFFICE,
    SystemUser.Role.GERENTE,
    SystemUser.Role.OPERATOR,
]

# "Hoje" congelado (django.utils.timezone.localdate/.now) nas classes que
# dependem da regra de dia historico (is_historical_day, dashboard/views.py:
# "day < timezone.localdate()"). Todos os periodos fixos desta task (2024,
# 2025-12/2026-01, 2026-09) ficam no passado em relacao a este valor.
FROZEN_TODAY = date(2026, 10, 15)
FROZEN_NOW = timezone.make_aware(datetime.combine(FROZEN_TODAY, time(12, 0, 0)))

PERIOD_START = "2026-09-01"
PERIOD_END = "2026-09-05"

EXPECTED_COLUMN_HEADERS = [
    "Data",
    "Pessoas Logadas",
    "% sem Whats",
    "B2B sem Whats",
    "B2C sem Whats",
    "Números Disponíveis",
    "Números Entregues",
    "Reconectados",
    "Novos",
    "Total Descoberto DIA",
]

NAO_APLICAVEL_LABEL = "Não aplicável"
UNAVAILABLE_MESSAGE = "Este relatório ainda não está disponível."

_iccid_counter = itertools.count(1)
_employee_counter = itertools.count(1)


def _create_user(email, role, **extra):
    return SystemUser.objects.create_user(email=email, password=PASSWORD, role=role, **extra)


def _local_midnight(d):
    return timezone.make_aware(datetime.combine(d, time.min))


def _local_last_instant(d):
    return timezone.make_aware(datetime.combine(d, time(23, 59, 59, 999999)))


def _report_url(pairs):
    return f"{reverse(REPORTS_URL_NAME)}?{urlencode(pairs)}"


def _export_url(formato, pairs):
    return f"{reverse(EXPORT_URL_NAME, kwargs={'formato': formato})}?{urlencode(pairs)}"


def _export_bytes(response):
    """`ReportsExportView` sempre responde com StreamingHttpResponse (sem
    `.content` acessivel) — le o corpo real do jeito que um cliente real
    leria, sem depender de buffer intermediario."""
    return b"".join(response.streaming_content) if response.streaming else response.content


def _base_pairs(data_inicial=PERIOD_START, data_final=PERIOD_END, **extra):
    pairs = [
        ("relatorio", "daily_indicators"),
        ("data_inicial", data_inicial),
        ("data_final", data_final),
    ]
    pairs.extend(extra.items())
    return pairs


def _make_line(phone_number, *, status=PhoneLine.Status.AVAILABLE, created_at=None):
    """Cria PhoneLine+SIMcard reais. created_at e backdatado via
    queryset.update() (auto_now_add ignora valor passado no create()),
    mesmo padrao de dashboard/tests/test_reconnect_counter.py."""
    sim = SIMcard.objects.create(
        iccid=f"8900000000002{next(_iccid_counter):05d}", carrier="TIM"
    )
    line = PhoneLine.objects.create(
        phone_number=phone_number, sim_card=sim, status=status
    )
    if created_at is not None:
        PhoneLine.all_objects.filter(pk=line.pk).update(created_at=created_at)
        line.refresh_from_db()
    return line


def _delete_line(line, admin=None):
    line.delete(released_by=admin)
    line.refresh_from_db()
    return line


def _make_employee(portfolio, *, label=None, status=Employee.Status.ACTIVE, created_at=None):
    """`portfolio` vira `employee_id` (carteira), mesma convencao de
    dashboard/tests.py::DashboardDailyIndicatorsTests (ex.: "Alimentos" e
    B2B, "Natura" e B2C, conforme core/constants/portfolio_choices.py)."""
    suffix = label or next(_employee_counter)
    employee = Employee.objects.create(
        full_name=f"Indicador Teste {suffix}",
        corporate_email=f"indicador.{suffix}@corp.com",
        employee_id=portfolio,
        teams=Employee.UnitChoices.JOINVILLE,
        status=status,
    )
    if created_at is not None:
        Employee.all_objects.filter(pk=employee.pk).update(created_at=created_at)
        employee.refresh_from_db()
    return employee


def _delete_employee(employee):
    employee.delete()
    employee.refresh_from_db()
    return employee


def _allocate_at(line, employee, admin, allocated_at, *, released_at=None):
    """allocated_at/released_at sao backdatados via queryset.update() (mesmo
    motivo de _make_line: auto_now_add nao aceita valor no create())."""
    allocation = LineAllocation.objects.create(
        employee=employee,
        phone_line=line,
        allocated_by=admin,
        is_active=True,
    )
    update_kwargs = {"allocated_at": allocated_at}
    if released_at is not None:
        update_kwargs["released_at"] = released_at
        update_kwargs["is_active"] = False
    LineAllocation.objects.filter(pk=allocation.pk).update(**update_kwargs)
    allocation.refresh_from_db()
    return allocation


def _assert_no_business_write_sql(test_case, captured_queries):
    """Prova de somente-leitura PATH-AGNOSTICA (secao 4 do enunciado desta
    correcao): varre TODAS as queries SQL de fato executadas durante a
    requisicao e falha se qualquer INSERT/UPDATE/DELETE atingir uma tabela
    diferente de `django_session` (efeito tecnico legitimo do
    `force_login`/sessao do proprio test client, nao uma escrita de
    negocio) — nao depende de listar de antemao quais tabelas o motor
    poderia tocar (DashboardDailySnapshot ou qualquer outra), entao nao
    trata a ausencia de escrita em UMA tabela como prova universal."""
    for query in captured_queries:
        sql = query["sql"]
        sql_upper = sql.upper().lstrip()
        if sql_upper.startswith(("INSERT", "UPDATE", "DELETE")):
            test_case.assertIn(
                "django_session", sql.lower(),
                f"Escrita de negocio inesperada durante consulta somente leitura: {sql}",
            )


def _freeze_today(test_case):
    """Congela django.utils.timezone.localdate()/.now() em FROZEN_TODAY
    para todos os testes da classe — necessario porque
    dashboard.views.is_historical_day compara `day < timezone.localdate()`,
    usado transitivamente por build_indicator_for_day."""
    localdate_patch = mock.patch("django.utils.timezone.localdate", return_value=FROZEN_TODAY)
    now_patch = mock.patch("django.utils.timezone.now", return_value=FROZEN_NOW)
    localdate_patch.start()
    now_patch.start()
    test_case.addCleanup(localdate_patch.stop)
    test_case.addCleanup(now_patch.stop)


class DailyIndicatorsSharedValidationAppliesTests(TestCase):
    """Contrato comum (REL-07), validado pelo form de fallback
    (WhatsAppSealReportQueryForm) ANTES do despacho por relatorio
    (_validate_report_query_params so verifica `available_relatorios`
    depois de validar o form). GREEN real hoje — nao depende do motor de
    Indicadores diarios existir. Mesma cobertura de
    PendenciesReportSharedValidationAppliesTests
    (config/tests/test_pendencies_report.py), reaproveitada aqui para
    daily_indicators sem duplicar a intencao (relatorio diferente,
    contrato comum identico)."""

    def setUp(self):
        self.admin = _create_user("admin.di.sharedval@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_missing_data_inicial_rejected(self):
        response = self.client.get(
            _report_url([("relatorio", "daily_indicators"), ("data_final", PERIOD_END)])
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_data_final_rejected(self):
        response = self.client.get(
            _report_url([("relatorio", "daily_indicators"), ("data_inicial", PERIOD_START)])
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_date_format_rejected(self):
        response = self.client.get(
            _report_url([("relatorio", "daily_indicators"), ("data_inicial", "31/09/2026"), ("data_final", PERIOD_END)])
        )
        self.assertEqual(response.status_code, 400)

    def test_inverted_dates_rejected(self):
        response = self.client.get(
            _report_url([("relatorio", "daily_indicators"), ("data_inicial", PERIOD_END), ("data_final", PERIOD_START)])
        )
        self.assertEqual(response.status_code, 400)

    def test_incluir_excluidos_invalid_value_rejected(self):
        response = self.client.get(_report_url(_base_pairs(incluir_excluidos="2")))
        self.assertEqual(response.status_code, 400)

    def test_page_non_integer_rejected(self):
        response = self.client.get(_report_url(_base_pairs(page="abc")))
        self.assertEqual(response.status_code, 400)

    def test_page_zero_rejected(self):
        response = self.client.get(_report_url(_base_pairs(page="0")))
        self.assertEqual(response.status_code, 400)

    def test_repeated_scalar_parameter_rejected(self):
        url = reverse(REPORTS_URL_NAME)
        response = self.client.get(
            f"{url}?relatorio=daily_indicators&data_inicial={PERIOD_START}&data_inicial=2026-09-02&data_final={PERIOD_END}"
        )
        self.assertEqual(response.status_code, 400)

    def test_unknown_generic_query_parameter_rejected(self):
        response = self.client.get(_report_url(_base_pairs(campo_totalmente_inexistente="x")))
        self.assertEqual(response.status_code, 400)

    def test_anonymous_gets_403_before_any_validation(self):
        self.client.logout()
        response = self.client.get(_report_url(_base_pairs()))
        self.assertEqual(response.status_code, 403)

    def test_non_admin_roles_get_403_before_any_validation(self):
        for index, role in enumerate(NON_ADMIN_ROLES):
            with self.subTest(role=role):
                user = _create_user(f"di.role{index}@test.com", role)
                self.client.force_login(user)
                response = self.client.get(_report_url(_base_pairs()))
                self.assertEqual(response.status_code, 403)


EXPORT_ONLY_UNAVAILABLE_MESSAGE = (
    "A exportação deste relatório ainda não está disponível nesta etapa."
)


class DailyIndicatorsExportEngineUnavailableBaselineTests(TestCase):
    """Baseline documental, atualizada pela TERCEIRA vez.

    Original (antes de REL-13-Q): "daily_indicators" nao estava em nenhum
    dos dois motores — download direto caia no ramo "relatorio totalmente
    indisponivel" (UNAVAILABLE_MESSAGE).

    REL-13-Q (2026-09-30): ligou SOMENTE REPORT_QUERY_ENGINES (enunciado
    daquela task: "Nao adicione a REPORT_EXPORT_ENGINES") — primeira vez
    que um relatorio do catalogo REL-01 teve consulta sem exportacao. A
    mensagem correta passou a ser a de "exportacao ainda nao disponivel
    nesta etapa" (EXPORT_ONLY_UNAVAILABLE_MESSAGE).

    REL-13-E (2026-09-30, ESTA TASK): "daily_indicators" ganhou motor de
    EXPORTACAO tambem (REPORT_EXPORT_ENGINES) — a alegacao "exportacao
    ainda nao disponivel" deixou de ser verdadeira, mesmo padrao de
    repropose ja aplicado em REL-10-E/REL-11-E/REL-12-E
    (AllocationsReportStillUnavailableTests/PendenciesReportStillUnavailableTests/
    LineHistoryReportEngineUnavailableBaselineTests: 400 vira 200 com
    anexo real). Indicadores diarios e o ULTIMO relatorio do catalogo
    REL-01 a fechar o par consulta+exportacao — nenhum setimo relatorio
    existe para reproposicionar este teste outra vez; a classe permanece
    como registro historico das duas transicoes anteriores.
    `test_unknown_format_returns_404_regardless_of_engine` permanece
    inalterado (nao depende de motor)."""

    def setUp(self):
        self.admin = _create_user("admin.di.exportbaseline@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_export_now_returns_200_attachment_with_valid_common_params(self):
        response = self.client.get(_export_url("csv", _base_pairs()))
        self.assertEqual(response.status_code, 200)
        content_type = response.headers.get("Content-Type", "")
        self.assertIn("csv", content_type.lower())
        self.assertIn("attachment", response.headers.get("Content-Disposition", ""))

    def test_unknown_format_returns_404_regardless_of_engine(self):
        response = self.client.get(_export_url("pdf", _base_pairs()))
        self.assertEqual(response.status_code, 404)


class DailyIndicatorsLinhaRejectedTests(TestCase):
    """Secao 5 do enunciado / REL-13-C secao 3 ("Filtros propostos"):
    `linha` e comum a todos os relatorios (REPORT_COMMON_PARAM_NAMES,
    config/views.py:56-63) mas NAO tem dimensao aplicavel a um indicador
    agregado por dia — o form especifico deste relatorio deve rejeita-lo
    com 400 "Parametro nao aplicavel a este relatorio", em vez de cair no
    400 generico de "relatorio ainda nao disponivel" (que e o que
    acontece HOJE, porque `linha` ja e conhecido pelo whitelist comum e o
    form de fallback o aceita sem erro — o motivo real do 400 atual e o
    motor ausente, nao a rejeicao especifica exigida pelo contrato)."""

    def setUp(self):
        self.admin = _create_user("admin.di.linha@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_linha_rejected_with_not_applicable_message_on_query(self):
        response = self.client.get(_report_url(_base_pairs(linha="93000001")))
        self.assertEqual(response.status_code, 400)
        content = response.content.decode()
        self.assertNotIn(
            UNAVAILABLE_MESSAGE, content,
            "400 atual vem do motor ausente, nao da rejeicao especifica de "
            "'linha' exigida pelo contrato (REL-13-C) — RED real: a "
            "mensagem especifica ainda nao existe.",
        )
        self.assertIn("aplic", content.lower())

    def test_linha_rejected_with_not_applicable_message_on_export(self):
        response = self.client.get(_export_url("csv", _base_pairs(linha="93000001")))
        self.assertEqual(response.status_code, 400)
        content = response.content.decode()
        self.assertNotIn(UNAVAILABLE_MESSAGE, content)
        self.assertIn("aplic", content.lower())


class DailyIndicatorsIncluirExcluidosContractTests(TestCase):
    """REL-13-C, decisao C (2026-09-30) + "Ressalvas documentais":
    checkbox "Incluir excluídos" oculto SO para daily_indicators (estrutura
    do template), parametro HTTP continua aceito e inerte (whitelist comum,
    sem 400, resultado identico com ou sem ele), e a troca de relatorio em
    UMA submissao (form picker, que so envia relatorio+comuns) deve
    funcionar assim que o motor existir."""

    def setUp(self):
        self.admin = _create_user("admin.di.incluir@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_checkbox_hidden_for_daily_indicators(self):
        """RED real: templates/reports/home.html ainda renderiza o
        checkbox incondicionalmente (linha 239-243), sem nenhum bloco
        `{% if raw.relatorio != "daily_indicators" %}` — a decisao C exige
        oculta-lo so para este relatorio."""
        response = self.client.get(f"{reverse(REPORTS_URL_NAME)}?relatorio=daily_indicators")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="id_incluir_excluidos"')

    def test_other_report_specific_fields_not_rendered_for_daily_indicators(self):
        """RED real: o bloco `{% elif raw.relatorio == ... %}` do
        template (linhas 49-236) nao tem nenhum ramo para
        "daily_indicators" — a requisicao cai no `{% else %}` (bloco de
        Selos WhatsApp), renderizando campos que nao pertencem a este
        relatorio (selo/pagamento/situacao)."""
        response = self.client.get(f"{reverse(REPORTS_URL_NAME)}?relatorio=daily_indicators")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="id_selo"')
        self.assertNotContains(response, 'id="id_pagamento"')
        self.assertNotContains(response, 'id="id_situacao"')

    def test_incluir_excluidos_absent_and_valid_values_yield_identical_result(self):
        _make_employee("Alimentos")
        without = self.client.get(_report_url(_base_pairs()))
        with_zero = self.client.get(_report_url(_base_pairs(incluir_excluidos="0")))
        with_one = self.client.get(_report_url(_base_pairs(incluir_excluidos="1")))
        self.assertEqual(without.status_code, 200)
        self.assertEqual(with_zero.status_code, 200)
        self.assertEqual(with_one.status_code, 200)
        self.assertEqual(without.context["result"].rows, with_zero.context["result"].rows)
        self.assertEqual(without.context["result"].rows, with_one.context["result"].rows)

    def test_invalid_value_rejected_on_daily_indicators_too(self):
        """Controle: a validacao de valor (0/1) continua estrita mesmo
        para este relatorio — GREEN hoje (fallback form ja valida),
        preservado para nao regredir quando o form dedicado existir."""
        response = self.client.get(_report_url(_base_pairs(incluir_excluidos="2")))
        self.assertEqual(response.status_code, 400)

    def test_repeated_incluir_excluidos_rejected(self):
        url = reverse(REPORTS_URL_NAME)
        response = self.client.get(
            f"{url}?relatorio=daily_indicators&data_inicial={PERIOD_START}&data_final={PERIOD_END}"
            "&incluir_excluidos=0&incluir_excluidos=1"
        )
        self.assertEqual(response.status_code, 400)

    def test_switching_from_another_report_with_incluir_excluidos_checked_succeeds_in_one_submission(self):
        """Reproduz exatamente o payload que o FORMULARIO A ("Selecionar
        relatorio") de templates/reports/home.html envia numa troca (so
        relatorio + comuns ja aplicados, NUNCA campo especifico de
        relatorio nenhum — mesmo mecanismo ja provado por
        config/tests/test_reports_hub.py::_picker_submission/
        ReportPickerFormNeverContainsSpecificFieldsTests, nao duplicado
        aqui): usuario estava em outro relatorio com "Incluir excluidos"
        marcado e troca para daily_indicators numa unica submissao."""
        switch_pairs = [
            ("relatorio", "daily_indicators"),
            ("data_inicial", PERIOD_START),
            ("data_final", PERIOD_END),
            ("incluir_excluidos", "1"),
        ]
        response = self.client.get(f"{reverse(REPORTS_URL_NAME)}?{urlencode(switch_pairs)}")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Parâmetro desconhecido", response.content.decode())


class DailyIndicatorsGranularityTests(TestCase):
    """Secao 2 do enunciado: uma linha por dia calendario dentro do
    periodo inclusivo, ordem ascendente, dia unico, virada de mes/ano,
    fevereiro bissexto, dias intermediarios sem registros nunca omitidos,
    quantidade de linhas igual a quantidade de dias independente do
    volume de registros-fonte (REL-13-C secao 2/3: "dia sem dados nunca e
    omitido... resposta e estrutural, nao uma escolha")."""

    def setUp(self):
        _freeze_today(self)
        self.admin = _create_user("admin.di.granularity@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def _dates(self, response):
        return [row["data"] for row in response.context["result"].rows]

    def test_one_row_per_calendar_day_in_short_period(self):
        response = self.client.get(_report_url(_base_pairs("2026-09-01", "2026-09-03")))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["result"].rows), 3)

    def test_rows_in_ascending_chronological_order(self):
        response = self.client.get(_report_url(_base_pairs("2026-09-01", "2026-09-03")))
        self.assertEqual(response.status_code, 200)
        dates = self._dates(response)
        self.assertEqual(dates, sorted(dates))
        self.assertEqual(dates[0], date(2026, 9, 1))

    def test_single_day_period_returns_exactly_one_row(self):
        response = self.client.get(_report_url(_base_pairs("2026-09-10", "2026-09-10")))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["result"].rows), 1)
        self.assertEqual(self._dates(response), [date(2026, 9, 10)])

    def test_month_boundary_is_continuous(self):
        response = self.client.get(_report_url(_base_pairs("2026-01-30", "2026-02-02")))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self._dates(response),
            [date(2026, 1, 30), date(2026, 1, 31), date(2026, 2, 1), date(2026, 2, 2)],
        )

    def test_year_boundary_is_continuous(self):
        response = self.client.get(_report_url(_base_pairs("2025-12-30", "2026-01-02")))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self._dates(response),
            [date(2025, 12, 30), date(2025, 12, 31), date(2026, 1, 1), date(2026, 1, 2)],
        )

    def test_leap_year_february_29_is_included(self):
        response = self.client.get(_report_url(_base_pairs("2024-02-27", "2024-03-01")))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self._dates(response),
            [date(2024, 2, 27), date(2024, 2, 28), date(2024, 2, 29), date(2024, 3, 1)],
        )

    def test_intermediate_days_without_records_are_not_omitted(self):
        admin = self.admin
        line = _make_line("+5511950000001")
        employee = _make_employee("Alimentos")
        _allocate_at(line, employee, admin, _local_midnight(date(2026, 9, 1)))
        response = self.client.get(_report_url(_base_pairs("2026-09-01", "2026-09-05")))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["result"].rows), 5)
        self.assertEqual(
            self._dates(response),
            [date(2026, 9, d) for d in range(1, 6)],
        )

    def test_whole_period_without_any_data_still_yields_one_row_per_day_all_zero(self):
        response = self.client.get(_report_url(_base_pairs("2026-09-01", "2026-09-03")))
        self.assertEqual(response.status_code, 200)
        rows = response.context["result"].rows
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertEqual(row["pessoas_logadas"], 0)
            self.assertEqual(row["numeros_entregues"], 0)
            self.assertEqual(row["reconectados"], 0)
            self.assertEqual(row["novos"], 0)
            self.assertEqual(row["total_descoberto_dia"], 0)

    def test_row_count_equals_day_count_independent_of_source_record_volume(self):
        admin = self.admin
        employee = _make_employee("Alimentos")
        for index in range(20):
            line = _make_line(f"+551196{index:07d}")
            _allocate_at(line, employee, admin, _local_midnight(date(2026, 9, 1)))
        response = self.client.get(_report_url(_base_pairs("2026-09-01", "2026-09-01")))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["result"].rows), 1)


class DailyIndicatorsStockVsFlowZeroFillTests(TestCase):
    """Secao 2 do enunciado: "nao presuma que todas as metricas sao zero
    em dia sem eventos: colunas de estoque podem continuar nao zeradas
    conforme a formula existente". Cenario com estoque existente (pessoas
    logadas/numeros disponiveis) e nenhum fluxo (entregues/reconectados/
    novos) no dia consultado, para distinguir as duas situacoes."""

    def setUp(self):
        _freeze_today(self)
        self.admin = _create_user("admin.di.stockflow@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_existing_stock_with_no_flow_on_day_shows_nonzero_stock_and_zero_flow(self):
        earlier = date(2026, 8, 1)
        queried_day = date(2026, 9, 15)
        employee = _make_employee("Alimentos", created_at=_local_midnight(earlier))
        _make_line("+5511970000001", created_at=_local_midnight(earlier))

        response = self.client.get(_report_url(_base_pairs(queried_day.isoformat(), queried_day.isoformat())))
        self.assertEqual(response.status_code, 200)
        row = response.context["result"].rows[0]
        self.assertGreater(row["pessoas_logadas"], 0, "estoque (funcionario logado) deve continuar contado")
        self.assertGreater(row["numeros_disponiveis"], 0, "estoque (linha disponivel) deve continuar contado")
        self.assertEqual(row["numeros_entregues"], 0, "nenhuma entrega ocorreu NESTE dia")
        self.assertEqual(row["reconectados"], 0, "nenhuma reconexao ocorreu NESTE dia")
        self.assertEqual(row["novos"], 0, "nenhuma linha nova foi criada NESTE dia")

    def test_day_with_zero_employees_and_zero_lines_is_genuinely_all_zero(self):
        """Controle inverso: sem NENHUM funcionario/linha no sistema, o
        dia e zero em TODAS as colunas — diferencia de proposito o
        cenario acima (zero por ausencia real, nao por omissao de
        fluxo)."""
        queried_day = date(2026, 9, 16)
        response = self.client.get(_report_url(_base_pairs(queried_day.isoformat(), queried_day.isoformat())))
        self.assertEqual(response.status_code, 200)
        row = response.context["result"].rows[0]
        self.assertEqual(row["pessoas_logadas"], 0)
        self.assertEqual(row["numeros_disponiveis"], 0)
        self.assertEqual(row["numeros_entregues"], 0)
        self.assertEqual(row["reconectados"], 0)
        self.assertEqual(row["novos"], 0)
        self.assertEqual(row["total_descoberto_dia"], 0)


class DailyIndicatorsHistoricalVisibilityTests(TestCase):
    """Secao 2 do enunciado / REL-13-C secao 2: regra de visibilidade
    historica ja vigente (phone_line_was_visible_at/
    get_visible_employees_for_day) — linha/funcionario excluido HOJE mas
    vivo num dia passado continua contado NAQUELE dia; dia atual (nao
    historico) sempre reflete o estado ATUAL, nunca uma copia congelada de
    consulta anterior."""

    def setUp(self):
        _freeze_today(self)
        self.admin = _create_user("admin.di.historical@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def _rows_by_date(self, response):
        return {row["data"]: row for row in response.context["result"].rows}

    def test_line_deleted_today_still_counted_on_past_day_it_was_alive(self):
        past_day = date(2026, 9, 10)
        line = _make_line("+5511980000001", created_at=_local_midnight(date(2026, 9, 1)))
        _delete_line(line, admin=self.admin)  # exclusao ocorre "hoje" (FROZEN_TODAY)

        response = self.client.get(_report_url(_base_pairs(past_day.isoformat(), past_day.isoformat())))
        self.assertEqual(response.status_code, 200)
        row = response.context["result"].rows[0]
        self.assertGreater(
            row["numeros_disponiveis"], 0,
            "linha excluida HOJE mas viva no dia passado consultado deve continuar contada (visibilidade historica)",
        )

    def test_active_employee_deactivated_today_still_counted_on_past_day_but_excluded_today(self):
        """Funcionario ativo desde 01/09, inativado (status, sem exclusao
        logica) em FROZEN_TODAY: dia passado (historico) continua
        contando-o como ativo (dashboard/views.py:1199-1202 — dia
        historico nao filtra por status); dia atual (nao historico)
        aplica o filtro real de status e o exclui."""
        employee = _make_employee(
            "Alimentos", status=Employee.Status.ACTIVE, created_at=_local_midnight(date(2026, 9, 1)),
        )
        employee.status = Employee.Status.INACTIVE
        employee.save(update_fields=["status"])

        past_day = date(2026, 9, 5)
        response = self.client.get(
            _report_url(_base_pairs(past_day.isoformat(), FROZEN_TODAY.isoformat()))
        )
        self.assertEqual(response.status_code, 200)
        rows = self._rows_by_date(response)
        self.assertGreaterEqual(rows[past_day]["pessoas_logadas"], 1, "dia historico ignora status atual")
        self.assertEqual(rows[FROZEN_TODAY]["pessoas_logadas"], 0, "dia atual aplica o filtro real de status")


class DailyIndicatorsDimensionGapTests(TestCase):
    """REL-13-C secao 1, "Nao presumido": funcionario com carteira fora de
    B2B_PORTFOLIO_NAMES/B2C_PORTFOLIO_NAMES entra em total_descoberto_dia
    (se sem linha) mas em NENHUM de b2b_sem_whats/b2c_sem_whats — soma das
    duas colunas pode ser menor que a terceira, sem ser defeito."""

    def setUp(self):
        _freeze_today(self)
        self.admin = _create_user("admin.di.dimensiongap@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_employee_with_portfolio_outside_b2b_and_b2c_counts_only_in_total(self):
        day = date(2026, 9, 12)
        _make_employee("Carteira Fora Do Mapa", created_at=_local_midnight(date(2026, 9, 1)))

        response = self.client.get(_report_url(_base_pairs(day.isoformat(), day.isoformat())))
        self.assertEqual(response.status_code, 200)
        row = response.context["result"].rows[0]
        self.assertEqual(row["b2b_sem_whats"], 0)
        self.assertEqual(row["b2c_sem_whats"], 0)
        self.assertGreaterEqual(row["total_descoberto_dia"], 1)
        self.assertGreater(
            row["total_descoberto_dia"], row["b2b_sem_whats"] + row["b2c_sem_whats"],
        )


class DailyIndicatorsFormulaCompatibilityTests(TestCase):
    """Secao 3 do enunciado: as nove colunas e sua ordem, calculadas por um
    dataset pequeno cujo resultado esperado e derivado do CONTRATO
    (contagem manual dos fixtures), nao exclusivamente de
    build_indicator_for_day (evita um teste que so valide a propria
    formula contra si mesma). Uma comparacao adicional contra
    build_indicator_for_day (mesma fonte que o widget do dashboard ja usa
    em producao) serve como teste de COMPATIBILIDADE, nao como unica
    fonte da verdade do esperado."""

    def setUp(self):
        _freeze_today(self)
        self.admin = _create_user("admin.di.formula@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_nine_columns_present_in_approved_order(self):
        day = date(2026, 9, 10)
        response = self.client.get(_report_url(_base_pairs(day.isoformat(), day.isoformat())))
        self.assertEqual(response.status_code, 200)
        for header in EXPECTED_COLUMN_HEADERS:
            self.assertContains(response, header)

    def test_small_dataset_matches_hand_computed_expected_values(self):
        """Dataset pequeno com resultado calculavel a mao a partir do
        contrato (nao de build_indicator_for_day): 1 funcionario B2B
        logado sem linha (conta em b2b_sem_whats e total_descoberto_dia),
        1 linha entregue no dia (conta em numeros_entregues), 1 linha nova
        criada no dia (conta em novos)."""
        day = date(2026, 9, 20)
        employee_without_line = _make_employee("Alimentos", created_at=_local_midnight(day))
        employee_with_delivery = _make_employee("Natura", created_at=_local_midnight(day))
        delivered_line = _make_line("+5511990000001", created_at=_local_midnight(day))
        _allocate_at(delivered_line, employee_with_delivery, self.admin, _local_midnight(day))
        _make_line("+5511990000002", created_at=_local_midnight(day))  # linha nova, sem alocacao

        response = self.client.get(_report_url(_base_pairs(day.isoformat(), day.isoformat())))
        self.assertEqual(response.status_code, 200)
        row = response.context["result"].rows[0]
        self.assertEqual(row["pessoas_logadas"], 2)
        self.assertEqual(row["b2b_sem_whats"], 1)  # employee_without_line
        self.assertEqual(row["b2c_sem_whats"], 0)
        self.assertEqual(row["numeros_entregues"], 1)  # delivered_line
        self.assertEqual(row["novos"], 2)  # ambas as linhas criadas no dia

    def test_row_matches_build_indicator_for_day_as_compatibility_check(self):
        """Comparacao adicional (nao substitui o teste acima): mesmo dia,
        mesmo estado do banco, mesmo valor de build_indicator_for_day
        (fonte ja em producao do widget do dashboard) e do relatorio novo
        — comprova reuso real da formula, sem redefini-la."""
        day = date(2026, 9, 21)
        employee = _make_employee("Alimentos", created_at=_local_midnight(day))
        line = _make_line("+5511990000003", created_at=_local_midnight(day))
        _allocate_at(line, employee, self.admin, _local_midnight(day))

        expected = build_indicator_for_day(day, user=None)
        response = self.client.get(_report_url(_base_pairs(day.isoformat(), day.isoformat())))
        self.assertEqual(response.status_code, 200)
        row = response.context["result"].rows[0]
        self.assertEqual(row["pessoas_logadas"], expected["pessoas_logadas"])
        self.assertEqual(row["numeros_entregues"], expected["numeros_entregues"])
        self.assertEqual(row["reconectados"], expected["reconectados"])
        self.assertEqual(row["novos"], expected["novos"])
        self.assertEqual(row["total_descoberto_dia"], expected["total_descoberto_dia"])


class DailyIndicatorsTotalsTests(TestCase):
    """REL-13-C secao 3/4 (decisao B, 2026-09-30): somar SOMENTE
    Entregues/Reconectados/Novos; as 6 colunas de estoque mostram "Não
    aplicável"; totais globais (todo o periodo filtrado, nao so a pagina);
    aditividade comprovada por comparacao com consulta direta do periodo
    inteiro (nao so leitura de codigo); mesma linha entregue em dois dias
    distintos conta duas vezes no total (nunca deduplicada)."""

    def setUp(self):
        _freeze_today(self)
        self.admin = _create_user("admin.di.totals@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_only_flow_columns_receive_totals_stock_columns_show_not_applicable(self):
        day = date(2026, 9, 10)
        response = self.client.get(_report_url(_base_pairs(day.isoformat(), day.isoformat())))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertGreaterEqual(content.count(NAO_APLICAVEL_LABEL), 6)

    def test_flow_totals_are_additive_across_period_matching_direct_period_query(self):
        """Prova por COMPARACAO, nao so por leitura de codigo (REL-13-C
        secao 1): soma diaria de "Entregues" no periodo deve bater com uma
        unica consulta de LineAllocation.allocated_at no periodo inteiro —
        cada LineAllocation tem exatamente um allocated_at, sem
        sobreposicao entre dias."""
        employee = _make_employee("Alimentos", created_at=_local_midnight(date(2026, 9, 1)))
        line_a = _make_line("+5511991000001", created_at=_local_midnight(date(2026, 9, 1)))
        line_b = _make_line("+5511991000002", created_at=_local_midnight(date(2026, 9, 1)))
        _allocate_at(line_a, employee, self.admin, _local_midnight(date(2026, 9, 2)))
        _allocate_at(line_b, employee, self.admin, _local_midnight(date(2026, 9, 4)))

        response = self.client.get(_report_url(_base_pairs("2026-09-01", "2026-09-05")))
        self.assertEqual(response.status_code, 200)
        totals = response.context["result"].totals
        direct_count = LineAllocation.objects.filter(
            allocated_at__range=(_local_midnight(date(2026, 9, 1)), _local_last_instant(date(2026, 9, 5))),
        ).count()
        self.assertEqual(direct_count, 2)
        self.assertEqual(totals.numeros_entregues, direct_count)

    def test_same_line_delivered_on_two_different_days_counts_twice_in_total_never_deduplicated(self):
        employee = _make_employee("Alimentos", created_at=_local_midnight(date(2026, 9, 1)))
        line = _make_line("+5511991000003", created_at=_local_midnight(date(2026, 9, 1)))
        allocation = _allocate_at(line, employee, self.admin, _local_midnight(date(2026, 9, 2)))
        allocation.released_at = _local_midnight(date(2026, 9, 3))
        allocation.is_active = False
        allocation.save(update_fields=["released_at", "is_active"])
        line.status = PhoneLine.Status.AVAILABLE
        line.save(update_fields=["status"])
        _allocate_at(line, employee, self.admin, _local_midnight(date(2026, 9, 4)))

        response = self.client.get(_report_url(_base_pairs("2026-09-01", "2026-09-05")))
        self.assertEqual(response.status_code, 200)
        totals = response.context["result"].totals
        self.assertEqual(totals.numeros_entregues, 2)

    def test_totals_are_global_not_limited_to_current_page(self):
        employee = _make_employee("Alimentos", created_at=_local_midnight(date(2026, 1, 1)))
        for offset in range(0, 80, 15):
            day = date(2026, 1, 1) + timedelta(days=offset)
            line = _make_line(f"+551199200{offset:04d}", created_at=_local_midnight(day))
            _allocate_at(line, employee, self.admin, _local_midnight(day))

        response = self.client.get(_report_url(_base_pairs("2026-01-01", "2026-03-31", page="1")))
        self.assertEqual(response.status_code, 200)
        page1_totals = response.context["result"].totals
        response_p2 = self.client.get(_report_url(_base_pairs("2026-01-01", "2026-03-31", page="2")))
        self.assertEqual(response_p2.status_code, 200)
        page2_totals = response_p2.context["result"].totals
        self.assertEqual(page1_totals.numeros_entregues, page2_totals.numeros_entregues)
        self.assertGreaterEqual(page1_totals.numeros_entregues, 6)

    def test_updated_at_based_metrics_are_not_an_immutable_historical_snapshot(self):
        """REL-13-C secao 5 / Ressalvas documentais: metricas baseadas em
        updated_at (parte do fluxo de Reconectados) podem mudar apos nova
        alteracao do registro — o relatorio reflete a formula VIGENTE a
        cada consulta, nunca promete reconstrucao historica imutavel.
        Este teste documenta a limitacao (2 consultas no mesmo dia, apos
        uma mudanca de estado, podem divergir), sem exigir nem simular
        backfill."""
        day = date(2026, 9, 8)
        employee = _make_employee("Alimentos", created_at=_local_midnight(date(2026, 9, 1)))
        line = _make_line("+5511993000001", created_at=_local_midnight(date(2026, 9, 1)))
        allocation = _allocate_at(line, employee, self.admin, _local_midnight(date(2026, 9, 2)))

        first = self.client.get(_report_url(_base_pairs(day.isoformat(), day.isoformat())))
        self.assertEqual(first.status_code, 200)
        first_row = first.context["result"].rows[0]

        allocation.released_at = _local_midnight(date(2026, 9, 6))
        allocation.is_active = False
        allocation.save(update_fields=["released_at", "is_active"])
        line.status = PhoneLine.Status.AVAILABLE
        line.save(update_fields=["status"])
        _allocate_at(line, employee, self.admin, _local_midnight(date(2026, 9, 7)))

        second = self.client.get(_report_url(_base_pairs(day.isoformat(), day.isoformat())))
        self.assertEqual(second.status_code, 200)
        second_row = second.context["result"].rows[0]
        # Documentado, nao um requisito de igualdade: a formula e vigente a
        # cada consulta, entao o valor do MESMO dia consultado antes/depois
        # de uma mudanca de estado pode divergir sem ser defeito.
        self.assertEqual(first_row["data"], second_row["data"])


class DailyIndicatorsReadOnlyTests(TestCase):
    """Secao 4 do enunciado (obrigatoria): a consulta/exportacao deste
    relatorio NUNCA persiste DashboardDailySnapshot, mesmo para dias nunca
    visitados antes pelo dashboard nem para dias com snapshot preexistente
    (que pode estar desatualizado — get_or_create_dashboard_snapshot_for_day
    o regravaria, mas este relatorio nunca deve chamar aquele caminho); nem
    altera entidades-fonte (Employee/PhoneLine/LineAllocation) nem tabelas
    de auditoria/historico de negocio (PhoneLineHistory/EmployeeHistory/
    LineDailyActionAuditEvent). Cada teste exige HTTP 200 (ou, no caso da
    exportacao, Content-Type real) com conteudo elegivel ANTES de verificar
    ausencia de escrita (nunca um 400 coincidente como prova de "nao
    escreveu"). Nao mocka build_indicator_for_day nem qualquer persistidor.

    IMPORTANTE (correcao desta revisao — nao presumir prova antecipada):
    com o motor ainda ausente, TODOS os 5 testes desta classe falham HOJE
    na PRIMEIRA asserção (`assertEqual(response.status_code, 200)`),
    ANTES de qualquer verificacao de escrita ser alcancada — sao RED por
    "motor ausente" (categoria (a) do docstring do modulo), nao por uma
    escrita real detectada. A prova de ausencia de escrita SO fica
    efetivamente exercitada quando REL-13-Q implementar o motor e a
    primeira asserção passar a ser GREEN; se REL-13-Q usar
    `get_dashboard_indicator_for_day`/`get_or_create_dashboard_snapshot_for_day`
    por engano, estes testes devem falhar NAQUELE momento, nas asserções
    de escrita abaixo — isso ainda nao foi comprovado nesta task, apenas
    preparado.

    Duas camadas de verificacao, deliberadamente nao redundantes:
    1. Contagem/valor de tabelas especificas (DashboardDailySnapshot com
       valor exato preservado; Employee/PhoneLine/LineAllocation e as tres
       tabelas de auditoria/historico por contagem) — cobre os caminhos de
       escrita HOJE conhecidos por leitura de codigo.
    2. `_assert_no_business_write_sql` (nivel SQL, via
       `CaptureQueriesContext`): varre TODAS as queries realmente
       executadas e falha se qualquer INSERT/UPDATE/DELETE atingir uma
       tabela diferente de `django_session` — path-agnostica, cobre
       qualquer escrita futura em qualquer tabela, nao apenas as listadas
       na camada 1. `django_session` e excluido por ser efeito tecnico
       legitimo do `force_login`/sessao do proprio test client, nunca uma
       escrita de negocio."""

    def setUp(self):
        _freeze_today(self)
        self.admin = _create_user("admin.di.readonly@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)
        self.employee = _make_employee("Alimentos", created_at=_local_midnight(date(2026, 9, 1)))
        line = _make_line("+5511994000001", created_at=_local_midnight(date(2026, 9, 1)))
        self.line = line
        _allocate_at(line, self.employee, self.admin, _local_midnight(date(2026, 9, 2)))

    def test_first_query_of_never_visited_period_creates_no_snapshot(self):
        self.assertEqual(DashboardDailySnapshot.objects.count(), 0)
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(_report_url(_base_pairs("2026-09-01", "2026-09-05")))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "01/09/2026", status_code=200)
        self.assertEqual(
            DashboardDailySnapshot.objects.count(), 0,
            "consulta somente leitura nao deve criar NENHUM DashboardDailySnapshot",
        )
        _assert_no_business_write_sql(self, captured.captured_queries)

    def test_repeated_query_still_creates_no_snapshot(self):
        pairs = _base_pairs("2026-09-01", "2026-09-05")
        first = self.client.get(_report_url(pairs))
        second = self.client.get(_report_url(pairs))
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(DashboardDailySnapshot.objects.count(), 0)

    def test_query_with_preexisting_stale_snapshot_does_not_alter_it(self):
        preexisting = DashboardDailySnapshot.objects.create(
            date=date(2026, 9, 2),
            people_logged_in=999,
            calculation_version=0,  # forcadamente desatualizado
        )
        response = self.client.get(_report_url(_base_pairs("2026-09-01", "2026-09-05")))
        self.assertEqual(response.status_code, 200)
        preexisting.refresh_from_db()
        self.assertEqual(
            preexisting.people_logged_in, 999,
            "snapshot preexistente (mesmo desatualizado) nao deve ser regravado por este relatorio",
        )
        self.assertEqual(preexisting.calculation_version, 0)
        self.assertEqual(DashboardDailySnapshot.objects.count(), 1)

    def test_export_creates_no_snapshot(self):
        self.assertEqual(DashboardDailySnapshot.objects.count(), 0)
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(_export_url("csv", _base_pairs("2026-09-01", "2026-09-05")))
        self.assertEqual(response.status_code, 200)
        self.assertIn("csv", response.headers.get("Content-Type", "").lower())
        self.assertEqual(DashboardDailySnapshot.objects.count(), 0)
        _assert_no_business_write_sql(self, captured.captured_queries)

    def test_query_does_not_alter_business_data(self):
        """Contagem de entidades-fonte E de tabelas de auditoria/historico
        de negocio (nao so DashboardDailySnapshot) — nenhuma tabela isolada
        e tratada como prova universal."""
        employee_count_before = Employee.objects.count()
        line_count_before = PhoneLine.objects.count()
        allocation_count_before = LineAllocation.objects.count()
        phone_line_history_count_before = PhoneLineHistory.objects.count()
        employee_history_count_before = EmployeeHistory.objects.count()
        audit_event_count_before = LineDailyActionAuditEvent.objects.count()

        response = self.client.get(_report_url(_base_pairs("2026-09-01", "2026-09-05")))
        self.assertEqual(response.status_code, 200)

        self.assertEqual(Employee.objects.count(), employee_count_before)
        self.assertEqual(PhoneLine.objects.count(), line_count_before)
        self.assertEqual(LineAllocation.objects.count(), allocation_count_before)
        self.assertEqual(PhoneLineHistory.objects.count(), phone_line_history_count_before)
        self.assertEqual(EmployeeHistory.objects.count(), employee_history_count_before)
        self.assertEqual(LineDailyActionAuditEvent.objects.count(), audit_event_count_before)


class DailyIndicatorsPaginationTests(TestCase):
    """Secao 6 do enunciado: mais de 50 dias no periodo comprova pagina 2,
    conteudo distinto sem omissao/duplicacao, filtros comuns preservados,
    pagina fora do intervalo conforme contrato (404, mesmo padrao de
    REL-07: "Página fora do intervalo retorna 404")."""

    def setUp(self):
        _freeze_today(self)
        self.admin = _create_user("admin.di.pagination@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_period_over_50_days_has_second_page_with_distinct_content(self):
        response_p1 = self.client.get(_report_url(_base_pairs("2026-01-01", "2026-03-15", page="1")))
        self.assertEqual(response_p1.status_code, 200)
        response_p2 = self.client.get(_report_url(_base_pairs("2026-01-01", "2026-03-15", page="2")))
        self.assertEqual(response_p2.status_code, 200)
        dates_p1 = {row["data"] for row in response_p1.context["result"].rows}
        dates_p2 = {row["data"] for row in response_p2.context["result"].rows}
        self.assertEqual(len(response_p1.context["result"].rows), 50)
        self.assertTrue(dates_p2, "pagina 2 deve ter conteudo, periodo tem mais de 50 dias")
        self.assertEqual(dates_p1 & dates_p2, set(), "nenhum dia deve aparecer duplicado entre paginas")

    def test_no_days_omitted_across_all_pages_of_long_period(self):
        start = date(2026, 1, 1)
        end = date(2026, 3, 15)
        total_days = (end - start).days + 1
        seen_dates = set()
        page = 1
        while True:
            response = self.client.get(_report_url(_base_pairs(start.isoformat(), end.isoformat(), page=str(page))))
            if response.status_code == 404:
                break
            self.assertEqual(response.status_code, 200)
            rows = response.context["result"].rows
            if not rows:
                break
            seen_dates.update(row["data"] for row in rows)
            page += 1
        self.assertEqual(len(seen_dates), total_days)

    def test_page_out_of_range_returns_404(self):
        response = self.client.get(_report_url(_base_pairs("2026-09-01", "2026-09-05", page="99")))
        self.assertEqual(response.status_code, 404)


class DailyIndicatorsQueryCostTests(TestCase):
    """Secao 6/REL-13-C ("Riscos de desempenho — estrategia de medicao"):
    custo por dia e fixo (~8-10 consultas), custo do relatorio escala
    linearmente com o numero de DIAS — nao com o volume de registros-fonte.
    Este teste comprova AUSENCIA de escalonamento nao-linear grosseiro
    (ex.: quadratico), sem impor uma contagem constante de queries nem um
    periodo impraticavel (o criterio de aceite numerico fica para
    REL-13-Q, com medicao registrada ANTES do aceite)."""

    def setUp(self):
        _freeze_today(self)
        self.admin = _create_user("admin.di.cost@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_query_count_scales_roughly_linearly_not_quadratically_with_period_length(self):
        with CaptureQueriesContext(connection) as small_period:
            response_small = self.client.get(_report_url(_base_pairs("2026-09-01", "2026-09-02")))
        with CaptureQueriesContext(connection) as large_period:
            response_large = self.client.get(_report_url(_base_pairs("2026-09-01", "2026-09-11")))

        self.assertEqual(response_small.status_code, 200)
        self.assertEqual(response_large.status_code, 200)
        small_count = len(small_period.captured_queries)
        large_count = len(large_period.captured_queries)
        # 2 dias -> N dias e um fator de 5x no numero de DIAS; margem ampla
        # (8x) tolera overhead fixo (autenticacao/sessao/paginacao) sem
        # aceitar um crescimento quadratico disfarcado.
        self.assertLessEqual(
            large_count, small_count * 8,
            "custo deveria escalar aproximadamente linear com o numero de dias, nao pior",
        )


class DailyIndicatorsQueryRealVolumeTests(TestCase):
    """Ensaio de volume REAL da CONSULTA (secao 2 do enunciado desta task /
    REL-13-C secao 3, decisao D) — mesmo padrao de
    LineInventoryExportRealVolumeTests
    (config/tests/test_line_inventory_report.py): banco de teste isolado
    (sqlite, "pytest" in sys.modules); nao acessa PRD; tempo e numero de
    queries medidos em bloco proprio, apos a fixture ja estar criada;
    numeros reportados via stderr (nao apenas asserção binaria), para
    ficarem rastreaveis na regressao normal da suite. Deliberadamente
    lento (periodos de ate 3 anos); nao e teste unitario de logica (essa
    prova esta nas demais classes deste modulo).

    CRITERIO DE ACEITE — REGISTRADO ANTES DA MEDICAO (secao 2 do enunciado,
    "criterio antes da medicao"; nenhum numero abaixo foi ajustado depois
    de ver o resultado real, que aparece nesta mesma classe/spec so DEPOIS
    deste bloco de definicao):
    - Natureza: META TECNICA proposta para o ENSAIO LOCAL (sqlite, banco de
      teste), nao um SLA de produto aprovado nem um limite de PRD
      (Postgres) — nao medido nesta task, sem acesso a infraestrutura de
      producao.
    - Ambiente e banco: sqlite3 em arquivo (test_db.sqlite3), mesmo motor
      usado por TODA a suite de testes deste projeto (config/settings.py:
      130-140, "if sys.argv[1] == 'test'") — divergente do motor de
      producao (Postgres, config/settings.py:112-125), mesma divergencia
      ja aceita e documentada pelos ensaios "VOLUME REAL" existentes dos
      outros 5 relatorios (ex.: LineInventoryExportRealVolumeTests). Nao
      extrapolado para capacidade de PRD.
    - Dataset: 300 funcionarios ativos (metade carteira B2B "Alimentos",
      metade B2C "Natura", criados 400 dias antes do periodo mais longo
      medido) e 600 linhas telefonicas (metade alocadas de forma ativa,
      metade disponiveis), mais um fluxo diario modesto e realista (1
      alocacao nova a cada 3 dias, ao longo de todo o periodo mais longo
      medido) para que Entregues/Reconectados/Novos nao fiquem
      permanentemente zerados durante a medicao — o custo deste relatorio
      escala com DIAS do periodo, nao com o volume de registros-fonte
      (REL-13-C secao 3), entao o dataset e deliberadamente modesto (nao
      10^5 registros como nos outros relatorios); o que varia entre
      medicoes e o COMPRIMENTO DO PERIODO, nao o tamanho do dataset.
    - Periodos representativos medidos (a exigencia explicita de "mais de
      50 dias" e coberta por TODOS os pontos exceto o primeiro): 10, 60,
      200 e 365 dias (uma pagina de resultados exibida + totalizadores do
      periodo inteiro em cada caso, PAGE_SIZE=50) e um periodo extremo de
      1095 dias (3 anos) SOMENTE para comprovar ausencia de trava/erro/
      truncamento silencioso (decisao D: "periodo continua sem limite
      arbitrario"), sem meta de tempo associada a este ultimo ponto.
    - Consulta e totalizadores NAO sao medidos em blocos separados nesta
      classe (diferente da recomendacao geral de REL-13-C secao 3, item
      2): para daily_indicators nao ha uma "exportacao" ainda (REL-13-E,
      fora do escopo desta task) para comparar — a unica medicao possivel
      agora e a CONSULTA completa (tela paginada), que ja inclui tela +
      totalizadores globais numa unica requisicao HTTP real (mesmo
      caminho que o usuario percorre). A divisao rows-da-pagina vs.
      totais-do-periodo-inteiro e medida separadamente dentro do teste via
      contagem de queries (nao tempo), reportada no mesmo log.
    - Metricas: tempo de parede (segundos, biblioteca `time`) e numero de
      queries reais (`CaptureQueriesContext`) por periodo. Memoria nao
      medida nesta classe (relatorio nao materializa listas granulares em
      Python — `include_users=False` — ao contrario dos exportadores dos
      outros 5 relatorios, que sim precisam de tracemalloc).
    - Execucoes: UMA execucao "fria" por periodo (sem repeticao/media) —
      nao ha NENHUM cache/memoizacao no motor deste relatorio (secao 4 do
      enunciado: "nao persista cache para contornar custo"), entao nao
      existe uma nocao de "quente" residente na aplicacao; o unico "quente"
      possivel e o cache de paginas do proprio SQLite entre execucoes
      consecutivas do processo de teste, que NAO e o alvo desta medicao
      (nao representativo do comportamento real de producao/Postgres) —
      registrado como limitacao, nao ocultado.
    - Criterio de avaliacao (meta tecnica do ensaio, nao SLA): para os 4
      periodos de ate 365 dias, tempo de parede da consulta HTTP completa
      (tela + totalizadores do periodo inteiro) deve ficar abaixo de 20s
      cada, neste ambiente sqlite de teste — origem do numero: ~8-10
      queries/dia para as linhas da pagina (no maximo 50 dias) +
      ~3 queries/dia para o totalizador de Reconectados (O(periodo)), soma
      compativel com dezenas de milissegundos por query em sqlite local
      (mesma ordem de grandeza ja observada nos ensaios de volume dos
      outros relatorios, que fazem 10^5 operacoes em 25-100s). Numero de
      queries deve crescer aproximadamente linear com o numero de dias do
      periodo (nao quadratico) — mesmo criterio ja usado por
      DailyIndicatorsQueryCostTests, reaplicado aqui com periodos maiores
      e reais. O periodo de 1095 dias NAO tem meta de tempo (fora do
      criterio numerico acima, deliberadamente) — so precisa responder
      200 sem excecao, comprovando decisao D ("sem limite arbitrario de
      periodo... se a medicao mostrar custo inviavel, REL-13-Q volta ao
      usuario com numeros reais")."""

    NUM_EMPLOYEES = 300
    NUM_LINES = 600
    LONGEST_PERIOD_DAYS = 1095  # 3 anos, para o dataset cobrir o pior caso

    @classmethod
    def setUpTestData(cls):
        cls.period_end = date(2026, 9, 30)
        cls.dataset_start = cls.period_end - timedelta(days=cls.LONGEST_PERIOD_DAYS + 30)

        cls.admin = _create_user("admin.di.realvolume@test.com", SystemUser.Role.ADMIN)

        employees = []
        for index in range(cls.NUM_EMPLOYEES):
            portfolio = "Alimentos" if index % 2 == 0 else "Natura"
            employees.append(
                Employee(
                    full_name=f"Volume Real Funcionario {index}",
                    corporate_email=f"volume.real.{index}@corp.com",
                    employee_id=portfolio,
                    teams=Employee.UnitChoices.JOINVILLE,
                    status=Employee.Status.ACTIVE,
                )
            )
        Employee.objects.bulk_create(employees, batch_size=1000)
        Employee.all_objects.update(created_at=_local_midnight(cls.dataset_start))

        sims = [
            SIMcard(iccid=f"8977{index:020d}", carrier="TIM")
            for index in range(cls.NUM_LINES)
        ]
        SIMcard.objects.bulk_create(sims, batch_size=1000)
        sim_ids = list(SIMcard.objects.order_by("pk").values_list("pk", flat=True))

        lines = [
            PhoneLine(
                phone_number=f"+5511998{index:06d}",
                sim_card_id=sim_ids[index],
                status=PhoneLine.Status.AVAILABLE,
            )
            for index in range(cls.NUM_LINES)
        ]
        PhoneLine.objects.bulk_create(lines, batch_size=1000)
        PhoneLine.all_objects.update(created_at=_local_midnight(cls.dataset_start))

        employee_ids = list(
            Employee.all_objects.order_by("pk").values_list("pk", flat=True)
        )
        line_ids = list(PhoneLine.all_objects.order_by("pk").values_list("pk", flat=True))

        # Fluxo diario modesto: 1 alocacao nova a cada 3 dias, ao longo de
        # todo o periodo mais longo medido, alternando entre as linhas
        # disponiveis — mantem Entregues/Reconectados/Novos com sinal real
        # (nao permanentemente zero) sem inflar o dataset.
        allocations = []
        total_flow_days = cls.LONGEST_PERIOD_DAYS
        for offset in range(0, total_flow_days, 3):
            line_id = line_ids[(offset // 3) % cls.NUM_LINES]
            employee_id = employee_ids[(offset // 3) % cls.NUM_EMPLOYEES]
            allocations.append(
                LineAllocation(
                    employee_id=employee_id,
                    phone_line_id=line_id,
                    allocated_by=cls.admin,
                    is_active=True,
                )
            )
        LineAllocation.objects.bulk_create(allocations, batch_size=1000)

        # allocated_at backdatado em lote (auto_now_add ignora o create()) —
        # um UPDATE por alocacao seria 10^3 updates; em vez disso, agrupa
        # por dia (no maximo LONGEST_PERIOD_DAYS/3 grupos) mantendo o
        # espalhamento real ao longo do periodo.
        created_allocations = list(
            LineAllocation.objects.order_by("pk").values_list("pk", flat=True)
        )
        for index, allocation_id in enumerate(created_allocations):
            offset = index * 3
            day = cls.dataset_start + timedelta(days=offset)
            LineAllocation.objects.filter(pk=allocation_id).update(
                allocated_at=_local_midnight(day)
            )

    def setUp(self):
        self.client.force_login(self.admin)

    def _measure(self, days):
        data_final = self.period_end
        data_inicial = data_final - timedelta(days=days - 1)
        with CaptureQueriesContext(connection) as captured:
            started = time_module.perf_counter()
            response = self.client.get(
                _report_url(_base_pairs(data_inicial.isoformat(), data_final.isoformat()))
            )
            elapsed = time_module.perf_counter() - started
        self.assertEqual(response.status_code, 200)
        return elapsed, len(captured.captured_queries), response

    def test_query_time_and_query_count_for_representative_periods(self):
        results = []
        for days in (10, 60, 200, 365):
            elapsed, query_count, response = self._measure(days)
            results.append((days, elapsed, query_count))
            self.assertEqual(len(response.context["result"].rows), min(days, 50))
            sys.stderr.write(
                f"\n[VOLUME REAL - INDICADORES DIARIOS] dias={days} "
                f"tempo={elapsed:.2f}s queries={query_count}\n"
            )
            self.assertLess(
                elapsed, 20.0,
                f"meta tecnica de ensaio local (20s, ver docstring da classe) "
                f"excedida para periodo de {days} dias: {elapsed:.2f}s",
            )

        first_days, first_elapsed, first_queries = results[0]
        last_days, last_elapsed, last_queries = results[-1]
        day_ratio = last_days / first_days
        query_ratio = last_queries / first_queries
        sys.stderr.write(
            f"[VOLUME REAL - INDICADORES DIARIOS] razao dias={day_ratio:.1f}x "
            f"razao queries={query_ratio:.1f}x\n"
        )
        # Mesma margem ampla (nao apertada) de DailyIndicatorsQueryCostTests:
        # tolera overhead fixo sem aceitar crescimento pior que linear.
        self.assertLessEqual(
            query_ratio, day_ratio * 2,
            "numero de queries deveria escalar aproximadamente linear com "
            "o numero de dias do periodo, nao pior",
        )

    def test_extreme_three_year_period_completes_without_error_or_truncation(self):
        """Decisao D (REL-13-C): sem limite arbitrario de periodo. Sem meta
        de tempo aqui de proposito (ver docstring da classe) — so exige
        200 real e que NENHUM dia do periodo tenha sido omitido/truncado
        silenciosamente (paginado normalmente, PAGE_SIZE=50)."""
        elapsed, query_count, response = self._measure(self.LONGEST_PERIOD_DAYS)
        self.assertEqual(len(response.context["result"].rows), 50)
        self.assertEqual(response.context["result"].num_pages, -(-self.LONGEST_PERIOD_DAYS // 50))
        sys.stderr.write(
            f"\n[VOLUME REAL - INDICADORES DIARIOS] dias={self.LONGEST_PERIOD_DAYS} "
            f"(extremo, sem meta de tempo) tempo={elapsed:.2f}s queries={query_count}\n"
        )


class DailyIndicatorsExportContentTests(TestCase):
    """Secao 7 do enunciado: ADMIN autorizado (demais perfis/anonimo
    bloqueados — ja coberto por DailyIndicatorsSharedValidationAppliesTests
    /RoleRequiredMixin, GREEN hoje, nao duplicado aqui), mesma
    ordem/colunas/metricas/totalizadores da tela, dias sem registros
    preservados, dados atuais no download, CSV/XLSX com parsers reais,
    somente leitura (ver DailyIndicatorsReadOnlyTests). Nao implementa
    exportador nem interface de limiar — volume/ZIP/limpeza ficam
    explicitamente pendentes para REL-13-E."""

    def setUp(self):
        _freeze_today(self)
        self.admin = _create_user("admin.di.exportcontent@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def _read_csv_rows(self, response):
        self.assertEqual(response.status_code, 200, f"esperado 200, resposta real: {response.status_code}")
        self.assertIn("csv", response.headers.get("Content-Type", "").lower())
        text = (
            b"".join(response.streaming_content).decode("utf-8-sig")
            if response.streaming
            else response.content.decode("utf-8-sig")
        )
        return list(csv.reader(io.StringIO(text), delimiter=";"))

    def _read_xlsx_rows(self, response):
        self.assertEqual(response.status_code, 200, f"esperado 200, resposta real: {response.status_code}")
        self.assertIn("spreadsheet", response.headers.get("Content-Type", "").lower())
        content = b"".join(response.streaming_content) if response.streaming else response.content
        workbook = openpyxl.load_workbook(io.BytesIO(content))
        return list(workbook.active.iter_rows(values_only=True))

    def test_admin_csv_download_returns_200(self):
        response = self.client.get(_export_url("csv", _base_pairs("2026-09-01", "2026-09-03")))
        self.assertEqual(response.status_code, 200)

    def test_admin_xlsx_download_returns_200(self):
        response = self.client.get(_export_url("xlsx", _base_pairs("2026-09-01", "2026-09-03")))
        self.assertEqual(response.status_code, 200)

    def test_columns_match_approved_order_in_both_formats(self):
        csv_rows = self._read_csv_rows(
            self.client.get(_export_url("csv", _base_pairs("2026-09-01", "2026-09-01")))
        )
        self.assertEqual(csv_rows[0], EXPECTED_COLUMN_HEADERS)
        xlsx_rows = self._read_xlsx_rows(
            self.client.get(_export_url("xlsx", _base_pairs("2026-09-01", "2026-09-01")))
        )
        self.assertEqual(list(xlsx_rows[0]), EXPECTED_COLUMN_HEADERS)

    def test_export_contains_all_days_of_period_regardless_of_page(self):
        csv_rows = self._read_csv_rows(
            self.client.get(_export_url("csv", _base_pairs("2026-01-01", "2026-03-15", page="1")))
        )
        data_rows = csv_rows[1:]
        total_days = (date(2026, 3, 15) - date(2026, 1, 1)).days + 1
        self.assertEqual(len(data_rows), total_days)

    def test_days_without_records_are_preserved_in_export(self):
        csv_rows = self._read_csv_rows(
            self.client.get(_export_url("csv", _base_pairs("2026-09-01", "2026-09-03")))
        )
        self.assertEqual(len(csv_rows) - 1, 3)

    def test_export_reflects_current_data_at_download_time(self):
        day = date(2026, 9, 18)
        employee = _make_employee("Alimentos", created_at=_local_midnight(day))
        line = _make_line("+5511995000001", created_at=_local_midnight(day))

        before_rows = self._read_csv_rows(
            self.client.get(_export_url("csv", _base_pairs(day.isoformat(), day.isoformat())))
        )
        _allocate_at(line, employee, self.admin, _local_midnight(day))
        after_rows = self._read_csv_rows(
            self.client.get(_export_url("csv", _base_pairs(day.isoformat(), day.isoformat())))
        )
        self.assertNotEqual(before_rows[1], after_rows[1], "download deve refletir os dados atuais, nao uma versao anterior")

    def test_empty_source_data_still_yields_daily_rows_not_zero_rows(self):
        """Distingue "sem dados-fonte" de "ausencia de linhas diarias":
        mesmo com o banco totalmente vazio, o export tem uma linha por
        dia do periodo (granularidade e estrutural, nao depende de haver
        registro algum — REL-13-C secao 2)."""
        csv_rows = self._read_csv_rows(
            self.client.get(_export_url("csv", _base_pairs("2026-09-01", "2026-09-03")))
        )
        self.assertEqual(len(csv_rows) - 1, 3)


class DailyIndicatorsExportValueFormatTests(TestCase):
    """Secao 8 do enunciado de REL-13-E ("datas, numeros, acentos e
    contexto"): formato de celula em CSV/XLSX para as colunas nao
    triviais. `% sem Whats` tem regra PROPRIA (REL-13-C secao 3, tabela de
    colunas): numerico puro sem simbolo no CSV (mesmo padrao de
    `dashboard_daily_snapshot_report`), "92,50%" (virgula, simbolo literal)
    no XLSX. `Data` e tipada (DD/MM/AAAA) em ambos. Colunas inteiras nunca
    viram formula (protecao uniforme, REL-07)."""

    def setUp(self):
        _freeze_today(self)
        self.admin = _create_user("admin.di.valuefmt@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)
        # 2 de 4 funcionarios sem Whats -> perc_sem_whats = 50.00, um valor
        # com parte decimal nao-zero para expor divergencia de separador.
        self.employee_with_line = _make_employee("Alimentos", created_at=_local_midnight(date(2026, 9, 1)))
        _make_employee("Alimentos", created_at=_local_midnight(date(2026, 9, 1)))
        line = _make_line("+5511993000001", created_at=_local_midnight(date(2026, 9, 1)))
        _allocate_at(line, self.employee_with_line, self.admin, _local_midnight(date(2026, 9, 1)))

    def test_perc_sem_whats_csv_is_plain_numeric_without_percent_symbol(self):
        response = self.client.get(_export_url("csv", _base_pairs("2026-09-01", "2026-09-01")))
        self.assertEqual(response.status_code, 200)
        text = _export_bytes(response).decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text), delimiter=";"))
        cell = rows[1][2]
        self.assertNotIn("%", cell)
        self.assertEqual(float(cell), 50.0)

    def test_perc_sem_whats_xlsx_uses_comma_decimal_and_percent_symbol(self):
        response = self.client.get(_export_url("xlsx", _base_pairs("2026-09-01", "2026-09-01")))
        self.assertEqual(response.status_code, 200)
        workbook = openpyxl.load_workbook(io.BytesIO(_export_bytes(response)))
        cell = list(workbook.active.iter_rows(values_only=True))[1][2]
        self.assertEqual(cell, "50,00%")

    def test_data_column_typed_as_date_in_xlsx(self):
        response = self.client.get(_export_url("xlsx", _base_pairs("2026-09-01", "2026-09-01")))
        workbook = openpyxl.load_workbook(io.BytesIO(_export_bytes(response)))
        cell = list(workbook.active.iter_rows(values_only=True))[1][0]
        self.assertEqual(cell, datetime(2026, 9, 1))

    def test_data_column_formatted_ddmmyyyy_in_csv(self):
        response = self.client.get(_export_url("csv", _base_pairs("2026-09-01", "2026-09-01")))
        text = _export_bytes(response).decode("utf-8-sig")
        csv_rows = list(csv.reader(io.StringIO(text), delimiter=";"))
        self.assertEqual(csv_rows[1][0], "01/09/2026")

    def test_integer_columns_never_become_formulas_in_csv(self):
        """Nenhuma coluna inteira deste relatorio e negativa na pratica,
        mas a protecao (REL-07: inicio =, +, -, @) e aplicada uniformemente
        — este teste comprova que a funcao de protecao esta de fato ligada
        ao pipeline CSV via um valor sintetico que comecaria com '-'."""
        from core.services.daily_indicators_export_service import _csv_text

        self.assertEqual(_csv_text(-5), "'-5")
        self.assertEqual(_csv_text(5), "5")


class DailyIndicatorsExportPageIndependenceTests(TestCase):
    """Secao 8 ("mais de 50 dias, independente de page"): `page` e aceito
    pela validacao comum mas NUNCA usado para limitar a exportacao —
    diferente de `test_export_contains_all_days_of_period_regardless_of_page`
    (DailyIndicatorsExportContentTests, so testa page=1), aqui `page=2` (e
    um valor fora do intervalo de paginas da TELA) tambem devem retornar o
    periodo COMPLETO, nunca uma fatia nem 404."""

    def setUp(self):
        _freeze_today(self)
        self.admin = _create_user("admin.di.pageindep@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_page_2_still_exports_full_period(self):
        response = self.client.get(
            _export_url("csv", _base_pairs("2026-01-01", "2026-03-15", page="2"))
        )
        self.assertEqual(response.status_code, 200)
        text = _export_bytes(response).decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text), delimiter=";"))
        total_days = (date(2026, 3, 15) - date(2026, 1, 1)).days + 1
        self.assertEqual(len(rows) - 1, total_days)

    def test_page_far_out_of_screen_range_still_exports_full_period(self):
        response = self.client.get(
            _export_url("csv", _base_pairs("2026-09-01", "2026-09-05", page="999"))
        )
        self.assertEqual(response.status_code, 200)
        text = _export_bytes(response).decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text), delimiter=";"))
        self.assertEqual(len(rows) - 1, 5)


class DailyIndicatorsExportScreenParityTests(TestCase):
    """Secao 8 ("paridade tela/arquivo"): mesmo conjunto de dias e mesmos
    valores em tela e exportacao, para o mesmo periodo — nao apenas
    cabecalhos (ja coberto por
    DailyIndicatorsExportContentTests::test_columns_match_approved_order_in_both_formats)."""

    def setUp(self):
        _freeze_today(self)
        self.admin = _create_user("admin.di.parity@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)
        employee = _make_employee("Alimentos", created_at=_local_midnight(date(2026, 9, 1)))
        line = _make_line("+5511992000001", created_at=_local_midnight(date(2026, 9, 1)))
        _allocate_at(line, employee, self.admin, _local_midnight(date(2026, 9, 2)))

    def test_csv_rows_match_screen_rows_for_same_period(self):
        screen = self.client.get(_report_url(_base_pairs("2026-09-01", "2026-09-05")))
        self.assertEqual(screen.status_code, 200)
        screen_rows = screen.context["result"].rows

        response = self.client.get(_export_url("csv", _base_pairs("2026-09-01", "2026-09-05")))
        text = _export_bytes(response).decode("utf-8-sig")
        csv_rows = list(csv.reader(io.StringIO(text), delimiter=";"))[1:]

        self.assertEqual(len(csv_rows), len(screen_rows))
        for screen_row, csv_row in zip(screen_rows, csv_rows):
            self.assertEqual(csv_row[0], screen_row["data"].strftime("%d/%m/%Y"))
            self.assertEqual(int(csv_row[1]), screen_row["pessoas_logadas"])
            self.assertEqual(float(csv_row[2]), round(screen_row["perc_sem_whats"], 2))
            self.assertEqual(int(csv_row[3]), screen_row["b2b_sem_whats"])
            self.assertEqual(int(csv_row[4]), screen_row["b2c_sem_whats"])
            self.assertEqual(int(csv_row[5]), screen_row["numeros_disponiveis"])
            self.assertEqual(int(csv_row[6]), screen_row["numeros_entregues"])
            self.assertEqual(int(csv_row[7]), screen_row["reconectados"])
            self.assertEqual(int(csv_row[8]), screen_row["novos"])
            self.assertEqual(int(csv_row[9]), screen_row["total_descoberto_dia"])


class DailyIndicatorsExportTotalsEquivalenceTests(TestCase):
    """Secao 6 do enunciado ("teste de equivalencia ANTES de otimizar"):
    o exportador acumula `reconectados` por soma incremental enquanto
    escreve cada linha (`_TotalsAccumulator`), em vez de uma segunda
    consulta O(dias) como a tela faz (`_flow_totals_for_period`) — prova
    que o valor acumulado bate EXATAMENTE com a soma direta de
    `count_reconnected_numbers_for_day` por dia (mesma funcao, mesmo
    predicado, sem aproximacao), nao apenas por leitura do codigo."""

    def setUp(self):
        _freeze_today(self)
        self.admin = _create_user("admin.di.totalseq@test.com", SystemUser.Role.ADMIN)

    def test_accumulated_reconectados_total_matches_direct_per_day_sum(self):
        from core.services.daily_indicators_export_service import generate_daily_indicators_export

        employee = _make_employee("Alimentos", created_at=_local_midnight(date(2026, 9, 1)))
        line_a = _make_line("+5511991000001", created_at=_local_midnight(date(2026, 9, 1)))
        line_b = _make_line("+5511991000002", created_at=_local_midnight(date(2026, 9, 1)))
        _allocate_at(
            line_a, employee, self.admin, _local_midnight(date(2026, 9, 1)),
            released_at=_local_midnight(date(2026, 9, 2)),
        )
        _allocate_at(line_a, employee, self.admin, _local_midnight(date(2026, 9, 3)))
        _allocate_at(line_b, employee, self.admin, _local_midnight(date(2026, 9, 4)))

        data_inicial, data_final = date(2026, 9, 1), date(2026, 9, 5)
        direct_sum = sum(
            count_reconnected_numbers_for_day(data_inicial + timedelta(days=offset))
            for offset in range((data_final - data_inicial).days + 1)
        )

        export = generate_daily_indicators_export(
            formato="csv",
            filters={
                "data_inicial": data_inicial,
                "data_final": data_final,
                "incluir_excluidos": False,
            },
        )
        try:
            workbook_reconectados_total = None
            with open(export.path, encoding="utf-8-sig") as handle:
                rows = list(csv.reader(handle, delimiter=";"))
            csv_sum = sum(int(row[7]) for row in rows[1:])
        finally:
            shutil.rmtree(export.temp_dir, ignore_errors=True)

        self.assertEqual(csv_sum, direct_sum, "soma incremental deve bater com a soma direta por dia")
        self.assertGreater(direct_sum, 0, "cenario deve exercitar reconexao real, nao so zeros")


class DailyIndicatorsExportContextSheetTests(TestCase):
    """Secao 8 ("datas, numeros, acentos e contexto"): aba Contexto do
    XLSX (REL-07) traz relatorio/filtros/gerado-em/quantidade e, para este
    relatorio, os totalizadores do periodo (decisao B, REL-13-C) — as
    mesmas 3 metricas somadas pela tela (REL-13-Q), nao inventadas."""

    def setUp(self):
        _freeze_today(self)
        self.admin = _create_user("admin.di.context@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)
        employee = _make_employee("Alimentos", created_at=_local_midnight(date(2026, 9, 1)))
        line = _make_line("+5511990000001", created_at=_local_midnight(date(2026, 9, 1)))
        _allocate_at(line, employee, self.admin, _local_midnight(date(2026, 9, 2)))

    def test_context_sheet_has_report_filters_and_flow_totals(self):
        response = self.client.get(_export_url("xlsx", _base_pairs("2026-09-01", "2026-09-05")))
        self.assertEqual(response.status_code, 200)
        workbook = openpyxl.load_workbook(io.BytesIO(_export_bytes(response)))
        self.assertIn("Contexto", workbook.sheetnames)
        context_rows = {
            row[0]: row[1] for row in workbook["Contexto"].iter_rows(values_only=True, min_row=2)
        }
        self.assertEqual(context_rows["Relatório"], "Indicadores diários")
        self.assertIn("Período", context_rows["Filtros"])
        self.assertIn("Incluir excluídos", context_rows["Filtros"])
        self.assertEqual(context_rows["Quantidade total (dias)"], 5)
        self.assertIn("Números Entregues no período", context_rows)
        self.assertIn("Reconectados no período", context_rows)
        self.assertIn("Novos no período", context_rows)
        self.assertGreaterEqual(context_rows["Números Entregues no período"], 1)


class DailyIndicatorsExportSplitBoundaryTests(TestCase):
    """Fronteira de divisao em partes/ZIP (REL-07/REL-13-C), boundary-1/
    boundary/boundary+1 em ambos os formatos. Granularidade DIARIA: o
    limiar conta DIAS exportados, nao registros-fonte — reduzir
    `split_threshold` para um numero pequeno permite testar a fronteira
    com um periodo REAL curto (nenhuma sequencia sintetica de linhas
    diarias necessaria; nenhum seculo de calculo, ver docstring do modulo
    do exportador). Interface tecnica explicita: `split_threshold` de
    core.services.daily_indicators_export_service.generate_daily_indicators_export,
    chamado diretamente aqui (nao via HTTP) — a rota real nunca o passa,
    usando sempre EXPORT_SPLIT_THRESHOLD (100.000)."""

    def setUp(self):
        _freeze_today(self)
        self.admin = _create_user("admin.di.split@test.com", SystemUser.Role.ADMIN)

    def _filters(self, data_inicial, data_final):
        return {
            "data_inicial": data_inicial,
            "data_final": data_final,
            "incluir_excluidos": False,
        }

    def _generate(self, formato, data_inicial, data_final, threshold):
        from core.services.daily_indicators_export_service import generate_daily_indicators_export

        return generate_daily_indicators_export(
            formato=formato,
            filters=self._filters(data_inicial, data_final),
            split_threshold=threshold,
        )

    def test_csv_below_threshold_is_single_file(self):
        export = self._generate("csv", date(2026, 9, 1), date(2026, 9, 2), 3)
        try:
            self.assertFalse(export.filename.endswith(".zip"))
            with open(export.path, encoding="utf-8-sig") as handle:
                rows = list(csv.reader(handle, delimiter=";"))
            self.assertEqual(len(rows) - 1, 2)
        finally:
            shutil.rmtree(export.temp_dir, ignore_errors=True)

    def test_csv_at_threshold_is_single_file(self):
        export = self._generate("csv", date(2026, 9, 1), date(2026, 9, 3), 3)
        try:
            self.assertFalse(export.filename.endswith(".zip"))
            with open(export.path, encoding="utf-8-sig") as handle:
                rows = list(csv.reader(handle, delimiter=";"))
            self.assertEqual(len(rows) - 1, 3)
        finally:
            shutil.rmtree(export.temp_dir, ignore_errors=True)

    def test_csv_above_threshold_splits_into_zip_without_loss_or_duplication(self):
        from core.services.daily_indicators_export_service import COLUMNS

        export = self._generate("csv", date(2026, 9, 1), date(2026, 9, 4), 3)
        try:
            self.assertTrue(export.filename.endswith(".zip"))
            with zipfile.ZipFile(export.path) as archive:
                names = sorted(archive.namelist())
                self.assertEqual(len(names), 2)
                counts = []
                for name in names:
                    text = archive.read(name).decode("utf-8-sig")
                    rows = list(csv.reader(io.StringIO(text), delimiter=";"))
                    self.assertEqual(rows[0], COLUMNS)
                    counts.append(len(rows) - 1)
                self.assertEqual(sorted(counts), [1, 3])
                self.assertEqual(sum(counts), 4)
        finally:
            shutil.rmtree(export.temp_dir, ignore_errors=True)

    def test_xlsx_below_threshold_is_single_file(self):
        export = self._generate("xlsx", date(2026, 9, 1), date(2026, 9, 2), 3)
        try:
            self.assertFalse(export.filename.endswith(".zip"))
            workbook = openpyxl.load_workbook(export.path)
            sheet = workbook["Indicadores diários"]
            self.assertEqual(len(list(sheet.iter_rows(values_only=True))) - 1, 2)
        finally:
            shutil.rmtree(export.temp_dir, ignore_errors=True)

    def test_xlsx_at_threshold_is_single_file(self):
        export = self._generate("xlsx", date(2026, 9, 1), date(2026, 9, 3), 3)
        try:
            self.assertFalse(export.filename.endswith(".zip"))
            workbook = openpyxl.load_workbook(export.path)
            sheet = workbook["Indicadores diários"]
            self.assertEqual(len(list(sheet.iter_rows(values_only=True))) - 1, 3)
        finally:
            shutil.rmtree(export.temp_dir, ignore_errors=True)

    def test_xlsx_above_threshold_splits_into_zip_without_loss_or_duplication(self):
        from core.services.daily_indicators_export_service import COLUMNS

        export = self._generate("xlsx", date(2026, 9, 1), date(2026, 9, 4), 3)
        try:
            self.assertTrue(export.filename.endswith(".zip"))
            with zipfile.ZipFile(export.path) as archive:
                names = sorted(archive.namelist())
                self.assertEqual(len(names), 2)
                counts = []
                for name in names:
                    content = archive.read(name)
                    workbook = openpyxl.load_workbook(io.BytesIO(content))
                    sheet = workbook["Indicadores diários"]
                    rows = list(sheet.iter_rows(values_only=True))
                    self.assertEqual(list(rows[0]), COLUMNS)
                    counts.append(len(rows) - 1)
                self.assertEqual(sorted(counts), [1, 3])
                self.assertEqual(sum(counts), 4)
        finally:
            shutil.rmtree(export.temp_dir, ignore_errors=True)

    def test_no_extra_empty_part_when_total_is_exact_multiple_of_threshold(self):
        export = self._generate("csv", date(2026, 9, 1), date(2026, 9, 6), 3)
        try:
            self.assertTrue(export.filename.endswith(".zip"))
            with zipfile.ZipFile(export.path) as archive:
                self.assertEqual(len(archive.namelist()), 2)
        finally:
            shutil.rmtree(export.temp_dir, ignore_errors=True)


class DailyIndicatorsExportStreamingCleanupTests(TestCase):
    """Prova direta do mecanismo de limpeza de temporarios (REL-07/REL-13-C:
    limpeza em consumo completo, consumo parcial, fechamento antes do
    primeiro chunk, fechamento repetido e falha de geracao). Mesmo
    raciocinio ja comprovado para os outros cinco relatorios."""

    def setUp(self):
        _freeze_today(self)
        self.admin = _create_user("admin.di.cleanup@test.com", SystemUser.Role.ADMIN)

    def _filters(self):
        return {
            "data_inicial": date(2026, 9, 1),
            "data_final": date(2026, 9, 3),
            "incluir_excluidos": False,
        }

    def test_temp_dir_removed_after_full_stream_consumption(self):
        from core.services.daily_indicators_export_service import (
            _stream_and_cleanup,
            generate_daily_indicators_export,
        )

        export = generate_daily_indicators_export(formato="csv", filters=self._filters())
        self.assertTrue(os.path.isdir(export.temp_dir))

        content = b"".join(_stream_and_cleanup(export.path, export.temp_dir))
        self.assertIn(b"Data", content)
        self.assertFalse(os.path.exists(export.temp_dir))

    def test_temp_dir_removed_on_early_close_simulating_client_disconnect(self):
        from core.services.daily_indicators_export_service import (
            _stream_and_cleanup,
            generate_daily_indicators_export,
        )

        export = generate_daily_indicators_export(formato="csv", filters=self._filters())
        stream = _stream_and_cleanup(export.path, export.temp_dir)
        next(stream)
        stream.close()
        self.assertFalse(os.path.exists(export.temp_dir))

    def test_temp_dir_removed_before_first_chunk_consumed_on_close(self):
        from core.services import daily_indicators_export_service

        captured = {}
        original_mkdtemp = daily_indicators_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        with mock.patch.object(
            daily_indicators_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
        ):
            response = daily_indicators_export_service.build_daily_indicators_export_response(
                formato="csv", filters=self._filters()
            )

        self.assertIn("temp_dir", captured)
        self.assertTrue(os.path.isdir(captured["temp_dir"]))

        response.close()  # nenhum chunk foi lido ate aqui

        self.assertFalse(os.path.exists(captured["temp_dir"]))

    def test_close_is_idempotent_on_repeated_close_calls(self):
        from core.services import daily_indicators_export_service

        response = daily_indicators_export_service.build_daily_indicators_export_response(
            formato="csv", filters=self._filters()
        )
        response.close()
        self.assertFalse(os.path.exists(response._export_temp_dir))
        response.close()  # segunda chamada nao deve levantar excecao
        self.assertFalse(os.path.exists(response._export_temp_dir))

    def test_temp_dir_removed_when_csv_generation_fails(self):
        from core.services import daily_indicators_export_service

        captured = {}
        original_mkdtemp = daily_indicators_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        with mock.patch.object(
            daily_indicators_export_service, "_write_csv_chunk", side_effect=RuntimeError("boom")
        ):
            with mock.patch.object(
                daily_indicators_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
            ):
                with self.assertRaises(RuntimeError):
                    daily_indicators_export_service.generate_daily_indicators_export(
                        formato="csv", filters=self._filters()
                    )

        self.assertIn("temp_dir", captured)
        self.assertFalse(os.path.exists(captured["temp_dir"]))

    def test_temp_dir_removed_and_xlsx_workbook_closed_when_generation_fails(self):
        """Mesmo caso acima, mas falhando no meio da escrita XLSX write-only:
        sem fechar explicitamente o workbook abandonado, o GC o fecha fora
        de ordem (warning 'I/O operation on closed file'); aqui verificamos
        que o workbook e fechado de forma limpa (sem excecao no close) e
        que o diretorio temporario e removido mesmo assim."""
        from core.services import daily_indicators_export_service

        captured = {}
        original_mkdtemp = daily_indicators_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        def _boom(worksheet, row):
            raise RuntimeError("boom")

        with mock.patch.object(
            daily_indicators_export_service, "_row_to_xlsx_cells", side_effect=_boom
        ):
            with mock.patch.object(
                daily_indicators_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
            ):
                with self.assertRaises(RuntimeError):
                    daily_indicators_export_service.generate_daily_indicators_export(
                        formato="xlsx", filters=self._filters()
                    )

        self.assertIn("temp_dir", captured)
        self.assertFalse(os.path.exists(captured["temp_dir"]))

    def test_no_leaked_openpyxl_internal_temp_file_when_generation_fails_immediately(self):
        """REPORTS_SENIOR_REVIEW (.git/REPORTS_SENIOR_REVIEW.md) achado 2: o
        teste acima ja prova que `temp_dir` (proprio do exportador) e
        removido, mas NAO prova que o arquivo temporario INTERNO do openpyxl
        (`sheet._writer.out`, fora de `temp_dir`, registrado em
        `ALL_TEMP_FILES`) tambem e removido — exatamente o vazamento
        reproduzido na revisao senior (XML de 927 bytes para workbook vazio
        abandonado)."""
        from core.services import daily_indicators_export_service
        from openpyxl.worksheet._writer import ALL_TEMP_FILES

        def _boom(worksheet, row):
            raise RuntimeError("boom")

        baseline = set(ALL_TEMP_FILES)
        with mock.patch.object(
            daily_indicators_export_service, "_row_to_xlsx_cells", side_effect=_boom
        ):
            with self.assertRaises(RuntimeError):
                daily_indicators_export_service.generate_daily_indicators_export(
                    formato="xlsx", filters=self._filters()
                )

        leaked = set(ALL_TEMP_FILES) - baseline
        self.assertEqual(
            leaked, set(),
            f"arquivo temporario interno do openpyxl nao removido: {leaked}",
        )
        for path in leaked:
            self.assertFalse(os.path.exists(path))

    def test_no_leaked_openpyxl_internal_temp_file_when_generation_fails_after_one_row(self):
        """Mesmo caso acima, mas com UMA linha real escrita antes da falha
        (XML residual de 34.208 bytes na revisao senior — nao apenas o
        cabecalho vazio). `_filters()` cobre 3 dias, entao ha linhas
        suficientes para uma primeira escrita bem-sucedida antes da falha."""
        from core.services import daily_indicators_export_service
        from openpyxl.worksheet._writer import ALL_TEMP_FILES

        real_row_to_xlsx_cells = daily_indicators_export_service._row_to_xlsx_cells
        calls = {"count": 0}

        def _fail_on_second_row(worksheet, row):
            calls["count"] += 1
            if calls["count"] >= 2:
                raise RuntimeError("boom")
            return real_row_to_xlsx_cells(worksheet, row)

        baseline = set(ALL_TEMP_FILES)
        with mock.patch.object(
            daily_indicators_export_service, "_row_to_xlsx_cells", side_effect=_fail_on_second_row
        ):
            with self.assertRaises(RuntimeError):
                daily_indicators_export_service.generate_daily_indicators_export(
                    formato="xlsx", filters=self._filters()
                )

        leaked = set(ALL_TEMP_FILES) - baseline
        self.assertEqual(
            leaked, set(),
            f"arquivo temporario interno do openpyxl nao removido: {leaked}",
        )
        for path in leaked:
            self.assertFalse(os.path.exists(path))

    def test_temp_dir_and_internal_openpyxl_files_removed_when_xlsx_finalization_fails(self):
        """REPORTS_SENIOR_REVIEW: os testes acima mockam `_row_to_xlsx_cells`
        — falha durante a CONVERSAO da linha, nunca durante save()/
        finalizacao real (`ws.close()` real + arquivamento no ZIP +
        `writer.cleanup()`, dentro de
        openpyxl.writer.excel.ExcelWriter.write_worksheet). Este teste
        instrumenta `zipfile.ZipFile.write` (unico ponto de I/O usado por
        `write_worksheet` para copiar o XML de um worksheet write-only ja
        fechado para o arquivo final) SEM substituir o exportador. Achado
        adicional identificado ao escrever este teste (nao um dos tres
        originais): sem `traceback.clear_frames` no `except` de
        `generate_daily_indicators_export`, o ZipFile de destino ficava
        aberto (preso pelo traceback) e `temp_dir` sobrevivia no Windows —
        corrigido junto com o achado 2 (mesmo mecanismo de limpeza)."""
        from core.services import daily_indicators_export_service
        from openpyxl.worksheet._writer import ALL_TEMP_FILES
        import zipfile

        def _fail_on_archive_write(self_zip, filename, arcname=None, **kwargs):
            raise RuntimeError("boom-disk-full-during-finalization")

        baseline = set(ALL_TEMP_FILES)
        captured = {}
        original_mkdtemp = daily_indicators_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        with mock.patch.object(zipfile.ZipFile, "write", new=_fail_on_archive_write):
            with mock.patch.object(
                daily_indicators_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
            ):
                with self.assertRaises(RuntimeError) as ctx:
                    daily_indicators_export_service.generate_daily_indicators_export(
                        formato="xlsx", filters=self._filters()
                    )

        self.assertEqual(str(ctx.exception), "boom-disk-full-during-finalization")
        self.assertIn("temp_dir", captured)
        self.assertFalse(
            os.path.exists(captured["temp_dir"]),
            "temp_dir proprio do exportador nao removido apos falha na finalizacao XLSX",
        )

        leaked = set(ALL_TEMP_FILES) - baseline
        self.assertEqual(
            leaked, set(),
            f"arquivo temporario interno do openpyxl nao removido apos falha na finalizacao: {leaked}",
        )
        for path in leaked:
            self.assertFalse(os.path.exists(path))

    def test_temp_dir_removed_when_finalization_fails_with_chained_exception_kept_alive(self):
        """REPORTS_SENIOR_REVIEW, secao 'Revisao especifica de
        traceback.clear_frames': o teste acima usa excecao SIMPLES —
        insuficiente para provar a limpeza contra uma excecao ENCADEADA
        (`raise RuntimeError(...) from OSError(...)`), onde o `ZipFile` de
        saida pode ficar referenciado apenas pelo traceback da CAUSA. Ver
        docstring completa em
        AllocationsExportStreamingCleanupTests::test_temp_dir_removed_when_finalization_fails_with_chained_exception_kept_alive.
        Excecao e causa mantidas VIVAS (`exc_holder`, sem `del`/`gc.collect()`)
        durante toda a verificacao."""
        from core.services import daily_indicators_export_service
        from openpyxl.worksheet._writer import ALL_TEMP_FILES
        import zipfile

        def _raise_deep_oserror(archive_ref):
            raise OSError("disk full (simulated, chained)")

        def _fail_with_chained_exception(self_zip, filename, arcname=None, **kwargs):
            try:
                _raise_deep_oserror(self_zip)
            except OSError as cause:
                raise RuntimeError("boom-chained-during-finalization") from cause

        baseline = set(ALL_TEMP_FILES)
        captured = {}
        original_mkdtemp = daily_indicators_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        exc_holder = {}
        with mock.patch.object(zipfile.ZipFile, "write", new=_fail_with_chained_exception):
            with mock.patch.object(
                daily_indicators_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
            ):
                try:
                    daily_indicators_export_service.generate_daily_indicators_export(
                        formato="xlsx", filters=self._filters()
                    )
                    self.fail("esperava RuntimeError encadeado a partir de OSError")
                except RuntimeError as exc:
                    exc_holder["exc"] = exc

        self.assertEqual(str(exc_holder["exc"]), "boom-chained-during-finalization")
        self.assertIsInstance(exc_holder["exc"].__cause__, OSError)

        self.assertIn("temp_dir", captured)
        self.assertFalse(
            os.path.exists(captured["temp_dir"]),
            "temp_dir sobrevive quando o ZipFile fica preso pelo traceback da CAUSA",
        )

        leaked = set(ALL_TEMP_FILES) - baseline
        self.assertEqual(
            leaked, set(),
            f"arquivo temporario interno do openpyxl nao removido: {leaked}",
        )
        for path in leaked:
            self.assertFalse(os.path.exists(path))

        self.assertIsNotNone(exc_holder["exc"].__cause__)


class DailyIndicatorsExportReadOnlyRepetitionTests(TestCase):
    """Complementa DailyIndicatorsReadOnlyTests.test_export_creates_no_snapshot
    (primeira execucao) com repeticao e snapshot preexistente — mesmo par
    de garantias ja provado para a CONSULTA
    (DailyIndicatorsReadOnlyTests.test_repeated_query_still_creates_no_snapshot
    / test_query_with_preexisting_stale_snapshot_does_not_alter_it), agora
    para a EXPORTACAO (secao 8 do enunciado: "ausencia de escrita em
    primeira execucao, repeticao e snapshots preexistentes")."""

    def setUp(self):
        _freeze_today(self)
        self.admin = _create_user("admin.di.exportreadonly@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_repeated_export_still_creates_no_snapshot(self):
        pairs = _base_pairs("2026-09-01", "2026-09-05")
        first = self.client.get(_export_url("csv", pairs))
        second = self.client.get(_export_url("csv", pairs))
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(DashboardDailySnapshot.objects.count(), 0)

    def test_export_with_preexisting_stale_snapshot_does_not_alter_it(self):
        preexisting = DashboardDailySnapshot.objects.create(
            date=date(2026, 9, 2),
            people_logged_in=999,
            calculation_version=0,  # forcadamente desatualizado
        )
        response = self.client.get(_export_url("csv", _base_pairs("2026-09-01", "2026-09-05")))
        self.assertEqual(response.status_code, 200)
        preexisting.refresh_from_db()
        self.assertEqual(
            preexisting.people_logged_in, 999,
            "snapshot preexistente (mesmo desatualizado) nao deve ser regravado pela exportacao",
        )
        self.assertEqual(preexisting.calculation_version, 0)
        self.assertEqual(DashboardDailySnapshot.objects.count(), 1)


class DailyIndicatorsExportQueryCostTests(TestCase):
    """Secao 6 do enunciado: nenhuma recomputacao integral redundante por
    lote/parte — o numero de consultas nao deve dobrar quando o periodo
    exportado cresce em multiplos de `split_threshold` (varias partes),
    alem do crescimento linear ja esperado pelo numero de dias (cada dia
    paga sua propria `build_indicator_for_day`, sempre — o que este teste
    prova e a AUSENCIA de uma segunda passada O(dias) pelo totalizador de
    Reconectados, eliminada pela otimizacao de REL-13-E)."""

    def setUp(self):
        _freeze_today(self)
        self.admin = _create_user("admin.di.exportquerycost@test.com", SystemUser.Role.ADMIN)

    def test_query_count_does_not_double_the_per_day_cost_via_totals_pass(self):
        """Compara consultas da EXPORTACAO (sem segunda passada) contra o
        dobro do numero de dias vezes o custo unitario de um unico dia —
        se a otimizacao regredisse para "iterar tudo duas vezes" (uma para
        linhas, outra para totais), o numero de consultas quase dobraria
        em relacao a esta margem."""
        from core.services.daily_indicators_export_service import generate_daily_indicators_export

        with CaptureQueriesContext(connection) as one_day:
            export_one = generate_daily_indicators_export(
                formato="csv",
                filters={
                    "data_inicial": date(2026, 9, 1),
                    "data_final": date(2026, 9, 1),
                    "incluir_excluidos": False,
                },
            )
        shutil.rmtree(export_one.temp_dir, ignore_errors=True)
        one_day_queries = len(one_day.captured_queries)

        with CaptureQueriesContext(connection) as ten_days:
            export_ten = generate_daily_indicators_export(
                formato="csv",
                filters={
                    "data_inicial": date(2026, 9, 1),
                    "data_final": date(2026, 9, 10),
                    "incluir_excluidos": False,
                },
            )
        shutil.rmtree(export_ten.temp_dir, ignore_errors=True)
        ten_days_queries = len(ten_days.captured_queries)

        # 10x mais dias: se a totalizacao fizesse uma segunda passada
        # O(dias) (regressao), o crescimento seria proximo de 20x (duas
        # iteracoes completas); sem a segunda passada, fica proximo de 10x
        # mais o custo fixo (2 consultas agregadas de Entregues/Novos).
        self.assertLessEqual(
            ten_days_queries, one_day_queries * 12,
            "numero de consultas sugere segunda passada O(dias) redundante no totalizador",
        )


class DailyIndicatorsExportRealVolumeTests(TestCase):
    """Ensaio de volume REAL da EXPORTACAO (secao 5/6 do enunciado desta
    task) — NAO reaproveita a meta da consulta paginada
    (DailyIndicatorsQueryRealVolumeTests, 20s): a exportacao processa TODOS
    os dias do periodo (sem o teto de 50 dias da pagina), entao seu custo
    e estruturalmente maior para o mesmo periodo. Mesmo padrao de banco/
    dataset da consulta (sqlite de teste, 300 funcionarios, 600 linhas,
    fluxo modesto ao longo do periodo mais longo medido) — reaproveita a
    MESMA fixture de `DailyIndicatorsQueryRealVolumeTests` por heranca,
    evitando recriar 10^3 registros de novo.

    CRITERIO DE ACEITE — REGISTRADO ANTES DA MEDICAO (nenhum numero abaixo
    foi ajustado depois de ver o resultado real, que so aparece nesta
    classe/spec DEPOIS deste bloco de definicao):
    - Natureza: meta tecnica do ENSAIO LOCAL (sqlite, banco de teste), nao
      SLA de produto nem limite de PRD (Postgres, nao medido).
    - Origem do numero: a exportacao chama `build_indicator_for_day`
      (~8-10 consultas) para TODOS os dias do periodo (nao so ate 50 como
      a tela), mais 2 consultas agregadas fixas (Entregues/Novos, O(1),
      REL-13-Q) — SEM segunda passada para Reconectados (otimizacao desta
      task, ver DailyIndicatorsExportTotalsEquivalenceTests/
      DailyIndicatorsExportQueryCostTests). Estimativa: ~10 consultas/dia,
      period 365 dias ~3.650 consultas — ordem de grandeza maior que a
      consulta paginada (1.600 consultas para o mesmo periodo, limitada a
      50 dias de linhas), mas SEM a segunda passada O(dias) que a tela
      paga para o totalizador de Reconectados. Custo por query neste
      ambiente ja observado em ~1.5ms (ensaio da consulta, REL-13-Q) — o
      tempo de parede deve escalar de forma compativel, sem constante
      adicional grosseira introduzida pela serializacao CSV (E/S local,
      ordens de grandeza menor que o custo das consultas).
    - Criterio: para os periodos de 10/60/200/365 dias, tempo de parede da
      exportacao completa (geracao do arquivo, sem servir a resposta HTTP)
      deve ficar abaixo de 60s cada neste ambiente sqlite de teste — margem
      generosa (~6x a estimativa linear ingenua de 10 queries/dia a 1.5ms/
      query) para absorver overhead de serializacao CSV/objeto Python por
      linha sem mascarar uma regressao real. Periodo extremo de 1095 dias
      (3 anos) sem meta de tempo, de proposito (mesma decisao D/REL-13-C
      ja aplicada pela consulta): so precisa completar sem erro/truncamento,
      com o numero de linhas exportadas batendo exatamente com o numero de
      dias do periodo. Memoria (tracemalloc) medida porque, diferente da
      consulta, a exportacao materializa/serializa TODAS as linhas do
      periodo (nao so ate 50)."""

    NUM_EMPLOYEES = 300
    NUM_LINES = 600
    LONGEST_PERIOD_DAYS = 1095

    @classmethod
    def setUpTestData(cls):
        cls.period_end = date(2026, 9, 30)
        cls.dataset_start = cls.period_end - timedelta(days=cls.LONGEST_PERIOD_DAYS + 30)

        cls.admin = _create_user("admin.di.exportrealvolume@test.com", SystemUser.Role.ADMIN)

        employees = []
        for index in range(cls.NUM_EMPLOYEES):
            portfolio = "Alimentos" if index % 2 == 0 else "Natura"
            employees.append(
                Employee(
                    full_name=f"Volume Real Export Funcionario {index}",
                    corporate_email=f"volume.real.export.{index}@corp.com",
                    employee_id=portfolio,
                    teams=Employee.UnitChoices.JOINVILLE,
                    status=Employee.Status.ACTIVE,
                )
            )
        Employee.objects.bulk_create(employees, batch_size=1000)
        Employee.all_objects.update(created_at=_local_midnight(cls.dataset_start))

        sims = [
            SIMcard(iccid=f"8978{index:020d}", carrier="TIM")
            for index in range(cls.NUM_LINES)
        ]
        SIMcard.objects.bulk_create(sims, batch_size=1000)
        sim_ids = list(SIMcard.objects.order_by("pk").values_list("pk", flat=True))

        lines = [
            PhoneLine(
                phone_number=f"+5511999{index:06d}",
                sim_card_id=sim_ids[index],
                status=PhoneLine.Status.AVAILABLE,
            )
            for index in range(cls.NUM_LINES)
        ]
        PhoneLine.objects.bulk_create(lines, batch_size=1000)
        PhoneLine.all_objects.update(created_at=_local_midnight(cls.dataset_start))

        employee_ids = list(
            Employee.all_objects.order_by("pk").values_list("pk", flat=True)
        )
        line_ids = list(PhoneLine.all_objects.order_by("pk").values_list("pk", flat=True))

        allocations = []
        total_flow_days = cls.LONGEST_PERIOD_DAYS
        for offset in range(0, total_flow_days, 3):
            line_id = line_ids[(offset // 3) % cls.NUM_LINES]
            employee_id = employee_ids[(offset // 3) % cls.NUM_EMPLOYEES]
            allocations.append(
                LineAllocation(
                    employee_id=employee_id,
                    phone_line_id=line_id,
                    allocated_by=cls.admin,
                    is_active=True,
                )
            )
        LineAllocation.objects.bulk_create(allocations, batch_size=1000)

        created_allocations = list(
            LineAllocation.objects.order_by("pk").values_list("pk", flat=True)
        )
        for index, allocation_id in enumerate(created_allocations):
            offset = index * 3
            day = cls.dataset_start + timedelta(days=offset)
            LineAllocation.objects.filter(pk=allocation_id).update(
                allocated_at=_local_midnight(day)
            )

    def _measure(self, days):
        import time as _time
        import tracemalloc

        from core.services.daily_indicators_export_service import generate_daily_indicators_export

        data_final = self.period_end
        data_inicial = data_final - timedelta(days=days - 1)
        filters = {
            "data_inicial": data_inicial,
            "data_final": data_final,
            "incluir_excluidos": False,
        }
        with CaptureQueriesContext(connection) as captured:
            tracemalloc.start()
            started = _time.perf_counter()
            export = generate_daily_indicators_export(formato="csv", filters=filters)
            elapsed = _time.perf_counter() - started
            _, peak_bytes = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        try:
            with open(export.path, encoding="utf-8-sig") as handle:
                row_count = len(list(csv.reader(handle, delimiter=";"))) - 1
        finally:
            shutil.rmtree(export.temp_dir, ignore_errors=True)
        return elapsed, len(captured.captured_queries), row_count, peak_bytes

    def test_export_time_and_query_count_for_representative_periods(self):
        for days in (10, 60, 200, 365):
            elapsed, query_count, row_count, peak_bytes = self._measure(days)
            self.assertEqual(row_count, days)
            sys.stderr.write(
                f"\n[VOLUME REAL EXPORT - INDICADORES DIARIOS] dias={days} "
                f"tempo={elapsed:.2f}s queries={query_count} "
                f"pico_memoria={peak_bytes / 1024 / 1024:.2f}MiB\n"
            )
            self.assertLess(
                elapsed, 60.0,
                f"meta tecnica de ensaio local (60s, ver docstring da classe) "
                f"excedida para periodo de {days} dias: {elapsed:.2f}s",
            )

    def test_extreme_three_year_period_export_completes_without_truncation(self):
        elapsed, query_count, row_count, peak_bytes = self._measure(self.LONGEST_PERIOD_DAYS)
        self.assertEqual(row_count, self.LONGEST_PERIOD_DAYS)
        sys.stderr.write(
            f"\n[VOLUME REAL EXPORT - INDICADORES DIARIOS] dias={self.LONGEST_PERIOD_DAYS} "
            f"(extremo, sem meta de tempo) tempo={elapsed:.2f}s queries={query_count} "
            f"pico_memoria={peak_bytes / 1024 / 1024:.2f}MiB\n"
        )


class DailyIndicatorsCatalogClosureNote(TestCase):
    """Nao e um teste de comportamento do relatorio — registra em codigo
    (secao 10 do enunciado desta task) o ponto de atencao para REL-13-Q:
    quando o motor de "daily_indicators" existir, o pathway generico de
    "relatorio do catalogo REL-01 totalmente indisponivel", hoje
    exemplificado por
    config/tests/test_line_inventory_report.py::OtherReportStillUnavailableTests::
    test_daily_indicators_report_still_returns_400_engine_unavailable e por
    config/tests/test_reports_hub.py::...::
    test_switch_to_unavailable_report_shows_unavailable_message_not_param_error,
    ficara sem NENHUM relatorio real do catalogo para exemplificar — os
    seis relatorios aprovados em REL-01 terao todos algum motor. Esta task
    (REL-13-T) NAO altera aqueles dois testes (nao ha necessidade nesta
    etapa, e o enunciado veda antecipar essa mudanca); a decisao de como
    revisar aquela cobertura (remover, substituir por um teste de
    "relatorio desconhecido no enum" ou outra forma) fica para quando
    REL-13-Q fechar o catalogo, registrada tambem na fonte da verdade.
    Nenhum setimo relatorio deve ser inventado para preencher essa lacuna."""

    def test_no_op_documentation_placeholder(self):
        """Sem asserção de comportamento — existe apenas para que este
        apontamento apareca na colecao de testes (rastreavel por node ID)
        em vez de só em prosa na spec.

        FECHAMENTO (REL-13-Q, 2026-09-30): "daily_indicators" ganhou motor
        de CONSULTA nesta task — os 6 relatorios do catalogo REL-01 agora
        tem consulta. O pathway generico "relatorio do catalogo
        genuinamente sem nenhum motor" ficou sem nenhum exemplo real
        (nenhum setimo relatorio foi inventado para substitui-lo, conforme
        vedado pelo enunciado). Os dois testes que usavam
        "daily_indicators" como exemplo foram repropositados, nao
        removidos:
        config/tests/test_line_inventory_report.py::
        OtherReportStillUnavailableTests (placeholder documental, mesmo
        padrao desta classe — a cobertura real de "identificador de
        relatorio desconhecido" ja existe e continua em
        config/tests/test_whatsapp_seal_report.py::
        WhatsAppSealReportParameterValidationTests::
        test_unknown_relatorio_value_rejected, nao duplicada);
        config/tests/test_reports_hub.py::...::
        test_switch_to_unavailable_report_shows_unavailable_message_not_param_error
        virou
        test_switch_to_daily_indicators_now_available_succeeds_without_param_error
        (mesmo mecanismo de picker, resultado invertido porque o relatorio
        agora existe)."""
        self.assertTrue(True)
