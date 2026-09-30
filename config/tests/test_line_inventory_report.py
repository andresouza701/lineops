"""Testes RED da task REL-09-T (fonte da verdade:
docs/superpowers/specs/2026-09-22-reports-hub-design.md, secoes REL-07 e
REL-09-C).

Cobrem o relatorio line_inventory: consulta na tela (endpoint existente
GET /relatorios/, motor ainda ausente) e exportacoes CSV/XLSX (endpoint
reports_export, ja registrado pela implementacao de Selos WhatsApp em
REL-08-E, mas cujo dispatch hoje so aceita relatorio=whatsapp_seal). Nao
testa a aba generica (rota, menu, autorizacao base da pagina) nem o motor
de Selos WhatsApp, ja cobertos em config/tests/test_reports_hub.py e
config/tests/test_whatsapp_seal_report.py — reaproveitados, nao duplicados.

Nenhum modulo de aplicacao futuro (formulario/servico proprios do
Inventario) e importado no topo deste arquivo: eles ainda nao existem.
reverse(EXPORT_URL_NAME) pode ser chamado no topo/setUp com seguranca,
diferente de REL-08-T: a rota ja esta registrada desde REL-08-E.

Decisao de escopo original (REL-09-T inicial): os parametros de filtro
proprios do Inventario (status_linha, operadora, origem, canal, com_selo,
com_vinculo) ainda NAO estao no whitelist global REPORT_QUERY_PARAM_NAMES
nem em nenhum form. Um teste ingenuo de "valor invalido rejeitado com 400"
para esses parametros passaria pelo motivo ERRADO (rejeicao generica de
"parametro desconhecido" do contrato comum, nao validacao especifica do
Inventario) — GREEN por acidente, mascarando requisito nao coberto.

Atualizacao (correcao de REL-09-T, 2026-09-25): status_linha/origem/canal
ja tem testes de "valor invalido, nao rejeitado como parametro
desconhecido" em LineInventoryFilterParameterValidationTests, usando o
helper _assert_not_rejected_as_unknown_parameter para distinguir as duas
causas sem fixar mensagem alem da ja aprovada pelo contrato comum
(REL-07). Apos a aprovacao dos tokens com/sem (com_selo/com_vinculo) e do
limite de 100 caracteres pos-trim de operadora em 2026-09-25,
LineInventoryApprovedFilterTokenTests cobre esses dois parametros e o
limite de operadora com o mesmo padrao (nao mais decisao de escopo em
aberto para eles). Os testes de "valor VALIDO" continuam validos como RED
funcional (esperam 200 com conteudo filtrado; hoje recebem 400 — o motivo
exato varia, documentado teste a teste).
"""

import csv
import io
import itertools
from datetime import date, datetime, time, timedelta

import openpyxl
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse
from django.utils import timezone
from urllib.parse import urlencode

from allocations.models import LineAllocation
from core.services.allocation_service import AllocationService
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser

PASSWORD = "StrongPass123"
REPORTS_URL_NAME = "reports_home"
EXPORT_URL_NAME = "reports_export"  # ja registrado desde REL-08-E

NON_ADMIN_ROLES = [
    SystemUser.Role.DEV,
    SystemUser.Role.SUPER,
    SystemUser.Role.BACKOFFICE,
    SystemUser.Role.GERENTE,
    SystemUser.Role.OPERATOR,
]

PERIOD_START = "2026-09-01"
PERIOD_END = "2026-09-24"
PERIOD_START_DATE = date(2026, 9, 1)
PERIOD_END_DATE = date(2026, 9, 24)

_iccid_counter = itertools.count(1)
_employee_counter = itertools.count(1)


def _create_user(email, role, **extra):
    return SystemUser.objects.create_user(email=email, password=PASSWORD, role=role, **extra)


def _local_midnight(d):
    return timezone.make_aware(datetime.combine(d, time.min))


def _local_last_instant(d):
    return timezone.make_aware(datetime.combine(d, time(23, 59, 59, 999999)))


def _mid_period_moment():
    """Um instante qualquer dentro do periodo padrao, usado por fixtures que
    nao testam fronteira (so precisam estar 'dentro')."""
    return _local_midnight(date(2026, 9, 10))


def _set_created_at(line, moment):
    """PhoneLine.created_at e auto_now_add: PhoneLine.objects.create(created_at=...)
    IGNORA silenciosamente o valor passado (Django sobrescreve no save()).
    Por isso o ajuste so e valido via update() no queryset (bypassa o
    auto_now_add), seguido de refresh_from_db() e confirmacao explicita do
    valor persistido — nunca presumido."""
    PhoneLine.all_objects.filter(pk=line.pk).update(created_at=moment)
    line.refresh_from_db()
    assert line.created_at == moment, (
        f"created_at nao persistiu o valor esperado: {line.created_at!r} != {moment!r}"
    )
    return line


def _make_line(
    phone_number,
    *,
    status=PhoneLine.Status.AVAILABLE,
    origem=None,
    canal=None,
    carrier="TIM",
    seal="",
    created_at=None,
    delete_line=False,
    delete_sim=False,
    cascade_delete_sim=False,
):
    """Cria SIMcard+PhoneLine direto via ORM (sem full_clean), permitindo
    tambem estados legados/inconsistentes previstos no contrato (exclusao
    isolada de SIMcard sem cascata). created_at default: um instante
    qualquer dentro do periodo padrao (ver _mid_period_moment)."""
    sim = SIMcard.objects.create(
        iccid=f"8900000000000{next(_iccid_counter):05d}", carrier=carrier
    )
    line = PhoneLine.objects.create(
        phone_number=phone_number,
        sim_card=sim,
        status=status,
        origem=origem,
        canal=canal,
        whatsapp_seal=seal,
    )
    _set_created_at(line, created_at if created_at is not None else _mid_period_moment())

    if cascade_delete_sim:
        sim.delete()
        line.refresh_from_db()
    else:
        if delete_line:
            line.delete()
        if delete_sim:
            SIMcard.all_objects.filter(pk=sim.pk).update(is_deleted=True)
    return line, sim


def _make_employee(label=None):
    suffix = label or next(_employee_counter)
    return Employee.objects.create(
        full_name=f"Inventario Teste {suffix}",
        corporate_email=f"corp.inv{suffix}@test.com",
        employee_id=f"INV-{suffix}",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )


def _allocate(line, admin, employee=None):
    employee = employee or _make_employee()
    return AllocationService.allocate_line(employee=employee, phone_line=line, allocated_by=admin)


def _force_second_active_allocation(line, admin, employee=None):
    """Cria uma SEGUNDA LineAllocation.is_active=True para a mesma linha via
    ORM direto, contornando deliberadamente AllocationService (que rejeita
    corretamente esse estado — nao alterado nem monkey-patchado aqui). Isso
    simula um dado inconsistente real (import/script), nunca um caminho
    suportado pela aplicacao, conforme mapeado em REL-09-C."""
    employee = employee or _make_employee()
    return LineAllocation.objects.create(
        employee=employee,
        phone_line=line,
        allocated_by=admin,
        is_active=True,
    )


def _release(allocation, admin):
    AllocationService.release_line(allocation, released_by=admin)


def _report_url(pairs):
    return f"{reverse(REPORTS_URL_NAME)}?{urlencode(pairs)}"


def _base_pairs(data_inicial=PERIOD_START, data_final=PERIOD_END, **extra):
    pairs = [
        ("relatorio", "line_inventory"),
        ("data_inicial", data_inicial),
        ("data_final", data_final),
    ]
    pairs.extend(extra.items())
    return pairs


def _export_url(formato, pairs):
    return f"{reverse(EXPORT_URL_NAME, kwargs={'formato': formato})}?{urlencode(pairs)}"


EXPECTED_COLUMN_HEADERS = [
    "Linha",
    "Status",
    "Operadora",
    "Origem",
    "Canal",
    "Selo",
    "Vínculo atual",
    "Data de cadastro",
    "Registro",
]


