"""Testes RED da task REL-10-T (fonte da verdade:
docs/superpowers/specs/2026-09-22-reports-hub-design.md, secoes REL-07 e
REL-10-C).

Cobrem o relatorio allocations: consulta na tela (endpoint existente
GET /relatorios/, motor ainda ausente) e exportacoes CSV/XLSX (endpoint ja
registrado desde REL-08-E, reports_export, cujo dispatch hoje so aceita
whatsapp_seal/line_inventory). Nao testa a aba generica (rota, menu,
autorizacao base, dropdown com 6 opcoes) nem os motores de Selos/Inventario,
ja cobertos em config/tests/test_reports_hub.py,
config/tests/test_whatsapp_seal_report.py e
config/tests/test_line_inventory_report.py — reaproveitados, nao duplicados.
Em particular, config/tests/test_line_inventory_report.py::
OtherReportStillUnavailableTests::test_allocations_report_still_returns_400_engine_unavailable
ja comprova, do lado da CONSULTA, que relatorio=allocations retorna 400 com
a mensagem de indisponibilidade — nao reproduzido aqui; este arquivo cobre
apenas o angulo complementar ainda nao coberto (acesso direto ao DOWNLOAD)
em AllocationsReportStillUnavailableTests.

Nenhum modulo de aplicacao futuro (formulario/servico proprios de
Alocacoes: AllocationsReportQueryForm, allocations_report_service,
allocations_export_service) e importado no topo deste arquivo: eles ainda
nao existem, conforme REL-10-C ("Implementation Plan"). reverse(
EXPORT_URL_NAME) pode ser chamado com seguranca (rota ja registrada desde
REL-08-E).

Estado atual do motor (2026-09-28, antes de REL-10-Q): "allocations" nao
esta em REPORT_SPECIFIC_PARAM_NAMES, REPORT_FORM_CLASSES,
REPORT_QUERY_ENGINES nem REPORT_EXPORT_ENGINES (config/views.py). Isso
produz DOIS tipos de resultado real e distinto, ambos verificados
explicitamente nas classes abaixo (nunca presumidos):

1. Validacao comum (REL-07: datas obrigatorias/invalidas/invertidas,
   incluir_excluidos, page, parametro repetido, parametro totalmente
   desconhecido) roda ANTES do despacho por relatorio (_validate_report_query_params
   monta o form ANTES de checar `available_relatorios`) — esses testes sao
   GREEN real hoje, nao RED, porque o contrato comum ja se aplica
   independente do motor especifico existir.
2. Qualquer requisito especifico do catalogo aprovado em REL-10-C (colunas,
   granularidade por evento, periodo por allocated_at, filtros
   situacao_alocacao/funcionario, totalizadores, ordenacao, paginacao real,
   exportacao) depende do motor ainda inexistente: a consulta cai sempre em
   "relatorio ainda nao disponivel" (400) antes de chegar a qualquer logica
   especifica — RED real e esperado, documentado teste a teste, nunca
   inventado. `situacao_alocacao`/`funcionario` caem hoje no bucket de
   "parametro desconhecido" (nem chegam a validacao de enum/formulario),
   igual ao gap ja documentado para os parametros do Inventario antes de
   REL-09-Q (config/tests/test_line_inventory_report.py,
   LineInventoryFilterParameterValidationTests) — mesmo padrao de teste
   reaproveitado aqui via _assert_not_rejected_as_unknown_parameter.

Volume/particionamento em ZIP/limpeza de temporarios (REL-08-C/REL-09-C,
herdado integralmente por REL-10-C) dependem de um exportador que ainda nao
existe (core/services/allocations_export_service.py, proposto para
REL-10-E) — nao ha interface de configuracao de limiar para reduzir em
teste sem inventar uma API nova, o que esta explicitamente fora do escopo
desta task. Cobertura pendente, registrada aqui e na fonte da verdade;
nenhuma tentativa de simular conclusao.
"""

import csv
import io
import itertools
import os
import shutil
import zipfile
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

EXPECTED_COLUMN_HEADERS = [
    "Linha",
    "Usuário vinculado",
    "Carteira",
    "Data de alocação",
    "Data de liberação",
    "Situação",
    "Registro da linha",
    "Funcionário excluído",
]

_iccid_counter = itertools.count(1)
_employee_counter = itertools.count(1)


def _create_user(email, role, **extra):
    return SystemUser.objects.create_user(email=email, password=PASSWORD, role=role, **extra)


def _local_midnight(d):
    return timezone.make_aware(datetime.combine(d, time.min))


def _local_last_instant(d):
    return timezone.make_aware(datetime.combine(d, time(23, 59, 59, 999999)))


def _mid_period_moment():
    return _local_midnight(date(2026, 9, 10))


def _set_allocated_at(allocation, moment):
    """LineAllocation.allocated_at e auto_now_add: create()/save() ignoram
    silenciosamente um valor explicito. Ajuste valido so via update() no
    queryset (bypassa o auto_now_add), seguido de refresh_from_db() e
    confirmacao explicita do valor persistido — mesmo padrao ja usado por
    _set_created_at em config/tests/test_line_inventory_report.py."""
    LineAllocation.objects.filter(pk=allocation.pk).update(allocated_at=moment)
    allocation.refresh_from_db()
    assert allocation.allocated_at == moment, (
        f"allocated_at nao persistiu o valor esperado: {allocation.allocated_at!r} != {moment!r}"
    )
    return allocation


def _make_line(phone_number, *, delete_line=False, delete_sim=False, cascade_delete_sim=False, released_by=None):
    """Cria SIMcard+PhoneLine disponiveis via ORM direto. cascade_delete_sim
    usa SIMcard.delete() (exclui a linha em cascata, fluxo real);
    delete_line usa PhoneLine.delete() diretamente (libera automaticamente
    qualquer alocacao ativa, efeito real do metodo, nao simulado);
    delete_sim=True sozinho simula inconsistencia legada via update() direto
    (sem cascata), mesmo padrao ja usado nos relatorios de Selos/Inventario."""
    sim = SIMcard.objects.create(
        iccid=f"8900000000000{next(_iccid_counter):05d}", carrier="TIM"
    )
    line = PhoneLine.objects.create(
        phone_number=phone_number,
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
    )
    if cascade_delete_sim:
        sim.delete(released_by=released_by)
        line.refresh_from_db()
    else:
        if delete_line:
            line.delete(released_by=released_by)
        if delete_sim:
            SIMcard.all_objects.filter(pk=sim.pk).update(is_deleted=True)
    return line, sim


def _make_employee(label=None, *, deleted=False):
    suffix = label or next(_employee_counter)
    employee = Employee.objects.create(
        full_name=f"Alocacao Teste {suffix}",
        corporate_email=f"corp.aloc{suffix}@test.com",
        employee_id=f"ALOC-{suffix}",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )
    if deleted:
        employee.delete()
        employee.refresh_from_db()
    return employee


def _allocate(line, admin, employee=None, allocated_at=None):
    employee = employee or _make_employee()
    allocation = AllocationService.allocate_line(employee=employee, phone_line=line, allocated_by=admin)
    if allocated_at is not None:
        _set_allocated_at(allocation, allocated_at)
    return allocation


def _release(allocation, admin):
    return AllocationService.release_line(allocation, released_by=admin)


def _force_second_active_allocation(line, admin, employee=None):
    """Cria uma SEGUNDA LineAllocation.is_active=True para a mesma linha via
    ORM direto, contornando deliberadamente AllocationService (que rejeita
    corretamente esse estado). Simula dado legado real (import/script),
    nunca um caminho suportado pela aplicacao — mesmo padrao ja usado em
    config/tests/test_line_inventory_report.py."""
    employee = employee or _make_employee()
    return LineAllocation.objects.create(
        employee=employee,
        phone_line=line,
        allocated_by=admin,
        is_active=True,
    )


def _report_url(pairs):
    return f"{reverse(REPORTS_URL_NAME)}?{urlencode(pairs)}"


def _base_pairs(data_inicial=PERIOD_START, data_final=PERIOD_END, **extra):
    pairs = [
        ("relatorio", "allocations"),
        ("data_inicial", data_inicial),
        ("data_final", data_final),
    ]
    pairs.extend(extra.items())
    return pairs


def _export_url(formato, pairs):
    return f"{reverse(EXPORT_URL_NAME, kwargs={'formato': formato})}?{urlencode(pairs)}"


