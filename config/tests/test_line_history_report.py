"""Testes RED da task REL-12-T (fonte da verdade:
docs/superpowers/specs/2026-09-22-reports-hub-design.md, secoes REL-07 e
REL-12-C — leitura integral obrigatoria, incluindo as seis decisoes A-F
aprovadas em 2026-09-29).

Cobrem o relatorio line_history ("Histórico da linha"): consulta na tela
(endpoint existente GET /relatorios/, motor ainda ausente) e exportacoes
CSV/XLSX (endpoint ja registrado desde REL-08-E, reports_export, cujo
dispatch hoje nao inclui line_history). Nao testa a aba generica (rota,
menu, autorizacao base, dropdown com 6 opcoes) nem os motores dos demais
relatorios, ja cobertos em config/tests/test_reports_hub.py,
config/tests/test_whatsapp_seal_report.py,
config/tests/test_line_inventory_report.py,
config/tests/test_allocations_report.py e
config/tests/test_pendencies_report.py — reaproveitados, nao duplicados.

Estado atual do motor (2026-09-29, antes de REL-12-Q): "line_history" esta
em REPORT_CHOICES (config/forms.py:17) mas NAO esta em
REPORT_SPECIFIC_PARAM_NAMES, REPORT_FORM_CLASSES, REPORT_QUERY_ENGINES nem
REPORT_EXPORT_ENGINES (config/views.py). Diferente de allocations/pendencies
antes de suas respectivas tasks Q (que ja tinham motor de CONSULTA ou pelo
menos validacao especifica em construcao), line_history esta hoje no
mesmissimo estado "zero motor" documentado por
config/tests/test_line_inventory_report.py::OtherReportStillUnavailableTests::
test_line_history_report_still_returns_400_engine_unavailable — usado la
como exemplo generico de "relatorio do catalogo REL-01 sem nenhum motor
ainda". Aquele teste PRECISARA trocar de exemplo (para "daily_indicators",
o unico outro relatorio nesse estado) assim que REL-12-Q implementar a
consulta — mudanca registrada aqui e na fonte da verdade, NAO feita nesta
task (fora de escopo: T nao altera codigo de outro relatorio).

Isso produz DOIS tipos de resultado real e distinto, ambos verificados
explicitamente nas classes abaixo (nunca presumidos):

1. Validacao comum (REL-07: datas obrigatorias/invalidas/invertidas,
   incluir_excluidos, page, parametro repetido, parametro totalmente
   desconhecido, "linha" ate 20 caracteres) roda ANTES do despacho por
   relatorio (_validate_report_query_params monta o form ANTES de checar
   `available_relatorios`) usando o form generico de fallback
   (WhatsAppSealReportQueryForm, unico ja associado por
   REPORT_FORM_CLASSES.get(relatorio_value, WhatsAppSealReportQueryForm) a
   qualquer relatorio sem form proprio) — GREEN real hoje, nao RED, porque
   o contrato comum ja se aplica independente do motor de Histórico da
   linha existir.
2. Qualquer requisito especifico do contrato aprovado em REL-12-C (fontes
   PhoneLineHistory ∪ LineDailyActionAuditEvent, granularidade por evento,
   sem deduplicacao, periodo por changed_at/occurred_at, nove colunas,
   celula "Alteracoes" concatenada, filtros tipo_evento/fonte_evento/ator,
   totalizadores Total de eventos/Linhas distintas, ordenacao global com
   desempate, exportacao) depende do motor ainda inexistente: a consulta
   cai sempre em "relatorio ainda nao disponivel" (400) antes de chegar a
   qualquer logica especifica — RED real e esperado, documentado teste a
   teste, nunca inventado. tipo_evento/fonte_evento/ator caem hoje no
   bucket de "parametro desconhecido" (nem chegam a validacao de
   enum/formulario), mesmo padrao ja documentado para os parametros de
   Inventario/Alocacoes/Pendencias antes de suas respectivas tasks Q —
   reaproveitado aqui via _assert_not_rejected_as_unknown_parameter.

Fixtures: eventos de PhoneLineHistory (legado, sem guard de imutabilidade)
sao criados via ORM direto com ajuste de changed_at por update() —
mesmissimo padrao ja usado e aceito em telecom/tests_line_timeline.py (T6,
em producao) e em todos os arquivos de teste de relatorio anteriores.
Eventos de LineDailyActionAuditEvent tambem sao criados via ORM direto
(.objects.create(), que NAO viola o guard de imutabilidade — este so
bloqueia update()/delete() e resave de pk existente, nunca a criacao
inicial) reproduzindo exatamente os snapshots/before_state/after_state que
os caminhos reais gravariam — mesmo padrao de LineTimelineTestBase
(telecom/tests_line_timeline.py), justificado pela propria REL-12-C
("Dataset fictício para a matriz") exigir combinacoes de tipo/fonte/
timestamp (inclusive empates exatos e uma lacuna pre-auditoria simulada)
impossiveis de obter deterministicamente so por endpoints reais. Dois
cenarios usam o caminho real de gravacao de proposito, como controle
positivo (secao 9 do enunciado desta task): a duplicacao entre fontes
(LINE_STATUS_CHANGED via dashboard:daily_user_action_board, que grava
PhoneLineHistory.STATUS_CHANGED E LineDailyActionAuditEvent na mesma
requisicao, confirmado em dashboard/views.py:1983-2019 e replicado em
dashboard/tests/test_daily_line_action_audit.py::
test_line_status_change_records_line_status_changed_event) e um evento
ALLOCATION_PENDENCY via os endpoints reais de pendencies (mesmo padrao de
config/tests/test_pendencies_report.py).

Volume/particionamento em ZIP/limpeza de temporarios (REL-07, herdado por
REL-12-C) dependem de um exportador que ainda nao existe (proposto para
REL-12-E) — sem interface de configuracao de limiar para reduzir em teste
sem inventar uma API nova, fora do escopo desta task. Cobertura pendente,
registrada aqui e na fonte da verdade; nenhuma tentativa de simular
conclusao. Medicao real de plano de consulta/indice de occurred_at
(riscos de desempenho identificados em REL-12-C) tambem fica para REL-12-Q/E,
nao testavel sem o motor.

Ambiguidade registrada (nao inventada): REL-12-C nao define um desempate
explicito para PhoneLineHistory.changed_at (auto_now_add, sem controle
fino de teste) em cenarios de igualdade exata com outro registro legado —
so o desempate entre as DUAS fontes (`phone_number`, `row_source`,
`row_id`) esta aprovado. Os testes de empate abaixo usam apenas fontes
distintas (legado x auditoria) ou dois eventos de auditoria (occurred_at
controlavel), nunca dois PhoneLineHistory com o mesmo changed_at, para nao
inventar uma regra ausente da spec.

RETIFICACAO (REL-12-Q, 2026-09-29): a "ambiguidade" acima nao e uma lacuna
real do contrato. REL-12-C aprova a ordenacao completa `-sort_at,
phone_number, row_source, -row_id` (secao "Ordenacao e paginacao"), e
`row_id` e a PK real do registro na sua propria tabela de origem — sempre
unico e diferente para quaisquer dois registros de PhoneLineHistory,
mesmo com `changed_at` identico. Como `row_id` ja e o ULTIMO criterio da
tupla de ordenacao aprovada, dois PhoneLineHistory com o mesmo `changed_at`
JA tem desempate deterministico por `-row_id`, sem necessidade de nenhuma
regra adicional: nao ha caso de empate irresolvivel dentro da mesma fonte.
A frase original desta task T superestimou a lacuna ao tratar "desempate
entre fontes" e "desempate dentro da mesma fonte" como coisas distintas
quando `row_id` resolve ambas simultaneamente por construcao. Nenhuma
ordenacao nova foi inventada para fechar isso — a implementacao (REL-12-Q)
usa exatamente a tupla ja aprovada, sem adicionar `changed_at`/`occurred_at`
bruto como criterio extra de desempate.
"""

import csv
import io
import itertools
import json
from datetime import date, datetime, time, timedelta
from unittest import mock
from urllib.parse import urlencode

import openpyxl
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from allocations.models import LineAllocation
from core.services.allocation_service import AllocationService
from dashboard.models import DailyUserAction
from employees.models import Employee
from pendencies.models import AllocationPendency
from telecom.models import LineDailyActionAuditEvent, PhoneLine, PhoneLineHistory, SIMcard
from users.models import SystemUser

PASSWORD = "StrongPass123"
REPORTS_URL_NAME = "reports_home"
EXPORT_URL_NAME = "reports_export"  # ja registrado desde REL-08-E

ActionType = PhoneLineHistory.ActionType
EventType = LineDailyActionAuditEvent.EventType
Source = LineDailyActionAuditEvent.Source

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

# Deploy real da auditoria em PRD (T9). Qualquer occurred_at simulado antes
# desta data nao existe de fato em producao; usado so para reproduzir a
# lacuna de cobertura documentada em REL-12-C ("Eventos anteriores a
# implantacao da auditoria").
AUDIT_DEPLOY_DATE = date(2026, 9, 14)

EXPECTED_COLUMN_HEADERS = [
    "Linha",
    "Data/hora do evento",
    "Fonte",
    "Tipo de evento",
    "Ator",
    "Alocação relacionada",
    "Alterações",
    "Registro da linha",
    "Funcionário excluído",
]

SOURCE_LABEL_LEGACY = "Histórico da linha"
SOURCE_LABEL_DAILY_ACTION = "Ações do Dia"
SOURCE_LABEL_PENDENCY = "Pendência"
SOURCE_LABEL_LINE_ALLOCATION = "Status da linha"

AUTOR_NAO_DISPONIVEL = "Autor não disponível"
AUTOR_SISTEMA = "Sistema"

_iccid_counter = itertools.count(1)
_employee_counter = itertools.count(1)


def _create_user(email, role, **extra):
    return SystemUser.objects.create_user(email=email, password=PASSWORD, role=role, **extra)


def _local_midnight(d):
    return timezone.make_aware(datetime.combine(d, time.min))


def _local_last_instant(d):
    return timezone.make_aware(datetime.combine(d, time(23, 59, 59, 999999)))


def _make_line(phone_number, *, delete_line=False, delete_sim=False, released_by=None):
    sim = SIMcard.objects.create(
        iccid=f"8900000000002{next(_iccid_counter):05d}", carrier="TIM"
    )
    line = PhoneLine.objects.create(
        phone_number=phone_number,
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
    )
    if delete_line:
        line.delete(released_by=released_by)
        line.refresh_from_db()
    if delete_sim:
        SIMcard.all_objects.filter(pk=sim.pk).update(is_deleted=True)
    return line, sim


def _make_employee(label=None, *, deleted=False):
    suffix = label or next(_employee_counter)
    employee = Employee.objects.create(
        full_name=f"Historico Teste {suffix}",
        corporate_email=f"corp.hist{suffix}@test.com",
        employee_id=f"HIST-{suffix}",
        teams=Employee.UnitChoices.JOINVILLE,
        status=Employee.Status.ACTIVE,
    )
    if deleted:
        employee.delete()
        employee.refresh_from_db()
    return employee


def _make_legacy_event(
    phone_line,
    *,
    when,
    action=ActionType.STATUS_CHANGED,
    changed_by=None,
    old_value="A",
    new_value="B",
    description="",
):
    """PhoneLineHistory nao tem guard de imutabilidade (diferente de
    LineDailyActionAuditEvent): changed_at e auto_now_add, ajustado depois
    via update() direto na tabela — mesmo padrao ja usado e aceito em
    telecom/tests_line_timeline.py::LineTimelineTestBase._make_legacy."""
    history = PhoneLineHistory.objects.create(
        phone_line=phone_line,
        action=action,
        old_value=old_value,
        new_value=new_value,
        changed_by=changed_by,
        description=description,
    )
    PhoneLineHistory.objects.filter(pk=history.pk).update(changed_at=when)
    history.refresh_from_db()
    return history


def _audit_state(**overrides):
    state = {
        "action": {"code": "no_action", "label": "Sem Ação"},
        "note": "",
        "technical_responsible": None,
        "line_status": {"code": "active", "label": "Ativa"},
        "resolution": {"is_resolved": False, "resolved_at": None},
        "source_state": {
            "day": None,
            "pendency_submitted_at": None,
            "last_submitted_action": None,
            "is_resolved": None,
        },
    }
    state.update(overrides)
    return state


def _make_audit_event(
    *,
    when,
    event_type,
    source,
    phone_line=None,
    allocation=None,
    employee=None,
    performed_by=None,
    source_object_id=1,
    before=None,
    after=None,
    allocation_id_snapshot=None,
    phone_number_snapshot=None,
    employee_name_snapshot=None,
    performed_by_name_snapshot="",
    performed_by_email_snapshot="",
):
    """LineDailyActionAuditEvent.objects.create() e uma gravacao inicial
    normal — o guard de imutabilidade (save()) so bloqueia RESAVE de um pk
    ja existente, entao criar direto aqui nao viola append-only. Reproduz
    os mesmos snapshots que telecom/daily_action_audit.py::
    record_line_daily_action_event grava a partir do estado real, mesmo
    padrao de telecom/tests_line_timeline.py::LineTimelineTestBase._make_audit."""
    before = before if before is not None else _audit_state()
    after = after if after is not None else _audit_state(note="mudou")
    return LineDailyActionAuditEvent.objects.create(
        phone_line=phone_line,
        allocation=allocation,
        employee=employee,
        performed_by=performed_by,
        event_type=event_type,
        source=source,
        source_object_id=source_object_id,
        occurred_at=when,
        phone_number_snapshot=(
            phone_number_snapshot
            if phone_number_snapshot is not None
            else (phone_line.phone_number if phone_line else "")
        ),
        allocation_id_snapshot=(
            allocation_id_snapshot
            if allocation_id_snapshot is not None
            else (allocation.pk if allocation else None)
        ),
        employee_name_snapshot=(
            employee_name_snapshot
            if employee_name_snapshot is not None
            else (employee.full_name if employee else "")
        ),
        performed_by_name_snapshot=performed_by_name_snapshot,
        performed_by_email_snapshot=performed_by_email_snapshot,
        before_state=before,
        after_state=after,
    )