class LineInventoryInitialLoadTests(TestCase):
    """Relatorio selecionado sem datas: sem motor, sem erro prematuro.
    Abertura totalmente sem parametros ja e coberta genericamente por
    ReportsHomeContentTests em config/tests/test_reports_hub.py."""

    def setUp(self):
        self.admin = _create_user("admin.inv.initial@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_report_selected_without_dates_does_not_run_engine_or_error(self):
        response = self.client.get(_report_url([("relatorio", "line_inventory")]))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode().lower()
        self.assertNotIn("obrigat", content)
        self.assertNotIn("erro", content)


class LineInventorySharedValidationAppliesTests(TestCase):
    """Contrato comum (REL-07) ja validado pelo mesmo form/endpoint
    independente do relatorio selecionado — confirma que a validacao
    estrita de datas/page/incluir_excluidos/parametro repetido precede o
    dispatch por relatorio, tambem para line_inventory. Reaproveita
    cobertura ja comprovada para whatsapp_seal; aqui so trava a ordem de
    execucao (validacao comum antes do "relatorio ainda indisponivel")."""

    def setUp(self):
        self.admin = _create_user("admin.inv.sharedval@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_missing_data_inicial_rejected(self):
        response = self.client.get(
            _report_url([("relatorio", "line_inventory"), ("data_final", PERIOD_END)])
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_date_format_rejected(self):
        response = self.client.get(
            _report_url([("relatorio", "line_inventory"), ("data_inicial", "31/09/2026"), ("data_final", PERIOD_END)])
        )
        self.assertEqual(response.status_code, 400)

    def test_inverted_dates_rejected(self):
        response = self.client.get(
            _report_url([("relatorio", "line_inventory"), ("data_inicial", PERIOD_END), ("data_final", PERIOD_START)])
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
            f"{url}?relatorio=line_inventory&data_inicial={PERIOD_START}&data_inicial=2026-09-02&data_final={PERIOD_END}"
        )
        self.assertEqual(response.status_code, 400)

    def test_unknown_generic_query_parameter_rejected(self):
        response = self.client.get(_report_url(_base_pairs(campo_totalmente_inexistente="x")))
        self.assertEqual(response.status_code, 400)


class LineInventoryDateBoundaryOverflowTests(TestCase):
    """REPORTS_SENIOR_REVIEW (.git/REPORTS_SENIOR_REVIEW.md) achado 3:
    `_period_bounds` (core/services/line_inventory_report_service.py) soma
    1 dia a `data_final` para obter o limite exclusivo do periodo (fuso
    local) — com data_final=date.max isso e `date.max + timedelta(days=1)`,
    que estoura (`OverflowError: date value out of range`) antes de
    qualquer consulta ao banco, nunca capturado pela view (500 real). O
    form agora rejeita esse valor como erro de campo, tanto na consulta
    quanto na exportacao (mesmo LineInventoryReportQueryForm valida os
    dois endpoints, ver _validate_report_query_params). Nenhum limite
    arbitrario de duracao de periodo: apenas a fronteira realmente
    representavel pelo calculo do limite exclusivo (date.max - 1 dia)."""

    def setUp(self):
        self.admin = _create_user("admin.inv.dateboundary@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_last_supported_end_date_returns_200_on_query(self):
        response = self.client.get(
            _report_url(_base_pairs(data_inicial="9999-12-30", data_final="9999-12-30"))
        )
        self.assertEqual(response.status_code, 200)

    def test_last_supported_end_date_returns_200_on_export(self):
        response = self.client.get(
            _export_url("csv", _base_pairs(data_inicial="9999-12-30", data_final="9999-12-30"))
        )
        self.assertEqual(response.status_code, 200)

    def test_first_unsupported_end_date_rejected_as_field_error_on_query(self):
        response = self.client.get(
            _report_url(_base_pairs(data_inicial="9999-12-31", data_final="9999-12-31"))
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(
            response,
            "Data final não pode ser posterior a 30/12/9999.",
            status_code=400,
        )

    def test_first_unsupported_end_date_rejected_as_field_error_on_export(self):
        response = self.client.get(
            _export_url("csv", _base_pairs(data_inicial="9999-12-31", data_final="9999-12-31"))
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(
            response,
            "Data final não pode ser posterior a 30/12/9999.",
            status_code=400,
        )

    def test_normal_period_query_unaffected_by_boundary_validation(self):
        response = self.client.get(_report_url(_base_pairs()))
        self.assertEqual(response.status_code, 200)


class OtherReportStillUnavailableTests(TestCase):
    """Correcao de escopo (REL-09-Q): esta classe se chamava
    LineInventoryUnavailableTodayTests e ancorava "line_inventory ainda sem
    motor -> 400" como baseline do estado anterior a REL-09-Q. Agora que a
    consulta do Inventario existe de verdade (GET /relatorios/?relatorio=
    line_inventory&... retorna 200 com conteudo real, coberto pelas demais
    classes deste arquivo), aquela alegacao ficou falsa e o teste original
    falharia (400 esperado, 200 obtido) nao por regressao, mas porque o
    proprio requisito que ele documentava foi implementado. Divergencia com
    a spec resolvida pela implementacao, nao erro de fixture.

    Repropositado para continuar cobrindo o mesmo pathway generico
    (relatorio do catalogo sem NENHUM motor ainda, nem consulta nem
    exportacao) usando "allocations" — um dos quatro relatorios do
    catalogo REL-01 ainda genuinamente sem motor — em vez de line_inventory,
    preservando a cobertura da mensagem/codigo de "relatorio indisponivel"
    sem reafirmar algo que deixou de ser verdade.

    Repropositado NOVAMENTE em REL-10-Q (2026-09-28): "allocations" ganhou
    motor de CONSULTA (REPORT_QUERY_ENGINES), entao a alegacao "nenhum
    motor" tambem deixou de ser verdade para esse relatorio — mesma
    divergencia documental do paragrafo acima, agora resolvida trocando o
    exemplo para "pendencies", que continua genuinamente sem nenhum motor
    (nem consulta nem exportacao) nesta etapa. Cobertura do pathway
    generico preservada, nao removida.

    Repropositado UMA TERCEIRA VEZ em REL-11-Q (2026-09-28): "pendencies"
    ganhou motor de CONSULTA nesta task (REPORT_QUERY_ENGINES), entao a
    alegacao "nenhum motor" tambem deixou de ser verdade para "pendencies"
    — mesma divergencia documental dos dois paragrafos acima, agora
    resolvida trocando o exemplo para "line_history", um dos dois
    relatorios do catalogo REL-01 que continuam genuinamente sem nenhum
    motor (nem consulta nem exportacao) nesta etapa (o outro e
    "daily_indicators"). Cobertura do pathway generico preservada, nao
    removida. O angulo do DOWNLOAD direto de "pendencies" (que agora cai no
    ramo distinto "consulta existe, exportacao ainda nao") passou a ser
    coberto por
    config/tests/test_pendencies_report.py::PendenciesReportStillUnavailableTests.

    Repropositado UMA QUARTA VEZ em REL-12-Q (2026-09-29): "line_history"
    ganhou motor de CONSULTA nesta task (REPORT_QUERY_ENGINES), entao a
    alegacao "nenhum motor" tambem deixou de ser verdade para "line_history"
    — mesma divergencia documental dos tres paragrafos acima, agora
    resolvida trocando o exemplo para "daily_indicators", o UNICO relatorio
    do catalogo REL-01 que continuava genuinamente sem nenhum motor (nem
    consulta nem exportacao) naquela etapa. O angulo do DOWNLOAD direto de
    "line_history" (que passou a cair no ramo distinto "consulta existe,
    exportacao ainda nao") passou a ser coberto por
    config/tests/test_line_history_report.py::LineHistoryReportEngineUnavailableBaselineTests::
    test_export_returns_400_export_engine_unavailable_message.

    FECHAMENTO (REL-13-Q, 2026-09-30): "daily_indicators" ganhou motor de
    CONSULTA nesta task — os 6 relatorios do catalogo REL-01 agora tem
    consulta. Nao ha setimo relatorio para reproposicionar mais uma vez
    (enunciado desta task veda inventar um), entao o pathway generico
    "relatorio do catalogo genuinamente sem NENHUM motor" fica sem nenhum
    exemplo real do catalogo — nao e uma lacuna de cobertura: a cobertura
    de "identificador de relatorio desconhecido" (fora do catalogo) ja
    existe e continua em
    config/tests/test_whatsapp_seal_report.py::
    WhatsAppSealReportParameterValidationTests::
    test_unknown_relatorio_value_rejected (nao duplicada aqui); o angulo do
    DOWNLOAD direto de "daily_indicators" (que agora cai no mesmo ramo
    "consulta existe, exportacao ainda nao" que "pendencies"/"line_history"
    ja cobriam) passou a ser coberto por
    config/tests/test_daily_indicators_report.py::
    DailyIndicatorsExportEngineUnavailableBaselineTests::
    test_export_direct_access_still_returns_400_export_engine_unavailable_message.
    Este teste (`test_daily_indicators_report_still_returns_400_engine_unavailable`)
    e retirado — nao substituido por um setimo relatorio fictício — porque
    o cenario que ele documentava (relatorio real do catalogo sem NENHUM
    motor) deixou de existir no dominio; a classe permanece como registro
    historico das quatro reproposicoes anteriores."""

    def setUp(self):
        self.admin = _create_user("admin.inv.otherunavailable@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_no_op_documentation_placeholder(self):
        """Sem asserção de comportamento (mesmo padrao de
        DailyIndicatorsCatalogClosureNote,
        config/tests/test_daily_indicators_report.py) — existe apenas para
        que o fechamento do pathway generico continue rastreavel por node
        ID em vez de so em prosa nesta docstring de classe."""
        self.assertTrue(True)


class LineInventoryFilterParameterValidationTests(TestCase):
    """Distingue, para os filtros restritos do Inventario com vocabulario
    fechado (status_linha, origem, canal), parametro RECONHECIDO com valor
    invalido de parametro DESCONHECIDO — evitando o falso GREEN que um
    teste ingenuo "valor invalido -> 400" teria hoje pelo motivo errado.

    Motivo do risco: REPORT_QUERY_PARAM_NAMES (config/views.py) ainda nao
    inclui esses seis nomes; hoje QUALQUER valor deles, valido ou
    invalido, e rejeitado com a MESMA mensagem generica "Parametro
    desconhecido: <nome>." (config/views.py, checagem de parametro
    desconhecido, executada antes de qualquer validacao de campo). Essa
    mensagem e, pelo contrato atual, reservada exatamente para nomes nao
    reconhecidos — uma vez que REL-09-Q registre o nome como campo
    proprio, essa mensagem especifica nao deve mais aparecer para ele,
    mesmo com valor invalido. Os testes abaixo comprovam que isso AINDA
    NAO acontece (RED real, nao um 400 gen[e]rico coincidente).

    com_selo/com_vinculo ficam FORA desta classe: REL-09-C aprovou so os
    rotulos humanos ("Todos/Com selo/Sem selo", "Todos/Com vinculo/Sem
    vinculo"), nao os tokens exatos do parametro HTTP — sem essa decisao
    nao ha um "valor invalido" definido sem ambiguidade. Pergunta
    registrada como pendente na fonte da verdade (secao REL-09-T,
    "Perguntas pendentes"); nenhum teste foi escrito presumindo os tokens.

    operadora fica FORA do padrao "valor invalido" desta classe por
    instrucao explicita da task: e busca substring em texto livre, nao
    enum — "operadora fora do enum" nao e invalidade real (REL-09-C nao
    aprova vocabulario fechado para operadora). Cobre-se aqui apenas a
    invalidade efetivamente definida no contrato comum aplicavel a
    qualquer parametro escalar: repeticao (REL-07)."""

    def setUp(self):
        self.admin = _create_user("admin.inv.paramval@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def _assert_not_rejected_as_unknown_parameter(self, response, param_name):
        self.assertEqual(response.status_code, 400)
        content = response.content.decode()
        self.assertNotIn(
            f"Parâmetro desconhecido: {param_name}",
            content,
            f"{param_name} com valor invalido ainda cai no bucket generico "
            "de 'parametro desconhecido' — sinal de que o nome ainda nao "
            "esta reconhecido/validado como campo proprio (gap real: nome "
            "fora do whitelist e sem form dedicado).",
        )

    # status_linha — PhoneLine.Status, vocabulario fechado (6 valores)

    def test_status_linha_invalid_value_not_treated_as_unknown_parameter(self):
        response = self.client.get(_report_url(_base_pairs(status_linha="INVALIDO")))
        self._assert_not_rejected_as_unknown_parameter(response, "status_linha")

    def test_status_linha_invalid_value_not_treated_as_unknown_parameter_on_export(self):
        response = self.client.get(_export_url("csv", _base_pairs(status_linha="INVALIDO")))
        self._assert_not_rejected_as_unknown_parameter(response, "status_linha")

    def test_status_linha_valid_value_control_returns_200_with_eligible_line(self):
        _make_line("+5511990100001", status=PhoneLine.Status.CANCELLED)
        response = self.client.get(_report_url(_base_pairs(status_linha="CANCELLED")))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "+5511990100001")

    # origem — PhoneLine.Origem, vocabulario fechado (10 valores)

    def test_origem_invalid_value_not_treated_as_unknown_parameter(self):
        response = self.client.get(_report_url(_base_pairs(origem="INVALIDO")))
        self._assert_not_rejected_as_unknown_parameter(response, "origem")

    def test_origem_invalid_value_not_treated_as_unknown_parameter_on_export(self):
        response = self.client.get(_export_url("xlsx", _base_pairs(origem="INVALIDO")))
        self._assert_not_rejected_as_unknown_parameter(response, "origem")

    def test_origem_valid_value_control_returns_200_with_eligible_line(self):
        _make_line("+5511990100002", origem=PhoneLine.Origem.BLIP)
        response = self.client.get(_report_url(_base_pairs(origem="BLIP")))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "+5511990100002")

    # canal — PhoneLine.Canal, vocabulario fechado (3 valores)

    def test_canal_invalid_value_not_treated_as_unknown_parameter(self):
        response = self.client.get(_report_url(_base_pairs(canal="INVALIDO")))
        self._assert_not_rejected_as_unknown_parameter(response, "canal")

    def test_canal_invalid_value_not_treated_as_unknown_parameter_on_export(self):
        response = self.client.get(_export_url("csv", _base_pairs(canal="INVALIDO")))
        self._assert_not_rejected_as_unknown_parameter(response, "canal")

    def test_canal_valid_value_control_returns_200_with_eligible_line(self):
        _make_line("+5511990100003", canal=PhoneLine.Canal.ANYCALL)
        response = self.client.get(_report_url(_base_pairs(canal="ANYCALL")))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "+5511990100003")

    # operadora — texto livre, substring; sem enum. So a invalidade comum
    # (repeticao de parametro escalar, REL-07) e testada aqui.

    def test_operadora_repeated_scalar_parameter_not_treated_as_unknown_parameter(self):
        """REL-07 exige rejeicao de parametro escalar repetido para
        qualquer campo, nao so os ja whitelisted. Hoje `operadora`
        repetido cai no bucket de 'parametro desconhecido' (a checagem de
        repeticao em config/views.py so percorre REPORT_QUERY_PARAM_NAMES,
        e operadora nao esta nela) — mesmo status 400 hoje, categoria
        ainda errada."""
        url = reverse(REPORTS_URL_NAME)
        response = self.client.get(
            f"{url}?{urlencode(_base_pairs())}&operadora=VIVO&operadora=CLARO"
        )
        self._assert_not_rejected_as_unknown_parameter(response, "operadora")

    def test_operadora_accepts_free_text_substring_control_returns_200(self):
        """Controle de valor legitimo: sem vocabulario fechado aprovado
        para operadora (REL-09-C), qualquer texto e potencialmente valido —
        so a busca substring importa, ja coberta em LineInventoryFilterTests."""
        _make_line("+5511990100004", carrier="VIVO")
        response = self.client.get(_report_url(_base_pairs(operadora="VIV")))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "+5511990100004")


class LineInventoryApprovedFilterTokenTests(TestCase):
    """Cobertura complementar de REL-09-T para as definicoes aprovadas pelo
    usuario em 2026-09-25 (fonte da verdade, secao "REL-09-T — Definicoes
    aprovadas apos a correcao"):

    - com_selo/com_vinculo: tokens HTTP `com`/`sem`; ausente ou vazio =
      Todos; qualquer outro token e 400 (campo RECONHECIDO com valor
      invalido, nao mais "parametro desconhecido").
    - operadora: texto livre, sem enum, com limite de 100 caracteres
      apos trim; 101 caracteres apos trim e 400 pelo LIMITE do campo, nao
      pelo whitelist.

    Reaproveitado, nao duplicado: `test_com_selo_filter_isolates_presence`/
    `_absence` e `test_com_vinculo_filter_isolates_presence`/`_absence`
    (LineInventoryFilterTests) ja provam "com"/"sem" reconhecidos com
    resultados coerentes via linhas-controle; `test_operadora_filter_substring`/
    `test_operadora_filter_trims_surrounding_whitespace` (idem) ja provam
    busca parcial e trim basico. Esta classe cobre apenas o que ainda
    faltava: ausencia/vazio = Todos, token/limite invalido distinguido de
    parametro desconhecido, e as fronteiras exatas de 100/101 caracteres,
    em consulta e exportacao."""

    def setUp(self):
        self.admin = _create_user("admin.inv.approvedtokens@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def _assert_not_rejected_as_unknown_parameter(self, response, param_name):
        self.assertEqual(response.status_code, 400)
        content = response.content.decode()
        self.assertNotIn(
            f"Parâmetro desconhecido: {param_name}",
            content,
            f"{param_name} ainda cai no bucket generico de 'parametro "
            "desconhecido' — sinal de que o nome/limite ainda nao esta "
            "reconhecido/validado como campo proprio.",
        )

    def _read_csv_rows(self, response):
        text = (
            b"".join(response.streaming_content).decode("utf-8-sig")
            if response.streaming
            else response.content.decode("utf-8-sig")
        )
        return list(csv.reader(io.StringIO(text), delimiter=";"))

    # com_selo / com_vinculo — ausente/vazio = Todos

    def test_com_selo_absent_behaves_as_todos(self):
        with_seal, _ = _make_line("+5511990200001", seal="META_ONE")
        without_seal, _ = _make_line("+5511990200002", seal="")
        response = self.client.get(_report_url(_base_pairs()))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("+5511990200001", content)
        self.assertIn("+5511990200002", content)

    def test_com_selo_empty_string_behaves_as_todos(self):
        with_seal, _ = _make_line("+5511990200003", seal="META_VERIFIED")
        without_seal, _ = _make_line("+5511990200004", seal="")
        response = self.client.get(_report_url(_base_pairs(com_selo="")))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("+5511990200003", content)
        self.assertIn("+5511990200004", content)

    def test_com_vinculo_absent_behaves_as_todos(self):
        with_link, _ = _make_line("+5511990200005")
        _allocate(with_link, self.admin)
        without_link, _ = _make_line("+5511990200006")
        response = self.client.get(_report_url(_base_pairs()))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("+5511990200005", content)
        self.assertIn("+5511990200006", content)

    def test_com_vinculo_empty_string_behaves_as_todos(self):
        with_link, _ = _make_line("+5511990200007")
        _allocate(with_link, self.admin)
        without_link, _ = _make_line("+5511990200008")
        response = self.client.get(_report_url(_base_pairs(com_vinculo="")))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("+5511990200007", content)
        self.assertIn("+5511990200008", content)

    # com_selo / com_vinculo — token desconhecido: campo reconhecido, nao
    # "parametro desconhecido"

    def test_com_selo_unknown_token_rejected_as_recognized_field(self):
        response = self.client.get(_report_url(_base_pairs(com_selo="xablau")))
        self._assert_not_rejected_as_unknown_parameter(response, "com_selo")

    def test_com_selo_unknown_token_rejected_on_export(self):
        response = self.client.get(_export_url("csv", _base_pairs(com_selo="xablau")))
        self._assert_not_rejected_as_unknown_parameter(response, "com_selo")

    def test_com_vinculo_unknown_token_rejected_as_recognized_field(self):
        response = self.client.get(_report_url(_base_pairs(com_vinculo="xablau")))
        self._assert_not_rejected_as_unknown_parameter(response, "com_vinculo")

    def test_com_vinculo_unknown_token_rejected_on_export(self):
        response = self.client.get(_export_url("xlsx", _base_pairs(com_vinculo="xablau")))
        self._assert_not_rejected_as_unknown_parameter(response, "com_vinculo")

    # com_selo / com_vinculo — conteudo real na exportacao (nao so status)

    def test_com_selo_com_token_returns_real_content_on_export(self):
        with_seal, _ = _make_line("+5511990200013", seal="META_ONE")
        without_seal, _ = _make_line("+5511990200014", seal="")
        response = self.client.get(_export_url("csv", _base_pairs(com_selo="com")))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Content-Type", "").split(";")[0], "text/csv")
        rows = self._read_csv_rows(response)
        phones = {row[0].lstrip("'") for row in rows[1:] if row}
        self.assertIn("+5511990200013", phones)
        self.assertNotIn("+5511990200014", phones)

    def test_com_vinculo_com_token_returns_real_content_on_export(self):
        with_link, _ = _make_line("+5511990200015")
        _allocate(with_link, self.admin)
        without_link, _ = _make_line("+5511990200016")
        response = self.client.get(_export_url("csv", _base_pairs(com_vinculo="com")))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Content-Type", "").split(";")[0], "text/csv")
        rows = self._read_csv_rows(response)
        phones = {row[0].lstrip("'") for row in rows[1:] if row}
        self.assertIn("+5511990200015", phones)
        self.assertNotIn("+5511990200016", phones)

    # operadora — ausente/vazio/so espacos nao restringem (busca parcial
    # basica ja coberta em LineInventoryFilterTests)

    def test_operadora_absent_and_empty_do_not_restrict(self):
        line_a, _ = _make_line("+5511990200017", carrier="VIVO")
        line_b, _ = _make_line("+5511990200018", carrier="CLARO")
        absent = self.client.get(_report_url(_base_pairs()))
        empty = self.client.get(_report_url(_base_pairs(operadora="")))
        self.assertEqual(absent.status_code, 200)
        self.assertEqual(empty.status_code, 200)
        for response in (absent, empty):
            content = response.content.decode()
            self.assertIn("+5511990200017", content)
            self.assertIn("+5511990200018", content)

    def test_operadora_only_spaces_does_not_restrict(self):
        line_a, _ = _make_line("+5511990200019", carrier="VIVO")
        line_b, _ = _make_line("+5511990200020", carrier="CLARO")
        response = self.client.get(_report_url(_base_pairs(operadora="   ")))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("+5511990200019", content)
        self.assertIn("+5511990200020", content)

    # operadora — fronteira de 100/101 caracteres apos trim
    #
    # Valor mixed-case sem espaco interno, fora de CARRIER_ALIASES, para
    # nao ser alterado por normalize_carrier_name (core/normalization.py):
    # raw.islower()/raw.isupper() sao ambos False para "Xy" repetido, entao
    # o valor persiste exatamente como gravado — a fronteira de tamanho
    # testada aqui nao fica acoplada a normalizacao de maiuscula/minuscula.

    def test_operadora_exactly_100_chars_accepted(self):
        carrier_value = "Xy" * 50  # 100 chars, estavel sob normalizacao
        eligible, _ = _make_line("+5511990200021", carrier=carrier_value)
        response = self.client.get(_report_url(_base_pairs(operadora=carrier_value)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "+5511990200021")

    def test_operadora_exactly_100_chars_accepted_on_export(self):
        carrier_value = "Xy" * 50
        eligible, _ = _make_line("+5511990200022", carrier=carrier_value)
        response = self.client.get(_export_url("csv", _base_pairs(operadora=carrier_value)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Content-Type", "").split(";")[0], "text/csv")
        rows = self._read_csv_rows(response)
        phones = {row[0].lstrip("'") for row in rows[1:] if row}
        self.assertIn("+5511990200022", phones)

    def test_operadora_101_chars_rejected_as_field_limit(self):
        response = self.client.get(_report_url(_base_pairs(operadora="Xy" * 50 + "Z")))
        self._assert_not_rejected_as_unknown_parameter(response, "operadora")

    def test_operadora_101_chars_rejected_on_export(self):
        response = self.client.get(_export_url("csv", _base_pairs(operadora="Xy" * 50 + "Z")))
        self._assert_not_rejected_as_unknown_parameter(response, "operadora")

    def test_operadora_raw_input_over_100_but_100_after_trim_accepted(self):
        trimmed_value = "Xy" * 50  # 100 chars
        raw_value = "  " + trimmed_value + "  "  # 104 chars brutos
        eligible, _ = _make_line("+5511990200023", carrier=trimmed_value)
        response = self.client.get(_report_url(_base_pairs(operadora=raw_value)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "+5511990200023")


class LineInventoryPeriodTests(TestCase):
    """Periodo filtra por PhoneLine.created_at (decisao REL-09-C), nao por
    activated_at, whatsapp_seal_activated_on ou LineAllocation.allocated_at.
    Fronteiras inclusivas: inicio local inclusivo ate inicio local do dia
    posterior ao fim, exclusivo (America/Sao_Paulo), conforme REL-07."""

    def setUp(self):
        self.admin = _create_user("admin.inv.period@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_start_boundary_inclusive(self):
        line, _ = _make_line("+5511900100001", created_at=_local_midnight(PERIOD_START_DATE))
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511900100001")

    def test_instant_before_start_boundary_excluded(self):
        control, _ = _make_line("+5511900100098", created_at=_local_midnight(PERIOD_START_DATE))
        excluded, _ = _make_line(
            "+5511900100002",
            created_at=_local_midnight(PERIOD_START_DATE) - timedelta(microseconds=1),
        )
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511900100098")
        self.assertNotContains(response, "+5511900100002")

    def test_end_boundary_inclusive_last_local_instant(self):
        line, _ = _make_line("+5511900100003", created_at=_local_last_instant(PERIOD_END_DATE))
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511900100003")

    def test_instant_at_start_of_day_after_end_excluded(self):
        control, _ = _make_line("+5511900100097", created_at=_local_last_instant(PERIOD_END_DATE))
        excluded, _ = _make_line(
            "+5511900100004",
            created_at=_local_midnight(PERIOD_END_DATE + timedelta(days=1)),
        )
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511900100097")
        self.assertNotContains(response, "+5511900100004")

    def test_created_at_persisted_value_matches_fixture_assumption(self):
        """Confirma explicitamente (nao presume) que o ajuste de created_at
        via update() persiste o valor exato usado pelas fronteiras acima."""
        moment = _local_midnight(PERIOD_START_DATE)
        line, _ = _make_line("+5511900100005", created_at=moment)
        line.refresh_from_db()
        self.assertEqual(line.created_at, moment)

    def test_activated_at_does_not_substitute_period_reference(self):
        line, _ = _make_line("+5511900100006", created_at=_local_midnight(PERIOD_START_DATE) - timedelta(days=5))
        line.activated_at = _local_midnight(date(2026, 9, 10))
        line.save(update_fields=["activated_at"])
        response = self.client.get(_report_url(_base_pairs()))
        self.assertNotContains(response, "+5511900100006")

    def test_whatsapp_seal_activated_on_does_not_substitute_period_reference(self):
        line, _ = _make_line(
            "+5511900100007",
            created_at=_local_midnight(PERIOD_START_DATE) - timedelta(days=5),
            seal="META_ONE",
        )
        line.whatsapp_seal_activated_on = date(2026, 9, 10)
        line.save(update_fields=["whatsapp_seal_activated_on"])
        response = self.client.get(_report_url(_base_pairs()))
        self.assertNotContains(response, "+5511900100007")

    def test_allocation_allocated_at_does_not_substitute_period_reference(self):
        line, _ = _make_line("+5511900100008", created_at=_local_midnight(PERIOD_START_DATE) - timedelta(days=5))
        _allocate(line, self.admin)
        response = self.client.get(_report_url(_base_pairs()))
        self.assertNotContains(response, "+5511900100008")


class LineInventoryGranularityAndVinculoTests(TestCase):
    """Uma linha por PhoneLine; vinculo atual reflete somente alocacoes
    is_active=True no momento da consulta, nunca duplica a linha."""

    def setUp(self):
        self.admin = _create_user("admin.inv.granularity@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_line_without_allocation_appears_in_result(self):
        """Semantica de 'Sem vinculo' propriamente dita (rotulo Nao/Sim na
        celula Vinculo atual) e coberta por com_vinculo=sem em
        LineInventoryFilterTests; aqui so confirma que a linha sem alocacao
        nenhuma nao e excluida do conjunto por essa ausencia."""
        line, _ = _make_line("+5511900200001")
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511900200001")

    def test_line_with_one_active_allocation_appears_once_with_sim(self):
        line, _ = _make_line("+5511900200002")
        _allocate(line, self.admin)
        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        self.assertEqual(content.count("+5511900200002"), 1)

    def test_history_of_released_allocations_does_not_count_as_current_link(self):
        line, _ = _make_line("+5511900200003")
        first = _allocate(line, self.admin)
        _release(first, self.admin)
        line.status = PhoneLine.Status.AVAILABLE
        line.save(update_fields=["status"])
        second = _allocate(line, self.admin)
        _release(second, self.admin)
        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        self.assertEqual(content.count("+5511900200003"), 1)

    def test_two_active_allocations_inconsistency_single_row_with_count(self):
        """Estado so alcancavel via bypass deliberado do servico de dominio
        (ver _force_second_active_allocation) — nunca produzido pelo
        caminho normal da aplicacao."""
        line, _ = _make_line("+5511900200004")
        _allocate(line, self.admin)
        _force_second_active_allocation(line, self.admin)
        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        self.assertEqual(content.count("+5511900200004"), 1)
        self.assertIn("inconsistente: 2 ativos", content)

    def test_employee_soft_deleted_does_not_remove_current_link(self):
        line, _ = _make_line("+5511900200005")
        employee = _make_employee("softdel")
        _allocate(line, self.admin, employee=employee)
        employee.delete()
        self.assertTrue(Employee.all_objects.get(pk=employee.pk).is_deleted)

        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        self.assertIn("+5511900200005", content)
        self.assertNotIn("Linha excluída", content)


class LineInventoryFilterTests(TestCase):
    """Filtros de status_linha/operadora/origem/canal/com_selo/com_vinculo/
    linha, isolados e combinados por AND, conforme REL-09-C."""

    def setUp(self):
        self.admin = _create_user("admin.inv.filters@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)
        self.allocated, _ = _make_line(
            "+5511900300001",
            status=PhoneLine.Status.AVAILABLE,
            origem=PhoneLine.Origem.SRVMEMU_01,
            canal=PhoneLine.Canal.WEB,
            carrier="VIVO",
            seal="META_ONE",
        )
        _allocate(self.allocated, self.admin)
        self.available, _ = _make_line(
            "+5511900300002",
            status=PhoneLine.Status.AVAILABLE,
            origem=PhoneLine.Origem.BLIP,
            canal=PhoneLine.Canal.MYLOOP,
            carrier="CLARO",
            seal="",
        )

    def test_status_linha_filter_isolates(self):
        _make_line("+5511900300003", status=PhoneLine.Status.CANCELLED)
        response = self.client.get(_report_url(_base_pairs(status_linha="CANCELLED")))
        content = response.content.decode()
        self.assertIn("+5511900300003", content)
        self.assertNotIn("+5511900300001", content)
        self.assertNotIn("+5511900300002", content)

    def test_operadora_filter_substring(self):
        response = self.client.get(_report_url(_base_pairs(operadora="VIV")))
        content = response.content.decode()
        self.assertIn("+5511900300001", content)
        self.assertNotIn("+5511900300002", content)

    def test_operadora_filter_trims_surrounding_whitespace(self):
        response = self.client.get(_report_url(_base_pairs(operadora="  VIV  ")))
        self.assertContains(response, "+5511900300001")

    def test_origem_filter_isolates(self):
        response = self.client.get(_report_url(_base_pairs(origem="BLIP")))
        content = response.content.decode()
        self.assertIn("+5511900300002", content)
        self.assertNotIn("+5511900300001", content)

    def test_canal_filter_isolates(self):
        response = self.client.get(_report_url(_base_pairs(canal="MYLOOP")))
        content = response.content.decode()
        self.assertIn("+5511900300002", content)
        self.assertNotIn("+5511900300001", content)

    def test_com_selo_filter_isolates_presence(self):
        response = self.client.get(_report_url(_base_pairs(com_selo="com")))
        content = response.content.decode()
        self.assertIn("+5511900300001", content)
        self.assertNotIn("+5511900300002", content)

    def test_com_selo_filter_isolates_absence(self):
        response = self.client.get(_report_url(_base_pairs(com_selo="sem")))
        content = response.content.decode()
        self.assertIn("+5511900300002", content)
        self.assertNotIn("+5511900300001", content)

    def test_com_vinculo_filter_isolates_presence(self):
        response = self.client.get(_report_url(_base_pairs(com_vinculo="com")))
        content = response.content.decode()
        self.assertIn("+5511900300001", content)
        self.assertNotIn("+5511900300002", content)

    def test_com_vinculo_filter_isolates_absence(self):
        response = self.client.get(_report_url(_base_pairs(com_vinculo="sem")))
        content = response.content.decode()
        self.assertIn("+5511900300002", content)
        self.assertNotIn("+5511900300001", content)

    def test_linha_search_partial_substring(self):
        response = self.client.get(_report_url(_base_pairs(linha="300002")))
        content = response.content.decode()
        self.assertIn("+5511900300002", content)
        self.assertNotIn("+5511900300001", content)

    def test_combined_filters_apply_as_and(self):
        response = self.client.get(
            _report_url(_base_pairs(com_selo="com", origem="SRVMEMU-01", operadora="VIV"))
        )
        content = response.content.decode()
        self.assertIn("+5511900300001", content)
        self.assertNotIn("+5511900300002", content)

        mismatch = self.client.get(_report_url(_base_pairs(com_selo="com", origem="BLIP")))
        content_mismatch = mismatch.content.decode()
        self.assertNotIn("+5511900300001", content_mismatch)
        self.assertNotIn("+5511900300002", content_mismatch)

    def test_status_linha_independent_from_vinculo_selo_and_exclusion(self):
        """status_linha nunca funciona como proxy de vinculo/exclusao/selo:
        uma linha CANCELLED com selo e vinculo continua aparecendo em
        com_selo=com e com_vinculo=com, isolada por status.

        Correcao de fixture (REL-09-Q): AllocationService.allocate_line
        exige phone_line.status == AVAILABLE e levanta BusinessRuleException
        caso contrario — nao e possivel alocar uma linha ja CANCELLED pelo
        caminho normal. A linha e criada disponivel, alocada normalmente, e
        so DEPOIS tem o status transicionado para CANCELLED via update()
        direto no queryset (mesmo padrao ja usado neste arquivo para
        estados legados/inconsistentes, ex. _force_second_active_allocation)
        — representa uma linha que permanece com vinculo ativo mesmo apos
        virar CANCELLED, estado alcancavel no banco independente de como a
        aplicacao normalmente o produziria."""
        cancelled_with_seal_and_link, _ = _make_line(
            "+5511900300009", status=PhoneLine.Status.AVAILABLE, seal="META_VERIFIED"
        )
        _allocate(cancelled_with_seal_and_link, self.admin)
        PhoneLine.all_objects.filter(pk=cancelled_with_seal_and_link.pk).update(
            status=PhoneLine.Status.CANCELLED
        )

        response = self.client.get(
            _report_url(_base_pairs(status_linha="CANCELLED", com_selo="com", com_vinculo="com"))
        )
        content = response.content.decode()
        self.assertIn("+5511900300009", content)
        self.assertNotIn("+5511900300001", content)
        self.assertNotIn("+5511900300002", content)


class LineInventoryOriginCanalNullTests(TestCase):
    """Origem/Canal nulos exibem 'Nao informado'; sem opcao de filtro
    dedicada para ausencia (decisao REL-09-C); Todos inclui os nulos, um
    valor especifico do enum nunca casa nulo."""

    def setUp(self):
        self.admin = _create_user("admin.inv.nullorigin@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)
        self.with_origin, _ = _make_line(
            "+5511900400001", origem=PhoneLine.Origem.BLIP, canal=PhoneLine.Canal.WEB
        )
        self.without_origin, _ = _make_line("+5511900400002", origem=None, canal=None)

    def test_null_origin_and_channel_render_not_informed(self):
        response = self.client.get(_report_url(_base_pairs(linha="400002")))
        self.assertContains(response, "Não informado")

    def test_todos_includes_null_origin(self):
        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        self.assertIn("+5511900400001", content)
        self.assertIn("+5511900400002", content)

    def test_specific_origem_value_never_matches_null(self):
        response = self.client.get(_report_url(_base_pairs(origem="BLIP")))
        content = response.content.decode()
        self.assertIn("+5511900400001", content)
        self.assertNotIn("+5511900400002", content)


class LineInventoryExclusionTests(TestCase):
    """Exclusao logica de linha/SIMcard: oculto por padrao, incluido com o
    filtro marcado, coluna Registro correta, sem restauracao. Employee
    excluido nao afeta inclusao da linha nem a coluna Registro."""

    def setUp(self):
        self.admin = _create_user("admin.inv.exclusion@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_line_deleted_hidden_by_default_shown_when_included(self):
        control, _ = _make_line("+5511900500098")
        excluded, _ = _make_line("+5511900500001", delete_line=True)
        default_resp = self.client.get(_report_url(_base_pairs()))
        self.assertContains(default_resp, "+5511900500098")
        self.assertNotContains(default_resp, "+5511900500001")

        included_resp = self.client.get(_report_url(_base_pairs(incluir_excluidos="1")))
        self.assertContains(included_resp, "+5511900500001")
        self.assertContains(included_resp, "Linha excluída")

    def test_simcard_deleted_only_hidden_by_default_shown_when_included(self):
        control, _ = _make_line("+5511900500097")
        excluded, _ = _make_line("+5511900500002", delete_sim=True)
        default_resp = self.client.get(_report_url(_base_pairs()))
        self.assertContains(default_resp, "+5511900500097")
        self.assertNotContains(default_resp, "+5511900500002")

        included_resp = self.client.get(_report_url(_base_pairs(incluir_excluidos="1")))
        self.assertContains(included_resp, "+5511900500002")
        self.assertContains(included_resp, "SIMcard excluído")

    def test_both_line_and_simcard_deleted(self):
        control, _ = _make_line("+5511900500096")
        excluded, _ = _make_line("+5511900500003", cascade_delete_sim=True)
        default_resp = self.client.get(_report_url(_base_pairs()))
        self.assertContains(default_resp, "+5511900500096")
        self.assertNotContains(default_resp, "+5511900500003")

        included_resp = self.client.get(_report_url(_base_pairs(incluir_excluidos="1")))
        self.assertContains(included_resp, "+5511900500003")
        self.assertContains(included_resp, "Linha e SIMcard excluídos")

    def test_checkbox_included_does_not_restore_flags(self):
        line, sim = _make_line("+5511900500004", delete_line=True)
        response = self.client.get(_report_url(_base_pairs(incluir_excluidos="1")))
        self.assertEqual(response.status_code, 200)
        line.refresh_from_db()
        self.assertTrue(line.is_deleted)

    def test_not_deleted_line_shows_registro_default_label(self):
        control, _ = _make_line("+5511900500099")
        line, _ = _make_line("+5511900500005")
        response = self.client.get(_report_url(_base_pairs(linha="500005")))
        self.assertContains(response, "+5511900500005")
        self.assertContains(response, "Não excluído")

    def test_employee_soft_deleted_alone_does_not_exclude_line_nor_change_registro(self):
        line, _ = _make_line("+5511900500006")
        employee = _make_employee("exclusion")
        _allocate(line, self.admin, employee=employee)
        employee.delete()

        default_resp = self.client.get(_report_url(_base_pairs()))
        self.assertContains(default_resp, "+5511900500006")
        self.assertContains(default_resp, "Não excluído")


class LineInventoryColumnsAndOrderTests(TestCase):
    """Nove colunas na ordem aprovada, sem colunas fora do catalogo
    (ICCID, dados de funcionario, activated_at)."""

    def setUp(self):
        self.admin = _create_user("admin.inv.columns@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_nine_column_headers_present_in_approved_order(self):
        """Correcao de fixture (REL-09-Q): busca ingenua por substring na
        pagina inteira (`content.find(header)`) e falsa — "Selo"/"Linha"
        tambem casam com textos do formulario de filtros acima da tabela
        (rotulos "Com selo"/"Sem selo" do select com_selo, label do campo
        Linha), fora de ordem em relacao ao thead real. Isolado ao trecho
        <thead>...</thead> para testar so os cabecalhos de fato, na tag
        <th>, nao qualquer ocorrencia solta do texto na pagina."""
        _make_line("+5511900600001")
        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()

        thead_start = content.index("<thead>")
        thead_end = content.index("</thead>") + len("</thead>")
        thead_html = content[thead_start:thead_end]

        indices = [thead_html.find(f"<th>{header}</th>") for header in EXPECTED_COLUMN_HEADERS]
        self.assertTrue(
            all(index != -1 for index in indices),
            f"nem todos os cabecalhos foram encontrados no thead: {list(zip(EXPECTED_COLUMN_HEADERS, indices))}",
        )
        self.assertEqual(indices, sorted(indices), "cabecalhos fora da ordem aprovada")

    def test_no_iccid_or_employee_identifying_columns(self):
        line, sim = _make_line("+5511900600002")
        employee = _make_employee("colcheck")
        employee.full_name = "Nome Nao Deve Aparecer"
        employee.employee_id = "MATRICULA-NAO-DEVE-APARECER"
        employee.save(update_fields=["full_name", "employee_id"])
        _allocate(line, self.admin, employee=employee)

        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        self.assertIn("+5511900600002", content)
        self.assertNotIn(sim.iccid, content)
        self.assertNotIn("Nome Nao Deve Aparecer", content)
        self.assertNotIn("MATRICULA-NAO-DEVE-APARECER", content)


class LineInventoryTotalsTests(TestCase):
    """Totalizadores: total geral, distribuicao por status, com/sem
    vinculo. Todos sobre o conjunto filtrado completo, independente de
    pagina; conjunto vazio mantem tudo em zero."""

    def setUp(self):
        self.admin = _create_user("admin.inv.totals@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_total_and_status_distribution_sum_consistently(self):
        """Marcacao HTML exata dos totalizadores (data-testid, classe etc.)
        ainda nao existe (depende do template de REL-09-Q) — nao presumida
        aqui. Este teste comprova o conjunto correto (pre-requisito de
        qualquer total correto); a formula exata soma-por-status=total e
        com/sem-vinculo=total sera reforcada em REL-09-Q com o markup real."""
        _make_line("+5511900700001", status=PhoneLine.Status.AVAILABLE)
        _make_line("+5511900700002", status=PhoneLine.Status.AVAILABLE)
        _make_line("+5511900700003", status=PhoneLine.Status.CANCELLED)
        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        for phone in ("+5511900700001", "+5511900700002", "+5511900700003"):
            self.assertIn(phone, content)

    def test_with_and_without_link_totals_count_lines_not_allocations(self):
        with_link, _ = _make_line("+5511900700004")
        _allocate(with_link, self.admin)
        _force_second_active_allocation(with_link, self.admin)  # inconsistencia: nao deve contar 2x
        without_link, _ = _make_line("+5511900700005")

        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        self.assertIn("+5511900700004", content)
        self.assertIn("+5511900700005", content)

    def test_empty_result_set_returns_zero_totals_no_error(self):
        response = self.client.get(
            _report_url(_base_pairs(data_inicial="2020-01-01", data_final="2020-01-02"))
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("erro", response.content.decode().lower())


class LineInventoryOrderingPaginationTests(TestCase):
    """Ordenacao phone_number crescente com desempate por pk crescente;
    paginacao fixa em 50; filtros preservados entre paginas."""

    def setUp(self):
        self.admin = _create_user("admin.inv.pagination@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_ascending_phone_number_order(self):
        _make_line("+5511900800003")
        _make_line("+5511900800001")
        _make_line("+5511900800002")
        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        idx1 = content.index("+5511900800001")
        idx2 = content.index("+5511900800002")
        idx3 = content.index("+5511900800003")
        self.assertLess(idx1, idx2)
        self.assertLess(idx2, idx3)

    def test_first_page_has_50_rows_and_not_the_51st(self):
        for index in range(51):
            _make_line(f"+55119008{index:06d}")
        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        phone_hits = sum(1 for index in range(51) if f"+55119008{index:06d}" in content)
        self.assertEqual(phone_hits, 50)

    def test_second_page_has_remaining_row(self):
        for index in range(51):
            _make_line(f"+55119009{index:06d}")
        response = self.client.get(_report_url(_base_pairs(page="2")))
        self.assertEqual(response.status_code, 200)

    def test_filters_preserved_across_pagination(self):
        """Investigacao do GREEN acidental original (node ID
        LineInventoryOrderingPaginationTests::test_filters_preserved_across_pagination):

        Requisito pretendido: REL-07 "paginacao preserva filtros" — pagina 2
        de uma consulta filtrada deve continuar mostrando o periodo
        submetido E deve conter de fato o restante do conjunto (nao a
        pagina 1 repetida, nem uma pagina vazia).

        Por que passava sem motor: a versao anterior so verificava
        `name="data_inicial" value="..."` no HTML — e esse campo e
        preenchido por `raw.data_inicial`/`raw.data_final` (valores BRUTOS
        da querystring, ecoados pelo template independentemente do motor
        ter rodado). Nenhuma consulta real precisa acontecer para esse
        texto aparecer; `page=2` nem chega a ser interpretado pelo motor
        hoje (a resposta e sempre o mesmo 400 de relatorio indisponivel,
        que ja inclui os campos de data preenchidos com o valor submetido).

        Evidencia que faltava: nenhuma prova de que a pagina 2 realmente
        contem um subconjunto DIFERENTE da pagina 1 — o requisito real de
        paginacao, nao so o eco de um campo de formulario.

        Correcao aplicada: comparar o CONTEUDO de duas respostas reais
        (pagina 1 vs pagina 2) e exigir que a 51a linha (unica elegivel na
        pagina 2, pela ordenacao crescente por phone_number aprovada em
        REL-09-C) apareca so na pagina 2, e a 1a linha (indice 0) apareca
        so na pagina 1 — mutuamente exclusivas, nao apenas "200 com texto
        generico". O eco do campo de data continua verificado, mas como
        evidencia adicional, nao mais como unica prova."""
        for index in range(51):
            _make_line(f"+55119010{index:06d}")
        first_line_number = f"+55119010{0:06d}"  # indice 0
        last_line_number = f"+55119010{50:06d}"  # indice 50, 51a linha

        page1 = self.client.get(_report_url(_base_pairs(page="1")))
        page2 = self.client.get(_report_url(_base_pairs(page="2")))
        self.assertEqual(page1.status_code, 200)
        self.assertEqual(page2.status_code, 200)

        content1 = page1.content.decode()
        content2 = page2.content.decode()

        self.assertIn(first_line_number, content1)
        self.assertNotIn(first_line_number, content2)
        self.assertIn(last_line_number, content2)
        self.assertNotIn(last_line_number, content1)

        self.assertIn(f'name="data_inicial" value="{PERIOD_START}"', content2)
        self.assertIn(f'name="data_final" value="{PERIOD_END}"', content2)

    def test_page_out_of_range_returns_404(self):
        response = self.client.get(_report_url(_base_pairs(page="999")))
        self.assertEqual(response.status_code, 404)


class LineInventoryNoWriteAndQueryCostTests(TestCase):
    """Somente leitura; custo de consulta nao escala linearmente com o
    numero de linhas mesmo com o Prefetch de vinculo."""

    def setUp(self):
        self.admin = _create_user("admin.inv.readonly@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_generating_report_does_not_write_business_data(self):
        line, _ = _make_line("+5511901100001")
        _allocate(line, self.admin)
        lines_before = PhoneLine.objects.count()
        allocations_before = LineAllocation.objects.count()

        first = self.client.get(_report_url(_base_pairs(incluir_excluidos="1")))
        second = self.client.get(_report_url(_base_pairs(status_linha="AVAILABLE")))
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(PhoneLine.objects.count(), lines_before)
        self.assertEqual(LineAllocation.objects.count(), allocations_before)

    def test_query_count_does_not_scale_linearly_with_row_count_including_links(self):
        for index in range(3):
            line, _ = _make_line(f"+5511901102{index:03d}")
            _allocate(line, self.admin)
        with CaptureQueriesContext(connection) as small:
            small_response = self.client.get(_report_url(_base_pairs()))

        for index in range(3, 30):
            line, _ = _make_line(f"+5511901102{index:03d}")
            _allocate(line, self.admin)
        with CaptureQueriesContext(connection) as large:
            large_response = self.client.get(_report_url(_base_pairs()))

        self.assertEqual(small_response.status_code, 200)
        self.assertEqual(large_response.status_code, 200)
        self.assertLessEqual(len(large.captured_queries) - len(small.captured_queries), 3)


class LineInventoryExportAuthorizationTests(TestCase):
    """E: autorizacao no download direto, ambos os formatos. Rota
    reports_export ja registrada (REL-08-E); autorizacao (RoleRequiredMixin)
    e checagem de formato ja precedem o dispatch por relatorio hoje — as
    verificacoes de 403/404/400-por-data ja sao GREEN preexistente,
    independentes de line_inventory estar implementado; so os dois casos
    ADMIN 200 abaixo sao RED funcional real desta task."""

    def setUp(self):
        self.admin = _create_user("admin.inv.exportauth@test.com", SystemUser.Role.ADMIN)

    def test_admin_can_download_csv(self):
        self.client.force_login(self.admin)
        response = self.client.get(_export_url("csv", _base_pairs()))
        self.assertEqual(response.status_code, 200)

    def test_admin_can_download_xlsx(self):
        self.client.force_login(self.admin)
        response = self.client.get(_export_url("xlsx", _base_pairs()))
        self.assertEqual(response.status_code, 200)

    def test_non_admin_roles_get_403_on_export(self):
        """GREEN preexistente: RoleRequiredMixin bloqueia antes do dispatch
        por relatorio, independente do motor existir."""
        for index, role in enumerate(NON_ADMIN_ROLES):
            with self.subTest(role=role):
                user = _create_user(f"inv.export.role{index}@test.com", role)
                self.client.force_login(user)
                response = self.client.get(_export_url("csv", _base_pairs()))
                self.assertEqual(response.status_code, 403)

    def test_anonymous_gets_403_on_export(self):
        """GREEN preexistente, mesmo motivo da classe acima."""
        response = self.client.get(_export_url("csv", _base_pairs()))
        self.assertEqual(response.status_code, 403)

    def test_invalid_dates_rejected_on_direct_export_access(self):
        """GREEN preexistente: validacao comum de datas precede o dispatch
        por relatorio."""
        self.client.force_login(self.admin)
        response = self.client.get(
            _export_url("csv", [("relatorio", "line_inventory"), ("data_inicial", PERIOD_END), ("data_final", PERIOD_START)])
        )
        self.assertEqual(response.status_code, 400)

    def test_unknown_format_returns_404(self):
        """GREEN preexistente: checagem de formato precede qualquer
        validacao/dispatch por relatorio em ReportsExportView.get()."""
        self.client.force_login(self.admin)
        response = self.client.get(_export_url("pdf", _base_pairs()))
        self.assertEqual(response.status_code, 404)


class LineInventoryExportContentTests(TestCase):
    """E: conteudo real lido via csv/openpyxl; nove colunas na ordem
    aprovada, conjunto completo independente da pagina, tipos/neutralizacao
    de formula, dados atuais no momento do download."""

    def setUp(self):
        self.admin = _create_user("admin.inv.exportcontent@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def _read_csv_rows(self, response):
        text = b"".join(response.streaming_content).decode("utf-8-sig") if response.streaming else response.content.decode("utf-8-sig")
        return list(csv.reader(io.StringIO(text), delimiter=";"))

    def _read_xlsx_rows(self, response):
        content = b"".join(response.streaming_content) if response.streaming else response.content
        workbook = openpyxl.load_workbook(io.BytesIO(content))
        sheet = workbook.active
        return list(sheet.iter_rows(values_only=True))

    def test_csv_and_xlsx_contain_all_filtered_rows_regardless_of_page(self):
        for index in range(60):
            _make_line(f"+5511902{index:07d}")

        csv_response = self.client.get(_export_url("csv", _base_pairs(page="1")))
        self.assertEqual(csv_response.status_code, 200)
        rows = self._read_csv_rows(csv_response)
        self.assertEqual(len(rows) - 1, 60)

        xlsx_response = self.client.get(_export_url("xlsx", _base_pairs(page="2")))
        self.assertEqual(xlsx_response.status_code, 200)
        xlsx_rows = self._read_xlsx_rows(xlsx_response)
        self.assertEqual(len(xlsx_rows) - 1, 60)

    def test_columns_match_approved_order_in_both_formats(self):
        _make_line("+5511903000001")
        csv_response = self.client.get(_export_url("csv", _base_pairs()))
        self.assertEqual(csv_response.status_code, 200)
        csv_rows = self._read_csv_rows(csv_response)
        self.assertEqual(csv_rows[0], EXPECTED_COLUMN_HEADERS)

        xlsx_response = self.client.get(_export_url("xlsx", _base_pairs()))
        self.assertEqual(xlsx_response.status_code, 200)
        xlsx_rows = self._read_xlsx_rows(xlsx_response)
        self.assertEqual(list(xlsx_rows[0]), EXPECTED_COLUMN_HEADERS)

    def test_empty_filtered_set_exports_headers_only(self):
        response = self.client.get(
            _export_url("csv", _base_pairs(data_inicial="2020-01-01", data_final="2020-01-02"))
        )
        self.assertEqual(response.status_code, 200)
        csv_rows = self._read_csv_rows(response)
        self.assertEqual(len(csv_rows), 1)

    def test_export_reflects_current_data_changed_after_query(self):
        line, _ = _make_line("+5511904000001", status=PhoneLine.Status.AVAILABLE)
        self.client.get(_report_url(_base_pairs()))

        line.status = PhoneLine.Status.CANCELLED
        line.save(update_fields=["status"])

        response = self.client.get(_export_url("csv", _base_pairs()))
        self.assertEqual(response.status_code, 200)
        csv_rows = self._read_csv_rows(response)
        matching = [row for row in csv_rows[1:] if row and row[0].lstrip("'") == "+5511904000001"]
        self.assertTrue(matching)
        self.assertEqual(matching[0][1], "Cancelado")

    def test_phone_number_stored_as_string_type_in_xlsx(self):
        _make_line("+5511905000001")
        response = self.client.get(_export_url("xlsx", _base_pairs()))
        self.assertEqual(response.status_code, 200)
        content = b"".join(response.streaming_content) if response.streaming else response.content
        workbook = openpyxl.load_workbook(io.BytesIO(content))
        sheet = workbook.active
        phone_cell = sheet.cell(row=2, column=1)
        self.assertEqual(phone_cell.data_type, "s")

    def test_formula_injection_neutralized_on_operadora_column(self):
        """Sem checar status_code==200 antes de indexar, uma resposta de
        erro (HTML) seria parseada pelo csv.reader como linhas de texto que,
        por acidente, tambem nao comecam por =/+/-/@ — produzindo um falso
        GREEN sem nenhum motor real. O assertEqual abaixo e o controle que
        evita isso."""
        _make_line("+5511906000001", carrier="+InjectedCarrier")
        response = self.client.get(_export_url("csv", _base_pairs()))
        self.assertEqual(response.status_code, 200)
        csv_rows = self._read_csv_rows(response)
        data_row = [row for row in csv_rows[1:] if row][0]
        for cell in data_row:
            self.assertFalse(cell.startswith(("=", "+", "-", "@")))

    def test_accents_preserved_and_do_not_break_parsing(self):
        _make_line("+5511907000001", carrier="Álgar Região Sul")
        response = self.client.get(_export_url("csv", _base_pairs()))
        self.assertEqual(response.status_code, 200)
        csv_rows = self._read_csv_rows(response)
        self.assertEqual(len(csv_rows), 2)
        self.assertIn("Álgar Região Sul", csv_rows[1])

    def test_xlsx_operadora_starting_with_equals_stored_as_plain_string_not_formula(self):
        """Achado da auditoria pre-REL-10-V (docs/superpowers/specs/2026-09-22-
        reports-hub-design.md): _row_to_xlsx_cells nao protegia NENHUM prefixo
        no XLSX (so o CSV, via _csv_text). openpyxl so promove data_type='f'
        para strings iniciadas por '=' (Cell._bind_value, venv/Lib/site-
        packages/openpyxl/cell/cell.py); '+'/'-'/'@' ja nascem 'texto'
        (data_type='s') mesmo sem protecao alguma — esta e a unica entrada
        que reproduz o defeito real (RED antes da correcao). Payload '=1+1'
        inofensivo: basta comecar por '=' para o openpyxl promover
        data_type='f' — nao precisa referenciar execucao de aplicativo (DDE)
        para comprovar o defeito de serializacao. SIMcard.save() chama
        normalize_carrier_name(), que preserva este payload por nao ter
        nenhum caractere alfabetico (raw.islower()/raw.isupper() sao False
        sem caractere "cased", caindo no ramo que devolve o valor original
        sem reformatacao) — por isso refresh_from_db() e a asserção contra
        o valor REAL persistido, nao um literal presumido."""
        line, sim = _make_line("+5511909000001", carrier="=1+1")
        sim.refresh_from_db()
        self.assertTrue(sim.carrier.startswith("="))
        response = self.client.get(_export_url("xlsx", _base_pairs()))
        self.assertEqual(response.status_code, 200)
        content = b"".join(response.streaming_content) if response.streaming else response.content
        workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=False)
        sheet = workbook["Inventário de linhas"]
        cell = sheet.cell(row=2, column=3)  # Operadora
        self.assertEqual(cell.data_type, "s")
        self.assertEqual(cell.value, sim.carrier)

    def test_xlsx_operadora_plus_minus_at_prefixes_were_never_typed_as_formula(self):
        """'+'/'-'/'@' nunca foram promovidos a formula pelo openpyxl (so
        '=' e' o gatilho real, ver teste acima) — este teste passa tanto
        antes quanto depois da correcao; existe para nao alegar retroativa-
        mente que esses tres prefixos eram um defeito corrigido aqui."""
        for index, prefixo in enumerate(("+5511InjOperadora", "-OperadoraX", "@OperadoraY")):
            line, sim = _make_line(f"+551191000000{index}", carrier=prefixo)
            sim.refresh_from_db()
            response = self.client.get(_export_url("xlsx", _base_pairs()))
            self.assertEqual(response.status_code, 200)
            content = b"".join(response.streaming_content) if response.streaming else response.content
            workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=False)
            sheet = workbook["Inventário de linhas"]
            cell_row_idx = next(
                r for r in range(2, sheet.max_row + 1) if sheet.cell(row=r, column=3).value == sim.carrier
            )
            self.assertEqual(sheet.cell(row=cell_row_idx, column=3).data_type, "s")

    def test_xlsx_created_at_date_remains_typed_after_formula_protection(self):
        """A protecao de formula so se aplica a colunas de TEXTO
        (_DATE_COLUMNS marca quais nao sao); confirma que a correcao nao
        forcou datas legitimas a texto."""
        moment = _local_midnight(date(2026, 9, 12))
        line, _ = _make_line("+5511912000001", carrier="=nao e o campo testado aqui", created_at=moment)
        response = self.client.get(_export_url("xlsx", _base_pairs()))
        self.assertEqual(response.status_code, 200)
        content = b"".join(response.streaming_content) if response.streaming else response.content
        workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=False)
        sheet = workbook["Inventário de linhas"]
        cell = sheet.cell(row=2, column=8)  # Data de cadastro
        value = cell.value.date() if hasattr(cell.value, "date") else cell.value
        self.assertEqual(value, date(2026, 9, 12))
        self.assertEqual(cell.number_format, "DD/MM/YYYY")

    def test_xlsx_context_sheet_filters_cell_safe_with_formula_like_operadora_filter(self):
        """A aba Contexto grava ["Filtros", filters_label]; filters_label
        sempre comeca com o texto fixo "Período: ", entao mesmo um filtro
        `operadora` iniciado por '=' nao faz a CELULA inteira comecar por
        '=' — confirma que a composicao atual ja e segura por construcao,
        sem exigir protecao adicional na aba Contexto."""
        _make_line("+5511913000001", carrier="TIM")
        response = self.client.get(
            _export_url("xlsx", _base_pairs(operadora="=1+1"))
        )
        self.assertEqual(response.status_code, 200)
        content = b"".join(response.streaming_content) if response.streaming else response.content
        workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=False)
        context_sheet = workbook["Contexto"]
        filtros_row = next(row for row in context_sheet.iter_rows(values_only=True) if row[0] == "Filtros")
        filtros_value = filtros_row[1]
        self.assertFalse(filtros_value.startswith(("=", "+", "-", "@")))
        self.assertIn("=1+1", filtros_value)
        cell = next(
            context_sheet.cell(row=r, column=2)
            for r in range(1, context_sheet.max_row + 1)
            if context_sheet.cell(row=r, column=1).value == "Filtros"
        )
        self.assertEqual(cell.data_type, "s")

    def test_inconsistent_link_and_registro_exported_correctly(self):
        line, _ = _make_line("+5511908000001", delete_line=False)
        _allocate(line, self.admin)
        _force_second_active_allocation(line, self.admin)
        excluded_line, _ = _make_line("+5511908000002", delete_line=True)

        response = self.client.get(_export_url("csv", _base_pairs(incluir_excluidos="1")))
        self.assertEqual(response.status_code, 200)
        csv_rows = self._read_csv_rows(response)
        by_phone = {row[0].lstrip("'"): row for row in csv_rows[1:] if row}
        self.assertIn("inconsistente: 2 ativos", by_phone["+5511908000001"][6])
        self.assertEqual(by_phone["+5511908000002"][8], "Linha excluída")


class LineInventoryExportVolumeTests(TestCase):
    """Caso trivial abaixo do limiar de divisao (arquivo unico, nao ZIP).

    Mesma decisao de escopo de REL-08-T (WhatsAppSealExportVolumeTests):
    nao ha interface publica para reduzir o limiar de producao em teste, e
    as instrucoes desta task proibem inventar uma so para isso e proibem
    ensaio de volume real nesta etapa. Fronteiras reais de divisao/ZIP,
    consumo de memoria/tempo e o custo especifico do Prefetch de vinculo em
    volume real ficam explicitamente para REL-09-E, com ensaio dedicado —
    metricas de volume de Selos WhatsApp nao comprovam o custo deste
    relatorio."""

    def setUp(self):
        self.admin = _create_user("admin.inv.exportvolume@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_small_filtered_set_returns_single_file_not_zip(self):
        _make_line("+5511909000001")
        response = self.client.get(_export_url("csv", _base_pairs()))
        self.assertEqual(response.status_code, 200)
        content_type = response.headers.get("Content-Type", "")
        self.assertNotIn("zip", content_type.lower())


class LineInventoryExportStreamingCleanupTests(TestCase):
    """Prova direta do mecanismo de limpeza de temporarios do exportador
    PROPRIO do Inventario (core/services/line_inventory_export_service),
    mesmo padrao/raciocinio ja comprovado para Selos WhatsApp em REL-08-E e
    sua correcao: consumo total, fechamento antecipado (desconexao
    simulada), fechamento ANTES do primeiro chunk (generator em
    GEN_CREATED, cujo finally so roda se ja suspenso em algum yield — por
    isso a resposta usa _CleanupStreamingHttpResponse.close(), nao apenas o
    generator), e falha durante a geracao."""

    def _filters(self):
        return dict(
            data_inicial=PERIOD_START_DATE,
            data_final=PERIOD_END_DATE,
            incluir_excluidos=False,
            status_linha="",
            operadora="",
            origem="",
            canal="",
            com_selo="",
            com_vinculo="",
            linha="",
        )

    def test_temp_dir_removed_after_full_stream_consumption(self):
        import os

        from core.services.line_inventory_export_service import (
            _stream_and_cleanup,
            generate_line_inventory_export,
        )

        _make_line("+5511920001001")
        export = generate_line_inventory_export(formato="csv", filters=self._filters())
        self.assertTrue(os.path.isdir(export.temp_dir))

        content = b"".join(_stream_and_cleanup(export.path, export.temp_dir))
        self.assertIn(b"+5511920001001", content)
        self.assertFalse(os.path.exists(export.temp_dir))

    def test_temp_dir_removed_on_early_close_simulating_client_disconnect(self):
        import os

        from core.services.line_inventory_export_service import (
            _stream_and_cleanup,
            generate_line_inventory_export,
        )

        _make_line("+5511920001002")
        export = generate_line_inventory_export(formato="csv", filters=self._filters())
        stream = _stream_and_cleanup(export.path, export.temp_dir)
        next(stream)
        stream.close()
        self.assertFalse(os.path.exists(export.temp_dir))

    def test_temp_dir_removed_before_first_chunk_consumed_on_close(self):
        """Fechamento ANTES de qualquer iteracao (cliente desconecta antes
        do primeiro byte). streaming_content nunca e tocado. Diretorio
        temporario localizado via mock em tempfile.mkdtemp, sem depender de
        atributo privado da resposta. Nenhuma limpeza manual antes da
        assertion final."""
        import os
        from unittest import mock

        from core.services import line_inventory_export_service

        _make_line("+5511920001004")

        captured = {}
        original_mkdtemp = line_inventory_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        with mock.patch.object(
            line_inventory_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
        ):
            response = line_inventory_export_service.build_line_inventory_export_response(
                formato="csv", filters=self._filters()
            )

        self.assertIn("temp_dir", captured)
        self.assertTrue(os.path.isdir(captured["temp_dir"]))

        response.close()

        self.assertFalse(os.path.exists(captured["temp_dir"]))

    def test_temp_dir_removed_when_generation_fails(self):
        import os
        from unittest import mock

        from core.services import line_inventory_export_service

        _make_line("+5511920001003")
        captured = {}
        original_mkdtemp = line_inventory_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        with mock.patch.object(
            line_inventory_export_service, "_write_csv_chunk", side_effect=RuntimeError("boom")
        ):
            with mock.patch.object(
                line_inventory_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
            ):
                with self.assertRaises(RuntimeError):
                    line_inventory_export_service.generate_line_inventory_export(
                        formato="csv", filters=self._filters()
                    )

        self.assertIn("temp_dir", captured)
        self.assertFalse(os.path.exists(captured["temp_dir"]))

    def test_temp_dir_removed_and_xlsx_workbook_closed_when_generation_fails(self):
        """Repropositado no REPORTS_SENIOR_REVIEW achado 2: ate entao,
        `_write_xlsx_chunk` deste exportador nao tinha try/except algum —
        uma falha no meio da escrita XLSX write-only nunca fechava o
        workbook abandonado, nem removia `temp_dir` (o `except` externo nao
        alcancava as partes xlsx ja escritas, so declaradas DENTRO do try).
        Mesmo padrao ja comprovado para os outros cinco relatorios."""
        import os
        from unittest import mock

        from core.services import line_inventory_export_service

        _make_line("+5511920001005")
        captured = {}
        original_mkdtemp = line_inventory_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        def _boom(worksheet, row):
            raise RuntimeError("boom")

        with mock.patch.object(
            line_inventory_export_service, "_row_to_xlsx_cells", side_effect=_boom
        ):
            with mock.patch.object(
                line_inventory_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
            ):
                with self.assertRaises(RuntimeError):
                    line_inventory_export_service.generate_line_inventory_export(
                        formato="xlsx", filters=self._filters()
                    )

        self.assertIn("temp_dir", captured)
        self.assertFalse(os.path.exists(captured["temp_dir"]))

    def test_no_leaked_openpyxl_internal_temp_file_when_generation_fails_immediately(self):
        """REPORTS_SENIOR_REVIEW (.git/REPORTS_SENIOR_REVIEW.md) achado 2:
        alem de nao fechar o workbook abandonado (teste acima), o arquivo
        temporario INTERNO do openpyxl (`sheet._writer.out`, fora de
        `temp_dir`, registrado em `ALL_TEMP_FILES`) tambem vazava — XML de
        927 bytes para workbook vazio abandonado, na revisao senior."""
        from unittest import mock

        from core.services import line_inventory_export_service
        from openpyxl.worksheet._writer import ALL_TEMP_FILES

        _make_line("+5511920001006")

        def _boom(worksheet, row):
            raise RuntimeError("boom")

        baseline = set(ALL_TEMP_FILES)
        with mock.patch.object(
            line_inventory_export_service, "_row_to_xlsx_cells", side_effect=_boom
        ):
            with self.assertRaises(RuntimeError):
                line_inventory_export_service.generate_line_inventory_export(
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
        cabecalho vazio)."""
        from unittest import mock

        from core.services import line_inventory_export_service
        from openpyxl.worksheet._writer import ALL_TEMP_FILES

        _make_line("+5511920001007")
        _make_line("+5511920001008")

        real_row_to_xlsx_cells = line_inventory_export_service._row_to_xlsx_cells
        calls = {"count": 0}

        def _fail_on_second_row(worksheet, row):
            calls["count"] += 1
            if calls["count"] >= 2:
                raise RuntimeError("boom")
            return real_row_to_xlsx_cells(worksheet, row)

        baseline = set(ALL_TEMP_FILES)
        with mock.patch.object(
            line_inventory_export_service, "_row_to_xlsx_cells", side_effect=_fail_on_second_row
        ):
            with self.assertRaises(RuntimeError):
                line_inventory_export_service.generate_line_inventory_export(
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
        `generate_line_inventory_export`, o ZipFile de destino ficava
        aberto (preso pelo traceback) e `temp_dir` sobrevivia no Windows —
        corrigido junto com o achado 2 (mesmo mecanismo de limpeza)."""
        import os
        import zipfile
        from unittest import mock

        from core.services import line_inventory_export_service
        from openpyxl.worksheet._writer import ALL_TEMP_FILES

        _make_line("+5511920001009")

        def _fail_on_archive_write(self_zip, filename, arcname=None, **kwargs):
            raise RuntimeError("boom-disk-full-during-finalization")

        baseline = set(ALL_TEMP_FILES)
        captured = {}
        original_mkdtemp = line_inventory_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        with mock.patch.object(zipfile.ZipFile, "write", new=_fail_on_archive_write):
            with mock.patch.object(
                line_inventory_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
            ):
                with self.assertRaises(RuntimeError) as ctx:
                    line_inventory_export_service.generate_line_inventory_export(
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
        import os
        import zipfile
        from unittest import mock

        from core.services import line_inventory_export_service
        from openpyxl.worksheet._writer import ALL_TEMP_FILES

        _make_line("+5511920001010")

        def _raise_deep_oserror(archive_ref):
            raise OSError("disk full (simulated, chained)")

        def _fail_with_chained_exception(self_zip, filename, arcname=None, **kwargs):
            try:
                _raise_deep_oserror(self_zip)
            except OSError as cause:
                raise RuntimeError("boom-chained-during-finalization") from cause

        baseline = set(ALL_TEMP_FILES)
        captured = {}
        original_mkdtemp = line_inventory_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        exc_holder = {}
        with mock.patch.object(zipfile.ZipFile, "write", new=_fail_with_chained_exception):
            with mock.patch.object(
                line_inventory_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
            ):
                try:
                    line_inventory_export_service.generate_line_inventory_export(
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


class LineInventoryExportSplitBoundaryTests(TestCase):
    """Fronteira de divisao em partes/ZIP, boundary-1/boundary/boundary+1
    em ambos os formatos. Interface tecnica explicita e pequena para
    reduzir o limiar em teste: o parametro `split_threshold` de
    core.services.line_inventory_export_service.generate_line_inventory_export,
    chamado diretamente aqui (nao via HTTP). A rota reports_export nunca
    passa esse parametro e usa sempre EXPORT_SPLIT_THRESHOLD (100.000) —
    producao permanece intocada por este teste."""

    def _filters(self):
        return dict(
            data_inicial=PERIOD_START_DATE,
            data_final=PERIOD_END_DATE,
            incluir_excluidos=False,
            status_linha="",
            operadora="",
            origem="",
            canal="",
            com_selo="",
            com_vinculo="",
            linha="",
        )

    def _make_lines(self, count, prefix):
        for index in range(count):
            _make_line(f"+55119{prefix}{index:06d}")

    def _generate(self, formato, threshold):
        from core.services.line_inventory_export_service import generate_line_inventory_export

        return generate_line_inventory_export(
            formato=formato, filters=self._filters(), split_threshold=threshold
        )

    def _read_csv_data_row_counts(self, path):
        with open(path, encoding="utf-8-sig") as handle:
            rows = list(csv.reader(handle, delimiter=";"))
        return rows[0], len(rows) - 1

    def _read_xlsx_data_row_counts(self, path):
        workbook = openpyxl.load_workbook(path)
        sheet = workbook["Inventário de linhas"]
        rows = list(sheet.iter_rows(values_only=True))
        return list(rows[0]), len(rows) - 1

    def test_csv_below_threshold_is_single_file(self):
        self._make_lines(2, "1")
        export = self._generate("csv", 3)
        try:
            self.assertFalse(export.filename.endswith(".zip"))
            _, count = self._read_csv_data_row_counts(export.path)
            self.assertEqual(count, 2)
        finally:
            import shutil

            shutil.rmtree(export.temp_dir, ignore_errors=True)

    def test_csv_at_threshold_is_single_file(self):
        self._make_lines(3, "2")
        export = self._generate("csv", 3)
        try:
            self.assertFalse(export.filename.endswith(".zip"))
            _, count = self._read_csv_data_row_counts(export.path)
            self.assertEqual(count, 3)
        finally:
            import shutil

            shutil.rmtree(export.temp_dir, ignore_errors=True)

    def test_csv_above_threshold_splits_into_zip_without_loss_or_duplication(self):
        import shutil
        import zipfile

        from core.services.line_inventory_export_service import COLUMNS

        self._make_lines(4, "3")
        export = self._generate("csv", 3)
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
        self._make_lines(2, "4")
        export = self._generate("xlsx", 3)
        try:
            self.assertFalse(export.filename.endswith(".zip"))
            _, count = self._read_xlsx_data_row_counts(export.path)
            self.assertEqual(count, 2)
        finally:
            import shutil

            shutil.rmtree(export.temp_dir, ignore_errors=True)

    def test_xlsx_at_threshold_is_single_file(self):
        self._make_lines(3, "5")
        export = self._generate("xlsx", 3)
        try:
            self.assertFalse(export.filename.endswith(".zip"))
            _, count = self._read_xlsx_data_row_counts(export.path)
            self.assertEqual(count, 3)
        finally:
            import shutil

            shutil.rmtree(export.temp_dir, ignore_errors=True)

    def test_xlsx_above_threshold_splits_into_zip_without_loss_or_duplication(self):
        import shutil
        import zipfile

        from core.services.line_inventory_export_service import COLUMNS

        self._make_lines(4, "6")
        export = self._generate("xlsx", 3)
        try:
            self.assertTrue(export.filename.endswith(".zip"))
            with zipfile.ZipFile(export.path) as archive:
                names = sorted(archive.namelist())
                self.assertEqual(len(names), 2)
                counts = []
                for name in names:
                    content = archive.read(name)
                    workbook = openpyxl.load_workbook(io.BytesIO(content))
                    sheet = workbook["Inventário de linhas"]
                    rows = list(sheet.iter_rows(values_only=True))
                    self.assertEqual(list(rows[0]), COLUMNS)
                    counts.append(len(rows) - 1)
                self.assertEqual(sorted(counts), [1, 3])
                self.assertEqual(sum(counts), 4)
        finally:
            shutil.rmtree(export.temp_dir, ignore_errors=True)


class LineInventoryExportNoSeparateCountTests(TestCase):
    """Verificacao estrutural (nao so comportamental): o exportador do
    Inventario usa UMA UNICA consulta para dimensionar partes/ZIP — nao ha
    count() previo separado (mesmo raciocinio da correcao de risco de
    REL-08-E: duas consultas independentes podem divergir por mudanca de
    dados entre elas). Nenhuma funcao count_line_inventory_report_rows foi
    criada no servico de consulta, por decisao deliberada; este teste
    confirma o efeito real: nenhum SELECT COUNT(*) isolado contra
    telecom_phoneline ocorre durante a exportacao."""

    def test_export_runs_no_separate_count_query(self):
        from core.services.line_inventory_export_service import generate_line_inventory_export

        _make_line("+5511920002001")
        filters = dict(
            data_inicial=PERIOD_START_DATE,
            data_final=PERIOD_END_DATE,
            incluir_excluidos=False,
            status_linha="",
            operadora="",
            origem="",
            canal="",
            com_selo="",
            com_vinculo="",
            linha="",
        )
        with CaptureQueriesContext(connection) as captured:
            export = generate_line_inventory_export(formato="csv", filters=filters)
        try:
            count_queries = [
                q["sql"]
                for q in captured.captured_queries
                if "telecom_phoneline" in q["sql"] and "COUNT(" in q["sql"].upper()
            ]
            self.assertEqual(count_queries, [])
        finally:
            import shutil

            shutil.rmtree(export.temp_dir, ignore_errors=True)


class LineInventoryExportRealVolumeTests(TestCase):
    """Ensaio de volume REAL na fronteira de producao (100.000/100.001
    linhas), exigido antes de liberar REL-09-E — metricas de Selos WhatsApp
    NAO comprovam o custo deste relatorio (Prefetch de vinculo atual,
    ausente no motor de Selos).

    Fixture UNICA de 100.001 PhoneLine (bulk_create; sem full_clean/sinais
    — populamento de volume, nao fluxo de negocio), criada uma vez para
    toda a classe (setUpTestData). `created_at` e auto_now_add: como
    bulk_create atribui o mesmo instante de criacao a todas as linhas,
    dois UPDATE em lote (nao 100.001 updates individuais) ajustam
    `created_at` das primeiras 100.000 para um instante dentro do periodo
    de teste e da ultima linha para um instante 1 dia depois — dois
    periodos de filtro sobre essa MESMA fixture selecionam exatamente
    100.000 ou 100.001 linhas, evitando recriar 10^5 registros por teste
    (mesmo padrao de duas janelas usado por WhatsAppSealExportRealVolumeTests).

    Vinculos representativos (nao Selos, que nao tem esse conceito): ~1%
    das linha (1.000 de 100.001, uma a cada 100) recebem uma LineAllocation
    ativa via bulk_create (Employee tambem via bulk_create) — exercita o
    custo real do Prefetch(..., to_attr='active_allocations') sobre o
    volume de producao, nao apenas linhas sem vinculo (mais baratas de
    prefetchar por retornarem lista vazia).

    Tempo e pico de memoria (tracemalloc) sao medidos em bloco proprio,
    iniciado somente APOS a fixture ja estar criada e confirmada — mede o
    processo de exportacao isoladamente, nao a criacao dos dados de teste.
    Total exportado e conferido lendo o arquivo/ZIP real gerado (nao uma
    contagem SQL previa: o exportador do Inventario deliberadamente nao
    tem count() separado, ver LineInventoryExportNoSeparateCountTests).
    Roda em banco de teste isolado (sqlite, "pytest" in sys.modules); nao
    acessa PRD. Deliberadamente lento (10^5 linhas reais); nao e um teste
    unitario comum e nao deve ser lido como prova de comportamento de
    logica (essa prova esta em LineInventoryExportSplitBoundaryTests)."""

    BASE_COUNT = 100_000
    LINK_STEP = 100  # ~1% das linhas com vinculo ativo representativo

    @classmethod
    def setUpTestData(cls):
        sims = [
            SIMcard(iccid=f"89{i:020d}", carrier="TIM", status=SIMcard.Status.ACTIVE)
            for i in range(cls.BASE_COUNT + 1)
        ]
        SIMcard.objects.bulk_create(sims, batch_size=5000)
        sim_ids = list(
            SIMcard.objects.order_by("pk").values_list("pk", flat=True)[: cls.BASE_COUNT + 1]
        )

        lines = [
            PhoneLine(
                phone_number=f"+55119{index:08d}",
                sim_card_id=sim_ids[index],
                status=PhoneLine.Status.AVAILABLE,
                origem=PhoneLine.Origem.BLIP,
                canal=PhoneLine.Canal.WEB,
            )
            for index in range(cls.BASE_COUNT)
        ]
        lines.append(
            PhoneLine(
                phone_number="+551199999999",
                sim_card_id=sim_ids[cls.BASE_COUNT],
                status=PhoneLine.Status.AVAILABLE,
                origem=PhoneLine.Origem.BLIP,
                canal=PhoneLine.Canal.WEB,
            )
        )
        PhoneLine.objects.bulk_create(lines, batch_size=5000)

        line_ids = list(
            PhoneLine.objects.order_by("pk").values_list("pk", flat=True)[: cls.BASE_COUNT + 1]
        )

        base_moment = _local_midnight(date(2026, 9, 10))
        last_moment = _local_midnight(date(2026, 9, 24))
        last_line_id = line_ids[cls.BASE_COUNT]
        # Evita clausula IN com 100.000 valores (limite de variaveis do
        # SQLite): exclui apenas a UNICA linha que precisa de outro
        # instante, em vez de listar as 100.000 restantes.
        PhoneLine.all_objects.exclude(pk=last_line_id).update(created_at=base_moment)
        PhoneLine.all_objects.filter(pk=last_line_id).update(created_at=last_moment)

        linked_line_ids = line_ids[:: cls.LINK_STEP]
        employees = [
            Employee(
                full_name=f"Volume Inventario {i}",
                corporate_email=f"vol.inv.{i}@test.com",
                employee_id=f"VOLINV-{i}",
                teams="Joinville",
                status=Employee.Status.ACTIVE,
            )
            for i in range(len(linked_line_ids))
        ]
        Employee.objects.bulk_create(employees, batch_size=2000)
        employee_ids = list(
            Employee.all_objects.filter(employee_id__startswith="VOLINV-")
            .order_by("pk")
            .values_list("pk", flat=True)[: len(linked_line_ids)]
        )

        allocations = [
            LineAllocation(
                employee_id=employee_ids[i],
                phone_line_id=linked_line_ids[i],
                is_active=True,
            )
            for i in range(len(linked_line_ids))
        ]
        LineAllocation.objects.bulk_create(allocations, batch_size=2000)

    def _filters(self, data_final):
        return dict(
            data_inicial=date(2026, 9, 1),
            data_final=data_final,
            incluir_excluidos=False,
            status_linha="",
            operadora="",
            origem="",
            canal="",
            com_selo="",
            com_vinculo="",
            linha="",
        )

    def _exported_data_row_count_csv(self, export):
        import zipfile

        if not export.filename.endswith(".zip"):
            with open(export.path, encoding="utf-8-sig") as handle:
                rows = list(csv.reader(handle, delimiter=";"))
            return len(rows) - 1
        total = 0
        with zipfile.ZipFile(export.path) as archive:
            for name in archive.namelist():
                text = archive.read(name).decode("utf-8-sig")
                rows = list(csv.reader(io.StringIO(text), delimiter=";"))
                total += len(rows) - 1
        return total

    def _exported_data_row_count_xlsx(self, export):
        import zipfile

        if not export.filename.endswith(".zip"):
            workbook = openpyxl.load_workbook(export.path)
            sheet = workbook["Inventário de linhas"]
            return len(list(sheet.iter_rows(values_only=True))) - 1
        total = 0
        with zipfile.ZipFile(export.path) as archive:
            for name in archive.namelist():
                content = archive.read(name)
                workbook = openpyxl.load_workbook(io.BytesIO(content))
                sheet = workbook["Inventário de linhas"]
                total += len(list(sheet.iter_rows(values_only=True))) - 1
        return total

    def _measure(self, formato, data_final, expected_total):
        import sys
        import time
        import tracemalloc
        import zipfile
        from pathlib import Path

        from core.services.line_inventory_export_service import generate_line_inventory_export

        filters = self._filters(data_final)

        tracemalloc.start()
        start = time.perf_counter()
        export = generate_line_inventory_export(formato=formato, filters=filters)
        elapsed = time.perf_counter() - start
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        try:
            counter = (
                self._exported_data_row_count_csv
                if formato == "csv"
                else self._exported_data_row_count_xlsx
            )
            written_total = counter(export)
            self.assertEqual(written_total, expected_total)

            size_bytes = Path(export.path).stat().st_size
            is_zip = export.filename.endswith(".zip")
            part_count = 1
            if is_zip:
                with zipfile.ZipFile(export.path) as archive:
                    part_count = len(archive.namelist())
            sys.stderr.write(
                "\n[VOLUME REAL - INVENTARIO] formato={} linhas={} tempo={:.2f}s "
                "tamanho={:.2f}MiB zip={} partes={} "
                "pico_memoria_exportador={:.2f}MiB vinculos_representativos={}\n".format(
                    formato,
                    expected_total,
                    elapsed,
                    size_bytes / 1024 / 1024,
                    is_zip,
                    part_count,
                    peak_bytes / 1024 / 1024,
                    len(range(0, self.BASE_COUNT + 1, self.LINK_STEP)),
                )
            )
            return elapsed, size_bytes, is_zip, part_count
        finally:
            import shutil

            shutil.rmtree(export.temp_dir, ignore_errors=True)

    def test_csv_100000_rows_single_file_no_zip(self):
        _, _, is_zip, part_count = self._measure("csv", date(2026, 9, 23), 100_000)
        self.assertFalse(is_zip)
        self.assertEqual(part_count, 1)

    def test_csv_100001_rows_splits_into_zip_two_parts(self):
        _, _, is_zip, part_count = self._measure("csv", date(2026, 9, 24), 100_001)
        self.assertTrue(is_zip)
        self.assertEqual(part_count, 2)

    def test_xlsx_100000_rows_single_file_no_zip(self):
        _, _, is_zip, part_count = self._measure("xlsx", date(2026, 9, 23), 100_000)
        self.assertFalse(is_zip)
        self.assertEqual(part_count, 1)

    def test_xlsx_100001_rows_splits_into_zip_two_parts(self):
        _, _, is_zip, part_count = self._measure("xlsx", date(2026, 9, 24), 100_001)
        self.assertTrue(is_zip)
        self.assertEqual(part_count, 2)