class AllocationsReportInitialLoadTests(TestCase):
    """Relatorio selecionado sem datas: sem motor, sem erro prematuro
    (ReportsHomeView.get so valida quando data_inicial/data_final estao
    presentes). Abertura totalmente sem parametros ja e coberta
    genericamente por ReportsHomeContentTests em
    config/tests/test_reports_hub.py."""

    def setUp(self):
        self.admin = _create_user("admin.aloc.initial@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_report_selected_without_dates_does_not_run_engine_or_error(self):
        response = self.client.get(_report_url([("relatorio", "allocations")]))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode().lower()
        self.assertNotIn("obrigat", content)
        self.assertNotIn("erro", content)


class AllocationsReportSharedValidationAppliesTests(TestCase):
    """Contrato comum (REL-07) ja validado pelo mesmo form/endpoint
    independente do relatorio selecionado, ANTES do despacho por relatorio
    (_validate_report_query_params so verifica `available_relatorios` depois
    de validar o form). GREEN real hoje — nao depende do motor de Alocacoes
    existir; reaproveita a mesma garantia ja comprovada para
    whatsapp_seal/line_inventory, aqui travada tambem para allocations."""

    def setUp(self):
        self.admin = _create_user("admin.aloc.sharedval@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_missing_data_inicial_rejected(self):
        response = self.client.get(
            _report_url([("relatorio", "allocations"), ("data_final", PERIOD_END)])
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_data_final_rejected(self):
        response = self.client.get(
            _report_url([("relatorio", "allocations"), ("data_inicial", PERIOD_START)])
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_date_format_rejected(self):
        response = self.client.get(
            _report_url([("relatorio", "allocations"), ("data_inicial", "31/09/2026"), ("data_final", PERIOD_END)])
        )
        self.assertEqual(response.status_code, 400)

    def test_inverted_dates_rejected(self):
        response = self.client.get(
            _report_url([("relatorio", "allocations"), ("data_inicial", PERIOD_END), ("data_final", PERIOD_START)])
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
            f"{url}?relatorio=allocations&data_inicial={PERIOD_START}&data_inicial=2026-09-02&data_final={PERIOD_END}"
        )
        self.assertEqual(response.status_code, 400)

    def test_unknown_generic_query_parameter_rejected(self):
        response = self.client.get(_report_url(_base_pairs(campo_totalmente_inexistente="x")))
        self.assertEqual(response.status_code, 400)

    def test_search_term_longer_than_20_chars_rejected(self):
        response = self.client.get(_report_url(_base_pairs(linha="1" * 21)))
        self.assertEqual(response.status_code, 400)


class AllocationsDateBoundaryOverflowTests(TestCase):
    """REPORTS_SENIOR_REVIEW (.git/REPORTS_SENIOR_REVIEW.md) achado 3:
    `_period_bounds` (core/services/allocations_report_service.py) soma 1
    dia a `data_final` para obter o limite exclusivo do periodo (fuso
    local) — com data_final=date.max isso e `date.max + timedelta(days=1)`,
    que estoura (`OverflowError: date value out of range`) antes de
    qualquer consulta ao banco, nunca capturado pela view (500 real). O
    form agora rejeita esse valor como erro de campo, tanto na consulta
    quanto na exportacao (mesmo AllocationsReportQueryForm valida os dois
    endpoints, ver _validate_report_query_params). Nenhum limite arbitrario
    de duracao de periodo: apenas a fronteira realmente representavel pelo
    calculo do limite exclusivo (date.max - 1 dia)."""

    def setUp(self):
        self.admin = _create_user("admin.aloc.dateboundary@test.com", SystemUser.Role.ADMIN)
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


class AllocationsReportStillUnavailableTests(TestCase):
    """Repropositada em REL-10-E (mesma obsolescencia ja prevista em
    REL-10-T/Q para este angulo): ate REL-10-Q, `allocations` estava em
    REPORT_QUERY_ENGINES mas nao em REPORT_EXPORT_ENGINES, entao o download
    direto com filtros comuns validos retornava 400 pelo ramo 'consulta
    existe, exportacao ainda nao'. REL-10-E adiciona `allocations` a
    REPORT_EXPORT_ENGINES e implementa core/services/allocations_export_service
    — a alegacao de indisponibilidade da exportacao deixou de ser verdadeira,
    mesma situacao ja resolvida para whatsapp_seal/line_inventory em suas
    respectivas tasks E. O requisito util (download direto do relatorio,
    filtros comuns validos) e preservado, invertendo a asserção para a
    disponibilidade agora exigida pelo contrato (REL-07/REL-10-C): 200, CSV
    real, anexo para download. O lado da CONSULTA continua coberto por
    config/tests/test_line_inventory_report.py::OtherReportStillUnavailableTests::
    test_pendencies_report_still_returns_400_engine_unavailable (repropositado
    em REL-10-Q para um relatorio genuinamente ainda sem motor)."""

    def setUp(self):
        self.admin = _create_user("admin.aloc.unavailable@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_export_now_returns_200_attachment_with_valid_common_params(self):
        """Antes de REL-10-E (RED por design, documentado em REL-10-T/Q):
        400 'A exportação deste relatório ainda não está disponível nesta
        etapa.'. Agora que o motor de exportacao existe, o mesmo acesso
        direto com filtros comuns validos deve retornar 200, com o arquivo
        como anexo — nao mais a mensagem de indisponibilidade."""
        line, _ = _make_line("+5511920950001")
        _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))

        response = self.client.get(_export_url("csv", _base_pairs()))
        self.assertEqual(response.status_code, 200)
        self.assertIn("csv", response.headers.get("Content-Type", "").lower())
        self.assertIn("attachment", response.headers.get("Content-Disposition", ""))
        self.assertNotContains(
            response,
            "A exportação deste relatório ainda não está disponível nesta etapa.",
            status_code=200,
        )


class AllocationsFilterParameterValidationTests(TestCase):
    """Repropositada em REL-10-Q (mesma correcao ja aplicada ao Inventario
    em REL-09-Q, LineInventoryFilterParameterValidationTests): antes desta
    task, situacao_alocacao/funcionario nao estavam em
    REPORT_SPECIFIC_PARAM_NAMES/REPORT_FORM_CLASSES e QUALQUER valor deles
    (valido ou invalido) era rejeitado pela mensagem generica "Parametro
    desconhecido: <nome>.". Agora que REL-10-Q registra os dois nomes:
    situacao_alocacao (enum fechado Todas/ativa/liberada) tem valor
    invalido rejeitado pela validacao de CAMPO do formulario, nunca mais
    pela mensagem generica de parametro desconhecido; valor valido retorna
    200 com conteudo elegivel real. funcionario e busca livre (sem enum,
    mesmo padrao de 'operadora' em REL-09-C) — sem conceito de 'valor
    invalido' proprio; cobertura correspondente e o controle positivo (200
    com conteudo elegivel) e a rejeicao de parametro escalar repetido
    (REL-07), aplicavel a qualquer campo."""

    def setUp(self):
        self.admin = _create_user("admin.aloc.paramval@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def _assert_not_rejected_as_unknown_parameter(self, response, param_name):
        self.assertEqual(response.status_code, 400)
        content = response.content.decode()
        self.assertNotIn(
            f"Parâmetro desconhecido: {param_name}",
            content,
            f"{param_name} ainda cai no bucket generico de 'parametro "
            "desconhecido' — sinal de que o nome ainda nao esta "
            "reconhecido/validado como campo proprio (gap real: fora do "
            "whitelist e sem form dedicado).",
        )

    def test_situacao_alocacao_invalid_value_not_treated_as_unknown_parameter(self):
        response = self.client.get(_report_url(_base_pairs(situacao_alocacao="invalido")))
        self._assert_not_rejected_as_unknown_parameter(response, "situacao_alocacao")

    def test_situacao_alocacao_invalid_value_not_treated_as_unknown_parameter_on_export(self):
        response = self.client.get(_export_url("csv", _base_pairs(situacao_alocacao="invalido")))
        self._assert_not_rejected_as_unknown_parameter(response, "situacao_alocacao")

    def test_situacao_alocacao_valid_value_control_returns_200_with_eligible_line(self):
        line, _ = _make_line("+5511920910001")
        _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))
        response = self.client.get(_report_url(_base_pairs(situacao_alocacao="ativa")))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "+5511920910001")

    def test_situacao_alocacao_recognized_and_export_now_filters_correctly(self):
        """Repropositado em REL-10-E (obsolescencia prevista em REL-10-Q):
        situacao_alocacao ja era reconhecido desde REL-10-Q, mas a
        EXPORTACAO de Alocacoes ainda estava indisponivel; agora que
        REL-10-E implementa o motor de exportacao, o mesmo parametro deve
        filtrar de fato o arquivo baixado (nao mais 400 de indisponibilidade)."""
        active_line, _ = _make_line("+5511920960001")
        _allocate(active_line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))
        released_line, _ = _make_line("+5511920960002")
        released_allocation = _allocate(
            released_line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10))
        )
        _release(released_allocation, self.admin)

        response = self.client.get(_export_url("csv", _base_pairs(situacao_alocacao="liberada")))
        self.assertEqual(response.status_code, 200)
        content = b"".join(response.streaming_content).decode("utf-8-sig")
        self.assertIn("+5511920960002", content)
        self.assertNotIn("+5511920960001", content)

    def test_funcionario_valid_value_control_returns_200_with_eligible_line(self):
        employee = _make_employee("filter-target")
        line, _ = _make_line("+5511920910002")
        _allocate(line, self.admin, employee=employee, allocated_at=_local_midnight(date(2026, 9, 10)))
        response = self.client.get(_report_url(_base_pairs(funcionario=employee.employee_id)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "+5511920910002")

    def test_funcionario_repeated_scalar_parameter_rejected(self):
        """REL-07 exige rejeicao de parametro escalar repetido para
        qualquer campo, agora tambem para um nome ja whitelisted: 400 pelo
        ramo de 'parametro repetido', nunca mais pelo de 'desconhecido'."""
        url = reverse(REPORTS_URL_NAME)
        response = self.client.get(
            f"{url}?{urlencode(_base_pairs())}&funcionario=Ana&funcionario=Bruno"
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(
            response,
            "Parâmetro repetido não é permitido: funcionario.",
            status_code=400,
        )


class AllocationsGranularityAndHistoryTests(TestCase):
    """Secao 1 do enunciado: uma linha de resultado por LineAllocation,
    historico completo (ativas e liberadas), sem colapso por linha/
    funcionario. Todos RED hoje: motor ausente, consulta sempre 400."""

    def setUp(self):
        self.admin = _create_user("admin.aloc.granularity@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_two_allocations_same_line_produce_two_result_rows(self):
        line, _ = _make_line("+5511920000001")
        first = _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 5)))
        _release(first, self.admin)
        line.status = PhoneLine.Status.AVAILABLE
        line.save(update_fields=["status"])
        _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 22)))

        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        self.assertEqual(content.count("+5511920000001"), 2)

    def test_released_allocation_remains_in_history(self):
        line, _ = _make_line("+5511920000002")
        allocation = _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))
        _release(allocation, self.admin)
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511920000002")

    def test_active_allocation_without_release_remains_visible(self):
        line, _ = _make_line("+5511920000003")
        _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511920000003")

    def test_distinct_records_for_same_employee_not_collapsed(self):
        employee = _make_employee("multi")
        line_one, _ = _make_line("+5511920000004")
        line_two, _ = _make_line("+5511920000005")
        _allocate(line_one, self.admin, employee=employee, allocated_at=_local_midnight(date(2026, 9, 8)))
        _allocate(line_two, self.admin, employee=employee, allocated_at=_local_midnight(date(2026, 9, 9)))

        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        self.assertIn("+5511920000004", content)
        self.assertIn("+5511920000005", content)

    def test_inconsistent_multiple_active_allocations_appear_as_distinct_rows_without_flag(self):
        """Estado so alcancavel via bypass deliberado do servico de dominio
        (_force_second_active_allocation) — diferente do Inventario
        (REL-09-C), aqui NAO exige rotulo de inconsistencia: a granularidade
        ja e o evento, entao cada LineAllocation aparece como esta no
        banco."""
        line, _ = _make_line("+5511920000006")
        _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))
        second = _force_second_active_allocation(line, self.admin)
        # allocated_at e auto_now_add: sem fixar explicitamente, a segunda
        # alocacao forcada recebe o instante real de execucao do teste, que
        # cai fora do periodo fixo de exemplo (01/09-24/09/2026) usado por
        # _base_pairs — precisa do mesmo ajuste de _set_allocated_at usado
        # pelo caminho normal (_allocate) para permanecer dentro do periodo
        # consultado.
        _set_allocated_at(second, _local_midnight(date(2026, 9, 10)))

        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        self.assertEqual(content.count("+5511920000006"), 2)
        self.assertNotIn("inconsistente", content.lower())