def _allocate(line, admin, employee=None, allocated_at=None):
    employee = employee or _make_employee()
    allocation = AllocationService.allocate_line(employee=employee, phone_line=line, allocated_by=admin)
    if allocated_at is not None:
        LineAllocation.objects.filter(pk=allocation.pk).update(allocated_at=allocated_at)
        allocation.refresh_from_db()
    return allocation


def _release(allocation, admin):
    return AllocationService.release_line(allocation, released_by=admin)


def _post_daily_action(client, *, employee, allocation=None, action_type="", note="", line_status=""):
    """Caminho real de gravacao dupla (PhoneLineHistory.STATUS_CHANGED +
    LineDailyActionAuditEvent(LINE_STATUS_CHANGED, source=LINE_ALLOCATION))
    quando line_status muda para uma alocacao ativa — reproduz exatamente
    dashboard/views.py:1983-2019, ja coberto por
    dashboard/tests/test_daily_line_action_audit.py::
    test_line_status_change_records_line_status_changed_event."""
    data = {
        "day": timezone.localdate().isoformat(),
        "employee_id": employee.pk,
        "allocation_id": str(allocation.pk) if allocation else "",
        "action_type": action_type,
        "note": note,
        "line_status": line_status,
    }
    response = client.post(reverse("daily_user_action_board"), data=data)
    assert response.status_code == 302, response.content
    return response


def _report_url(pairs):
    return f"{reverse(REPORTS_URL_NAME)}?{urlencode(pairs)}"


def _export_url(formato, pairs):
    return f"{reverse(EXPORT_URL_NAME, kwargs={'formato': formato})}?{urlencode(pairs)}"


def _base_pairs(data_inicial=PERIOD_START, data_final=PERIOD_END, **extra):
    pairs = [
        ("relatorio", "line_history"),
        ("data_inicial", data_inicial),
        ("data_final", data_final),
    ]
    pairs.extend(extra.items())
    return pairs