class AllocationsPeriodTests(TestCase):
    """Secao 2: periodo por allocated_at ('alocado no periodo'), fronteiras
    inclusivas (inicio local inclusivo ate inicio local do dia posterior ao
    fim, exclusivo, America/Sao_Paulo, REL-07), e o exemplo C de REL-10-C
    (alocada fora do periodo mas liberada dentro NAO entra)."""

    def setUp(self):
        self.admin = _create_user("admin.aloc.period@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_start_boundary_inclusive(self):
        line, _ = _make_line("+5511920100001")
        _allocate(line, self.admin, allocated_at=_local_midnight(PERIOD_START_DATE))
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511920100001")

    def test_instant_before_start_boundary_excluded(self):
        control_line, _ = _make_line("+5511920100098")
        _allocate(control_line, self.admin, allocated_at=_local_midnight(PERIOD_START_DATE))
        excluded_line, _ = _make_line("+5511920100002")
        _allocate(
            excluded_line,
            self.admin,
            allocated_at=_local_midnight(PERIOD_START_DATE) - timedelta(microseconds=1),
        )
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511920100098")
        self.assertNotContains(response, "+5511920100002")

    def test_end_boundary_inclusive_last_local_instant(self):
        line, _ = _make_line("+5511920100003")
        _allocate(line, self.admin, allocated_at=_local_last_instant(PERIOD_END_DATE))
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511920100003")

    def test_instant_at_start_of_day_after_end_excluded(self):
        control_line, _ = _make_line("+5511920100097")
        _allocate(control_line, self.admin, allocated_at=_local_last_instant(PERIOD_END_DATE))
        excluded_line, _ = _make_line("+5511920100004")
        _allocate(
            excluded_line,
            self.admin,
            allocated_at=_local_midnight(PERIOD_END_DATE + timedelta(days=1)),
        )
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511920100097")
        self.assertNotContains(response, "+5511920100004")

    def test_allocated_at_persisted_value_matches_fixture_assumption(self):
        moment = _local_midnight(PERIOD_START_DATE)
        line, _ = _make_line("+5511920100005")
        allocation = _allocate(line, self.admin, allocated_at=moment)
        allocation.refresh_from_db()
        self.assertEqual(allocation.allocated_at, moment)

    def test_allocated_outside_period_never_enters_even_if_released_inside(self):
        """Exemplo C de REL-10-C: alocada fora do periodo (20/08), liberada
        dentro (05/09) — NAO entra com 'alocado no periodo'."""
        line, _ = _make_line("+5511920100006")
        allocation = _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 8, 20)))
        _release(allocation, self.admin)
        LineAllocation.objects.filter(pk=allocation.pk).update(
            released_at=_local_midnight(date(2026, 9, 5))
        )
        response = self.client.get(_report_url(_base_pairs()))
        self.assertNotContains(response, "+5511920100006")

    def test_allocated_inside_period_enters_even_if_released_outside(self):
        line, _ = _make_line("+5511920100007")
        allocation = _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 5)))
        _release(allocation, self.admin)
        LineAllocation.objects.filter(pk=allocation.pk).update(
            released_at=_local_midnight(date(2026, 10, 5))
        )
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511920100007")

    def test_released_at_alone_does_not_substitute_period_reference(self):
        """Controle inverso: released_at DENTRO do periodo, allocated_at
        FORA — reforca que released_at nunca e usado como referencia de
        periodo nesta entrega (decisao do usuario, REL-10-C)."""
        line, _ = _make_line("+5511920100008")
        allocation = _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 7, 1)))
        _release(allocation, self.admin)
        LineAllocation.objects.filter(pk=allocation.pk).update(
            released_at=_local_midnight(date(2026, 9, 10))
        )
        response = self.client.get(_report_url(_base_pairs()))
        self.assertNotContains(response, "+5511920100008")


class AllocationsExclusionTests(TestCase):
    """Secao 3: exclusao logica de linha/SIMcard/funcionario, separadamente.
    Checkbox unico de 'Incluir excluidos' governa as tres entidades
    relacionadas (decisao do usuario, REL-10-C) — LineAllocation em si nunca
    e excluida (nao tem is_deleted)."""

    def setUp(self):
        self.admin = _create_user("admin.aloc.exclusion@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_line_deleted_hidden_by_default_shown_when_included(self):
        control_line, _ = _make_line("+5511920200098")
        _allocate(control_line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))

        excluded_line, _ = _make_line("+5511920200001")
        _allocate(excluded_line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))
        excluded_line.delete(released_by=self.admin)

        default_resp = self.client.get(_report_url(_base_pairs()))
        self.assertContains(default_resp, "+5511920200098")
        self.assertNotContains(default_resp, "+5511920200001")

        included_resp = self.client.get(_report_url(_base_pairs(incluir_excluidos="1")))
        self.assertContains(included_resp, "+5511920200001")
        self.assertContains(included_resp, "Linha excluída")

    def test_simcard_deleted_isolated_hidden_by_default_shown_when_included(self):
        line, sim = _make_line("+5511920200002")
        _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))
        SIMcard.all_objects.filter(pk=sim.pk).update(is_deleted=True)

        default_resp = self.client.get(_report_url(_base_pairs()))
        self.assertNotContains(default_resp, "+5511920200002")

        included_resp = self.client.get(_report_url(_base_pairs(incluir_excluidos="1")))
        self.assertContains(included_resp, "+5511920200002")
        self.assertContains(included_resp, "SIMcard excluído")

    def test_line_and_simcard_deleted_via_cascade(self):
        line, _ = _make_line("+5511920200003")
        _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))
        line.refresh_from_db()
        line.sim_card.delete(released_by=self.admin)

        default_resp = self.client.get(_report_url(_base_pairs()))
        self.assertNotContains(default_resp, "+5511920200003")

        included_resp = self.client.get(_report_url(_base_pairs(incluir_excluidos="1")))
        self.assertContains(included_resp, "+5511920200003")
        self.assertContains(included_resp, "Linha e SIMcard excluídos")

    def test_employee_deleted_hidden_by_default_shown_when_included(self):
        """Decisao do usuario em REL-10-C: diferente do Inventario
        (REL-09-C), aqui o funcionario excluido TAMBEM e ocultado pelo
        checkbox padrao, porque 'usuario vinculado' e coluna central do
        catalogo."""
        control_line, _ = _make_line("+5511920200097")
        control_employee = _make_employee("exclusion-control")
        _allocate(control_line, self.admin, employee=control_employee, allocated_at=_local_midnight(date(2026, 9, 10)))

        line, _ = _make_line("+5511920200004")
        # AllocationService.allocate_line exige employee ATIVO
        # (Employee.objects, manager default, filtra is_deleted=False):
        # aloca primeiro, depois exclui — ordem real de "funcionario
        # excluido depois de ja ter uma alocacao", nao "alocacao criada
        # para funcionario ja excluido" (impossivel pelo caminho normal).
        employee = _make_employee("exclusion-target")
        _allocate(line, self.admin, employee=employee, allocated_at=_local_midnight(date(2026, 9, 10)))
        employee.delete()
        employee.refresh_from_db()

        default_resp = self.client.get(_report_url(_base_pairs()))
        self.assertContains(default_resp, "+5511920200097")
        self.assertNotContains(default_resp, "+5511920200004")

        included_resp = self.client.get(_report_url(_base_pairs(incluir_excluidos="1")))
        self.assertContains(included_resp, "+5511920200004")

    def test_checkbox_included_does_not_restore_any_deleted_flag(self):
        line, sim = _make_line("+5511920200005")
        # Mesmo ajuste de ordem do teste anterior: aloca com funcionario
        # ativo, so entao exclui — AllocationService exige employee ativo.
        employee = _make_employee("no-restore")
        _allocate(line, self.admin, employee=employee, allocated_at=_local_midnight(date(2026, 9, 10)))
        employee.delete()
        employee.refresh_from_db()
        line.delete(released_by=self.admin)

        response = self.client.get(_report_url(_base_pairs(incluir_excluidos="1")))
        self.assertEqual(response.status_code, 200)

        line.refresh_from_db()
        employee.refresh_from_db()
        self.assertTrue(line.is_deleted)
        self.assertTrue(employee.is_deleted)

    def test_not_deleted_line_shows_default_registro_label(self):
        line, _ = _make_line("+5511920200006")
        _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))
        response = self.client.get(_report_url(_base_pairs(linha="200006")))
        self.assertContains(response, "+5511920200006")
        self.assertContains(response, "Não excluído")

    def test_release_alone_is_not_exclusion_and_stays_visible_by_default(self):
        line, _ = _make_line("+5511920200007")
        allocation = _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))
        _release(allocation, self.admin)
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511920200007")

    def test_deleted_line_allocation_is_never_situacao_ativa(self):
        """Invariante do dominio: PhoneLine.delete libera automaticamente a
        alocacao ativa (telecom/models.py) antes de marcar is_deleted=True —
        uma linha excluida nunca deveria aparecer com Situacao = Ativa."""
        line, _ = _make_line("+5511920200008")
        allocation = _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))
        line.refresh_from_db()
        line.delete(released_by=self.admin)
        allocation.refresh_from_db()
        self.assertFalse(allocation.is_active)

        response = self.client.get(_report_url(_base_pairs(incluir_excluidos="1")))
        content = response.content.decode()
        self.assertIn("+5511920200008", content)
        self.assertNotIn("Ativa</td>", content)


class AllocationsColumnsAndTotalsTests(TestCase):
    """Secao 5: oito colunas na ordem aprovada (cabecalho da tabela, nao
    substring solta) e totalizadores diferenciados (total de alocacoes,
    linhas distintas, funcionarios distintos, ativas/liberadas), usando o
    dataset de exemplo de REL-10-C que produz numeros DIFERENTES entre os
    tres primeiros totalizadores (5 != 4 != 3 com excluidos)."""

    def setUp(self):
        self.admin = _create_user("admin.aloc.columns@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_eight_column_headers_present_in_approved_order(self):
        line, _ = _make_line("+5511920300001")
        _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))
        response = self.client.get(_report_url(_base_pairs()))
        self.assertEqual(response.status_code, 200, "motor ausente: resposta nao e a tela com tabela de resultados")
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

    def test_totals_differ_from_each_other_with_excluded_dataset(self):
        """Reproduz o exemplo aprovado em REL-10-C: sem excluidos -> total=3,
        linhas distintas=2, funcionarios distintos=2; com excluidos -> total=5,
        linhas distintas=4, funcionarios distintos=3 (Bruno repetido)."""
        ana = _make_employee("ana")
        bruno = _make_employee("bruno")
        # AllocationService exige employee ATIVO: eva e excluida SO depois
        # de alocada (abaixo), nao na criacao — mesmo ajuste de ordem
        # aplicado nos demais testes de funcionario excluido desta secao.
        eva = _make_employee("eva")

        line_l1, _ = _make_line("+5511920300010")  # A + F (mesma linha)
        line_l2, _ = _make_line("+5511920300011")  # B
        line_l3, _ = _make_line("+5511920300012")  # D (excluida)
        line_l4, _ = _make_line("+5511920300013")  # E (funcionario excluido)

        allocation_a = _allocate(line_l1, self.admin, employee=ana, allocated_at=_local_midnight(date(2026, 9, 5)))
        _release(allocation_a, self.admin)
        line_l1.status = PhoneLine.Status.AVAILABLE
        line_l1.save(update_fields=["status"])
        _allocate(line_l1, self.admin, employee=ana, allocated_at=_local_midnight(date(2026, 9, 22)))  # F, ativa

        allocation_b = _allocate(line_l2, self.admin, employee=bruno, allocated_at=_local_midnight(date(2026, 9, 10)))
        _release(allocation_b, self.admin)

        allocation_d = _allocate(line_l3, self.admin, employee=bruno, allocated_at=_local_midnight(date(2026, 9, 15)))
        line_l3.refresh_from_db()
        line_l3.delete(released_by=self.admin)  # libera automaticamente + exclui

        _allocate(line_l4, self.admin, employee=eva, allocated_at=_local_midnight(date(2026, 9, 18)))  # E, ativa
        eva.delete()
        eva.refresh_from_db()

        default_resp = self.client.get(_report_url(_base_pairs()))
        default_content = default_resp.content.decode()
        for phone in ("+5511920300010", "+5511920300011"):
            self.assertIn(phone, default_content)
        for phone in ("+5511920300012", "+5511920300013"):
            self.assertNotIn(phone, default_content)

        included_resp = self.client.get(_report_url(_base_pairs(incluir_excluidos="1")))
        included_content = included_resp.content.decode()
        for phone in ("+5511920300010", "+5511920300011", "+5511920300012", "+5511920300013"):
            self.assertIn(phone, included_content)
        self.assertEqual(included_content.count("+5511920300010"), 2)  # A + F

    def test_active_and_released_counts_sum_to_total(self):
        line_active, _ = _make_line("+5511920300020")
        _allocate(line_active, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))
        line_released, _ = _make_line("+5511920300021")
        allocation = _allocate(line_released, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))
        _release(allocation, self.admin)

        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        self.assertIn("+5511920300020", content)
        self.assertIn("+5511920300021", content)

    def test_empty_result_set_returns_zero_totals_no_error(self):
        response = self.client.get(
            _report_url(_base_pairs(data_inicial="2020-01-01", data_final="2020-01-02"))
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("erro", response.content.decode().lower())


class AllocationsOrderingPaginationTests(TestCase):
    """Secao 6: allocated_at decrescente com desempate por pk decrescente,
    paginacao fixa em 50, filtros preservados entre paginas."""

    def setUp(self):
        self.admin = _create_user("admin.aloc.pagination@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_descending_allocated_at_order(self):
        line1, _ = _make_line("+5511920400001")
        _allocate(line1, self.admin, allocated_at=_local_midnight(date(2026, 9, 5)))
        line2, _ = _make_line("+5511920400002")
        _allocate(line2, self.admin, allocated_at=_local_midnight(date(2026, 9, 20)))
        line3, _ = _make_line("+5511920400003")
        _allocate(line3, self.admin, allocated_at=_local_midnight(date(2026, 9, 12)))

        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        idx2 = content.index("+5511920400002")
        idx3 = content.index("+5511920400003")
        idx1 = content.index("+5511920400001")
        self.assertLess(idx2, idx3)
        self.assertLess(idx3, idx1)

    def test_tie_break_by_descending_pk(self):
        line1, _ = _make_line("+5511920400011")
        first = _allocate(line1, self.admin, allocated_at=_local_midnight(date(2026, 9, 15)))
        line2, _ = _make_line("+5511920400012")
        second = _allocate(line2, self.admin, allocated_at=_local_midnight(date(2026, 9, 15)))
        self.assertLess(first.pk, second.pk)

        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        idx_second = content.index("+5511920400012")
        idx_first = content.index("+5511920400011")
        self.assertLess(idx_second, idx_first)

    def test_first_page_has_50_rows_and_not_the_51st(self):
        for index in range(51):
            line, _ = _make_line(f"+55119205{index:06d}")
            _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 1 + (index % 20))))
        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        phone_hits = sum(1 for index in range(51) if f"+55119205{index:06d}" in content)
        self.assertEqual(phone_hits, 50)

    def test_filters_preserved_across_pagination_and_second_page_has_distinct_content(self):
        """Correcao do mesmo risco ja identificado e documentado em
        config/tests/test_line_inventory_report.py::
        LineInventoryOrderingPaginationTests::test_filters_preserved_across_pagination
        (GREEN acidental original): so comparar o eco do campo de data no
        HTML, ou so comparar status_code entre paginas, passaria mesmo sem
        nenhum motor rodando (ambas as respostas seriam o mesmo 400). A
        prova real exige 200 com conteudo REALMENTE distinto entre pagina 1
        e pagina 2 (ordenacao allocated_at decrescente aprovada em
        REL-10-C: o registro mais antigo cai na pagina 2)."""
        for index in range(51):
            line, _ = _make_line(f"+55119206{index:06d}")
            # allocated_at estritamente crescente por indice (minutos), sem
            # empate: garante ordem determinista para a asserção abaixo,
            # independente do desempate por pk.
            _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 1)) + timedelta(minutes=index))

        page1 = self.client.get(_report_url(_base_pairs(page="1")))
        page2 = self.client.get(_report_url(_base_pairs(page="2")))
        self.assertEqual(page1.status_code, 200)
        self.assertEqual(page2.status_code, 200)

        content1 = page1.content.decode()
        content2 = page2.content.decode()
        newest_number = f"+55119206{50:06d}"  # allocated_at mais recente
        oldest_number = f"+55119206{0:06d}"  # allocated_at mais antigo
        self.assertIn(newest_number, content1)
        self.assertNotIn(newest_number, content2)
        self.assertIn(oldest_number, content2)
        self.assertNotIn(oldest_number, content1)

        self.assertIn(f'name="data_inicial" value="{PERIOD_START}"', content2)
        self.assertIn(f'name="data_final" value="{PERIOD_END}"', content2)

    def test_page_out_of_range_returns_404_not_generic_400(self):
        """Hoje o motor ausente responde 400 (relatorio indisponivel) mesmo
        para page=999, ANTES de qualquer EmptyPage ser avaliado — diferente
        do contrato final (404), que so se aplica quando o motor existe
        (comprovado em Selos/Inventario). RED real ate REL-10-Q."""
        response = self.client.get(_report_url(_base_pairs(page="999")))
        self.assertEqual(response.status_code, 404)


class AllocationsNoWriteAndQueryCostTests(TestCase):
    """Secao 6 (continuacao): somente leitura; custo de consulta sem N+1.

    Fortalecido na Retificacao documental de REL-10-T (2026-09-28): as duas
    verificacoes abaixo agora exigem HTTP 200 real e conteudo elegivel
    (numero de linha visivel na resposta) ANTES de checar
    escrita/custo — um 400 residual do motor ausente nao satisfaz mais
    nenhuma das duas. A ausencia de escrita compara um retrato completo dos
    campos de negocio (is_active/released_at/allocated_at/status da linha),
    nao so contagens agregadas, que poderiam empatar por coincidencia
    mesmo com um UPDATE que preserva a cardinalidade."""

    def setUp(self):
        self.admin = _create_user("admin.aloc.readonly@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_generating_report_does_not_write_business_data(self):
        line, _ = _make_line("+5511920500001")
        allocation = _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))
        line.refresh_from_db()

        lines_before = PhoneLine.objects.count()
        allocations_before = LineAllocation.objects.count()
        allocation_snapshot_before = (
            allocation.is_active,
            allocation.released_at,
            allocation.allocated_at,
            allocation.employee_id,
            allocation.phone_line_id,
        )
        line_snapshot_before = (line.is_deleted, line.status)

        first = self.client.get(_report_url(_base_pairs(incluir_excluidos="1")))
        second = self.client.get(_report_url(_base_pairs()))
        self.assertEqual(first.status_code, 200, "motor deve responder com a tela real, nao um 400 residual")
        self.assertEqual(second.status_code, 200)
        self.assertContains(first, "+5511920500001", msg_prefix="conteudo elegivel real ausente na resposta")

        self.assertEqual(PhoneLine.objects.count(), lines_before)
        self.assertEqual(LineAllocation.objects.count(), allocations_before)

        allocation.refresh_from_db()
        line.refresh_from_db()
        self.assertEqual(
            (
                allocation.is_active,
                allocation.released_at,
                allocation.allocated_at,
                allocation.employee_id,
                allocation.phone_line_id,
            ),
            allocation_snapshot_before,
            "consulta alterou campos de negocio da alocacao",
        )
        self.assertEqual(
            (line.is_deleted, line.status),
            line_snapshot_before,
            "consulta alterou campos de negocio da linha",
        )

    def test_query_count_does_not_scale_linearly_with_row_count(self):
        for index in range(3):
            line, _ = _make_line(f"+5511920501{index:03d}")
            _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))
        with CaptureQueriesContext(connection) as small:
            small_response = self.client.get(_report_url(_base_pairs()))

        for index in range(3, 30):
            line, _ = _make_line(f"+5511920501{index:03d}")
            _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))
        with CaptureQueriesContext(connection) as large:
            large_response = self.client.get(_report_url(_base_pairs()))

        self.assertEqual(small_response.status_code, 200, "motor deve responder com a tela real, nao um 400 residual")
        self.assertEqual(large_response.status_code, 200)
        self.assertContains(small_response, "+5511920501000")
        self.assertContains(large_response, "+5511920501029")
        self.assertLessEqual(len(large.captured_queries) - len(small.captured_queries), 3)


class AllocationsExportAuthorizationTests(TestCase):
    """Secao 7: autorizacao no download direto, ambos os formatos. Rota
    reports_export ja registrada (REL-08-E); autorizacao (RoleRequiredMixin)
    precede a validacao de parametros, entao os cenarios negativos sao
    GREEN real independente do motor de Alocacoes existir."""

    def setUp(self):
        self.admin = _create_user("admin.aloc.exportauth@test.com", SystemUser.Role.ADMIN)

    def test_admin_download_csv_returns_200(self):
        """RED real: motor de exportacao ainda ausente (REL-10-E), ADMIN
        recebe 400 'relatorio ainda nao disponivel' em vez de 200."""
        self.client.force_login(self.admin)
        response = self.client.get(_export_url("csv", _base_pairs()))
        self.assertEqual(response.status_code, 200)

    def test_admin_download_xlsx_returns_200(self):
        self.client.force_login(self.admin)
        response = self.client.get(_export_url("xlsx", _base_pairs()))
        self.assertEqual(response.status_code, 200)

    def test_non_admin_roles_get_403_on_export(self):
        for index, role in enumerate(NON_ADMIN_ROLES):
            with self.subTest(role=role):
                user = _create_user(f"aloc.export.role{index}@test.com", role)
                self.client.force_login(user)
                response = self.client.get(_export_url("csv", _base_pairs()))
                self.assertEqual(response.status_code, 403)

    def test_anonymous_gets_403_on_export(self):
        response = self.client.get(_export_url("csv", _base_pairs()))
        self.assertEqual(response.status_code, 403)

    def test_invalid_dates_rejected_on_direct_export_access(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            _export_url("csv", [("relatorio", "allocations"), ("data_inicial", PERIOD_END), ("data_final", PERIOD_START)])
        )
        self.assertEqual(response.status_code, 400)

    def test_unknown_format_returns_404(self):
        """GREEN real: formato e checado antes de qualquer validacao de
        relatorio (ReportsExportView.get), independente de allocations ter
        motor ou nao."""
        self.client.force_login(self.admin)
        response = self.client.get(_export_url("pdf", _base_pairs()))
        self.assertEqual(response.status_code, 404)