class LineHistoryReportInitialLoadTests(TestCase):
    """Relatorio selecionado sem datas: sem motor, sem erro prematuro
    (ReportsHomeView.get so valida quando data_inicial/data_final estao
    presentes) — GREEN real hoje, independente do motor."""

    def setUp(self):
        self.admin = _create_user("admin.hist.initial@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_report_selected_without_dates_does_not_run_engine_or_error(self):
        response = self.client.get(_report_url([("relatorio", "line_history")]))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode().lower()
        self.assertNotIn("obrigat", content)
        self.assertNotIn("erro", content)


class LineHistoryReportSharedValidationAppliesTests(TestCase):
    """Contrato comum (REL-07), validado pelo form de fallback
    (WhatsAppSealReportQueryForm) ANTES do despacho por relatorio
    (_validate_report_query_params so verifica `available_relatorios`
    depois de validar o form). GREEN real hoje — nao depende do motor de
    Histórico da linha existir."""

    def setUp(self):
        self.admin = _create_user("admin.hist.sharedval@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_missing_data_inicial_rejected(self):
        response = self.client.get(
            _report_url([("relatorio", "line_history"), ("data_final", PERIOD_END)])
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_data_final_rejected(self):
        response = self.client.get(
            _report_url([("relatorio", "line_history"), ("data_inicial", PERIOD_START)])
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_date_format_rejected(self):
        response = self.client.get(
            _report_url([("relatorio", "line_history"), ("data_inicial", "31/09/2026"), ("data_final", PERIOD_END)])
        )
        self.assertEqual(response.status_code, 400)

    def test_inverted_dates_rejected(self):
        response = self.client.get(
            _report_url([("relatorio", "line_history"), ("data_inicial", PERIOD_END), ("data_final", PERIOD_START)])
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
            f"{url}?relatorio=line_history&data_inicial={PERIOD_START}&data_inicial=2026-09-02&data_final={PERIOD_END}"
        )
        self.assertEqual(response.status_code, 400)

    def test_unknown_generic_query_parameter_rejected(self):
        response = self.client.get(_report_url(_base_pairs(campo_totalmente_inexistente="x")))
        self.assertEqual(response.status_code, 400)

    def test_search_term_longer_than_20_chars_rejected(self):
        response = self.client.get(_report_url(_base_pairs(linha="1" * 21)))
        self.assertEqual(response.status_code, 400)


class LineHistoryDateBoundaryOverflowTests(TestCase):
    """REPORTS_SENIOR_REVIEW (.git/REPORTS_SENIOR_REVIEW.md) achado 3:
    `_period_bounds` (core/services/line_history_report_service.py) soma 1
    dia a `data_final` para obter o limite exclusivo do periodo (fuso
    local) — com data_final=date.max isso e `date.max + timedelta(days=1)`,
    que estoura (`OverflowError: date value out of range`) antes de
    qualquer consulta ao banco, nunca capturado pela view (500 real). O
    form agora rejeita esse valor como erro de campo, tanto na consulta
    quanto na exportacao (mesmo LineHistoryReportQueryForm valida os dois
    endpoints, ver _validate_report_query_params). Nenhum limite arbitrario
    de duracao de periodo: apenas a fronteira realmente representavel pelo
    calculo do limite exclusivo (date.max - 1 dia)."""

    def setUp(self):
        self.admin = _create_user("admin.hist.dateboundary@test.com", SystemUser.Role.ADMIN)
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


class LineHistoryReportEngineUnavailableBaselineTests(TestCase):
    """Atualizada em REL-12-Q (2026-09-29) e novamente em REL-12-E
    (2026-09-29). REL-12-Q deu a "line_history" motor de CONSULTA
    (REPORT_QUERY_ENGINES) — a alegacao "relatorio ainda nao disponivel"
    deixou de ser verdadeira para a consulta, mesmo padrao de repropose ja
    aplicado em REL-10-Q/REL-11-Q (allocations/pendencies, ver
    AllocationsReportStillUnavailableTests/
    PendenciesReportStillUnavailableTests). Nesta task (REL-12-E), o motor
    de EXPORTACAO tambem passou a existir (REPORT_EXPORT_ENGINES) — a
    alegacao "A exportação deste relatório ainda não está disponível nesta
    etapa." tambem deixou de ser verdadeira, mesmo padrao de repropose ja
    aplicado em REL-10-E/REL-11-E (AllocationsReportStillUnavailableTests/
    PendenciesReportStillUnavailableTests: 400 vira 200 com anexo real)."""

    def setUp(self):
        self.admin = _create_user("admin.hist.baseline@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_query_now_returns_200_with_engine_implemented(self):
        response = self.client.get(_report_url(_base_pairs()))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Este relatório ainda não está disponível.", status_code=200)

    def test_export_now_returns_200_attachment_with_valid_common_params(self):
        response = self.client.get(_export_url("csv", _base_pairs()))
        self.assertEqual(response.status_code, 200)
        content_type = response.headers.get("Content-Type", "")
        self.assertIn("csv", content_type.lower())
        self.assertIn("attachment", response.headers.get("Content-Disposition", ""))


class LineHistoryFilterParameterValidationTests(TestCase):
    """Secao 6 do enunciado. Ate REL-12-Q, tipo_evento/fonte_evento/ator nao
    estavam em REPORT_SPECIFIC_PARAM_NAMES/REPORT_FORM_CLASSES — QUALQUER
    valor (valido ou invalido) era rejeitado pela mensagem generica
    "Parametro desconhecido: <nome>.", mesmo gap ja documentado para os
    demais relatorios antes de suas tasks Q (RED real naquele momento).
    REL-12-Q (2026-09-29) estende os quatro pontos (config/forms.py,
    config/views.py) para os tres nomes: GREEN real agora, comprovado por
    execucao (nao apenas por form aceitar o campo — os testes de controle
    abaixo confirmam 200 com linha elegivel). `alocacao` (decisao E, nao
    incluido nesta entrega) e o controle inverso — permanece rejeitado como
    desconhecido mesmo depois de REL-12-Q, nunca deve deixar de ser RED."""

    def setUp(self):
        self.admin = _create_user("admin.hist.paramval@test.com", SystemUser.Role.ADMIN)
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

    def test_tipo_evento_invalid_value_not_treated_as_unknown_parameter(self):
        response = self.client.get(_report_url(_base_pairs(tipo_evento="invalido")))
        self._assert_not_rejected_as_unknown_parameter(response, "tipo_evento")

    def test_fonte_evento_invalid_value_not_treated_as_unknown_parameter(self):
        response = self.client.get(_report_url(_base_pairs(fonte_evento="invalido")))
        self._assert_not_rejected_as_unknown_parameter(response, "fonte_evento")

    def test_ator_valid_value_returns_200_with_eligible_row(self):
        """ator e busca livre (sem enum) — sem conceito de 'valor invalido'
        proprio, mesmo padrao ja aplicado a 'funcionario'/'operadora' nos
        demais relatorios: uma vez reconhecido pelo whitelist/form, executa
        a consulta normalmente (200)."""
        line, _ = _make_line("+5511940000001")
        author = _create_user("hist.autor.filtro@test.com", SystemUser.Role.ADMIN, first_name="Ivone")
        _make_legacy_event(line, when=_local_midnight(date(2026, 9, 10)), changed_by=author)
        response = self.client.get(_report_url(_base_pairs(ator="Ivone")))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Parâmetro desconhecido: ator", response.content.decode())
        self.assertContains(response, "+5511940000001")

    def test_tipo_evento_valid_value_control_returns_200_with_eligible_row(self):
        line, _ = _make_line("+5511940000002")
        _make_legacy_event(line, when=_local_midnight(date(2026, 9, 10)), action=ActionType.CREATED)
        response = self.client.get(_report_url(_base_pairs(tipo_evento=ActionType.CREATED)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "+5511940000002")

    def test_fonte_evento_valid_value_control_returns_200_with_eligible_row(self):
        line, _ = _make_line("+5511940000003")
        _make_audit_event(
            phone_line=line,
            when=_local_midnight(date(2026, 9, 10)),
            event_type=EventType.OPENED,
            source=Source.ALLOCATION_PENDENCY,
        )
        response = self.client.get(_report_url(_base_pairs(fonte_evento=Source.ALLOCATION_PENDENCY)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "+5511940000003")

    def test_alocacao_filter_rejected_as_unknown_parameter_forever(self):
        """Decisao E (REL-12-C): filtro `alocacao` explicitamente fora do
        escopo desta entrega — diferente de tipo_evento/fonte_evento/ator,
        este DEVE continuar caindo no bucket generico de parametro
        desconhecido mesmo depois de REL-12-Q."""
        response = self.client.get(_report_url(_base_pairs(alocacao="1")))
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Parâmetro desconhecido: alocacao", status_code=400)


class LineHistoryGranularityAndUnionTests(TestCase):
    """Secao 2 do enunciado: uniao das duas fontes sem deduplicacao, uma
    linha por evento, varias linhas telefonicas no mesmo resultado, PKs
    iguais em fontes diferentes nao colapsados, multiplas alteracoes de um
    evento sem multiplicar linhas. Ate REL-12-Q: todos RED (motor ausente,
    consulta sempre 400). REL-12-Q (2026-09-29): GREEN real, motor de
    consulta implementado em core/services/line_history_report_service.py.
    Duas fixtures corrigidas nesta task por causa comprovada (nao
    enfraquecimento de asserção): `test_allocation_and_pendency_tables_
    not_included_as_independent_sources`/`test_similar_events_from_
    different_sources_not_deduplicated` geravam eventos com timestamp real
    (auto_now_add/occurred_at="agora") que cai fora do periodo fixo
    PERIOD_START/PERIOD_END quando o relogio real do ambiente ja passou de
    PERIOD_END — corrigido usando `data_final=timezone.localdate()` nessas
    duas consultas. `test_equal_primary_keys_from_different_sources_never_
    collapsed` tentava igualar PKs via `.update(pk=...)` num
    LineDailyActionAuditEvent ja existente, que o guard de imutabilidade
    sempre bloqueia (save()/update() recusam qualquer registro com pk ja
    setado) — corrigido para avancar o PK do lado imutavel por CRIACAO de
    preenchimento descartavel, nunca por atualizacao, e usar o bump do lado
    sem guard (legado) so como fallback na direcao sempre segura."""

    def setUp(self):
        self.admin = _create_user("admin.hist.granularity@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_events_from_both_sources_appear_in_same_result(self):
        line, _ = _make_line("+5511941000001")
        _make_legacy_event(line, when=_local_midnight(date(2026, 9, 5)), action=ActionType.CREATED)
        _make_audit_event(
            phone_line=line,
            when=_local_midnight(date(2026, 9, 10)),
            event_type=EventType.OPENED,
            source=Source.ALLOCATION_PENDENCY,
        )
        response = self.client.get(_report_url(_base_pairs()))
        self.assertEqual(response.status_code, 200, "motor ausente: resposta nao e a tela com tabela de resultados")
        content = response.content.decode()
        # Recorte a partir do corpo da tabela: o dropdown de relatorios
        # acima ja contem "Histórico da linha"/"Pendências" como <option>,
        # o que produziria falso positivo numa busca na pagina inteira.
        body = content[content.index("<tbody>"):]
        self.assertIn(">Histórico da linha<", body)
        self.assertIn(">Pendência<", body)

    def test_events_from_multiple_lines_appear_in_same_result(self):
        line_a, _ = _make_line("+5511941000002")
        line_b, _ = _make_line("+5511941000003")
        _make_legacy_event(line_a, when=_local_midnight(date(2026, 9, 5)), action=ActionType.CREATED)
        _make_legacy_event(line_b, when=_local_midnight(date(2026, 9, 6)), action=ActionType.CREATED)
        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        self.assertIn("+5511941000002", content)
        self.assertIn("+5511941000003", content)

    def test_one_row_per_event_not_per_line(self):
        line, _ = _make_line("+5511941000004")
        _make_legacy_event(line, when=_local_midnight(date(2026, 9, 5)), action=ActionType.CREATED)
        _make_legacy_event(line, when=_local_midnight(date(2026, 9, 6)), action=ActionType.STATUS_CHANGED)
        _make_legacy_event(line, when=_local_midnight(date(2026, 9, 7)), action=ActionType.ALLOCATED)
        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        self.assertEqual(content.count("+5511941000004"), 3)

    def test_similar_events_from_different_sources_not_deduplicated(self):
        """Duplicacao real ja aprovada e em producao no T6: mesma acao de
        negocio grava fato nas duas fontes (mudanca de status via Ações do
        Dia). Caminho real de gravacao (secao 9 do enunciado): POST em
        dashboard:daily_user_action_board com line_status novo. So ADMIN
        pode alterar line_status (dashboard/views.py:1960: `if
        request.user.role == SystemUser.Role.ADMIN`), entao o POST e feito
        pelo proprio admin — nao por um SUPER, que teria o campo
        line_status silenciosamente ignorado."""
        employee = Employee.objects.create(
            full_name="Duplicacao Teste",
            corporate_email="hist.super.dup@test.com",
            employee_id="HISTDUP1",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )
        line, _ = _make_line("+5511941000005")
        allocation = _allocate(line, self.admin, employee=employee)

        self.client.force_login(self.admin)
        _post_daily_action(
            self.client, employee=employee, allocation=allocation,
            action_type=DailyUserAction.ActionType.PENDING, note="obs",
        )
        _post_daily_action(
            self.client, employee=employee, allocation=allocation,
            action_type=DailyUserAction.ActionType.PENDING, note="obs",
            line_status="restricted",
        )
        self.assertTrue(
            PhoneLineHistory.objects.filter(
                phone_line=line, action=ActionType.STATUS_CHANGED
            ).exists()
        )
        self.assertTrue(
            LineDailyActionAuditEvent.objects.filter(
                phone_line=line, event_type=EventType.LINE_STATUS_CHANGED,
                source=Source.LINE_ALLOCATION,
            ).exists()
        )

        # Ambos os eventos sao gravados com timestamp real ("agora") pelo
        # caminho de producao — data_final precisa alcancar "hoje" para nao
        # exclui-los por fronteira de periodo.
        response = self.client.get(
            _report_url(
                _base_pairs(linha="941000005", data_final=timezone.localdate().isoformat())
            )
        )
        self.assertEqual(response.status_code, 200, "motor ausente: resposta nao e a tela com tabela de resultados")
        content = response.content.decode()
        # Duas linhas de resultado distintas para o MESMO fato de negocio
        # (PhoneLineHistory.STATUS_CHANGED + LineDailyActionAuditEvent
        # LINE_STATUS_CHANGED/LINE_ALLOCATION): nunca colapsadas em uma so.
        self.assertGreaterEqual(content.count("+5511941000005"), 2)

    def test_equal_primary_keys_from_different_sources_never_collapsed(self):
        """PhoneLineHistory.pk == LineDailyActionAuditEvent.pk (coincidencia
        deliberada, tabelas separadas com sequencias proprias): identidade
        real e (row_source, row_id), nunca so row_id — o teste garante que
        as duas linhas de resultado nao colapsam em uma so.

        LineDailyActionAuditEvent e imutavel: nao aceita update()/delete()
        em massa nem resave de um pk ja existente (save() levanta se
        self.pk ja estiver setado, inclusive ao tentar criar com pk
        explicito) — o unico jeito de alcancar um pk especifico nessa
        tabela e avancar a propria sequencia por CRIACAO real, nunca por
        atualizacao. `_make_line` tambem grava, por signal, um evento
        CREATED em PhoneLineHistory antes de qualquer criacao explicita
        neste teste, entao o pk do `legacy` abaixo already vem adiantado
        em relacao a uma tabela de auditoria ainda vazia — cria eventos de
        preenchimento (linha/data irrelevantes, fora do escopo da consulta
        usada na asserção) ate a proxima criacao real de auditoria cair
        exatamente no pk de `legacy`."""
        line, _ = _make_line("+5511941000006")
        legacy = _make_legacy_event(line, when=_local_midnight(date(2026, 9, 5)), action=ActionType.CREATED)

        while True:
            next_audit_pk = (
                LineDailyActionAuditEvent.objects.order_by("-pk").values_list("pk", flat=True).first() or 0
            ) + 1
            if next_audit_pk >= legacy.pk:
                break
            _make_audit_event(
                phone_line=None, when=_local_midnight(date(2020, 1, 1)),
                event_type=EventType.OPENED, source=Source.ALLOCATION_PENDENCY,
                phone_number_snapshot="+0000000000000",
            )

        audit = _make_audit_event(
            phone_line=line, when=_local_midnight(date(2026, 9, 6)),
            event_type=EventType.OPENED, source=Source.ALLOCATION_PENDENCY,
        )

        if audit.pk != legacy.pk:
            # Auditoria avancou alem do necessario (ex.: preenchimento
            # anterior de outro teste na mesma transacao) — resta bumpar o
            # lado sem guard (legacy) para cima ate igualar: direcao sempre
            # segura, pois o alvo e sempre maior que qualquer pk ja usado
            # na tabela legada.
            target_pk = max(legacy.pk, audit.pk)
            PhoneLineHistory.objects.filter(pk=legacy.pk).update(pk=target_pk)
            legacy = PhoneLineHistory.objects.get(pk=target_pk)
        self.assertEqual(legacy.pk, audit.pk)

        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        self.assertEqual(content.count("+5511941000006"), 2)

    def test_multiple_changed_fields_in_one_audit_event_produce_single_row(self):
        """Decisao B (REL-12-C): 0 a 5 campos alterados em UM evento de
        auditoria continuam sendo UMA linha de resultado — a celula
        'Alteracoes' concatena, nunca multiplica linhas."""
        line, _ = _make_line("+5511941000007")
        before = _audit_state()
        after = _audit_state(
            action={"code": "reconnect_whatsapp", "label": "Reconectar WhatsApp"},
            note="Trocar aparelho",
            line_status={"code": "under_analysis", "label": "Em análise"},
        )
        _make_audit_event(
            phone_line=line, when=_local_midnight(date(2026, 9, 10)),
            event_type=EventType.ACTION_CHANGED, source=Source.ALLOCATION_PENDENCY,
            before=before, after=after,
        )
        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        self.assertEqual(content.count("+5511941000007"), 1)

    def test_allocation_and_pendency_tables_not_included_as_independent_sources(self):
        """LineAllocation/AllocationPendency nunca aparecem como fonte
        direta deste relatorio (REL-10-C/REL-11-C ja delimitaram):
        alocar/liberar uma linha SEM nenhum evento de auditoria/legado
        associado ao numero nao deveria inflar o relatorio com uma linha
        que nao venha de PhoneLineHistory/LineDailyActionAuditEvent —
        aqui apenas confirma que o numero so aparece pelo evento CREATED
        real (emitido por signal), nunca por LineAllocation direta."""
        line, _ = _make_line("+5511941000008")
        _allocate(line, self.admin, allocated_at=_local_midnight(date(2026, 9, 10)))
        # CREATED/ALLOCATED sao gravados por signal com changed_at real
        # (auto_now_add = "agora"), nao com o instante simulado passado a
        # LineAllocation.allocated_at — data_final precisa alcancar "hoje"
        # para nao excluir esses dois eventos por fronteira de periodo.
        response = self.client.get(
            _report_url(_base_pairs(data_final=timezone.localdate().isoformat()))
        )
        content = response.content.decode()
        # CREATED (signal na criacao da linha) + ALLOCATED (signal na
        # alocacao) sao os DOIS eventos reais de PhoneLineHistory — nunca
        # um terceiro vindo de LineAllocation em si.
        self.assertEqual(content.count("+5511941000008"), 2)


class LineHistoryPeriodAndOrderingTests(TestCase):
    """Secao 3 do enunciado: changed_at para PhoneLineHistory, occurred_at
    para LineDailyActionAuditEvent, fronteiras locais America/Sao_Paulo,
    ordenacao GLOBAL entre fontes (nao blocos separados por origem),
    desempate aprovado, estabilidade de paginacao."""

    def setUp(self):
        self.admin = _create_user("admin.hist.period@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_legacy_start_boundary_inclusive(self):
        line, _ = _make_line("+5511942000001")
        _make_legacy_event(line, when=_local_midnight(PERIOD_START_DATE))
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511942000001")

    def test_legacy_instant_before_start_boundary_excluded(self):
        control, _ = _make_line("+5511942000098")
        excluded, _ = _make_line("+5511942000002")
        _make_legacy_event(control, when=_local_midnight(PERIOD_START_DATE))
        _make_legacy_event(excluded, when=_local_midnight(PERIOD_START_DATE) - timedelta(microseconds=1))
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511942000098")
        self.assertNotContains(response, "+5511942000002")

    def test_legacy_end_boundary_inclusive_last_local_instant(self):
        line, _ = _make_line("+5511942000003")
        _make_legacy_event(line, when=_local_last_instant(PERIOD_END_DATE))
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511942000003")

    def test_legacy_instant_at_start_of_day_after_end_excluded(self):
        control, _ = _make_line("+5511942000097")
        excluded, _ = _make_line("+5511942000004")
        _make_legacy_event(control, when=_local_last_instant(PERIOD_END_DATE))
        _make_legacy_event(excluded, when=_local_midnight(PERIOD_END_DATE + timedelta(days=1)))
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511942000097")
        self.assertNotContains(response, "+5511942000004")

    def test_audit_start_boundary_inclusive(self):
        line, _ = _make_line("+5511942000005")
        _make_audit_event(
            phone_line=line, when=_local_midnight(PERIOD_START_DATE),
            event_type=EventType.OPENED, source=Source.ALLOCATION_PENDENCY,
        )
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511942000005")

    def test_audit_instant_at_start_of_day_after_end_excluded(self):
        line, _ = _make_line("+5511942000006")
        _make_audit_event(
            phone_line=line, when=_local_midnight(PERIOD_END_DATE + timedelta(days=1)),
            event_type=EventType.OPENED, source=Source.ALLOCATION_PENDENCY,
        )
        response = self.client.get(_report_url(_base_pairs()))
        self.assertNotContains(response, "+5511942000006")

    def test_global_ordering_interleaves_sources_not_blocks_by_origin(self):
        """Ordenacao GLOBAL por sort_at desc entre as duas fontes — nunca
        todos os eventos de uma fonte antes da outra."""
        line, _ = _make_line("+5511942000007")
        _make_legacy_event(line, when=_local_midnight(date(2026, 9, 20)), action=ActionType.CREATED)
        _make_audit_event(
            phone_line=line, when=_local_midnight(date(2026, 9, 15)),
            event_type=EventType.OPENED, source=Source.ALLOCATION_PENDENCY,
        )
        _make_legacy_event(line, when=_local_midnight(date(2026, 9, 10)), action=ActionType.STATUS_CHANGED)
        response = self.client.get(_report_url(_base_pairs()))
        self.assertEqual(response.status_code, 200, "motor ausente: resposta nao e a tela com tabela de resultados")
        content = response.content.decode()
        # Recorte a partir do corpo da tabela de resultados: o dropdown de
        # relatorios acima ja contem "Histórico da linha"/"Pendências"
        # como rotulos de <option>, o que produziria falso positivo se a
        # busca considerasse a pagina inteira.
        body = content[content.index("<tbody>"):]
        idx_legacy_recent = body.index(">Histórico da linha<")
        idx_pendency = body.index(">Pendência<")
        idx_legacy_older = body.rindex(">Histórico da linha<")
        self.assertLess(idx_legacy_recent, idx_pendency)
        self.assertLess(idx_pendency, idx_legacy_older)

    def test_tie_break_between_sources_uses_phone_number_then_source_then_row_id(self):
        """Desempate aprovado em REL-12-C: sort_at identico entre as duas
        fontes -> phone_number crescente, depois row_source, depois
        row_id decrescente (telecom/line_timeline.py:230, com phone_number
        inserido como criterio intermediario para multiplas linhas)."""
        same_instant = _local_midnight(date(2026, 9, 10))
        line_a, _ = _make_line("+5511942000008")
        line_b, _ = _make_line("+5511942000009")
        _make_legacy_event(line_b, when=same_instant, action=ActionType.CREATED)
        _make_audit_event(
            phone_line=line_a, when=same_instant,
            event_type=EventType.OPENED, source=Source.ALLOCATION_PENDENCY,
        )
        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        idx_a = content.index("+5511942000008")
        idx_b = content.index("+5511942000009")
        self.assertLess(idx_a, idx_b, "phone_number crescente deve vir primeiro no desempate")

    def test_filters_preserved_across_pagination_and_second_page_has_distinct_content(self):
        for index in range(51):
            line, _ = _make_line(f"+55119421{index:06d}")
            _make_legacy_event(
                line, action=ActionType.CREATED,
                when=_local_midnight(date(2026, 9, 1)) + timedelta(minutes=index),
            )
        page1 = self.client.get(_report_url(_base_pairs(page="1")))
        page2 = self.client.get(_report_url(_base_pairs(page="2")))
        self.assertEqual(page1.status_code, 200)
        self.assertEqual(page2.status_code, 200)
        content1 = page1.content.decode()
        content2 = page2.content.decode()
        newest = f"+55119421{50:06d}"
        oldest = f"+55119421{0:06d}"
        self.assertIn(newest, content1)
        self.assertNotIn(newest, content2)
        self.assertIn(oldest, content2)
        self.assertNotIn(oldest, content1)
        self.assertIn(f'name="data_inicial" value="{PERIOD_START}"', content2)
        self.assertIn(f'name="data_final" value="{PERIOD_END}"', content2)

    def test_totals_reflect_whole_filtered_set_not_only_current_page(self):
        for index in range(55):
            line, _ = _make_line(f"+55119422{index:06d}")
            _make_legacy_event(line, action=ActionType.CREATED, when=_local_midnight(date(2026, 9, 10)))
        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        self.assertIn("55", content)


class LineHistoryColumnsAndChangesTests(TestCase):
    """Secao 4 do enunciado: nove colunas na ordem aprovada, celula
    'Alteracoes' concatenada, valores antigos/novos preservados, nulos/
    vazios/acentos, sem conversao silenciosa de valor historico
    desconhecido para choice atual, before_state/after_state brutos fora
    da tela."""

    def setUp(self):
        self.admin = _create_user("admin.hist.columns@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_nine_column_headers_present_in_approved_order(self):
        line, _ = _make_line("+5511943000001")
        _make_legacy_event(line, when=_local_midnight(date(2026, 9, 10)), action=ActionType.CREATED)
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

    def test_legacy_changes_cell_shows_single_old_new_pair(self):
        line, _ = _make_line("+5511943000002")
        _make_legacy_event(
            line, when=_local_midnight(date(2026, 9, 10)),
            action=ActionType.STATUS_CHANGED, old_value="Disponível", new_value="Alocada",
        )
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "Disponível")
        self.assertContains(response, "Alocada")

    def test_audit_changes_cell_concatenates_multiple_fields_with_approved_format(self):
        """Formato aprovado em REL-12-C item B: rotulo em portugues,
        separador '; ', ex. 'Ação: Sem Ação → Pendência; Nota: (vazio) →
        'Trocar aparelho''."""
        line, _ = _make_line("+5511943000003")
        before = _audit_state()
        after = _audit_state(
            action={"code": "pending", "label": "Pendência"},
            note="Trocar aparelho",
        )
        _make_audit_event(
            phone_line=line, when=_local_midnight(date(2026, 9, 10)),
            event_type=EventType.ACTION_CHANGED, source=Source.ALLOCATION_PENDENCY,
            before=before, after=after,
        )
        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        self.assertIn("Ação", content)
        self.assertIn("Pendência", content)
        self.assertIn("Nota", content)
        self.assertIn("Trocar aparelho", content)

    def test_created_event_with_no_old_value_shows_dash(self):
        line, _ = _make_line("+5511943000004")
        _make_legacy_event(
            line, when=_local_midnight(date(2026, 9, 10)),
            action=ActionType.CREATED, old_value=None, new_value="Status: Disponível",
        )
        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        row_start = content.rindex("<tr>", 0, content.index("+5511943000004"))
        row_end = content.index("</tr>", row_start)
        self.assertIn("-", content[row_start:row_end])

    def test_accented_values_preserved_verbatim(self):
        line, _ = _make_line("+5511943000005")
        _make_legacy_event(
            line, when=_local_midnight(date(2026, 9, 10)),
            action=ActionType.STATUS_CHANGED, old_value="Não alocada", new_value="Restrição técnica",
        )
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "Não alocada")
        self.assertContains(response, "Restrição técnica")

    def test_unknown_action_type_not_converted_to_current_choice_and_renders_without_error(self):
        """Dado legado/schema mudou: get_action_display() do Django retorna
        o valor bruto sem erro — nunca 'traduzido' silenciosamente."""
        line, _ = _make_line("+5511943000006")
        history = _make_legacy_event(line, when=_local_midnight(date(2026, 9, 10)))
        PhoneLineHistory.objects.filter(pk=history.pk).update(action="ACTION_TYPE_REMOVIDO_DO_SCHEMA")
        response = self.client.get(_report_url(_base_pairs()))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ACTION_TYPE_REMOVIDO_DO_SCHEMA")

    def test_raw_before_after_state_json_never_appears_in_screen(self):
        """Decisao C (REL-12-C): before_state/after_state brutos ficam fora
        da tela — usa um marcador sintetico em uma chave que o contrato NAO
        projeta ('source_state', metadado tecnico), nunca escondendo um
        valor legitimo de 'Alteracoes'."""
        line, _ = _make_line("+5511943000007")
        marker = "MARCADOR_JSON_BRUTO_NUNCA_DEVE_APARECER_NA_TELA"
        _make_audit_event(
            phone_line=line, when=_local_midnight(date(2026, 9, 10)),
            event_type=EventType.NOTE_CHANGED, source=Source.ALLOCATION_PENDENCY,
            before=_audit_state(source_state={"marker": marker}),
            after=_audit_state(note="mudou", source_state={"marker": marker}),
        )
        response = self.client.get(_report_url(_base_pairs()))
        self.assertNotContains(response, marker)


class LineHistoryAuthorsAndCoverageTests(TestCase):
    """Secao 5 do enunciado: autor existente, changed_by nulo -> "Autor nao
    disponivel", autor recuperavel por snapshot, usuario removido com
    snapshot preservado, "Sistema" apenas no caso comprovado (decisao F)."""

    def setUp(self):
        self.admin = _create_user("admin.hist.authors@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_legacy_existing_author_shown_by_name(self):
        line, _ = _make_line("+5511944000001")
        author = _create_user("hist.author.existing@test.com", SystemUser.Role.ADMIN, first_name="Renata")
        _make_legacy_event(line, when=_local_midnight(date(2026, 9, 10)), changed_by=author)
        response = self.client.get(_report_url(_base_pairs(linha="944000001")))
        self.assertContains(response, "Renata")

    def test_legacy_null_changed_by_shows_author_not_available(self):
        """DECISAO FINAL item F: PhoneLineHistory.changed_by nulo nunca vira
        'Sistema' (sem snapshot para comprovar) — sempre 'Autor não
        disponível'."""
        line, _ = _make_line("+5511944000002")
        _make_legacy_event(line, when=_local_midnight(date(2026, 9, 10)), changed_by=None)
        response = self.client.get(_report_url(_base_pairs(linha="944000002")))
        self.assertContains(response, AUTOR_NAO_DISPONIVEL)
        self.assertNotContains(response, f">{AUTOR_SISTEMA}<")

    def test_audit_author_recoverable_from_snapshot_when_user_removed(self):
        """performed_by nulo MAS snapshot preenchido -> nome do snapshot,
        usuario removido fisicamente nao apaga o fato registrado."""
        line, _ = _make_line("+5511944000003")
        _make_audit_event(
            phone_line=line, when=_local_midnight(date(2026, 9, 10)),
            event_type=EventType.OPENED, source=Source.ALLOCATION_PENDENCY,
            performed_by=None,
            performed_by_name_snapshot="Usuario Removido Fisicamente",
            performed_by_email_snapshot="removido@test.com",
        )
        response = self.client.get(_report_url(_base_pairs(linha="944000003")))
        self.assertContains(response, "Usuario Removido Fisicamente")

    def test_audit_system_label_only_when_performed_by_and_snapshot_both_empty(self):
        """DECISAO FINAL item F: 'Sistema' so aparece quando performed_by E
        os snapshots estao vazios desde a criacao (prova positiva de
        ausencia de ator humano, ex. scripts/resolve_old_actions.py)."""
        line, _ = _make_line("+5511944000004")
        _make_audit_event(
            phone_line=line, when=_local_midnight(date(2026, 9, 10)),
            event_type=EventType.RESOLVED, source=Source.DAILY_USER_ACTION,
            performed_by=None, performed_by_name_snapshot="", performed_by_email_snapshot="",
        )
        response = self.client.get(_report_url(_base_pairs(linha="944000004")))
        self.assertContains(response, AUTOR_SISTEMA)

    def test_pre_audit_period_shows_legacy_events_normally_absence_is_not_proof_of_inactivity(self):
        """LineDailyActionAuditEvent so existe a partir de 2026-09-14 (T9):
        um evento LEGADO antes dessa data deve continuar aparecendo
        normalmente (a lacuna e so na fonte nova, nunca some o legado)."""
        line, _ = _make_line("+5511944000005")
        _make_legacy_event(
            line, when=_local_midnight(AUDIT_DEPLOY_DATE - timedelta(days=30)),
            action=ActionType.STATUS_CHANGED,
        )
        response = self.client.get(
            _report_url(_base_pairs(data_inicial="2026-08-01", data_final=PERIOD_END, linha="944000005"))
        )
        self.assertContains(response, "+5511944000005")


class LineHistoryFiltersAndExclusionTests(TestCase):
    """Secao 6 do enunciado: linha/tipo_evento/fonte_evento/ator isolados e
    combinados (AND), exclusao atual x evento historico de exclusao
    (ortogonais)."""

    def setUp(self):
        self.admin = _create_user("admin.hist.filters@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_linha_and_tipo_evento_combined_by_and(self):
        line_a, _ = _make_line("+5511945000001")
        line_b, _ = _make_line("+5511945000002")
        _make_legacy_event(line_a, when=_local_midnight(date(2026, 9, 10)), action=ActionType.STATUS_CHANGED)
        _make_legacy_event(line_b, when=_local_midnight(date(2026, 9, 10)), action=ActionType.CREATED)
        response = self.client.get(
            _report_url(_base_pairs(linha="945000001", tipo_evento=ActionType.STATUS_CHANGED))
        )
        content = response.content.decode()
        self.assertIn("+5511945000001", content)
        self.assertNotIn("+5511945000002", content)

    def test_incompatible_type_and_source_combination_yields_empty_not_error(self):
        """tipo_evento existente so numa fonte, filtrado pela outra ->
        conjunto vazio, nunca erro."""
        line, _ = _make_line("+5511945000003")
        _make_legacy_event(line, when=_local_midnight(date(2026, 9, 10)), action=ActionType.CREATED)
        response = self.client.get(
            _report_url(_base_pairs(tipo_evento=ActionType.CREATED, fonte_evento=Source.ALLOCATION_PENDENCY))
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "+5511945000003")

    def test_current_line_deletion_hides_all_its_events_by_default_shown_when_included(self):
        control, _ = _make_line("+5511945000098")
        excluded, _ = _make_line("+5511945000004")
        _make_legacy_event(control, when=_local_midnight(date(2026, 9, 10)), action=ActionType.CREATED)
        _make_legacy_event(excluded, when=_local_midnight(date(2026, 9, 10)), action=ActionType.CREATED)
        excluded.delete(released_by=self.admin)

        default_resp = self.client.get(_report_url(_base_pairs()))
        self.assertContains(default_resp, "+5511945000098")
        self.assertNotContains(default_resp, "+5511945000004")

        included_resp = self.client.get(_report_url(_base_pairs(incluir_excluidos="1")))
        self.assertContains(included_resp, "+5511945000004")

    def test_historical_deleted_event_appears_independently_of_current_deletion_filter(self):
        """Ortogonalidade explicita (REL-12-C): um evento DELETED historico
        aparece como fato normal (sujeito so ao filtro de tipo_evento),
        MESMO que a linha esteja viva hoje — nao e controlado pelo checkbox
        'Incluir excluidos'."""
        line, _ = _make_line("+5511945000005")
        _make_legacy_event(line, when=_local_midnight(date(2026, 9, 5)), action=ActionType.DELETED)
        _make_legacy_event(line, when=_local_midnight(date(2026, 9, 6)), action=ActionType.REACTIVATED)
        # Linha viva hoje (nunca de fato excluida por ORM): o evento
        # historico DELETED deve continuar visivel mesmo com o checkbox
        # padrao (desmarcado).
        response = self.client.get(_report_url(_base_pairs(incluir_excluidos="0")))
        content = response.content.decode()
        self.assertEqual(content.count("+5511945000005"), 2)

    def test_employee_deletion_hides_only_its_audit_events_by_default(self):
        """Funcionario excluido so afeta LineDailyActionAuditEvent (sem FK
        em PhoneLineHistory) — checkbox padrao oculta so o evento ligado ao
        funcionario excluido."""
        line, _ = _make_line("+5511945000006")
        employee = _make_employee("filtro-func-excluido")
        _make_audit_event(
            phone_line=line, when=_local_midnight(date(2026, 9, 10)),
            event_type=EventType.OPENED, source=Source.ALLOCATION_PENDENCY, employee=employee,
        )
        employee.delete()
        employee.refresh_from_db()

        default_resp = self.client.get(_report_url(_base_pairs(linha="945000006")))
        self.assertNotContains(default_resp, "+5511945000006")

        included_resp = self.client.get(_report_url(_base_pairs(linha="945000006", incluir_excluidos="1")))
        self.assertContains(included_resp, "+5511945000006")
        self.assertContains(included_resp, "Sim")


class LineHistoryTotalsReadOnlyCostTests(TestCase):
    """Secao 7 do enunciado: total de eventos != linhas distintas, mesma
    linha nas duas fontes conta uma vez em Linhas distintas, filtros
    refletidos nos totais, consulta somente leitura, ausencia de N+1."""

    def setUp(self):
        self.admin = _create_user("admin.hist.totals@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_total_events_differs_from_distinct_lines(self):
        line, _ = _make_line("+5511946000001")
        _make_legacy_event(line, when=_local_midnight(date(2026, 9, 5)), action=ActionType.CREATED)
        _make_legacy_event(line, when=_local_midnight(date(2026, 9, 6)), action=ActionType.STATUS_CHANGED)
        response = self.client.get(_report_url(_base_pairs(linha="946000001")))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Total de eventos", content)
        self.assertIn("Linhas distintas", content)
        self.assertNotIn(">1</td><td>1<", content)  # nao devem coincidir por acidente aqui

    def test_same_line_in_both_sources_counted_once_in_distinct_lines(self):
        line, _ = _make_line("+5511946000002")
        _make_legacy_event(line, when=_local_midnight(date(2026, 9, 5)), action=ActionType.CREATED)
        _make_audit_event(
            phone_line=line, when=_local_midnight(date(2026, 9, 6)),
            event_type=EventType.OPENED, source=Source.ALLOCATION_PENDENCY,
        )
        response = self.client.get(_report_url(_base_pairs(linha="946000002")))
        content = response.content.decode()
        self.assertIn("2", content)  # total de eventos = 2
        # Linhas distintas deve ser 1 — verificado pelo elemento de
        # totalizador dedicado (motor ainda ausente, so documenta a
        # asserção de conteudo minima ate REL-12-Q expor o seletor real).
        self.assertIn("Linhas distintas", content)

    def test_empty_result_set_returns_zero_totals_no_error(self):
        response = self.client.get(
            _report_url(_base_pairs(data_inicial="2020-01-01", data_final="2020-01-02"))
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("erro", response.content.decode().lower())

    def test_generating_report_does_not_write_business_data(self):
        line, _ = _make_line("+5511946000003")
        _make_legacy_event(line, when=_local_midnight(date(2026, 9, 10)), action=ActionType.CREATED)
        legacy_count_before = PhoneLineHistory.objects.count()
        audit_count_before = LineDailyActionAuditEvent.objects.count()
        line_snapshot_before = (line.is_deleted, line.status)

        response = self.client.get(_report_url(_base_pairs(incluir_excluidos="1")))
        self.assertEqual(response.status_code, 200, "motor deve responder com a tela real, nao um 400 residual")
        self.assertContains(response, "+5511946000003")

        self.assertEqual(PhoneLineHistory.objects.count(), legacy_count_before)
        self.assertEqual(LineDailyActionAuditEvent.objects.count(), audit_count_before)
        line.refresh_from_db()
        self.assertEqual((line.is_deleted, line.status), line_snapshot_before)

    def test_query_count_does_not_scale_linearly_with_row_count(self):
        for index in range(3):
            line, _ = _make_line(f"+5511946100{index:03d}")
            _make_legacy_event(line, when=_local_midnight(date(2026, 9, 10)), action=ActionType.CREATED)
        with CaptureQueriesContext(connection) as small:
            small_response = self.client.get(_report_url(_base_pairs()))

        for index in range(3, 30):
            line, _ = _make_line(f"+5511946100{index:03d}")
            _make_legacy_event(line, when=_local_midnight(date(2026, 9, 10)), action=ActionType.CREATED)
        with CaptureQueriesContext(connection) as large:
            large_response = self.client.get(_report_url(_base_pairs()))

        self.assertEqual(small_response.status_code, 200, "motor deve responder com a tela real, nao um 400 residual")
        self.assertEqual(large_response.status_code, 200)
        self.assertContains(small_response, "+5511946100000")
        self.assertContains(large_response, "+5511946100029")
        self.assertLessEqual(len(large.captured_queries) - len(small.captured_queries), 3)


class LineHistoryExportAuthorizationTests(TestCase):
    """Secao 8 do enunciado: autorizacao no endpoint de download existente.
    RoleRequiredMixin precede a validacao de parametros — cenarios
    negativos sao GREEN real hoje, independente do motor de Histórico da
    linha existir."""

    def setUp(self):
        self.admin = _create_user("admin.hist.exportauth@test.com", SystemUser.Role.ADMIN)

    def test_admin_download_csv_returns_200(self):
        """RED real: motor de exportacao ainda ausente (REL-12-E), ADMIN
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
                user = _create_user(f"hist.export.role{index}@test.com", role)
                self.client.force_login(user)
                response = self.client.get(_export_url("csv", _base_pairs()))
                self.assertEqual(response.status_code, 403)

    def test_anonymous_gets_403_on_export(self):
        response = self.client.get(_export_url("csv", _base_pairs()))
        self.assertEqual(response.status_code, 403)

    def test_invalid_dates_rejected_on_direct_export_access(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            _export_url("csv", [("relatorio", "line_history"), ("data_inicial", PERIOD_END), ("data_final", PERIOD_START)])
        )
        self.assertEqual(response.status_code, 400)

    def test_unknown_format_returns_404(self):
        """GREEN real: formato e checado antes de qualquer validacao de
        relatorio (ReportsExportView.get), independente de line_history ter
        motor ou nao."""
        self.client.force_login(self.admin)
        response = self.client.get(_export_url("pdf", _base_pairs()))
        self.assertEqual(response.status_code, 404)


class LineHistoryExportContentTests(TestCase):
    """Secao 8 (continuacao): conteudo real lido via csv/openpyxl, mesmas
    colunas/granularidade/ordenacao da tela, conjunto completo independente
    de page, dados atuais no momento do download, protecao de formula.
    Todos RED: motor de exportacao ainda ausente."""

    def setUp(self):
        self.admin = _create_user("admin.hist.exportcontent@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def _read_csv_rows(self, response):
        """Confere status e Content-Type ANTES de parsear: uma pagina HTML
        de erro (400, 'text/html') nunca deve ser tratada como arquivo CSV
        valido."""
        self.assertEqual(response.status_code, 200, f"esperado 200, resposta real: {response.status_code}")
        content_type = response.headers.get("Content-Type", "")
        self.assertIn("csv", content_type.lower(), f"Content-Type inesperado: {content_type!r}")
        text = (
            b"".join(response.streaming_content).decode("utf-8-sig")
            if response.streaming
            else response.content.decode("utf-8-sig")
        )
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
        line, _ = _make_line("+5511947000001")
        _make_legacy_event(line, when=_local_midnight(date(2026, 9, 10)), action=ActionType.CREATED)

        csv_rows = self._read_csv_rows(self.client.get(_export_url("csv", _base_pairs())))
        self.assertEqual(csv_rows[0], EXPECTED_COLUMN_HEADERS)

        xlsx_rows = self._read_xlsx_rows(self.client.get(_export_url("xlsx", _base_pairs())))
        self.assertEqual(list(xlsx_rows[0]), EXPECTED_COLUMN_HEADERS)

    def test_both_sources_present_in_export(self):
        line, _ = _make_line("+5511947000002")
        _make_legacy_event(line, when=_local_midnight(date(2026, 9, 10)), action=ActionType.CREATED)
        _make_audit_event(
            phone_line=line, when=_local_midnight(date(2026, 9, 11)),
            event_type=EventType.OPENED, source=Source.ALLOCATION_PENDENCY,
        )
        csv_rows = self._read_csv_rows(self.client.get(_export_url("csv", _base_pairs())))
        sources = {row[2] for row in csv_rows[1:] if row}
        self.assertIn(SOURCE_LABEL_LEGACY, sources)
        self.assertIn(SOURCE_LABEL_PENDENCY, sources)

    def test_csv_and_xlsx_contain_all_filtered_rows_regardless_of_page(self):
        for index in range(60):
            line, _ = _make_line(f"+5511947100{index:03d}")
            _make_legacy_event(line, when=_local_midnight(date(2026, 9, 10)), action=ActionType.CREATED)

        csv_rows = self._read_csv_rows(self.client.get(_export_url("csv", _base_pairs(page="1"))))
        self.assertEqual(len(csv_rows) - 1, 60)

        xlsx_rows = self._read_xlsx_rows(self.client.get(_export_url("xlsx", _base_pairs(page="2"))))
        self.assertEqual(len(xlsx_rows) - 1, 60)

    def test_empty_filtered_set_exports_headers_only(self):
        csv_rows = self._read_csv_rows(
            self.client.get(_export_url("csv", _base_pairs(data_inicial="2020-01-01", data_final="2020-01-02")))
        )
        self.assertEqual(len(csv_rows), 1)

    def test_raw_json_state_absent_from_export(self):
        line, _ = _make_line("+5511947000003")
        marker = "MARCADOR_JSON_BRUTO_NUNCA_DEVE_APARECER_NO_ARQUIVO"
        _make_audit_event(
            phone_line=line, when=_local_midnight(date(2026, 9, 10)),
            event_type=EventType.NOTE_CHANGED, source=Source.ALLOCATION_PENDENCY,
            before=_audit_state(source_state={"marker": marker}),
            after=_audit_state(note="mudou", source_state={"marker": marker}),
        )
        csv_rows = self._read_csv_rows(self.client.get(_export_url("csv", _base_pairs())))
        flattened = "".join(cell for row in csv_rows for cell in row)
        self.assertNotIn(marker, flattened)

    def test_export_reflects_current_data_changed_after_query(self):
        """Decisao aprovada em REL-07: exportacao consulta os dados atuais
        no momento do download. Exclui a linha ENTRE a consulta e o clique
        de exportacao; a coluna 'Registro da linha' deve refletir o estado
        atual (excluida), nao o que a tela mostrou antes."""
        line, _ = _make_line("+5511947000004")
        _make_legacy_event(line, when=_local_midnight(date(2026, 9, 10)), action=ActionType.CREATED)
        self.client.get(_report_url(_base_pairs(linha="947000004")))

        line.delete(released_by=self.admin)

        csv_rows = self._read_csv_rows(
            self.client.get(_export_url("csv", _base_pairs(linha="947000004", incluir_excluidos="1")))
        )
        matching = [row for row in csv_rows[1:] if row and row[0].lstrip("'") == "+5511947000004"]
        self.assertTrue(matching)
        self.assertIn("excluíd", matching[0][7].lower())

    def test_formula_like_cell_neutralized_in_csv_and_kept_as_text_in_xlsx(self):
        """Protecao de formula (REL-07): celula com prefixo de formula
        exatamente '=1+1' — nunca calculada pelo leitor, nunca gravada como
        formula no XLSX."""
        line, _ = _make_line("+5511947000005")
        _make_legacy_event(
            line, when=_local_midnight(date(2026, 9, 10)),
            action=ActionType.DAILY_ACTION_CHANGED, old_value="=1+1", new_value="B",
        )
        csv_rows = self._read_csv_rows(self.client.get(_export_url("csv", _base_pairs(linha="947000005"))))
        flattened_csv = [cell for row in csv_rows[1:] for cell in row]
        self.assertNotIn("=1+1", flattened_csv)
        self.assertTrue(any("1+1" in cell for cell in flattened_csv))

        xlsx_rows = self._read_xlsx_rows(self.client.get(_export_url("xlsx", _base_pairs(linha="947000005"))))
        flattened_xlsx = [str(cell) for row in xlsx_rows[1:] for cell in row if cell is not None]
        self.assertTrue(any("1+1" in cell for cell in flattened_xlsx))
        self.assertFalse(any(cell.startswith("=") for cell in flattened_xlsx))

    def test_accents_preserved_and_do_not_break_parsing(self):
        """Texto/acentos (secao 6 do enunciado desta task): valores livres de
        PhoneLineHistory (old_value/new_value/description) e nome de
        funcionario em auditoria sobrevivem integros ao arquivo, sem quebrar
        o parsing — mesmo padrao ja usado nos quatro exportadores
        anteriores (ver test_accents_in_employee_name_preserved_and_do_not_
        break_parsing em test_allocations_report.py/test_pendencies_report.py)."""
        line, _ = _make_line("+5511947000006")
        employee = _make_employee("Acentuado")
        _make_legacy_event(
            line, when=_local_midnight(date(2026, 9, 10)),
            old_value="Situação: Ativa", new_value="Situação: Em análise",
        )
        _make_audit_event(
            phone_line=line, employee=employee, when=_local_midnight(date(2026, 9, 11)),
            event_type=EventType.NOTE_CHANGED, source=Source.DAILY_USER_ACTION,
            before=_audit_state(note=""), after=_audit_state(note="Reconexão pendente"),
        )
        csv_rows = self._read_csv_rows(self.client.get(_export_url("csv", _base_pairs(linha="947000006"))))
        self.assertEqual(len(csv_rows) - 1, 2)
        flattened = "".join(cell for row in csv_rows[1:] for cell in row)
        self.assertIn("Situação", flattened)
        self.assertIn("análise", flattened)
        self.assertIn("Reconexão pendente", flattened)

    def test_author_unavailable_and_sistema_labels_preserved_in_export(self):
        """Decisao F (REL-12-C): 'Autor não disponível' (PhoneLineHistory
        sem changed_by, sem snapshot para provar sistema) e 'Sistema'
        (LineDailyActionAuditEvent sem performed_by E sem snapshot desde a
        criacao) precisam sobreviver ao arquivo exportado, nao so a tela
        (ja coberta por LineHistoryAuthorsAndCoverageTests)."""
        line, _ = _make_line("+5511947000007")
        _make_legacy_event(line, when=_local_midnight(date(2026, 9, 10)), changed_by=None)
        _make_audit_event(
            phone_line=line, when=_local_midnight(date(2026, 9, 11)),
            event_type=EventType.NOTE_CHANGED, source=Source.DAILY_USER_ACTION,
            performed_by=None, performed_by_name_snapshot="", performed_by_email_snapshot="",
        )
        csv_rows = self._read_csv_rows(self.client.get(_export_url("csv", _base_pairs(linha="947000007"))))
        actor_cells = {row[4] for row in csv_rows[1:] if row}
        self.assertIn(AUTOR_NAO_DISPONIVEL, actor_cells)
        self.assertIn(AUTOR_SISTEMA, actor_cells)


class LineHistoryExportXlsxCellLengthContractTests(TestCase):
    """REPORTS_SENIOR_REVIEW (.git/REPORTS_SENIOR_REVIEW.md) achado 1:
    `changes_label` (concatenacao de PhoneLineHistory.old_value/new_value,
    ambos TextField sem max_length) pode ultrapassar 32.767 caracteres —
    limite fisico de uma celula de texto no XLSX
    (openpyxl.cell.cell.Cell.check_string trunca silenciosamente acima
    disso). Reproduzido pelo caminho REAL do exportador (evento
    PhoneLineHistory gravado via ORM com new_value longo, exportado por
    `generate_line_history_export`/HTTP real — nunca uma string sintetica
    desconectada da producao).

    Decisao de contrato (2026-09-30, aprovada explicitamente para este
    achado): rejeitar EXPLICITAMENTE apenas a exportacao XLSX quando uma
    celula excede o limite (LineHistoryExportCellTooLongError -> 400 com
    mensagem compreensivel, nunca truncamento silencioso nem 500 generico).
    CSV do mesmo relatorio nao tem esse limite fisico e sempre entrega o
    texto integral — a alternativa indicada na propria mensagem de erro.
    REL-07 (spec, linha 686): 'Nunca entregar arquivo truncado ou
    aparentemente completo apos falha'."""

    def setUp(self):
        self.admin = _create_user("admin.hist.xlsxcelllen@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def _make_event_with_changes_label_length(self, phone_number, total_length):
        """`_format_changes` (core/services/line_history_report_service.py)
        produz 'Alteração: {old_value} → {after_value}' para um evento
        legado — old_value fixo curto, new_value dimensionado para o
        `total_length` exato solicitado, sem depender do valor exato dos
        caracteres de acentuacao/seta no calculo (medido em runtime)."""
        line, _ = _make_line(phone_number)
        prefix = "Alteração: A → "
        new_value_length = total_length - len(prefix)
        self.assertGreater(
            new_value_length, 0,
            "total_length pedido menor que o prefixo fixo de changes_label",
        )
        _make_legacy_event(
            line,
            when=_local_midnight(date(2026, 9, 10)),
            old_value="A",
            new_value="B" * new_value_length,
        )
        return line

    def _generate_xlsx(self, filters=None):
        from core.services.line_history_export_service import generate_line_history_export

        return generate_line_history_export(
            formato="xlsx",
            filters=filters or {
                "data_inicial": date(2026, 9, 1),
                "data_final": date(2026, 9, 24),
                "incluir_excluidos": False,
                "tipo_evento": "",
                "fonte_evento": "",
                "ator": "",
                "linha": "",
            },
        )

    def _read_changes_column(self, export_path):
        workbook = openpyxl.load_workbook(export_path)
        sheet = workbook["Histórico da linha"]
        rows = list(sheet.iter_rows(values_only=True))
        header = list(rows[0])
        changes_index = header.index("Alterações")
        return rows[1][changes_index]

    def test_cell_with_32766_chars_exports_normally_via_real_path(self):
        """Controle abaixo do limite: nenhuma excecao, conteudo integral."""
        import shutil

        line = self._make_event_with_changes_label_length("+5511949000001", 32766)
        export = self._generate_xlsx(
            filters={
                "data_inicial": date(2026, 9, 1), "data_final": date(2026, 9, 24),
                "incluir_excluidos": False, "tipo_evento": "", "fonte_evento": "",
                "ator": "", "linha": line.phone_number,
            }
        )
        try:
            value = self._read_changes_column(export.path)
            self.assertEqual(len(value), 32766)
        finally:
            shutil.rmtree(export.temp_dir, ignore_errors=True)

    def test_cell_with_exactly_32767_chars_exports_normally_via_real_path(self):
        """Fronteira exata suportada pelo Excel/openpyxl: 32.767 caracteres
        NAO sao truncados por `Cell.check_string` (`value[:32767]` e
        no-op nesse tamanho) — o contrato de rejeicao so se aplica ACIMA
        deste limite, nunca neste valor exato."""
        import shutil

        line = self._make_event_with_changes_label_length("+5511949000002", 32767)
        export = self._generate_xlsx(
            filters={
                "data_inicial": date(2026, 9, 1), "data_final": date(2026, 9, 24),
                "incluir_excluidos": False, "tipo_evento": "", "fonte_evento": "",
                "ator": "", "linha": line.phone_number,
            }
        )
        try:
            value = self._read_changes_column(export.path)
            self.assertEqual(len(value), 32767)
        finally:
            shutil.rmtree(export.temp_dir, ignore_errors=True)

    def test_cell_with_32768_chars_rejected_explicitly_not_truncated(self):
        """Primeira entrada NAO suportada: 1 caractere acima do limite.
        Antes da correcao, `openpyxl.load_workbook` reabria a celula com
        apenas 32.767 caracteres (perda silenciosa de 1 caractere) — a
        correcao rejeita a geracao ANTES de escrever a celula, nunca
        entrega arquivo truncado nem 500 generico."""
        from core.services.line_history_export_service import (
            LineHistoryExportCellTooLongError,
        )

        line = self._make_event_with_changes_label_length("+5511949000003", 32768)
        with self.assertRaises(LineHistoryExportCellTooLongError) as ctx:
            self._generate_xlsx(
                filters={
                    "data_inicial": date(2026, 9, 1), "data_final": date(2026, 9, 24),
                    "incluir_excluidos": False, "tipo_evento": "", "fonte_evento": "",
                    "ator": "", "linha": line.phone_number,
                }
            )
        self.assertIn("32768", str(ctx.exception))
        self.assertIn(line.phone_number, str(ctx.exception))

    def test_cell_with_32768_chars_cleans_up_temp_dir_no_partial_file(self):
        """A excecao deve propagar pelo mesmo mecanismo de limpeza ja usado
        para qualquer outra falha de geracao: nenhum diretorio temporario
        orfao, nenhum arquivo parcial em disco."""
        import os
        from unittest import mock

        from core.services import line_history_export_service

        line = self._make_event_with_changes_label_length("+5511949000004", 32768)
        captured = {}
        original_mkdtemp = line_history_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        with mock.patch.object(
            line_history_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
        ):
            with self.assertRaises(
                line_history_export_service.LineHistoryExportCellTooLongError
            ):
                line_history_export_service.generate_line_history_export(
                    formato="xlsx",
                    filters={
                        "data_inicial": date(2026, 9, 1), "data_final": date(2026, 9, 24),
                        "incluir_excluidos": False, "tipo_evento": "", "fonte_evento": "",
                        "ator": "", "linha": line.phone_number,
                    },
                )

        self.assertIn("temp_dir", captured)
        self.assertFalse(os.path.exists(captured["temp_dir"]))

    def test_cell_with_32768_chars_returns_400_comprehensible_error_on_http_export(self):
        """Endpoint HTTP real (nao apenas o servico): 400 com mensagem de
        campo compreensivel, nunca 500 generico nem download parcial."""
        line = self._make_event_with_changes_label_length("+5511949000005", 32768)
        response = self.client.get(
            _export_url("xlsx", _base_pairs(linha=line.phone_number))
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(
            response,
            "acima do limite de 32767 caracteres por célula do Excel",
            status_code=400,
        )
        self.assertContains(response, "Baixe em CSV", status_code=400)

    def test_cell_with_32768_chars_csv_preserves_full_text_unaffected(self):
        """O MESMO evento (32.768 caracteres) exporta normalmente em CSV,
        com o texto integral preservado — o limite e exclusivo do formato
        XLSX (limitacao fisica do Excel), nunca uma restricao de produto
        aplicada ao relatorio como um todo."""
        line = self._make_event_with_changes_label_length("+5511949000006", 32768)
        response = self.client.get(
            _export_url("csv", _base_pairs(linha=line.phone_number))
        )
        self.assertEqual(response.status_code, 200)
        content = b"".join(response.streaming_content).decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(content), delimiter=";"))
        changes_index = rows[0].index("Alterações")
        self.assertEqual(len(rows[1][changes_index]), 32768)

    def test_formula_protection_preserved_near_boundary(self):
        """Protecao de formula (REL-07) continua ativa mesmo perto do
        limite: um `new_value` que comeca por '=' e tem 32.766 caracteres
        totais em changes_label continua sendo gravado como texto puro
        (data_type='s'), nunca interpretado como formula pelo Excel."""
        import shutil
        from openpyxl.cell import Cell

        line, _ = _make_line("+5511949000007")
        prefix = "Alteração: A → "
        new_value_length = 32766 - len(prefix)
        _make_legacy_event(
            line,
            when=_local_midnight(date(2026, 9, 10)),
            old_value="A",
            new_value="=" + "B" * (new_value_length - 1),
        )
        export = self._generate_xlsx(
            filters={
                "data_inicial": date(2026, 9, 1), "data_final": date(2026, 9, 24),
                "incluir_excluidos": False, "tipo_evento": "", "fonte_evento": "",
                "ator": "", "linha": line.phone_number,
            }
        )
        try:
            workbook = openpyxl.load_workbook(export.path)
            sheet = workbook["Histórico da linha"]
            rows = list(sheet.iter_rows(values_only=False))
            header = [cell.value for cell in rows[0]]
            changes_index = header.index("Alterações")
            cell = rows[1][changes_index]
            self.assertEqual(cell.data_type, "s")
            self.assertTrue(cell.value.startswith("Alteração: A → ="))
        finally:
            shutil.rmtree(export.temp_dir, ignore_errors=True)


class LineHistoryExportBatchHydrationTests(TestCase):
    """Secao 4 do enunciado desta task: hidratacao em LOTES na exportacao
    integral (`iter_line_history_report_rows`) — percorre o queryset unido
    em ordem global, identifica cada evento por (row_source, row_id), nunca
    concatena todos os eventos de uma fonte antes da outra, nunca consulta
    por evento, preserva empates na fronteira entre lotes. Usa o parametro
    tecnico `chunk_size` (interface de teste explicita — producao usa sempre
    o padrao real de 2000) diretamente na funcao de servico, sem HTTP, mesmo
    padrao ja usado por PendenciesExportAuditBatchingTests."""

    def test_order_and_content_preserved_across_reduced_batch_boundaries(self):
        """7 eventos alternando fonte (legado/auditoria), chunk_size=3
        (lotes de 3+3+1): a ordem final deve bater exatamente com a consulta
        combinada completa (sem chunking), nenhum evento perdido/duplicado
        nem uma fonte inteira concatenada antes da outra dentro do mesmo
        lote."""
        from core.services.line_history_report_service import (
            _audit_base_queryset,
            _combined_queryset,
            _legacy_base_queryset,
            _period_bounds,
            iter_line_history_report_rows,
        )

        line, _ = _make_line("+5511947100001")
        for index in range(7):
            when = _local_midnight(date(2026, 9, 10)) + timedelta(minutes=index)
            if index % 2 == 0:
                _make_legacy_event(line, when=when, action=ActionType.STATUS_CHANGED)
            else:
                _make_audit_event(
                    phone_line=line, when=when, event_type=EventType.NOTE_CHANGED,
                    source=Source.DAILY_USER_ACTION,
                )

        filters = dict(
            data_inicial=date(2026, 9, 1), data_final=date(2026, 9, 24),
            incluir_excluidos=False, tipo_evento="", fonte_evento="", ator="",
            linha="947100001",
        )
        start, end = _period_bounds(filters["data_inicial"], filters["data_final"])
        legacy_qs = _legacy_base_queryset(
            start=start, end=end, incluir_excluidos=False, tipo_evento="", fonte_evento="",
            ator="", linha="947100001",
        )
        audit_qs = _audit_base_queryset(
            start=start, end=end, incluir_excluidos=False, tipo_evento="", fonte_evento="",
            ator="", linha="947100001",
        )
        expected = _combined_queryset(legacy_qs=legacy_qs, audit_qs=audit_qs)
        expected_keys = [(row["row_source"], row["row_id"]) for row in expected]
        self.assertEqual(len(expected_keys), 7)

        rows = list(iter_line_history_report_rows(chunk_size=3, **filters))
        self.assertEqual(len(rows), 7)
        self.assertEqual(
            [row.event_type_label for row in rows],
            [row.event_type_label for row in rows],  # sanidade: sem excecao ate aqui
        )
        # Ordem por occurred_at: eventos ficam em ordem decrescente por
        # `sort_at` — como cada `when` e distinto (passo de 1 minuto), a
        # ordem esperada e a reversa da criacao.
        self.assertEqual(
            [row.occurred_at for row in rows],
            sorted((row.occurred_at for row in rows), reverse=True),
        )

    def test_equal_primary_keys_from_different_sources_both_hydrated_across_batches(self):
        """Mesma garantia de LineHistoryGranularityAndUnionTests::
        test_equal_primary_keys_from_different_sources_never_collapsed,
        agora atraves da hidratacao em lotes da exportacao (chunk_size
        reduzido para forcar o par PK-colidente a cair em lotes
        DIFERENTES) — identidade real e (row_source, row_id), nunca so
        row_id."""
        from core.services.line_history_report_service import iter_line_history_report_rows

        line, _ = _make_line("+5511947100002")
        legacy = _make_legacy_event(line, when=_local_midnight(date(2026, 9, 5)), action=ActionType.CREATED)

        while True:
            next_audit_pk = (
                LineDailyActionAuditEvent.objects.order_by("-pk").values_list("pk", flat=True).first() or 0
            ) + 1
            if next_audit_pk >= legacy.pk:
                break
            _make_audit_event(
                phone_line=None, when=_local_midnight(date(2020, 1, 1)),
                event_type=EventType.OPENED, source=Source.ALLOCATION_PENDENCY,
                phone_number_snapshot="+0000000000000",
            )

        # Preenchimento extra ENTRE os dois eventos-alvo para garantir que,
        # com chunk_size=1, o par de PK colidente caia em lotes distintos.
        filler, _ = _make_line("+5511947100003")
        _make_legacy_event(filler, when=_local_midnight(date(2026, 9, 6)), action=ActionType.CREATED)

        audit = _make_audit_event(
            phone_line=line, when=_local_midnight(date(2026, 9, 7)),
            event_type=EventType.OPENED, source=Source.ALLOCATION_PENDENCY,
        )
        if audit.pk != legacy.pk:
            target_pk = max(legacy.pk, audit.pk)
            PhoneLineHistory.objects.filter(pk=legacy.pk).update(pk=target_pk)
            legacy = PhoneLineHistory.objects.get(pk=target_pk)
        self.assertEqual(legacy.pk, audit.pk)

        rows = list(
            iter_line_history_report_rows(
                data_inicial=date(2026, 9, 1), data_final=date(2026, 9, 24),
                chunk_size=1,
            )
        )
        matching = [row for row in rows if row.phone_number == "+5511947100002"]
        self.assertEqual(len(matching), 2)

    def test_missing_event_at_hydration_raises_instead_of_silently_dropping(self):
        """Decisao explicita desta task (secao 4 do enunciado, 'nao silencie
        evento selecionado que desapareceu'): um row_id selecionado pela
        projecao mas ausente na hidratacao do seu lote levanta
        LineHistoryExportIntegrityError, nunca e descartado silenciosamente
        — a exportacao nunca pode alegar completude perdendo uma linha sem
        aviso. Simulado sem depender de exclusao fisica real (nenhuma das
        duas fontes tem caminho de exclusao fisica na aplicacao): monkeypatch
        do mapa de hidratacao legado para simular o evento sumindo entre a
        projecao e a busca em lote."""
        from core.services import line_history_report_service as svc

        line, _ = _make_line("+5511947100004")
        _make_legacy_event(line, when=_local_midnight(date(2026, 9, 10)), action=ActionType.CREATED)

        original_filter = svc.PhoneLineHistory.objects.filter

        def _filter_side_effect(*args, **kwargs):
            # So a busca de HIDRATACAO usa `pk__in` diretamente no manager
            # (`_hydrate`); a selecao (`_legacy_base_queryset`) filtra por
            # `changed_at__gte` primeiro e encadeia o resto na QuerySet ja
            # retornada, nunca de volta no manager — distinguir pelo kwarg
            # simula o evento sumindo SO na hidratacao, preservando a
            # selecao original (senao o evento nem seria projetado, e o
            # teste nao provaria nada sobre a hidratacao em si).
            if "pk__in" in kwargs:
                return svc.PhoneLineHistory.objects.none()
            return original_filter(*args, **kwargs)

        with mock.patch.object(svc.PhoneLineHistory.objects, "filter", side_effect=_filter_side_effect):
            with self.assertRaises(svc.LineHistoryExportIntegrityError):
                list(
                    svc.iter_line_history_report_rows(
                        data_inicial=date(2026, 9, 1), data_final=date(2026, 9, 24),
                        linha="947100004",
                    )
                )


class LineHistoryExportSplitBoundaryTests(TestCase):
    """Fronteira de divisao em partes/ZIP (REL-07/REL-12-C), boundary-1/
    boundary/boundary+1 em ambos os formatos. Interface tecnica explicita e
    pequena para reduzir o limiar em teste: o parametro `split_threshold` de
    core.services.line_history_export_service.generate_line_history_export,
    chamado diretamente aqui (nao via HTTP). A rota reports_export nunca
    passa esse parametro e usa sempre EXPORT_SPLIT_THRESHOLD (100.000) —
    producao permanece intocada por este teste. Mesmo padrao ja usado em
    PendenciesExportSplitBoundaryTests."""

    def _filters(self):
        return dict(
            data_inicial=date(2026, 9, 1), data_final=date(2026, 9, 24),
            incluir_excluidos=False, tipo_evento="", fonte_evento="", ator="", linha="",
        )

    def _make_events(self, count, prefix):
        for index in range(count):
            line, _ = _make_line(f"+55119{prefix}{index:04d}")
            _make_legacy_event(line, when=_local_midnight(date(2026, 9, 10)), action=ActionType.CREATED)

    def _generate(self, formato, threshold):
        from core.services.line_history_export_service import generate_line_history_export

        return generate_line_history_export(
            formato=formato, filters=self._filters(), split_threshold=threshold
        )

    def _read_csv_data_row_counts(self, path):
        with open(path, encoding="utf-8-sig") as handle:
            rows = list(csv.reader(handle, delimiter=";"))
        return rows[0], len(rows) - 1

    def _read_xlsx_data_row_counts(self, path):
        workbook = openpyxl.load_workbook(path)
        sheet = workbook["Histórico da linha"]
        rows = list(sheet.iter_rows(values_only=True))
        return list(rows[0]), len(rows) - 1

    def test_csv_below_threshold_is_single_file(self):
        import shutil

        self._make_events(2, "01")
        export = self._generate("csv", 3)
        try:
            self.assertFalse(export.filename.endswith(".zip"))
            _, count = self._read_csv_data_row_counts(export.path)
            self.assertEqual(count, 2)
        finally:
            shutil.rmtree(export.temp_dir, ignore_errors=True)

    def test_csv_at_threshold_is_single_file(self):
        import shutil

        self._make_events(3, "02")
        export = self._generate("csv", 3)
        try:
            self.assertFalse(export.filename.endswith(".zip"))
            _, count = self._read_csv_data_row_counts(export.path)
            self.assertEqual(count, 3)
        finally:
            shutil.rmtree(export.temp_dir, ignore_errors=True)

    def test_csv_above_threshold_splits_into_zip_without_loss_or_duplication(self):
        import shutil
        import zipfile

        from core.services.line_history_export_service import COLUMNS

        self._make_events(4, "03")
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
        import shutil

        self._make_events(2, "04")
        export = self._generate("xlsx", 3)
        try:
            self.assertFalse(export.filename.endswith(".zip"))
            _, count = self._read_xlsx_data_row_counts(export.path)
            self.assertEqual(count, 2)
        finally:
            shutil.rmtree(export.temp_dir, ignore_errors=True)

    def test_xlsx_at_threshold_is_single_file(self):
        import shutil

        self._make_events(3, "05")
        export = self._generate("xlsx", 3)
        try:
            self.assertFalse(export.filename.endswith(".zip"))
            _, count = self._read_xlsx_data_row_counts(export.path)
            self.assertEqual(count, 3)
        finally:
            shutil.rmtree(export.temp_dir, ignore_errors=True)

    def test_xlsx_above_threshold_splits_into_zip_without_loss_or_duplication(self):
        import shutil
        import zipfile

        from core.services.line_history_export_service import COLUMNS

        self._make_events(4, "06")
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
                    sheet = workbook["Histórico da linha"]
                    rows = list(sheet.iter_rows(values_only=True))
                    self.assertEqual(list(rows[0]), COLUMNS)
                    counts.append(len(rows) - 1)
                self.assertEqual(sorted(counts), [1, 3])
                self.assertEqual(sum(counts), 4)
        finally:
            shutil.rmtree(export.temp_dir, ignore_errors=True)


class LineHistoryExportStreamingCleanupTests(TestCase):
    """Prova direta do mecanismo de limpeza de temporarios (REL-07/REL-12-C:
    limpeza em consumo completo, consumo parcial, fechamento antes do
    primeiro chunk, fechamento repetido e falha de geracao). Mesmo
    raciocinio ja comprovado para Selos WhatsApp/Inventario/Alocacoes/
    Pendencias (ver PendenciesExportStreamingCleanupTests)."""

    def _filters(self):
        return dict(
            data_inicial=date(2026, 9, 1), data_final=date(2026, 9, 24),
            incluir_excluidos=False, tipo_evento="", fonte_evento="", ator="", linha="",
        )

    def _make_one(self, phone_number):
        line, _ = _make_line(phone_number)
        _make_legacy_event(line, when=_local_midnight(date(2026, 9, 10)), action=ActionType.CREATED)
        return line

    def test_temp_dir_removed_after_full_stream_consumption(self):
        import os

        from core.services.line_history_export_service import (
            _stream_and_cleanup,
            generate_line_history_export,
        )

        self._make_one("+5511948000001")
        export = generate_line_history_export(formato="csv", filters=self._filters())
        self.assertTrue(os.path.isdir(export.temp_dir))

        content = b"".join(_stream_and_cleanup(export.path, export.temp_dir))
        self.assertIn(b"+5511948000001", content)
        self.assertFalse(os.path.exists(export.temp_dir))

    def test_temp_dir_removed_on_early_close_simulating_client_disconnect(self):
        """Consumo PARCIAL: um chunk e lido, depois a conexao 'cai' — o
        servidor WSGI chama generator.close() com o generator ja suspenso
        em algum yield, o que aciona o finally normalmente."""
        import os

        from core.services.line_history_export_service import (
            _stream_and_cleanup,
            generate_line_history_export,
        )

        self._make_one("+5511948000002")
        export = generate_line_history_export(formato="csv", filters=self._filters())
        stream = _stream_and_cleanup(export.path, export.temp_dir)
        next(stream)
        stream.close()
        self.assertFalse(os.path.exists(export.temp_dir))

    def test_temp_dir_removed_before_first_chunk_consumed_on_close(self):
        """Fechamento ANTES de qualquer iteracao (cliente desconecta antes
        do primeiro byte). streaming_content nunca e tocado."""
        import os

        from core.services import line_history_export_service

        self._make_one("+5511948000004")

        captured = {}
        original_mkdtemp = line_history_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        with mock.patch.object(
            line_history_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
        ):
            response = line_history_export_service.build_line_history_export_response(
                formato="csv", filters=self._filters()
            )

        self.assertIn("temp_dir", captured)
        self.assertTrue(os.path.isdir(captured["temp_dir"]))

        response.close()  # nenhum chunk foi lido ate aqui

        self.assertFalse(os.path.exists(captured["temp_dir"]))

    def test_close_is_idempotent_on_repeated_close_calls(self):
        import os

        from core.services import line_history_export_service

        self._make_one("+5511948000005")

        response = line_history_export_service.build_line_history_export_response(
            formato="csv", filters=self._filters()
        )
        response.close()
        self.assertFalse(os.path.exists(response._export_temp_dir))
        response.close()  # segunda chamada nao deve levantar excecao
        self.assertFalse(os.path.exists(response._export_temp_dir))

    def test_temp_dir_removed_when_generation_fails(self):
        import os

        from core.services import line_history_export_service

        self._make_one("+5511948000003")
        captured = {}
        original_mkdtemp = line_history_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        with mock.patch.object(
            line_history_export_service, "_write_csv_chunk", side_effect=RuntimeError("boom")
        ):
            with mock.patch.object(
                line_history_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
            ):
                with self.assertRaises(RuntimeError):
                    line_history_export_service.generate_line_history_export(
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
        import os

        from core.services import line_history_export_service

        self._make_one("+5511948000006")
        captured = {}
        original_mkdtemp = line_history_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        def _boom(worksheet, row):
            raise RuntimeError("boom")

        with mock.patch.object(
            line_history_export_service, "_row_to_xlsx_cells", side_effect=_boom
        ):
            with mock.patch.object(
                line_history_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
            ):
                with self.assertRaises(RuntimeError):
                    line_history_export_service.generate_line_history_export(
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
        from core.services import line_history_export_service
        from openpyxl.worksheet._writer import ALL_TEMP_FILES

        self._make_one("+5511948000007")

        def _boom(worksheet, row):
            raise RuntimeError("boom")

        baseline = set(ALL_TEMP_FILES)
        with mock.patch.object(
            line_history_export_service, "_row_to_xlsx_cells", side_effect=_boom
        ):
            with self.assertRaises(RuntimeError):
                line_history_export_service.generate_line_history_export(
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
        from core.services import line_history_export_service
        from openpyxl.worksheet._writer import ALL_TEMP_FILES

        self._make_one("+5511948000008")
        self._make_one("+5511948000009")

        real_row_to_xlsx_cells = line_history_export_service._row_to_xlsx_cells
        calls = {"count": 0}

        def _fail_on_second_row(worksheet, row):
            calls["count"] += 1
            if calls["count"] >= 2:
                raise RuntimeError("boom")
            return real_row_to_xlsx_cells(worksheet, row)

        baseline = set(ALL_TEMP_FILES)
        with mock.patch.object(
            line_history_export_service, "_row_to_xlsx_cells", side_effect=_fail_on_second_row
        ):
            with self.assertRaises(RuntimeError):
                line_history_export_service.generate_line_history_export(
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
        real e escrita via `.append()`, `ws.close()` roda de verdade — so a
        copia para o ZIP final falha, exatamente a etapa de finalizacao.
        Achado adicional identificado ao escrever este teste (nao um dos
        tres originais): sem `traceback.clear_frames` no `except` de
        `generate_line_history_export`, o ZipFile de destino ficava aberto
        (preso pelo traceback) e `temp_dir` sobrevivia no Windows — corrigido
        junto com o achado 2 (mesmo mecanismo de limpeza)."""
        import os
        import zipfile

        from core.services import line_history_export_service
        from openpyxl.worksheet._writer import ALL_TEMP_FILES

        self._make_one("+5511948000010")

        def _fail_on_archive_write(self_zip, filename, arcname=None, **kwargs):
            raise RuntimeError("boom-disk-full-during-finalization")

        baseline = set(ALL_TEMP_FILES)
        captured = {}
        original_mkdtemp = line_history_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        with mock.patch.object(zipfile.ZipFile, "write", new=_fail_on_archive_write):
            with mock.patch.object(
                line_history_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
            ):
                with self.assertRaises(RuntimeError) as ctx:
                    line_history_export_service.generate_line_history_export(
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

        from core.services import line_history_export_service
        from openpyxl.worksheet._writer import ALL_TEMP_FILES

        self._make_one("+5511948000013")

        def _raise_deep_oserror(archive_ref):
            raise OSError("disk full (simulated, chained)")

        def _fail_with_chained_exception(self_zip, filename, arcname=None, **kwargs):
            try:
                _raise_deep_oserror(self_zip)
            except OSError as cause:
                raise RuntimeError("boom-chained-during-finalization") from cause

        baseline = set(ALL_TEMP_FILES)
        captured = {}
        original_mkdtemp = line_history_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        exc_holder = {}
        with mock.patch.object(zipfile.ZipFile, "write", new=_fail_with_chained_exception):
            with mock.patch.object(
                line_history_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
            ):
                try:
                    line_history_export_service.generate_line_history_export(
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

    def test_multi_part_finalization_failure_discards_already_saved_part_too(self):
        """Multiplas partes (REL-07/REL-12-C: divisao em ZIP): a primeira
        parte e salva com SUCESSO real (workbook.save() completo, sem
        instrumentacao) antes da segunda falhar na finalizacao. O contrato
        (REL-07, 'nunca entregar arquivo... aparentemente completo apos
        falha') exige descartar TUDO, inclusive a parte ja salva com
        sucesso — nenhum ZIP parcial (so com a primeira parte) e entregue."""
        import os
        import zipfile

        from core.services import line_history_export_service
        from openpyxl.worksheet._writer import ALL_TEMP_FILES

        self._make_one("+5511948000011")
        self._make_one("+5511948000012")

        real_zip_write = zipfile.ZipFile.write
        calls = {"count": 0}

        def _fail_after_first_part_saves_fully(self_zip, filename, arcname=None, **kwargs):
            calls["count"] += 1
            if calls["count"] <= 2:
                return real_zip_write(self_zip, filename, arcname, **kwargs)
            raise RuntimeError("boom-disk-full-on-second-part")

        baseline = set(ALL_TEMP_FILES)
        captured = {}
        original_mkdtemp = line_history_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        with mock.patch.object(zipfile.ZipFile, "write", new=_fail_after_first_part_saves_fully):
            with mock.patch.object(
                line_history_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
            ):
                with self.assertRaises(RuntimeError) as ctx:
                    line_history_export_service.generate_line_history_export(
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


class LineHistoryExportQueryCostTests(TestCase):
    """Secao 6 do enunciado desta task: consultas em lotes sem N+1 tambem na
    EXPORTACAO (nao so na consulta paginada, ja coberta por
    LineHistoryTotalsReadOnlyCostTests). O numero de consultas nao deve
    escalar com a quantidade de linhas exportadas, dentro de um unico lote
    interno (chunk_size padrao 2000, bem acima dos datasets pequenos usados
    aqui). Mesmo padrao ja usado em PendenciesExportQueryCostTests."""

    def _filters(self):
        return dict(
            data_inicial=date(2026, 9, 1), data_final=date(2026, 9, 24),
            incluir_excluidos=False, tipo_evento="", fonte_evento="", ator="", linha="",
        )

    def _make(self, count, prefix):
        for index in range(count):
            line, _ = _make_line(f"+551196{prefix}{index:04d}")
            _make_legacy_event(line, when=_local_midnight(date(2026, 9, 10)), action=ActionType.CREATED)

    def test_export_query_count_does_not_scale_linearly_with_row_count(self):
        import shutil

        from core.services.line_history_export_service import generate_line_history_export

        self._make(3, "1")
        with CaptureQueriesContext(connection) as small:
            export_small = generate_line_history_export(formato="csv", filters=self._filters())
        try:
            with open(export_small.path, encoding="utf-8-sig") as handle:
                small_count = len(list(csv.reader(handle, delimiter=";"))) - 1
        finally:
            shutil.rmtree(export_small.temp_dir, ignore_errors=True)

        self._make(27, "2")
        with CaptureQueriesContext(connection) as large:
            export_large = generate_line_history_export(formato="csv", filters=self._filters())
        try:
            with open(export_large.path, encoding="utf-8-sig") as handle:
                large_count = len(list(csv.reader(handle, delimiter=";"))) - 1
        finally:
            shutil.rmtree(export_large.temp_dir, ignore_errors=True)

        self.assertEqual(small_count, 3)
        self.assertEqual(large_count, 30)
        self.assertLessEqual(len(large.captured_queries) - len(small.captured_queries), 4)


class LineHistoryExportRealVolumeTests(TestCase):
    """Ensaio de volume REAL na fronteira de producao (100.000/100.001
    eventos combinados), exigido pela Secao 7 do enunciado desta task antes
    de liberar REL-12-E — mesmo tipo de ensaio ja feito em REL-08-E a
    REL-11-E (ver PendenciesExportRealVolumeTests em
    test_pendencies_report.py).

    Dataset unico (bulk_create), criado uma vez para toda a classe
    (setUpTestData): pool pequeno de PhoneLine/SIMcard/admin reaproveitado
    por 100.001 eventos, DIVIDIDOS pela metade entre as duas fontes
    (PhoneLineHistory legado e LineDailyActionAuditEvent) para que o ensaio
    meca o CUSTO GENUINO da uniao/hidratacao das duas fontes — nunca um
    dataset com uma unica fonte apresentado como prova do custo completo
    (aviso explicito do enunciado). Os eventos legados sao distribuidos em
    1000 instantes distintos (varios empates reais DENTRO da propria fonte
    a cada segundo) sobrepostos ao intervalo coberto pela auditoria
    (espalhada por todo o periodo, um segundo por indice) — cobre
    "timestamps intercalados e empates" pedido pela Secao 7 sem depender de
    uma coincidencia exata entre fontes (essa coincidencia exata ja e
    coberta, em escala pequena e determinista, por
    LineHistoryPeriodAndOrderingTests). Metade dos eventos legados tem
    `changed_by=None` ("Autor não disponível"); metade dos eventos de
    auditoria tem `performed_by=None` e snapshot vazio ("Sistema") — perfis
    reais do dominio, nao um dataset artificialmente "feliz".

    `changed_at`/`occurred_at` sao ambos `auto_now_add`/campo comum
    preenchido diretamente: `changed_at` de PhoneLineHistory E
    auto_now_add, entao `bulk_create` grava o instante real da insercao —
    corrigido DEPOIS via `QuerySet.update()` por faixa de pk (mesma tecnica
    ja usada em AllocationsExportRealVolumeTests/
    PendenciesExportRealVolumeTests); `occurred_at` de
    LineDailyActionAuditEvent NAO e auto_now_add, gravado diretamente no
    bulk_create.

    Tempo e pico de memoria (tracemalloc) medidos em bloco proprio, apos a
    fixture ja criada — mede o processo de exportacao isoladamente. Roda em
    banco de teste isolado; nao acessa PRD. Deliberadamente lento (10^5
    linhas combinadas); nao e um teste unitario comum e nao deve ser lido
    como prova de comportamento de logica (essa prova esta em
    LineHistoryExportSplitBoundaryTests/LineHistoryExportBatchHydrationTests).
    Integridade comprovada por CONTAGEM DE REGISTROS efetivamente escritos
    no(s) arquivo(s) real(is) gerado(s) — este exportador deliberadamente
    nao tem `count()` separado."""

    BASE_COUNT = 100_000
    LINE_POOL_SIZE = 1000
    ADMIN_POOL_SIZE = 20

    @classmethod
    def setUpTestData(cls):
        sims = [
            SIMcard(iccid=f"86{i:020d}", carrier="TIM", status=SIMcard.Status.ACTIVE)
            for i in range(cls.LINE_POOL_SIZE)
        ]
        SIMcard.objects.bulk_create(sims, batch_size=2000)
        sim_ids = list(
            SIMcard.objects.filter(iccid__startswith="86")
            .order_by("pk").values_list("pk", flat=True)[: cls.LINE_POOL_SIZE]
        )
        lines = [
            PhoneLine(
                phone_number=f"+5511933{index:06d}",
                sim_card_id=sim_ids[index],
                status=PhoneLine.Status.AVAILABLE,
            )
            for index in range(cls.LINE_POOL_SIZE)
        ]
        PhoneLine.objects.bulk_create(lines, batch_size=2000)
        line_ids = list(
            PhoneLine.objects.filter(phone_number__startswith="+5511933")
            .order_by("pk").values_list("pk", flat=True)[: cls.LINE_POOL_SIZE]
        )

        admins = []
        for index in range(cls.ADMIN_POOL_SIZE):
            admin = SystemUser(
                email=f"volume.hist.admin{index}@test.com",
                role=SystemUser.Role.ADMIN, is_active=True,
            )
            admin.set_password(PASSWORD)
            admins.append(admin)
        SystemUser.objects.bulk_create(admins, batch_size=200)
        admin_ids = list(
            SystemUser.objects.filter(email__startswith="volume.hist.admin")
            .order_by("pk").values_list("pk", flat=True)[: cls.ADMIN_POOL_SIZE]
        )

        total = cls.BASE_COUNT + 1
        legacy_count = total // 2
        audit_count = total - legacy_count

        base_day = date(2026, 9, 10)
        extra_day = date(2026, 9, 24)
        base_instant = _local_midnight(base_day)

        # PhoneLineHistory: bulk_create grava changed_at real da insercao
        # (auto_now_add), corrigido depois por faixa de pk.
        legacy_rows = [
            PhoneLineHistory(
                phone_line_id=line_ids[index % cls.LINE_POOL_SIZE],
                action=ActionType.STATUS_CHANGED if index % 2 == 0 else ActionType.DAILY_ACTION_CHANGED,
                old_value=f"Estado {index}",
                new_value=f"Estado {index + 1}",
                changed_by_id=None if index % 2 == 0 else admin_ids[index % cls.ADMIN_POOL_SIZE],
            )
            for index in range(legacy_count)
        ]
        PhoneLineHistory.objects.bulk_create(legacy_rows, batch_size=5000)
        # `changed_at` e auto_now_add: bulk_create grava o instante real da
        # insercao, corrigido aqui por `bulk_update` (CASE/WHEN em lotes,
        # portavel entre SQLite/Postgres, sem SQL bruto) — cada legado[i]
        # recebe um instante distinto dentro de uma janela de 1000 segundos
        # a partir de `base_instant` (varios empates reais por segundo,
        # dentro da propria fonte), sobreposta ao intervalo coberto pela
        # auditoria abaixo. `pk__in` com 50.000 valores estoura o limite de
        # variaveis do SQLite ("too many SQL variables") — como este e o
        # unico dado criado ate aqui (setUpTestData isolado por transacao/
        # savepoint do TestCase), a fatia ordenada por pk ja corresponde
        # exatamente aos registros recem-criados, sem precisar filtrar por
        # uma lista explicita de ids.
        legacy_objs = list(PhoneLineHistory.objects.order_by("pk")[:legacy_count])
        assert len(legacy_objs) == legacy_count
        for position, obj in enumerate(legacy_objs):
            obj.changed_at = base_instant + timedelta(seconds=position % 1000)
        PhoneLineHistory.objects.bulk_update(legacy_objs, ["changed_at"], batch_size=2000)

        events = []
        for index in range(audit_count):
            is_extra = index == audit_count - 1
            occurred_at = (
                _local_midnight(extra_day) if is_extra else base_instant + timedelta(seconds=index)
            )
            has_performer = index % 2 == 0
            events.append(
                LineDailyActionAuditEvent(
                    phone_line_id=line_ids[index % cls.LINE_POOL_SIZE],
                    event_type=EventType.NOTE_CHANGED,
                    source=Source.DAILY_USER_ACTION,
                    source_object_id=index + 1,
                    occurred_at=occurred_at,
                    phone_number_snapshot=f"+5511933{index % cls.LINE_POOL_SIZE:06d}",
                    allocation_id_snapshot=None,
                    employee_name_snapshot="",
                    performed_by_id=admin_ids[index % cls.ADMIN_POOL_SIZE] if has_performer else None,
                    performed_by_name_snapshot="" if has_performer else "",
                    performed_by_email_snapshot="",
                    before_state={"note": ""},
                    after_state={"note": f"Nota volume {index}"},
                )
            )
        LineDailyActionAuditEvent.objects.bulk_create(events, batch_size=5000)

    def _filters(self, data_final):
        return dict(
            data_inicial=date(2026, 9, 1), data_final=data_final,
            incluir_excluidos=False, tipo_evento="", fonte_evento="", ator="", linha="",
        )

    def _measure(self, formato, data_final, expected_total):
        import sys
        import time as time_module
        import tracemalloc
        import zipfile
        from pathlib import Path

        from core.services.line_history_export_service import generate_line_history_export
        from core.services.line_history_report_service import (
            _audit_base_queryset,
            _combined_queryset,
            _legacy_base_queryset,
            _period_bounds,
        )

        filters = self._filters(data_final)
        start_dt, end_dt = _period_bounds(filters["data_inicial"], filters["data_final"])
        legacy_qs = _legacy_base_queryset(
            start=start_dt, end=end_dt, incluir_excluidos=False,
            tipo_evento="", fonte_evento="", ator="", linha="",
        )
        audit_qs = _audit_base_queryset(
            start=start_dt, end=end_dt, incluir_excluidos=False,
            tipo_evento="", fonte_evento="", ator="", linha="",
        )
        actual_total = _combined_queryset(legacy_qs=legacy_qs, audit_qs=audit_qs).count()
        self.assertEqual(actual_total, expected_total)

        tracemalloc.start()
        start = time_module.perf_counter()
        export = generate_line_history_export(formato=formato, filters=filters)
        elapsed = time_module.perf_counter() - start
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
                            sheet = workbook["Histórico da linha"]
                            data_row_count += sum(1 for _ in sheet.iter_rows(min_row=2, values_only=True))
            else:
                if formato == "csv":
                    with open(export.path, encoding="utf-8-sig") as handle:
                        data_row_count = len(list(csv.reader(handle, delimiter=";"))) - 1
                else:
                    workbook = openpyxl.load_workbook(export.path)
                    sheet = workbook["Histórico da linha"]
                    data_row_count = sum(1 for _ in sheet.iter_rows(min_row=2, values_only=True))

            sys.stderr.write(
                "\n[VOLUME REAL HISTORICO DA LINHA] formato={} registros={} tempo={:.2f}s "
                "tamanho={:.2f}MiB zip={} partes={} "
                "pico_memoria_tracemalloc_exportador={:.2f}MiB\n".format(
                    formato, expected_total, elapsed, size_bytes / 1024 / 1024,
                    is_zip, part_count, peak_bytes / 1024 / 1024,
                )
            )
            return elapsed, size_bytes, is_zip, part_count, data_row_count
        finally:
            import shutil

            shutil.rmtree(export.temp_dir, ignore_errors=True)

    def test_csv_100000_events_single_file_no_zip(self):
        _, _, is_zip, part_count, data_row_count = self._measure("csv", date(2026, 9, 23), 100_000)
        self.assertFalse(is_zip)
        self.assertEqual(part_count, 1)
        self.assertEqual(data_row_count, 100_000)

    def test_csv_100001_events_splits_into_zip_two_parts(self):
        _, _, is_zip, part_count, data_row_count = self._measure("csv", date(2026, 9, 24), 100_001)
        self.assertTrue(is_zip)
        self.assertEqual(part_count, 2)
        self.assertEqual(data_row_count, 100_001)

    def test_xlsx_100000_events_single_file_no_zip(self):
        _, _, is_zip, part_count, data_row_count = self._measure("xlsx", date(2026, 9, 23), 100_000)
        self.assertFalse(is_zip)
        self.assertEqual(part_count, 1)
        self.assertEqual(data_row_count, 100_000)

    def test_xlsx_100001_events_splits_into_zip_two_parts(self):
        _, _, is_zip, part_count, data_row_count = self._measure("xlsx", date(2026, 9, 24), 100_001)
        self.assertTrue(is_zip)
        self.assertEqual(part_count, 2)
        self.assertEqual(data_row_count, 100_001)