class AllocationsExportContentTests(TestCase):
    """Secao 7 (continuacao): conteudo real lido via csv/openpyxl, mesmas
    colunas/granularidade/ordenacao da tela, conjunto completo independente
    de page, dados atuais no momento do download. Todos RED: motor de
    exportacao ainda ausente."""

    def setUp(self):
        self.admin = _create_user("admin.aloc.exportcontent@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def _read_csv_rows(self, response):
        """Confere status e Content-Type ANTES de parsear: uma pagina HTML
        de erro (400, 'text/html') nunca deve ser tratada como arquivo CSV
        valido — falha aqui com uma causa clara, em vez de um parser CSV
        coincidentemente 'conseguindo' ler HTML como linhas."""
        self.assertEqual(response.status_code, 200, f"esperado 200, resposta real: {response.status_code}")
        content_type = response.headers.get("Content-Type", "")
        self.assertIn("csv", content_type.lower(), f"Content-Type inesperado: {content_type!r}")
        text = b"".join(response.streaming_content).decode("utf-8-sig") if response.streaming else response.content.decode("utf-8-sig")
        return list(csv.reader(io.StringIO(text), delimiter=";"))

    def _read_xlsx_rows(self, response):
        self.assertEqual(response.status_code, 200, f"esperado 200, resposta real: {response.status_code}")
        content_type = response.headers.get("Content-Type", "")
        self.assertIn("spreadsheet", content_type.lower(), f"Content-Type inesperado: {content_type!r}")
        content = b"".join(response.streaming_content) if response.streaming else response.content
        workbook = openpyxl.load_workbook(io.BytesIO(content))
        sheet = workbook.active
        return list(sheet.iter_rows(values_only=True))

    def test_columns_match_approved_order_in_both_formats(self):
        line, _ = _make_line("+5511920600001")
        _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))

        csv_rows = self._read_csv_rows(self.client.get(_export_url("csv", _base_pairs())))
        self.assertEqual(csv_rows[0], EXPECTED_COLUMN_HEADERS)

        xlsx_rows = self._read_xlsx_rows(self.client.get(_export_url("xlsx", _base_pairs())))
        self.assertEqual(list(xlsx_rows[0]), EXPECTED_COLUMN_HEADERS)

    def test_csv_and_xlsx_contain_all_filtered_rows_regardless_of_page(self):
        for index in range(60):
            line, _ = _make_line(f"+5511920700{index:03d}")
            _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))

        csv_response = self.client.get(_export_url("csv", _base_pairs(page="1")))
        rows = self._read_csv_rows(csv_response)
        self.assertEqual(len(rows) - 1, 60)

        xlsx_response = self.client.get(_export_url("xlsx", _base_pairs(page="2")))
        xlsx_rows = self._read_xlsx_rows(xlsx_response)
        self.assertEqual(len(xlsx_rows) - 1, 60)

    def test_empty_filtered_set_exports_headers_only(self):
        csv_rows = self._read_csv_rows(
            self.client.get(_export_url("csv", _base_pairs(data_inicial="2020-01-01", data_final="2020-01-02")))
        )
        self.assertEqual(len(csv_rows), 1)

    def test_export_reflects_current_data_changed_after_query(self):
        """Decisao aprovada em REL-07: exportacao consulta os dados atuais
        no momento do download. Libera a alocacao ENTRE a consulta e o
        clique de exportacao; o arquivo deve refletir 'Liberada', nao o
        estado 'Ativa' visto na consulta anterior."""
        line, _ = _make_line("+5511920800001")
        allocation = _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))
        self.client.get(_report_url(_base_pairs()))

        _release(allocation, self.admin)

        csv_rows = self._read_csv_rows(self.client.get(_export_url("csv", _base_pairs())))
        matching = [row for row in csv_rows[1:] if row and row[0].lstrip("'") == "+5511920800001"]
        self.assertTrue(matching)
        self.assertEqual(matching[0][5], "Liberada")

    def test_phone_number_stored_as_string_type_in_xlsx(self):
        line, _ = _make_line("+5511920900001")
        _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))
        rows_sheet = self._read_xlsx_rows(self.client.get(_export_url("xlsx", _base_pairs())))
        self.assertTrue(rows_sheet)  # reaproveita a validacao de status/Content-Type do helper
        response = self.client.get(_export_url("xlsx", _base_pairs()))
        content = b"".join(response.streaming_content) if response.streaming else response.content
        workbook = openpyxl.load_workbook(io.BytesIO(content))
        sheet = workbook.active
        phone_cell = sheet.cell(row=2, column=1)
        self.assertEqual(phone_cell.data_type, "s")

    def test_accents_in_employee_name_preserved_and_do_not_break_parsing(self):
        employee = Employee.objects.create(
            full_name="José Ação Ínãti",
            corporate_email="acentos.aloc@test.com",
            employee_id="ALOC-ACC",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        line, _ = _make_line("+5511921000001")
        _allocate(line, self.admin, employee=employee, allocated_at=_local_midnight(date(2026, 9, 10)))
        csv_rows = self._read_csv_rows(self.client.get(_export_url("csv", _base_pairs())))
        self.assertEqual(len(csv_rows), 2)

    def test_released_at_empty_cell_for_active_allocation_both_formats(self):
        """REL-07: nulos exportados como celula vazia, nao substituidos por
        zero/placeholder. Alocacao ativa tem released_at nulo — a celula da
        coluna 'Data de liberação' deve ser vazia (CSV) / None (XLSX).
        Telefone comeca com '+': neutralizado com prefixo "'" no CSV (REL-07:
        "inclusive telefones iniciados em +"), mesmo padrao de
        AllocationsExportFormulaProtectionTests."""
        line, _ = _make_line("+5511921100001")
        _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))

        csv_rows = self._read_csv_rows(self.client.get(_export_url("csv", _base_pairs())))
        data_row = csv_rows[1]
        self.assertEqual(data_row[0], "'+5511921100001")
        self.assertEqual(data_row[4], "")

        xlsx_response = self.client.get(_export_url("xlsx", _base_pairs()))
        content = b"".join(xlsx_response.streaming_content) if xlsx_response.streaming else xlsx_response.content
        workbook = openpyxl.load_workbook(io.BytesIO(content))
        sheet = workbook.active
        released_cell = sheet.cell(row=2, column=5)
        self.assertIsNone(released_cell.value)


class AllocationsExportFormulaProtectionTests(TestCase):
    """Secao 7 (REL-07): valores textuais que comecam com =, +, -, @ (ou
    espacos/controles que encubram esses prefixos) devem ser neutralizados
    no CSV com prefixo textual ('). No XLSX, o valor e sempre gravado como
    string simples (nunca como formula), entao nenhuma neutralizacao
    adicional e necessaria alem de nao usar o tipo formula do openpyxl."""

    def setUp(self):
        self.admin = _create_user("admin.aloc.formula@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def _read_csv_rows(self, response):
        self.assertEqual(response.status_code, 200)
        text = b"".join(response.streaming_content).decode("utf-8-sig") if response.streaming else response.content.decode("utf-8-sig")
        return list(csv.reader(io.StringIO(text), delimiter=";"))

    def test_employee_name_starting_with_equals_neutralized_in_csv(self):
        """Employee.save() normaliza full_name (core/normalization.py,
        capitalizacao por token) — o valor persistido pode nao ser
        identico ao literal enviado, mas continua comecando por '=' (o
        gatilho de formula nao e removido pela normalizacao de nomes).
        A asserção usa o valor REAL persistido, nao um literal hardcoded
        que presumiria o comportamento exato da normalizacao de dominio."""
        employee = Employee.objects.create(
            full_name="=cmd|'/c calc'!A1",
            corporate_email="formula.aloc@test.com",
            employee_id="ALOC-FORM",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        employee.refresh_from_db()
        self.assertTrue(employee.full_name.startswith("="))
        line, _ = _make_line("+5511921200001")
        _allocate(line, self.admin, employee=employee, allocated_at=_local_midnight(date(2026, 9, 10)))

        rows = self._read_csv_rows(self.client.get(_export_url("csv", _base_pairs())))
        self.assertEqual(rows[1][1], "'" + employee.full_name)

    def test_employee_id_starting_with_plus_neutralized_in_csv(self):
        employee = Employee.objects.create(
            full_name="Carteira Formula",
            corporate_email="formula2.aloc@test.com",
            employee_id="+5511999999999",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        line, _ = _make_line("+5511921200002")
        _allocate(line, self.admin, employee=employee, allocated_at=_local_midnight(date(2026, 9, 10)))

        rows = self._read_csv_rows(self.client.get(_export_url("csv", _base_pairs())))
        self.assertEqual(rows[1][2], "'+5511999999999")

    def test_xlsx_stores_formula_like_value_as_plain_string_not_formula(self):
        employee = Employee.objects.create(
            full_name="=SUM(A1:A2)",
            corporate_email="formula3.aloc@test.com",
            employee_id="ALOC-FORM3",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        employee.refresh_from_db()
        self.assertTrue(employee.full_name.startswith("="))
        line, _ = _make_line("+5511921200003")
        _allocate(line, self.admin, employee=employee, allocated_at=_local_midnight(date(2026, 9, 10)))

        response = self.client.get(_export_url("xlsx", _base_pairs()))
        content = b"".join(response.streaming_content) if response.streaming else response.content
        workbook = openpyxl.load_workbook(io.BytesIO(content))
        sheet = workbook.active
        cell = sheet.cell(row=2, column=2)
        self.assertEqual(cell.data_type, "s")
        self.assertEqual(cell.value, employee.full_name)


class AllocationsExportSplitBoundaryTests(TestCase):
    """Fronteira de divisao em partes/ZIP (REL-07/REL-10-C), boundary-1/
    boundary/boundary+1 em ambos os formatos. Interface tecnica explicita e
    pequena para reduzir o limiar em teste: o parametro `split_threshold` de
    core.services.allocations_export_service.generate_allocations_export,
    chamado diretamente aqui (nao via HTTP). A rota reports_export nunca
    passa esse parametro e usa sempre EXPORT_SPLIT_THRESHOLD (100.000) —
    producao permanece intocada por este teste."""

    def _filters(self):
        return dict(
            data_inicial=date(2026, 9, 1),
            data_final=date(2026, 9, 24),
            incluir_excluidos=False,
            situacao_alocacao="",
            funcionario="",
            linha="",
        )

    def _make_allocations(self, count, prefix, admin):
        for index in range(count):
            line, _ = _make_line(f"+55119{prefix}{index:06d}")
            _allocate(line, admin, allocated_at=_local_midnight(date(2026, 9, 10)))

    def _generate(self, formato, threshold):
        from core.services.allocations_export_service import generate_allocations_export

        return generate_allocations_export(
            formato=formato, filters=self._filters(), split_threshold=threshold
        )

    def _read_csv_data_row_counts(self, path):
        with open(path, encoding="utf-8-sig") as handle:
            rows = list(csv.reader(handle, delimiter=";"))
        return rows[0], len(rows) - 1

    def _read_xlsx_data_row_counts(self, path):
        workbook = openpyxl.load_workbook(path)
        sheet = workbook["Alocações"]
        rows = list(sheet.iter_rows(values_only=True))
        return list(rows[0]), len(rows) - 1

    def setUp(self):
        self.admin = _create_user("admin.aloc.split@test.com", SystemUser.Role.ADMIN)

    def test_csv_below_threshold_is_single_file(self):
        self._make_allocations(2, "3001", self.admin)
        export = self._generate("csv", 3)
        try:
            self.assertFalse(export.filename.endswith(".zip"))
            _, count = self._read_csv_data_row_counts(export.path)
            self.assertEqual(count, 2)
        finally:
            shutil.rmtree(export.temp_dir, ignore_errors=True)

    def test_csv_at_threshold_is_single_file(self):
        self._make_allocations(3, "3002", self.admin)
        export = self._generate("csv", 3)
        try:
            self.assertFalse(export.filename.endswith(".zip"))
            _, count = self._read_csv_data_row_counts(export.path)
            self.assertEqual(count, 3)
        finally:
            shutil.rmtree(export.temp_dir, ignore_errors=True)

    def test_csv_above_threshold_splits_into_zip_without_loss_or_duplication(self):
        from core.services.allocations_export_service import COLUMNS

        self._make_allocations(4, "3003", self.admin)
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
        self._make_allocations(2, "3004", self.admin)
        export = self._generate("xlsx", 3)
        try:
            self.assertFalse(export.filename.endswith(".zip"))
            _, count = self._read_xlsx_data_row_counts(export.path)
            self.assertEqual(count, 2)
        finally:
            shutil.rmtree(export.temp_dir, ignore_errors=True)

    def test_xlsx_at_threshold_is_single_file(self):
        self._make_allocations(3, "3005", self.admin)
        export = self._generate("xlsx", 3)
        try:
            self.assertFalse(export.filename.endswith(".zip"))
            _, count = self._read_xlsx_data_row_counts(export.path)
            self.assertEqual(count, 3)
        finally:
            shutil.rmtree(export.temp_dir, ignore_errors=True)

    def test_xlsx_above_threshold_splits_into_zip_without_loss_or_duplication(self):
        from core.services.allocations_export_service import COLUMNS

        self._make_allocations(4, "3006", self.admin)
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
                    sheet = workbook["Alocações"]
                    rows = list(sheet.iter_rows(values_only=True))
                    self.assertEqual(list(rows[0]), COLUMNS)
                    counts.append(len(rows) - 1)
                self.assertEqual(sorted(counts), [1, 3])
                self.assertEqual(sum(counts), 4)
        finally:
            shutil.rmtree(export.temp_dir, ignore_errors=True)


class AllocationsExportStreamingCleanupTests(TestCase):
    """Prova direta do mecanismo de limpeza de temporarios (REL-07/REL-10-C:
    limpeza em consumo completo, consumo parcial, fechamento antes do
    primeiro chunk, fechamento repetido e falha de geracao). Mesmo
    raciocinio ja comprovado para Selos WhatsApp (REL-08-E) e Inventario
    (REL-09-E): StreamingHttpResponse com generator, Django chama
    generator.close() como resource closer, e _CleanupStreamingHttpResponse
    cobre o caso de fechamento ANTES de qualquer iteracao (generator em
    GEN_CREATED nao roda seu proprio finally nesse caso)."""

    def setUp(self):
        self.admin = _create_user("admin.aloc.cleanup@test.com", SystemUser.Role.ADMIN)

    def _filters(self):
        return dict(
            data_inicial=date(2026, 9, 1),
            data_final=date(2026, 9, 24),
            incluir_excluidos=False,
            situacao_alocacao="",
            funcionario="",
            linha="",
        )

    def test_temp_dir_removed_after_full_stream_consumption(self):
        from core.services.allocations_export_service import (
            _stream_and_cleanup,
            generate_allocations_export,
        )

        line, _ = _make_line("+5511921300001")
        _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))
        export = generate_allocations_export(formato="csv", filters=self._filters())
        self.assertTrue(os.path.isdir(export.temp_dir))

        content = b"".join(_stream_and_cleanup(export.path, export.temp_dir))
        self.assertIn(b"+5511921300001", content)
        self.assertFalse(os.path.exists(export.temp_dir))

    def test_temp_dir_removed_on_early_close_simulating_client_disconnect(self):
        """Consumo PARCIAL: um chunk e lido, depois a conexao 'cai' — o
        servidor WSGI chama generator.close() com o generator ja suspenso
        em algum yield, o que aciona o finally normalmente."""
        from core.services.allocations_export_service import (
            _stream_and_cleanup,
            generate_allocations_export,
        )

        line, _ = _make_line("+5511921300002")
        _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))
        export = generate_allocations_export(formato="csv", filters=self._filters())
        stream = _stream_and_cleanup(export.path, export.temp_dir)
        next(stream)
        stream.close()
        self.assertFalse(os.path.exists(export.temp_dir))

    def test_temp_dir_removed_before_first_chunk_consumed_on_close(self):
        """Fechamento ANTES de qualquer iteracao (cliente desconecta antes
        do primeiro byte). streaming_content nunca e tocado. Diretorio
        temporario localizado via mock em tempfile.mkdtemp, sem depender de
        atributo privado da resposta. Nenhuma limpeza manual antes da
        assertion final: se o mecanismo real nao cobrir este caminho, a
        assertion falha de verdade (RED)."""
        from unittest import mock

        from core.services import allocations_export_service

        line, _ = _make_line("+5511921300004")
        _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))

        captured = {}
        original_mkdtemp = allocations_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        with mock.patch.object(
            allocations_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
        ):
            response = allocations_export_service.build_allocations_export_response(
                formato="csv", filters=self._filters()
            )

        self.assertIn("temp_dir", captured)
        self.assertTrue(os.path.isdir(captured["temp_dir"]))

        response.close()  # nenhum chunk foi lido ate aqui

        self.assertFalse(os.path.exists(captured["temp_dir"]))

    def test_close_is_idempotent_on_repeated_close_calls(self):
        """Fechamento REPETIDO: um servidor WSGI real so chama close() uma
        vez, mas a limpeza deve ser segura mesmo se chamada mais de uma vez
        (idempotente via flag propria, redundante com
        shutil.rmtree(..., ignore_errors=True))."""
        from core.services import allocations_export_service

        line, _ = _make_line("+5511921300005")
        _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))

        response = allocations_export_service.build_allocations_export_response(
            formato="csv", filters=self._filters()
        )
        response.close()
        self.assertFalse(os.path.exists(response._export_temp_dir))
        response.close()  # segunda chamada nao deve levantar excecao
        self.assertFalse(os.path.exists(response._export_temp_dir))

    def test_temp_dir_removed_when_generation_fails(self):
        from unittest import mock

        from core.services import allocations_export_service

        line, _ = _make_line("+5511921300003")
        _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))
        captured = {}
        original_mkdtemp = allocations_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        with mock.patch.object(
            allocations_export_service, "_write_csv_chunk", side_effect=RuntimeError("boom")
        ):
            with mock.patch.object(
                allocations_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
            ):
                with self.assertRaises(RuntimeError):
                    allocations_export_service.generate_allocations_export(
                        formato="csv", filters=self._filters()
                    )

        self.assertIn("temp_dir", captured)
        self.assertFalse(os.path.exists(captured["temp_dir"]))

    def test_temp_dir_removed_and_xlsx_workbook_closed_when_generation_fails(self):
        """Mesmo caso acima, mas falhando no meio da escrita XLSX write-only:
        sem fechar explicitamente o workbook abandonado, o GC o fecha fora
        de ordem (warning 'I/O operation on closed file'); aqui verificamos
        que o workbook e' fechado de forma limpa (sem excecao no close) e
        que o diretorio temporario e' removido mesmo assim."""
        from unittest import mock

        from core.services import allocations_export_service

        line, _ = _make_line("+5511921300004")
        _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))
        captured = {}
        original_mkdtemp = allocations_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        original_cells = allocations_export_service._row_to_xlsx_cells

        def _boom(worksheet, row):
            raise RuntimeError("boom")

        with mock.patch.object(
            allocations_export_service, "_row_to_xlsx_cells", side_effect=_boom
        ):
            with mock.patch.object(
                allocations_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
            ):
                with self.assertRaises(RuntimeError):
                    allocations_export_service.generate_allocations_export(
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
        abandonado). `_close_abandoned_workbook` so fechava o worksheet
        (`sheet.close()`), nunca chamava `sheet._writer.cleanup()` (unico
        jeito de remover esse arquivo antes de `save()`)."""
        from unittest import mock

        from core.services import allocations_export_service
        from openpyxl.worksheet._writer import ALL_TEMP_FILES

        line, _ = _make_line("+5511921300006")
        _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))

        def _boom(worksheet, row):
            raise RuntimeError("boom")

        baseline = set(ALL_TEMP_FILES)
        with mock.patch.object(
            allocations_export_service, "_row_to_xlsx_cells", side_effect=_boom
        ):
            with self.assertRaises(RuntimeError):
                allocations_export_service.generate_allocations_export(
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

        from core.services import allocations_export_service
        from openpyxl.worksheet._writer import ALL_TEMP_FILES

        line1, _ = _make_line("+5511921300007")
        _allocate(line1, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))
        line2, _ = _make_line("+5511921300008")
        _allocate(line2, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))

        real_row_to_xlsx_cells = allocations_export_service._row_to_xlsx_cells
        calls = {"count": 0}

        def _fail_on_second_row(worksheet, row):
            calls["count"] += 1
            if calls["count"] >= 2:
                raise RuntimeError("boom")
            return real_row_to_xlsx_cells(worksheet, row)

        baseline = set(ALL_TEMP_FILES)
        with mock.patch.object(
            allocations_export_service, "_row_to_xlsx_cells", side_effect=_fail_on_second_row
        ):
            with self.assertRaises(RuntimeError):
                allocations_export_service.generate_allocations_export(
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
        fechado para o arquivo final) SEM substituir o exportador: a linha
        real e escrita via `.append()`, `ws.close()` roda de verdade
        (fecha e grava a cauda do XML no temporario interno do openpyxl) —
        so a copia para o ZIP final falha, exatamente a etapa de
        finalizacao, comprovadamente alcancada (nao a de conversao)."""
        import zipfile
        from unittest import mock

        from core.services import allocations_export_service
        from openpyxl.worksheet._writer import ALL_TEMP_FILES

        line, _ = _make_line("+5511921300009")
        _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))

        def _fail_on_archive_write(self_zip, filename, arcname=None, **kwargs):
            raise RuntimeError("boom-disk-full-during-finalization")

        baseline = set(ALL_TEMP_FILES)
        captured = {}
        original_mkdtemp = allocations_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        with mock.patch.object(zipfile.ZipFile, "write", new=_fail_on_archive_write):
            with mock.patch.object(
                allocations_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
            ):
                with self.assertRaises(RuntimeError) as ctx:
                    allocations_export_service.generate_allocations_export(
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
        traceback.clear_frames' (.git/REPORTS_SENIOR_REVIEW.md): o teste
        acima usa uma excecao SIMPLES (RuntimeError direta) — insuficiente
        para provar a limpeza contra uma excecao ENCADEADA
        (`raise RuntimeError(...) from OSError(...)`), onde o `ZipFile` de
        saida pode ficar referenciado apenas pelo traceback da CAUSA
        (`exc.__cause__.__traceback__`), fora do alcance de uma abordagem
        baseada em `traceback.clear_frames(exc.__traceback__)` (que so
        percorre a excecao principal). Reproduzido aqui com uma funcao
        auxiliar que recebe o proprio `ZipFile` como argumento e levanta o
        `OSError` (essa funcao — nao `zipfile.ZipFile.write` diretamente —
        fica no traceback da CAUSA), capturado e relancado como
        `RuntimeError` um nivel acima (fica no traceback PRINCIPAL). A
        excecao e sua causa sao mantidas VIVAS (variavel `exc_holder`,
        nunca `del`, nenhum `gc.collect()`) durante toda a verificacao,
        inclusive apos `generate_allocations_export` retornar (propagar) —
        exatamente o cenario que `traceback.clear_frames` nao resolvia."""
        import zipfile
        from unittest import mock

        from core.services import allocations_export_service
        from openpyxl.worksheet._writer import ALL_TEMP_FILES

        line, _ = _make_line("+5511921300015")
        _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))

        def _raise_deep_oserror(archive_ref):
            # `archive_ref` (o ZipFile de destino) fica como variavel LOCAL
            # desta frame — que so entra no traceback da CAUSA (OSError),
            # nunca no traceback do RuntimeError relancado abaixo.
            raise OSError("disk full (simulated, chained)")

        def _fail_with_chained_exception(self_zip, filename, arcname=None, **kwargs):
            try:
                _raise_deep_oserror(self_zip)
            except OSError as cause:
                raise RuntimeError("boom-chained-during-finalization") from cause

        baseline = set(ALL_TEMP_FILES)
        captured = {}
        original_mkdtemp = allocations_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        exc_holder = {}
        with mock.patch.object(zipfile.ZipFile, "write", new=_fail_with_chained_exception):
            with mock.patch.object(
                allocations_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
            ):
                try:
                    allocations_export_service.generate_allocations_export(
                        formato="xlsx", filters=self._filters()
                    )
                    self.fail("esperava RuntimeError encadeado a partir de OSError")
                except RuntimeError as exc:
                    exc_holder["exc"] = exc  # mantido vivo deliberadamente

        # A excecao (e sua causa) continuam referenciadas por exc_holder —
        # nenhum del/clear_frames/gc.collect() antes destas verificacoes.
        self.assertEqual(str(exc_holder["exc"]), "boom-chained-during-finalization")
        self.assertIsInstance(exc_holder["exc"].__cause__, OSError)
        self.assertEqual(str(exc_holder["exc"].__cause__), "disk full (simulated, chained)")

        self.assertIn("temp_dir", captured)
        self.assertFalse(
            os.path.exists(captured["temp_dir"]),
            "temp_dir sobrevive quando o ZipFile fica preso pelo traceback da CAUSA "
            "(exatamente o caso que traceback.clear_frames nao cobria)",
        )

        leaked = set(ALL_TEMP_FILES) - baseline
        self.assertEqual(
            leaked, set(),
            f"arquivo temporario interno do openpyxl nao removido: {leaked}",
        )
        for path in leaked:
            self.assertFalse(os.path.exists(path))

        # A excecao (com sua causa) ainda esta viva neste ponto, apos o
        # retorno/propagacao do exportador — prova de que a limpeza nao
        # dependeu de ela ter sido liberada.
        self.assertIsNotNone(exc_holder["exc"])
        self.assertIsNotNone(exc_holder["exc"].__cause__)

    def test_secondary_close_failure_during_finalization_does_not_replace_original_exception(self):
        """REPORTS_SENIOR_REVIEW, revisao de _save_xlsx_workbook (2026-09-30):
        os testes acima cobrem escrita falhando seguida de fechamento NORMAL
        (`archive.close()` bem-sucedido). Falta o caso em que o proprio
        `close()` de limpeza (chamado dentro do `except` de
        `_save_xlsx_workbook` apos a falha original de escrita) TAMBEM
        falha — ex.: disco realmente cheio, onde ate liberar o handle
        encontra erro. A falha SECUNDARIA (do `close()` de limpeza) nunca
        pode substituir a excecao ORIGINAL (a que motivou a limpeza) — e a
        unica forma de garantir isso e engolir a falha do `close()` dentro
        de `_save_xlsx_workbook`, nunca deixa-la se propagar.

        `zipfile.ZipFile.close` e' substituido por uma versao que primeiro
        executa o `close()` REAL (libera o handle de verdade — mesma
        garantia que o proprio `zipfile` da via `finally` em `close()`,
        nao dependente do mock) e so DEPOIS levanta um `OSError` simulando
        uma falha secundaria que ocorre apos a liberacao do recurso
        (cenario realista: o `finally` interno do `zipfile` sempre libera
        `fp`, entao uma falha de `close()` que deixe o handle preso nao e'
        reproduzivel via stdlib — mas uma falha secundaria POS-liberacao,
        por ex. numa camada acima do proprio `zipfile`, e')."""
        import zipfile
        from unittest import mock

        from core.services import allocations_export_service

        line, _ = _make_line("+5511921300017")
        _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))

        real_zip_close = zipfile.ZipFile.close

        def _fail_on_archive_write(self_zip, filename, arcname=None, **kwargs):
            raise RuntimeError("boom-original-write-failure")

        def _fail_after_real_close(self_zip):
            # `was_open` evita relancar numa segunda chamada redundante a
            # `close()` (ex.: `ZipFile.__del__` na finalizacao do objeto,
            # apos o handle ja ter sido liberado pela primeira chamada
            # real acima) — sem isto, o GC dispara
            # PytestUnraisableExceptionWarning ao tentar propagar uma
            # excecao de dentro de `__del__`.
            was_open = self_zip.fp is not None
            real_zip_close(self_zip)
            if was_open:
                raise OSError("boom-secondary-close-failure")

        captured = {}
        original_mkdtemp = allocations_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        with mock.patch.object(zipfile.ZipFile, "write", new=_fail_on_archive_write):
            with mock.patch.object(zipfile.ZipFile, "close", new=_fail_after_real_close):
                with mock.patch.object(
                    allocations_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
                ):
                    with self.assertRaises(RuntimeError) as ctx:
                        allocations_export_service.generate_allocations_export(
                            formato="xlsx", filters=self._filters()
                        )

        self.assertEqual(
            str(ctx.exception), "boom-original-write-failure",
            "falha secundaria do close() de limpeza substituiu a excecao original de escrita",
        )
        self.assertIsNone(
            ctx.exception.__cause__,
            "excecao original nao deveria ganhar __cause__ a partir da falha de limpeza",
        )
        self.assertIn("temp_dir", captured)
        self.assertFalse(
            os.path.exists(captured["temp_dir"]),
            "temp_dir nao removido apesar do close() real ja ter liberado o handle",
        )

    def test_multi_part_finalization_failure_discards_already_saved_part_too(self):
        """Multiplas partes (REL-07/REL-10-C: divisao em ZIP): a primeira
        parte e salva com SUCESSO real (workbook.save() completo, sem
        instrumentacao) antes da segunda falhar na finalizacao. O contrato
        (REL-07, 'nunca entregar arquivo... aparentemente completo apos
        falha') exige descartar TUDO, inclusive a parte ja salva com
        sucesso — nenhum ZIP parcial (so com a primeira parte) e
        entregue."""
        import zipfile
        from unittest import mock

        from core.services import allocations_export_service
        from openpyxl.worksheet._writer import ALL_TEMP_FILES

        # 2 linhas, split_threshold=1 -> 2 partes; cada parte tem 2 sheets
        # (dados + Contexto) -> 2 chamadas reais de zipfile.write por save().
        line1, _ = _make_line("+5511921300010")
        _allocate(line1, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))
        line2, _ = _make_line("+5511921300011")
        _allocate(line2, self.admin, allocated_at=_local_midnight(date(2026, 9, 11)))

        real_zip_write = zipfile.ZipFile.write
        calls = {"count": 0}

        def _fail_after_first_part_saves_fully(self_zip, filename, arcname=None, **kwargs):
            calls["count"] += 1
            if calls["count"] <= 2:
                # As 2 chamadas da PRIMEIRA parte (dados + Contexto) rodam
                # de verdade — primeira parte fica de fato, genuinamente,
                # salva com sucesso em disco antes da falha.
                return real_zip_write(self_zip, filename, arcname, **kwargs)
            raise RuntimeError("boom-disk-full-on-second-part")

        baseline = set(ALL_TEMP_FILES)
        captured = {}
        original_mkdtemp = allocations_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        with mock.patch.object(zipfile.ZipFile, "write", new=_fail_after_first_part_saves_fully):
            with mock.patch.object(
                allocations_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
            ):
                with self.assertRaises(RuntimeError) as ctx:
                    allocations_export_service.generate_allocations_export(
                        formato="xlsx", filters=self._filters(), split_threshold=1
                    )

        self.assertEqual(str(ctx.exception), "boom-disk-full-on-second-part")
        self.assertGreaterEqual(
            calls["count"], 3,
            "a primeira parte precisa ter completado suas 2 escritas reais antes da falha da segunda",
        )
        self.assertIn("temp_dir", captured)
        self.assertFalse(
            os.path.exists(captured["temp_dir"]),
            "temp_dir removido inteiro, mesmo com a primeira parte ja salva com sucesso — "
            "nenhum arquivo parcialmente completo pode sobrar",
        )

        leaked = set(ALL_TEMP_FILES) - baseline
        self.assertEqual(
            leaked, set(),
            f"arquivo temporario interno do openpyxl nao removido (de nenhuma das 2 partes): {leaked}",
        )
        for path in leaked:
            self.assertFalse(os.path.exists(path))

    def test_finalization_failure_does_not_touch_temp_files_of_an_unrelated_export(self):
        """Escopo da limpeza (REPORTS_SENIOR_REVIEW achado 2, restricao
        explicita): a limpeza de uma exportacao que falha deve atingir
        SOMENTE os recursos daquela operacao — nunca `ALL_TEMP_FILES`
        globalmente, nem o `temp_dir`/arquivo final de uma exportacao NAO
        relacionada que ja terminou com sucesso antes dela."""
        import zipfile
        from unittest import mock

        from core.services import allocations_export_service
        from openpyxl.worksheet._writer import ALL_TEMP_FILES

        healthy_line, _ = _make_line("+5511921300012")
        _allocate(healthy_line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))
        unrelated_export = allocations_export_service.generate_allocations_export(
            formato="xlsx", filters=self._filters()
        )
        self.assertTrue(os.path.isfile(unrelated_export.path))
        self.assertTrue(os.path.isdir(unrelated_export.temp_dir))

        failing_line, _ = _make_line("+5511921300013")
        _allocate(failing_line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))

        def _fail_on_archive_write(self_zip, filename, arcname=None, **kwargs):
            raise RuntimeError("boom-disk-full-during-finalization")

        try:
            with mock.patch.object(zipfile.ZipFile, "write", new=_fail_on_archive_write):
                with self.assertRaises(RuntimeError):
                    allocations_export_service.generate_allocations_export(
                        formato="xlsx", filters=self._filters()
                    )

            self.assertTrue(
                os.path.isfile(unrelated_export.path),
                "arquivo de uma exportacao NAO relacionada foi apagado pela limpeza de outra",
            )
            self.assertTrue(
                os.path.isdir(unrelated_export.temp_dir),
                "temp_dir de uma exportacao NAO relacionada foi removido pela limpeza de outra",
            )
        finally:
            shutil.rmtree(unrelated_export.temp_dir, ignore_errors=True)

    def test_download_response_never_created_and_no_partial_file_served_on_finalization_failure(self):
        """Nivel HTTP real (nao so o servico): quando a finalizacao XLSX
        falha por erro inesperado (nao um contrato de negocio como o
        achado 1), `build_allocations_export_response` nunca chega a
        construir o `StreamingHttpResponse` (a geracao integral do arquivo
        termina, com sucesso ou excecao, ANTES de qualquer resposta HTTP
        comecar — ver docstring de `generate_allocations_export`); o
        Django test client, com `raise_request_exception=False`, expõe o
        500 real sem nenhum cabecalho de anexo nem corpo de arquivo."""
        import zipfile
        from unittest import mock
        from django.test import Client

        line, _ = _make_line("+5511921300014")
        _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))

        def _fail_on_archive_write(self_zip, filename, arcname=None, **kwargs):
            raise RuntimeError("boom-disk-full-during-finalization")

        client = Client(raise_request_exception=False)
        client.force_login(self.admin)

        with mock.patch.object(zipfile.ZipFile, "write", new=_fail_on_archive_write):
            response = client.get(_export_url("xlsx", _base_pairs()))

        self.assertEqual(response.status_code, 500)
        self.assertNotIn("Content-Disposition", response.headers)
        self.assertNotIn(
            "spreadsheet", response.headers.get("Content-Type", "").lower()
        )


class AllocationsExportQueryCostTests(TestCase):
    """Secao 15: consultas em lotes sem N+1 tambem na EXPORTACAO (nao so na
    consulta paginada, ja coberta por AllocationsNoWriteAndQueryCostTests).
    select_related sem Prefetch e suficiente (REL-10-C: granularidade por
    evento dispensa Prefetch); o numero de consultas nao deve escalar com a
    quantidade de linhas exportadas."""

    def setUp(self):
        self.admin = _create_user("admin.aloc.exportquerycost@test.com", SystemUser.Role.ADMIN)

    def _filters(self):
        return dict(
            data_inicial=date(2026, 9, 1),
            data_final=date(2026, 9, 24),
            incluir_excluidos=False,
            situacao_alocacao="",
            funcionario="",
            linha="",
        )

    def test_export_query_count_does_not_scale_linearly_with_row_count(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from core.services.allocations_export_service import generate_allocations_export

        for index in range(3):
            line, _ = _make_line(f"+5511921400{index:03d}")
            _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))
        with CaptureQueriesContext(connection) as small:
            export_small = generate_allocations_export(formato="csv", filters=self._filters())
        try:
            with open(export_small.path, encoding="utf-8-sig") as handle:
                small_count = len(list(csv.reader(handle, delimiter=";"))) - 1
        finally:
            shutil.rmtree(export_small.temp_dir, ignore_errors=True)

        for index in range(3, 30):
            line, _ = _make_line(f"+5511921400{index:03d}")
            _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))
        with CaptureQueriesContext(connection) as large:
            export_large = generate_allocations_export(formato="csv", filters=self._filters())
        try:
            with open(export_large.path, encoding="utf-8-sig") as handle:
                large_count = len(list(csv.reader(handle, delimiter=";"))) - 1
        finally:
            shutil.rmtree(export_large.temp_dir, ignore_errors=True)

        self.assertEqual(small_count, 3)
        self.assertEqual(large_count, 30)
        self.assertLessEqual(len(large.captured_queries) - len(small.captured_queries), 3)


class AllocationsExportRealVolumeTests(TestCase):
    """Ensaio de volume REAL na fronteira de producao (100.000/100.001
    linhas de LineAllocation), exigido por REL-10-C/REL-10-T antes de
    liberar REL-10-E.

    Dataset unico (bulk_create), criado uma vez para toda a classe
    (setUpTestData): um pool pequeno de PhoneLine/Employee (para nao pagar o
    custo de 10^5 linhas/funcionarios distintos, o que nao e exigido pelo
    contrato) reaproveitado por 100.001 LineAllocation — representa
    alocacoes ativas e liberadas, linhas com historico repetido e
    funcionarios compartilhados entre registros, exatamente o perfil exigido
    pela task. allocated_at e auto_now_add: bulk_create() sempre grava o
    instante real da insercao, entao os valores de periodo sao aplicados
    DEPOIS via QuerySet.update() em lotes (bypassa auto_now_add), cada
    chamada deixando os campos relacionados (is_active/released_at) num
    estado ja consistente com as CheckConstraints do modelo.

    Tempo e pico de memoria (tracemalloc) sao medidos em bloco proprio,
    iniciado somente APOS a fixture ja estar criada e confirmada — mede o
    processo de exportacao isoladamente, nao a criacao dos dados de teste.
    Roda em banco de teste isolado; nao acessa PRD. Deliberadamente lento
    (10^5 linhas reais); nao e um teste unitario comum e nao deve ser lido
    como prova de comportamento de logica (essa prova esta em
    AllocationsExportSplitBoundaryTests). Integridade comprovada por
    CONTAGEM DE REGISTROS DE ALOCACAO (nao por telefone unico: telefones
    repetidos sao esperados neste relatorio, granularidade por evento)."""

    BASE_COUNT = 100_000
    LINE_POOL_SIZE = 1000
    EMPLOYEE_POOL_SIZE = 500

    @classmethod
    def setUpTestData(cls):
        sims = [
            SIMcard(iccid=f"89{i:020d}", carrier="TIM", status=SIMcard.Status.ACTIVE)
            for i in range(cls.LINE_POOL_SIZE)
        ]
        SIMcard.objects.bulk_create(sims, batch_size=2000)
        sim_ids = list(
            SIMcard.objects.order_by("pk").values_list("pk", flat=True)[: cls.LINE_POOL_SIZE]
        )
        lines = [
            PhoneLine(
                phone_number=f"+5511930{index:06d}",
                sim_card_id=sim_ids[index],
                status=PhoneLine.Status.AVAILABLE,
            )
            for index in range(cls.LINE_POOL_SIZE)
        ]
        PhoneLine.objects.bulk_create(lines, batch_size=2000)
        line_ids = list(
            PhoneLine.objects.order_by("pk").values_list("pk", flat=True)[: cls.LINE_POOL_SIZE]
        )

        employees = [
            Employee(
                full_name=f"Volume Alocacao {index}",
                corporate_email=f"volume.aloc{index}@test.com",
                employee_id=f"VOLALOC-{index}",
                teams="Joinville",
                status=Employee.Status.ACTIVE,
            )
            for index in range(cls.EMPLOYEE_POOL_SIZE)
        ]
        Employee.objects.bulk_create(employees, batch_size=2000)
        employee_ids = list(
            Employee.objects.order_by("pk").values_list("pk", flat=True)[: cls.EMPLOYEE_POOL_SIZE]
        )

        total = cls.BASE_COUNT + 1
        allocations = [
            LineAllocation(
                employee_id=employee_ids[index % cls.EMPLOYEE_POOL_SIZE],
                phone_line_id=line_ids[index % cls.LINE_POOL_SIZE],
                is_active=True,
            )
            for index in range(total)
        ]
        LineAllocation.objects.bulk_create(allocations, batch_size=5000)

        pks = list(LineAllocation.objects.order_by("pk").values_list("pk", flat=True))
        assert len(pks) == total

        # Faixas de pk (nao pk__in com dezenas de milhares de valores: o
        # driver sqlite3 rejeita "too many SQL variables" acima de ~32.000
        # parametros por statement). pk e sequencial/contiguo logo apos o
        # bulk_create acima (tabela recem-criada pelo banco de teste), entao
        # pk__range e equivalente a pk__in para este dataset e muito mais
        # leve em numero de parametros.
        released_first, released_last = pks[0], pks[cls.BASE_COUNT // 2 - 1]
        active_first, active_last = pks[cls.BASE_COUNT // 2], pks[cls.BASE_COUNT - 1]
        extra_pk = pks[cls.BASE_COUNT]

        # Uma unica chamada por lote: allocated_at + released_at + is_active
        # juntos, para nunca deixar uma linha num estado intermediario
        # invalido perante as CheckConstraints do modelo entre chamadas.
        LineAllocation.objects.filter(pk__range=(released_first, released_last)).update(
            allocated_at=_local_midnight(date(2026, 9, 10)),
            released_at=_local_midnight(date(2026, 9, 15)),
            is_active=False,
        )
        LineAllocation.objects.filter(pk__range=(active_first, active_last)).update(
            allocated_at=_local_midnight(date(2026, 9, 10)),
        )
        LineAllocation.objects.filter(pk=extra_pk).update(
            allocated_at=_local_midnight(date(2026, 9, 24)),
        )

    def _filters(self, data_final):
        return dict(
            data_inicial=date(2026, 9, 1),
            data_final=data_final,
            incluir_excluidos=False,
            situacao_alocacao="",
            funcionario="",
            linha="",
        )

    def _measure(self, formato, data_final, expected_total):
        import sys
        import time
        import tracemalloc
        from pathlib import Path

        from core.services.allocations_export_service import generate_allocations_export

        filters = self._filters(data_final)
        actual_total = LineAllocation.objects.filter(
            allocated_at__gte=_local_midnight(date(2026, 9, 1)),
            allocated_at__lt=_local_midnight(data_final + timedelta(days=1)),
        ).count()
        self.assertEqual(actual_total, expected_total)

        tracemalloc.start()
        start = time.perf_counter()
        export = generate_allocations_export(formato=formato, filters=filters)
        elapsed = time.perf_counter() - start
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        try:
            size_bytes = Path(export.path).stat().st_size
            is_zip = export.filename.endswith(".zip")
            part_count = 1
            data_row_count = None
            if is_zip:
                with zipfile.ZipFile(export.path) as archive:
                    part_count = len(archive.namelist())
                    data_row_count = 0
                    for name in archive.namelist():
                        if formato == "csv":
                            text = archive.read(name).decode("utf-8-sig")
                            data_row_count += len(list(csv.reader(io.StringIO(text), delimiter=";"))) - 1
                        else:
                            content = archive.read(name)
                            workbook = openpyxl.load_workbook(io.BytesIO(content))
                            sheet = workbook["Alocações"]
                            data_row_count += sum(1 for _ in sheet.iter_rows(min_row=2, values_only=True))
            else:
                if formato == "csv":
                    with open(export.path, encoding="utf-8-sig") as handle:
                        data_row_count = len(list(csv.reader(handle, delimiter=";"))) - 1
                else:
                    workbook = openpyxl.load_workbook(export.path)
                    sheet = workbook["Alocações"]
                    data_row_count = sum(1 for _ in sheet.iter_rows(min_row=2, values_only=True))

            sys.stderr.write(
                "\n[VOLUME REAL ALOCACOES] formato={} registros_alocacao={} tempo={:.2f}s "
                "tamanho={:.2f}MiB zip={} partes={} "
                "pico_memoria_tracemalloc_exportador={:.2f}MiB\n".format(
                    formato,
                    expected_total,
                    elapsed,
                    size_bytes / 1024 / 1024,
                    is_zip,
                    part_count,
                    peak_bytes / 1024 / 1024,
                )
            )
            return elapsed, size_bytes, is_zip, part_count, data_row_count
        finally:
            shutil.rmtree(export.temp_dir, ignore_errors=True)

    def test_csv_100000_allocations_single_file_no_zip(self):
        _, _, is_zip, part_count, data_row_count = self._measure("csv", date(2026, 9, 23), 100_000)
        self.assertFalse(is_zip)
        self.assertEqual(part_count, 1)
        self.assertEqual(data_row_count, 100_000)

    def test_csv_100001_allocations_splits_into_zip_two_parts(self):
        _, _, is_zip, part_count, data_row_count = self._measure("csv", date(2026, 9, 24), 100_001)
        self.assertTrue(is_zip)
        self.assertEqual(part_count, 2)
        self.assertEqual(data_row_count, 100_001)

    def test_xlsx_100000_allocations_single_file_no_zip(self):
        _, _, is_zip, part_count, data_row_count = self._measure("xlsx", date(2026, 9, 23), 100_000)
        self.assertFalse(is_zip)
        self.assertEqual(part_count, 1)
        self.assertEqual(data_row_count, 100_000)

    def test_xlsx_100001_allocations_splits_into_zip_two_parts(self):
        _, _, is_zip, part_count, data_row_count = self._measure("xlsx", date(2026, 9, 24), 100_001)
        self.assertTrue(is_zip)
        self.assertEqual(part_count, 2)
        self.assertEqual(data_row_count, 100_001)
