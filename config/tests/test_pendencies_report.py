"""Testes RED da task REL-11-T (fonte da verdade:
docs/superpowers/specs/2026-09-22-reports-hub-design.md, secoes REL-07 e
REL-11-C — leitura integral obrigatoria, incluindo as oito decisoes
aprovadas em 2026-09-28, os exemplos A-I e as regras de Solicitante/
Responsavel).

Cobrem o relatorio pendencies: consulta na tela (endpoint existente
GET /relatorios/, motor ainda ausente) e exportacoes CSV/XLSX (endpoint ja
registrado desde REL-08-E, reports_export, cujo dispatch hoje nao inclui
pendencies). Nao testa a aba generica (rota, menu, autorizacao base,
dropdown com 6 opcoes) nem os motores de Selos/Inventario/Alocacoes, ja
cobertos em config/tests/test_reports_hub.py,
config/tests/test_whatsapp_seal_report.py,
config/tests/test_line_inventory_report.py e
config/tests/test_allocations_report.py — reaproveitados, nao duplicados.

Estado atual do motor (2026-09-28, antes de REL-11-Q/E): "pendencies" nao
esta em REPORT_SPECIFIC_PARAM_NAMES, REPORT_FORM_CLASSES,
REPORT_QUERY_ENGINES nem REPORT_EXPORT_ENGINES (config/views.py). Isso
produz DOIS tipos de resultado real e distinto, ambos verificados
explicitamente nas classes abaixo (nunca presumidos):

1. Validacao comum (REL-07: datas obrigatorias/invalidas/invertidas,
   incluir_excluidos, page, parametro repetido, parametro totalmente
   desconhecido, "linha" ate 20 caracteres) roda ANTES do despacho por
   relatorio (_validate_report_query_params monta o form ANTES de checar
   `available_relatorios`) usando o form generico de fallback
   (WhatsAppSealReportQueryForm, unico que ja possui data_inicial/
   data_final/incluir_excluidos/page/linha) — GREEN real hoje, nao RED,
   porque o contrato comum ja se aplica independente do motor de Pendencias
   existir.
2. Qualquer requisito especifico do catalogo aprovado em REL-11-C (colunas,
   granularidade por AllocationPendency, periodo por
   pendency_submitted_at, Solicitante/Responsavel via auditoria, motivo,
   tempo em aberto, filtros situacao_pendencia/motivo_pendencia/
   com_responsavel/funcionario, totalizadores, ordenacao, paginacao real,
   exportacao) depende do motor ainda inexistente: a consulta cai sempre em
   "relatorio ainda nao disponivel" (400) antes de chegar a qualquer logica
   especifica — RED real e esperado, documentado teste a teste, nunca
   inventado. situacao_pendencia/motivo_pendencia/com_responsavel/
   funcionario caem hoje no bucket de "parametro desconhecido" (nem chegam
   a validacao de enum/formulario), mesmo padrao ja documentado para os
   parametros de Inventario/Alocacoes antes de suas respectivas tasks Q
   (LineInventoryFilterParameterValidationTests/
   AllocationsFilterParameterValidationTests) — reaproveitado aqui via
   _assert_not_rejected_as_unknown_parameter.

Teste ja existente que usa "pendencies" como exemplo generico de relatorio
"genuinamente sem nenhum motor" (nem consulta, nem exportacao):
config/tests/test_line_inventory_report.py::OtherReportStillUnavailableTests::
test_pendencies_report_still_returns_400_engine_unavailable. Nao duplicado
aqui; PendenciesReportStillUnavailableTests cobre apenas o angulo
complementar ainda nao coberto (acesso direto ao DOWNLOAD) e documenta que,
quando REL-11-Q for implementada, aquele teste generico precisara trocar de
exemplo outra vez (registrado tambem na fonte da verdade, nao alterado
nesta task).

Fixtures de auditoria (Solicitante/Responsavel-resolvido) passam pelos
ENDPOINTS REAIS (pendencies:detail/update/claim/release), nunca criacao
direta de AllocationPendency/LineDailyActionAuditEvent por ORM — exceto
para simular explicitamente os cenarios "pre-auditoria" (exemplos C/G/I de
REL-11-C, via _make_legacy_pendency), unica excecao documentada pelo Test
Strategy de REL-11-C. O relogio e congelado via
mock.patch("pendencies.views.timezone.now", ...) para controlar
pendency_submitted_at/resolved_at/occurred_at com precisao de microssegundo
(REL-11-C: "mesmo objeto datetime now dentro da mesma requisicao").

Volume/particionamento em ZIP/limpeza de temporarios (REL-07, herdado
integralmente por REL-11-C) dependem de um exportador que ainda nao existe
(core/services/pendencies_export_service.py, proposto para REL-11-E) — sem
interface de configuracao de limiar para reduzir em teste sem inventar uma
API nova, o que esta explicitamente fora do escopo desta task. Cobertura
pendente, registrada aqui e na fonte da verdade; nenhuma tentativa de
simular conclusao. Pelo mesmo motivo, nenhum teste de custo especifico da
consulta em lote de auditoria (REL-11-E) e criado aqui alem do teste geral
de nao-escalonamento linear de queries (Secao 6 do enunciado desta task).
"""

import csv
import io
import itertools
import json
import os
import re
import shutil
import zipfile
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
from employees.models import Employee
from pendencies.models import AllocationPendency
from telecom.models import LineDailyActionAuditEvent, PhoneLine, SIMcard
from users.models import SystemUser

PASSWORD = "StrongPass123"
REPORTS_URL_NAME = "reports_home"
EXPORT_URL_NAME = "reports_export"  # ja registrado desde REL-08-E

ActionType = AllocationPendency.ActionType

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

# Deploy real da auditoria em PRD (T9), usado para ilustrar os casos
# "sem evento de abertura"/"sem evento de resolucao" (exemplos C/G/I de
# REL-11-C). Qualquer pendency_submitted_at/resolved_at ANTES desta data
# nunca tem evento real correspondente.
AUDIT_DEPLOY_DATE = date(2026, 9, 14)

EXPECTED_COLUMN_HEADERS = [
    "Linha",
    "Funcionário",
    "Solicitante",
    "Responsável",
    "Situação",
    "Motivo",
    "Tempo em aberto",
    "Registro",
    "Funcionário excluído",
]

NOT_ASSIGNED_LABEL = "Não atribuída"
NOT_AVAILABLE_LABEL = "Não disponível (anterior à auditoria)"

_iccid_counter = itertools.count(1)
_employee_counter = itertools.count(1)


def _create_user(email, role, **extra):
    return SystemUser.objects.create_user(email=email, password=PASSWORD, role=role, **extra)


def _local_midnight(d):
    return timezone.make_aware(datetime.combine(d, time.min))


def _local_last_instant(d):
    return timezone.make_aware(datetime.combine(d, time(23, 59, 59, 999999)))


def _make_line(phone_number, *, delete_line=False, delete_sim=False, cascade_delete_sim=False, released_by=None):
    """Mesmo padrao de config/tests/test_allocations_report.py::_make_line."""
    sim = SIMcard.objects.create(
        iccid=f"8900000000001{next(_iccid_counter):05d}", carrier="TIM"
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


def _make_supervisor(label):
    """Ator SUPER com corporate_email == employee.corporate_email do seu
    proprio portfolio (users/models.py::scope_employee_queryset:
    SUPER so enxerga/abre pendencia de employee cujo corporate_email seja o
    proprio e-mail do supervisor), mesmo padrao ja usado em
    pendencies/tests/test_line_status_web_restriction.py."""
    return _create_user(f"pend.super.{label}@test.com", SystemUser.Role.SUPER)


def _make_employee_for(supervisor, label=None, *, deleted=False):
    suffix = label or next(_employee_counter)
    employee = Employee.objects.create(
        full_name=f"Pendencia Teste {suffix}",
        corporate_email=supervisor.email,
        employee_id=f"PEND-{suffix}",
        teams=Employee.UnitChoices.JOINVILLE,
        status=Employee.Status.ACTIVE,
    )
    if deleted:
        employee.delete()
        employee.refresh_from_db()
    return employee


def _allocate(line, admin, employee):
    return AllocationService.allocate_line(employee=employee, phone_line=line, allocated_by=admin)


def _release(allocation, admin):
    return AllocationService.release_line(allocation, released_by=admin)


def _post(client, url_name, moment, **payload):
    """POST autenticado com o relogio de pendencies/views.py congelado em
    `moment` — garante pendency_submitted_at/resolved_at/occurred_at do
    evento de auditoria correspondente com igualdade exata (REL-11-C:
    "mesmo objeto datetime now dentro da mesma requisicao")."""
    with mock.patch("pendencies.views.timezone.now", return_value=moment):
        return client.post(
            reverse(url_name), data=json.dumps(payload), content_type="application/json"
        )


def _detail_get_or_create(client, actor, employee, allocation=None):
    client.force_login(actor)
    params = {"employee_id": employee.pk}
    if allocation is not None:
        params["allocation_id"] = allocation.pk
    response = client.get(reverse("pendencies:detail"), params)
    assert response.status_code == 200, response.content
    return AllocationPendency.objects.get(pk=response.json()["id"])


def _open_or_reopen(client, opener, pendency_id, action, moment):
    """Mesmo endpoint real cobre abertura (pendency.resolved_at is None) e
    reabertura (pendency.resolved_at preenchido): PendencyUpdateView decide
    OPENED vs REOPENED sozinho a partir do estado atual."""
    client.force_login(opener)
    response = _post(
        client, "pendencies:update", moment,
        pendency_id=pendency_id, action=action, observation="", line_status="",
    )
    assert response.status_code == 200, response.content
    return response


def _open_pendency(client, opener, employee, action, moment, allocation=None):
    pendency = _detail_get_or_create(client, opener, employee, allocation)
    _open_or_reopen(client, opener, pendency.pk, action, moment)
    pendency.refresh_from_db()
    return pendency


def _reopen_pendency(client, opener, pendency, action, moment):
    _open_or_reopen(client, opener, pendency.pk, action, moment)
    pendency.refresh_from_db()
    return pendency


def _claim(client, admin, pendency, moment):
    client.force_login(admin)
    response = _post(client, "pendencies:claim", moment, pendency_id=pendency.pk)
    assert response.status_code == 200, response.content
    pendency.refresh_from_db()
    return pendency


def _resolve(client, admin, pendency, moment):
    client.force_login(admin)
    response = _post(
        client, "pendencies:update", moment,
        pendency_id=pendency.pk, action=ActionType.NO_ACTION, observation="", line_status="",
    )
    assert response.status_code == 200, response.content
    pendency.refresh_from_db()
    return pendency


def _make_legacy_pendency(*, employee, allocation=None, action, last_submitted_action, pendency_submitted_at, resolved_at=None, technical_responsible=None):
    """Simula pendencia legada, cujo ciclo (abertura e/ou resolucao) ocorreu
    ANTES do deploy da auditoria em PRD (AUDIT_DEPLOY_DATE): cria o
    registro diretamente por ORM, sem o(s) evento(s) correspondente(s) de
    LineDailyActionAuditEvent. Unica excecao documentada em REL-11-C/T ao
    uso dos endpoints reais — a auditoria em si sempre nasce dos mesmos
    endpoints, entao nao ha outra forma real de reproduzir dado legado
    anterior ao deploy. `action` deve refletir o estado real do ciclo
    (NO_ACTION quando resolvida, por design de
    AllocationPendency.record_action_change)."""
    return AllocationPendency.objects.create(
        employee=employee,
        allocation=allocation,
        action=action,
        last_submitted_action=last_submitted_action,
        pendency_submitted_at=pendency_submitted_at,
        resolved_at=resolved_at,
        technical_responsible=technical_responsible,
    )


def _report_url(pairs):
    return f"{reverse(REPORTS_URL_NAME)}?{urlencode(pairs)}"


def _export_url(formato, pairs):
    return f"{reverse(EXPORT_URL_NAME, kwargs={'formato': formato})}?{urlencode(pairs)}"


def _base_pairs(data_inicial=PERIOD_START, data_final=PERIOD_END, **extra):
    pairs = [
        ("relatorio", "pendencies"),
        ("data_inicial", data_inicial),
        ("data_final", data_final),
    ]
    pairs.extend(extra.items())
    return pairs


class PendenciesReportInitialLoadTests(TestCase):
    """Relatorio selecionado sem datas: sem motor, sem erro prematuro
    (ReportsHomeView.get so valida quando data_inicial/data_final estao
    presentes) — GREEN real hoje, independente do motor."""

    def setUp(self):
        self.admin = _create_user("admin.pend.initial@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_report_selected_without_dates_does_not_run_engine_or_error(self):
        response = self.client.get(_report_url([("relatorio", "pendencies")]))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode().lower()
        self.assertNotIn("obrigat", content)
        self.assertNotIn("erro", content)


class PendenciesReportSharedValidationAppliesTests(TestCase):
    """Contrato comum (REL-07), validado pelo form de fallback
    (WhatsAppSealReportQueryForm) ANTES do despacho por relatorio
    (_validate_report_query_params so verifica `available_relatorios`
    depois de validar o form). GREEN real hoje — nao depende do motor de
    Pendencias existir."""

    def setUp(self):
        self.admin = _create_user("admin.pend.sharedval@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_missing_data_inicial_rejected(self):
        response = self.client.get(
            _report_url([("relatorio", "pendencies"), ("data_final", PERIOD_END)])
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_data_final_rejected(self):
        response = self.client.get(
            _report_url([("relatorio", "pendencies"), ("data_inicial", PERIOD_START)])
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_date_format_rejected(self):
        response = self.client.get(
            _report_url([("relatorio", "pendencies"), ("data_inicial", "31/09/2026"), ("data_final", PERIOD_END)])
        )
        self.assertEqual(response.status_code, 400)

    def test_inverted_dates_rejected(self):
        response = self.client.get(
            _report_url([("relatorio", "pendencies"), ("data_inicial", PERIOD_END), ("data_final", PERIOD_START)])
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
            f"{url}?relatorio=pendencies&data_inicial={PERIOD_START}&data_inicial=2026-09-02&data_final={PERIOD_END}"
        )
        self.assertEqual(response.status_code, 400)

    def test_unknown_generic_query_parameter_rejected(self):
        response = self.client.get(_report_url(_base_pairs(campo_totalmente_inexistente="x")))
        self.assertEqual(response.status_code, 400)

    def test_search_term_longer_than_20_chars_rejected(self):
        response = self.client.get(_report_url(_base_pairs(linha="1" * 21)))
        self.assertEqual(response.status_code, 400)


class PendenciesDateBoundaryOverflowTests(TestCase):
    """REPORTS_SENIOR_REVIEW (.git/REPORTS_SENIOR_REVIEW.md) achado 3:
    `_period_bounds` (core/services/pendencies_report_service.py) soma 1 dia
    a `data_final` para obter o limite exclusivo do periodo (fuso local) —
    com data_final=date.max isso e `date.max + timedelta(days=1)`, que
    estoura (`OverflowError: date value out of range`) antes de qualquer
    consulta ao banco, nunca capturado pela view (500 real). O form agora
    rejeita esse valor como erro de campo, tanto na consulta quanto na
    exportacao (mesmo PendenciesReportQueryForm valida os dois endpoints,
    ver _validate_report_query_params). Nenhum limite arbitrario de duracao
    de periodo: apenas a fronteira realmente representavel pelo calculo do
    limite exclusivo (date.max - 1 dia)."""

    def setUp(self):
        self.admin = _create_user("admin.pend.dateboundary@test.com", SystemUser.Role.ADMIN)
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


class PendenciesReportStillUnavailableTests(TestCase):
    """Repropositada em REL-11-E (mesma obsolescencia ja prevista em
    REL-11-Q para este angulo, ver AllocationsReportStillUnavailableTests em
    test_allocations_report.py, repropositada de forma identica em
    REL-10-E): ate REL-11-E, "pendencies" estava em REPORT_QUERY_ENGINES mas
    nao em REPORT_EXPORT_ENGINES, entao o download direto com filtros comuns
    validos retornava 400 pelo ramo 'consulta existe, exportacao ainda nao'.
    REL-11-E adiciona "pendencies" a REPORT_EXPORT_ENGINES e implementa
    core/services/pendencies_export_service — a alegacao de indisponibilidade
    da exportacao deixou de ser verdadeira, mesma situacao ja resolvida para
    whatsapp_seal/line_inventory/allocations em suas respectivas tasks E. O
    requisito util (download direto do relatorio, filtros comuns validos) e
    preservado, invertendo a asserção para a disponibilidade agora exigida
    pelo contrato (REL-07/REL-11-C): 200, CSV real, anexo para download. O
    lado da CONSULTA continua coberto por
    config/tests/test_line_inventory_report.py::OtherReportStillUnavailableTests
    — repropositada em REL-11-Q para "line_history" (o unico relatorio
    genuinamente ainda sem nenhum motor naquela etapa) e novamente em
    REL-12-Q para "daily_indicators", apos "line_history" tambem ganhar
    motor de consulta (ver config/tests/test_line_history_report.py::
    LineHistoryReportEngineUnavailableBaselineTests para o angulo de
    exportacao de line_history, ainda sem motor)."""

    def setUp(self):
        self.admin = _create_user("admin.pend.unavailable@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_export_now_returns_200_attachment_with_valid_common_params(self):
        """Antes de REL-11-E (RED por design, documentado em REL-11-T/Q):
        400 'A exportação deste relatório ainda não está disponível nesta
        etapa.'. Agora que o motor de exportacao existe, o mesmo acesso
        direto com filtros comuns validos deve retornar 200, com o arquivo
        como anexo — nao mais a mensagem de indisponibilidade."""
        response = self.client.get(_export_url("csv", _base_pairs()))
        self.assertEqual(response.status_code, 200)
        self.assertIn("csv", response.headers.get("Content-Type", "").lower())
        self.assertIn("attachment", response.headers.get("Content-Disposition", ""))
        self.assertNotContains(
            response,
            "A exportação deste relatório ainda não está disponível nesta etapa.",
            status_code=200,
        )


class PendenciesFilterParameterValidationTests(TestCase):
    """Secao 5 do enunciado: nenhum dos quatro filtros especificos de
    REL-11-C (situacao_pendencia/motivo_pendencia/com_responsavel/
    funcionario) esta em REPORT_SPECIFIC_PARAM_NAMES/REPORT_FORM_CLASSES
    ainda — QUALQUER valor (valido ou invalido) e rejeitado hoje pela
    mensagem generica "Parametro desconhecido: <nome>.", mesmo gap ja
    documentado para Inventario/Alocacoes antes de suas tasks Q. O teste
    abaixo prova o requisito real (rejeicao pela validacao de CAMPO, nunca
    mais pela mensagem generica) e falha hoje por design (RED real: a
    mensagem generica ainda esta presente)."""

    def setUp(self):
        self.admin = _create_user("admin.pend.paramval@test.com", SystemUser.Role.ADMIN)
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

    def test_situacao_pendencia_invalid_value_not_treated_as_unknown_parameter(self):
        response = self.client.get(_report_url(_base_pairs(situacao_pendencia="invalido")))
        self._assert_not_rejected_as_unknown_parameter(response, "situacao_pendencia")

    def test_motivo_pendencia_invalid_value_not_treated_as_unknown_parameter(self):
        response = self.client.get(_report_url(_base_pairs(motivo_pendencia="invalido")))
        self._assert_not_rejected_as_unknown_parameter(response, "motivo_pendencia")

    def test_com_responsavel_invalid_value_not_treated_as_unknown_parameter(self):
        response = self.client.get(_report_url(_base_pairs(com_responsavel="invalido")))
        self._assert_not_rejected_as_unknown_parameter(response, "com_responsavel")

    def test_funcionario_valid_value_returns_200_with_eligible_row(self):
        """Corrigido em REL-11-Q (causa comprovada): diferente dos outros
        tres filtros desta classe (enum fechado, sempre 400 de validacao de
        CAMPO para valor invalido, mesmo com o motor existindo),
        'funcionario' e busca livre sem conceito de 'valor invalido' proprio
        — uma vez reconhecido pelo whitelist/form, executa a consulta
        normalmente (200), mesmo padrao do controle positivo ja usado para
        situacao_pendencia. A asserção original (400 fixo, herdada do
        helper generico _assert_not_rejected_as_unknown_parameter) ficou
        logicamente incompativel com o proprio nome do teste ('nao tratado
        como parametro desconhecido') assim que o motor de Pendencias
        existe de verdade: um parametro reconhecido e com valor
        sintaticamente valido nunca retorna 400. Mantido o requisito real:
        nunca mais a mensagem generica, e consulta executada com sucesso."""
        supervisor = _make_supervisor("filtro-funcionario")
        admin = self.admin
        employee = _make_employee_for(supervisor, "filtro-funcionario")
        line, _ = _make_line("+5511930000003")
        allocation = _allocate(line, admin, employee)
        _open_pendency(
            self.client, supervisor, employee, ActionType.PENDING,
            _local_midnight(date(2026, 9, 10)), allocation=allocation,
        )
        self.client.force_login(admin)
        response = self.client.get(_report_url(_base_pairs(funcionario=employee.full_name)))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Parâmetro desconhecido: funcionario", response.content.decode())
        self.assertContains(response, "+5511930000003")

    def test_situacao_pendencia_valid_value_control_returns_200_with_eligible_row(self):
        supervisor = _make_supervisor("filtro-situacao")
        admin = self.admin
        employee = _make_employee_for(supervisor, "filtro-situacao")
        line, _ = _make_line("+5511930000001")
        allocation = _allocate(line, admin, employee)
        _open_pendency(
            self.client, supervisor, employee, ActionType.PENDING,
            _local_midnight(date(2026, 9, 10)), allocation=allocation,
        )
        self.client.force_login(admin)
        response = self.client.get(_report_url(_base_pairs(situacao_pendencia="aberta")))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "+5511930000001")

    def test_com_responsavel_invalid_combo_with_resolvida_yields_zero_registros(self):
        """Fato de codigo documentado em REL-11-C: com_responsavel=com so
        reflete technical_responsible ATUAL (nunca o resolvedor), que e
        sempre limpo por record_action_change na resolucao — combinado com
        situacao_pendencia=resolvida, o resultado e SEMPRE vazio, nunca um
        defeito. Teste explicito para nao confundir as duas coisas."""
        supervisor = _make_supervisor("filtro-comresp")
        admin = self.admin
        employee = _make_employee_for(supervisor, "filtro-comresp")
        line, _ = _make_line("+5511930000002")
        allocation = _allocate(line, admin, employee)
        pendency = _open_pendency(
            self.client, supervisor, employee, ActionType.PENDING,
            _local_midnight(date(2026, 9, 10)), allocation=allocation,
        )
        _claim(self.client, admin, pendency, _local_midnight(date(2026, 9, 11)))
        _resolve(self.client, admin, pendency, _local_midnight(date(2026, 9, 12)))

        self.client.force_login(admin)
        response = self.client.get(
            _report_url(_base_pairs(situacao_pendencia="resolvida", com_responsavel="com"))
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "+5511930000002")


class PendenciesGranularityTests(TestCase):
    """Secao 2 do enunciado: uma linha por AllocationPendency elegivel
    (pendency_submitted_at preenchido), reabertura atualiza a mesma
    entidade sem duplicar, pendencia inerte (exemplo F) nunca aparece,
    multiplas pendencias da mesma linha/funcionario aparecem distintas
    (exemplos A+H)."""

    def setUp(self):
        self.admin = _create_user("admin.pend.granularity@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_one_row_per_eligible_pendency(self):
        supervisor = _make_supervisor("gran-one")
        employee = _make_employee_for(supervisor, "gran-one")
        line, _ = _make_line("+5511931000001")
        allocation = _allocate(line, self.admin, employee)
        _open_pendency(
            self.client, supervisor, employee, ActionType.RECONNECT_WHATSAPP,
            _local_midnight(date(2026, 9, 10)), allocation=allocation,
        )
        self.client.force_login(self.admin)
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511931000001")

    def test_reopened_pendency_updates_same_row_without_duplication(self):
        supervisor = _make_supervisor("gran-reopen")
        employee = _make_employee_for(supervisor, "gran-reopen")
        line, _ = _make_line("+5511931000002")
        allocation = _allocate(line, self.admin, employee)
        pendency = _open_pendency(
            self.client, supervisor, employee, ActionType.PENDING,
            _local_midnight(date(2026, 9, 5)), allocation=allocation,
        )
        _claim(self.client, self.admin, pendency, _local_midnight(date(2026, 9, 6)))
        _resolve(self.client, self.admin, pendency, _local_midnight(date(2026, 9, 7)))
        _reopen_pendency(
            self.client, supervisor, pendency, ActionType.NEW_NUMBER,
            _local_midnight(date(2026, 9, 8)),
        )

        self.assertEqual(AllocationPendency.objects.filter(pk=pendency.pk).count(), 1)
        self.client.force_login(self.admin)
        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        self.assertEqual(content.count("+5511931000002"), 1)

    def test_inert_pendency_without_action_never_appears(self):
        """Exemplo F de REL-11-C: modal aberto (get_or_create via
        pendencies:detail), acao nunca definida — pendency_submitted_at
        continua nulo, fora do conjunto elegivel em qualquer periodo."""
        supervisor = _make_supervisor("gran-inert")
        employee = _make_employee_for(supervisor, "gran-inert")
        line, _ = _make_line("+5511931000003")
        allocation = _allocate(line, self.admin, employee)
        _detail_get_or_create(self.client, self.admin, employee, allocation)

        self.client.force_login(self.admin)
        response = self.client.get(_report_url(_base_pairs(data_inicial="2020-01-01", data_final="2030-01-01")))
        self.assertNotContains(response, "+5511931000003")

    def test_multiple_pendencies_same_line_different_allocations_appear_as_distinct_rows(self):
        """Exemplos A+H de REL-11-C: mesma linha, alocacoes diferentes
        (liberada e realocada), pendencias proprias — aparecem como duas
        linhas distintas."""
        supervisor = _make_supervisor("gran-sameline")
        employee_a = _make_employee_for(supervisor, "gran-sameline-a")
        employee_h = _make_employee_for(supervisor, "gran-sameline-h")
        line, _ = _make_line("+5511931000004")

        allocation_a = _allocate(line, self.admin, employee_a)
        _open_pendency(
            self.client, supervisor, employee_a, ActionType.RECONNECT_WHATSAPP,
            _local_midnight(date(2026, 9, 5)), allocation=allocation_a,
        )
        _release(allocation_a, self.admin)
        line.status = PhoneLine.Status.AVAILABLE
        line.save(update_fields=["status"])

        allocation_h = _allocate(line, self.admin, employee_h)
        _open_pendency(
            self.client, supervisor, employee_h, ActionType.PENDING,
            _local_midnight(date(2026, 9, 22)), allocation=allocation_h,
        )

        self.client.force_login(self.admin)
        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        self.assertEqual(content.count("+5511931000004"), 2)

    def test_multiple_pendencies_same_employee_over_time_appear_as_distinct_rows(self):
        """Um mesmo funcionario pode ter uma pendencia 'sem alocacao'
        (aguardando linha) e, depois, uma pendencia ligada a alocacao que
        recebeu — ambas coexistem como linhas distintas (REL-11-C,
        'Granularidade decidida')."""
        supervisor = _make_supervisor("gran-multi-emp")
        employee = _make_employee_for(supervisor, "gran-multi-emp")
        _open_pendency(
            self.client, supervisor, employee, ActionType.PENDING,
            _local_midnight(date(2026, 9, 5)), allocation=None,
        )
        line, _ = _make_line("+5511931000005")
        allocation = _allocate(line, self.admin, employee)
        _open_pendency(
            self.client, supervisor, employee, ActionType.NEW_NUMBER,
            _local_midnight(date(2026, 9, 12)), allocation=allocation,
        )

        self.client.force_login(self.admin)
        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        self.assertEqual(content.count(employee.full_name), 2)


class PendenciesPeriodTests(TestCase):
    """Secao 2: periodo por pendency_submitted_at ('aberta/criada no
    periodo'), fronteiras inclusivas (inicio local inclusivo ate inicio
    local do dia posterior ao fim, exclusivo, America/Sao_Paulo, REL-07),
    e o exemplo D de REL-11-C (aberta fora do periodo, resolvida dentro,
    NAO entra)."""

    def setUp(self):
        self.admin = _create_user("admin.pend.period@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_start_boundary_inclusive(self):
        supervisor = _make_supervisor("period-start")
        employee = _make_employee_for(supervisor, "period-start")
        line, _ = _make_line("+5511932000001")
        allocation = _allocate(line, self.admin, employee)
        _open_pendency(
            self.client, supervisor, employee, ActionType.PENDING,
            _local_midnight(PERIOD_START_DATE), allocation=allocation,
        )
        self.client.force_login(self.admin)
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511932000001")

    def test_instant_before_start_boundary_excluded(self):
        supervisor = _make_supervisor("period-before")
        control_employee = _make_employee_for(supervisor, "period-before-ctl")
        excluded_employee = _make_employee_for(supervisor, "period-before-exc")
        control_line, _ = _make_line("+5511932000098")
        excluded_line, _ = _make_line("+5511932000002")
        control_allocation = _allocate(control_line, self.admin, control_employee)
        excluded_allocation = _allocate(excluded_line, self.admin, excluded_employee)

        _open_pendency(
            self.client, supervisor, control_employee, ActionType.PENDING,
            _local_midnight(PERIOD_START_DATE), allocation=control_allocation,
        )
        _open_pendency(
            self.client, supervisor, excluded_employee, ActionType.PENDING,
            _local_midnight(PERIOD_START_DATE) - timedelta(microseconds=1), allocation=excluded_allocation,
        )

        self.client.force_login(self.admin)
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511932000098")
        self.assertNotContains(response, "+5511932000002")

    def test_end_boundary_inclusive_last_local_instant(self):
        supervisor = _make_supervisor("period-end")
        employee = _make_employee_for(supervisor, "period-end")
        line, _ = _make_line("+5511932000003")
        allocation = _allocate(line, self.admin, employee)
        _open_pendency(
            self.client, supervisor, employee, ActionType.PENDING,
            _local_last_instant(PERIOD_END_DATE), allocation=allocation,
        )
        self.client.force_login(self.admin)
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511932000003")

    def test_instant_at_start_of_day_after_end_excluded(self):
        supervisor = _make_supervisor("period-after")
        control_employee = _make_employee_for(supervisor, "period-after-ctl")
        excluded_employee = _make_employee_for(supervisor, "period-after-exc")
        control_line, _ = _make_line("+5511932000097")
        excluded_line, _ = _make_line("+5511932000004")
        control_allocation = _allocate(control_line, self.admin, control_employee)
        excluded_allocation = _allocate(excluded_line, self.admin, excluded_employee)

        _open_pendency(
            self.client, supervisor, control_employee, ActionType.PENDING,
            _local_last_instant(PERIOD_END_DATE), allocation=control_allocation,
        )
        _open_pendency(
            self.client, supervisor, excluded_employee, ActionType.PENDING,
            _local_midnight(PERIOD_END_DATE + timedelta(days=1)), allocation=excluded_allocation,
        )

        self.client.force_login(self.admin)
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511932000097")
        self.assertNotContains(response, "+5511932000004")

    def test_opened_outside_period_never_enters_even_if_resolved_inside(self):
        """Exemplo D de REL-11-C: aberta 20/08/2026 (fora do periodo
        01/09-24/09), resolvida 05/09/2026 (dentro) — NAO entra com 'aberta
        no periodo' (opcao decidida)."""
        supervisor = _make_supervisor("period-example-d")
        employee = _make_employee_for(supervisor, "period-example-d")
        line, _ = _make_line("+5511932000005")
        allocation = _allocate(line, self.admin, employee)
        pendency = _open_pendency(
            self.client, supervisor, employee, ActionType.PENDING,
            _local_midnight(date(2026, 8, 20)), allocation=allocation,
        )
        _claim(self.client, self.admin, pendency, _local_midnight(date(2026, 9, 4)))
        _resolve(self.client, self.admin, pendency, _local_midnight(date(2026, 9, 5)))

        self.client.force_login(self.admin)
        response = self.client.get(_report_url(_base_pairs()))
        self.assertNotContains(response, "+5511932000005")

    def test_resolved_at_alone_does_not_substitute_period_reference(self):
        """Controle inverso: resolved_at DENTRO do periodo, mas
        pendency_submitted_at FORA — reforca que resolved_at nunca e usado
        como referencia de periodo nesta entrega (decisao do usuario,
        REL-11-C)."""
        supervisor = _make_supervisor("period-inverse")
        employee = _make_employee_for(supervisor, "period-inverse")
        line, _ = _make_line("+5511932000006")
        allocation = _allocate(line, self.admin, employee)
        pendency = _open_pendency(
            self.client, supervisor, employee, ActionType.PENDING,
            _local_midnight(date(2026, 7, 1)), allocation=allocation,
        )
        _claim(self.client, self.admin, pendency, _local_midnight(date(2026, 9, 9)))
        _resolve(self.client, self.admin, pendency, _local_midnight(date(2026, 9, 10)))

        self.client.force_login(self.admin)
        response = self.client.get(_report_url(_base_pairs()))
        self.assertNotContains(response, "+5511932000006")


class PendenciesSolicitanteResponsavelTests(TestCase):
    """Secao 3 do enunciado: os tres estados reais de Responsavel, o rotulo
    de Solicitante ausente, a correlacao exata por occurred_at, e a
    independencia das duas lacunas (exemplos A, B, C, G, I de REL-11-C)."""

    def setUp(self):
        self.admin = _create_user("admin.pend.solresp@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_open_pendency_without_responsible_shows_not_assigned_label(self):
        """Exemplo A: aberta com evento real, nunca assumida — Responsavel
        = 'Nao atribuida' (estado b), nunca 'Nao disponivel'."""
        supervisor = _make_supervisor("solresp-a")
        employee = _make_employee_for(supervisor, "solresp-a")
        line, _ = _make_line("+5511933000001")
        allocation = _allocate(line, self.admin, employee)
        _open_pendency(
            self.client, supervisor, employee, ActionType.RECONNECT_WHATSAPP,
            _local_midnight(date(2026, 9, 5)), allocation=allocation,
        )

        self.client.force_login(self.admin)
        response = self.client.get(_report_url(_base_pairs(linha="933000001")))
        self.assertContains(response, supervisor.get_full_name().strip() or supervisor.email)
        self.assertContains(response, NOT_ASSIGNED_LABEL)
        self.assertNotContains(response, NOT_AVAILABLE_LABEL)

    def test_open_pendency_with_current_responsible_shows_name(self):
        """Exemplo B: aberta com evento real, ja assumida — Responsavel =
        nome do admin atual (estado a)."""
        supervisor = _make_supervisor("solresp-b")
        employee = _make_employee_for(supervisor, "solresp-b")
        responsible_admin = _create_user(
            "carla.responsavel@test.com", SystemUser.Role.ADMIN, first_name="Carla"
        )
        line, _ = _make_line("+5511933000002")
        allocation = _allocate(line, self.admin, employee)
        pendency = _open_pendency(
            self.client, supervisor, employee, ActionType.NEW_NUMBER,
            _local_midnight(date(2026, 9, 8)), allocation=allocation,
        )
        _claim(self.client, responsible_admin, pendency, _local_midnight(date(2026, 9, 9)))

        self.client.force_login(self.admin)
        response = self.client.get(_report_url(_base_pairs(linha="933000002")))
        self.assertContains(response, "Carla")
        self.assertNotContains(response, NOT_ASSIGNED_LABEL)

    def test_resolved_pendency_with_real_events_shows_solicitante_gap_and_responsavel_name(self):
        """Exemplo C de REL-11-C: abertura pre-auditoria (sem evento OPENED
        real — 10/09, antes de AUDIT_DEPLOY_DATE), resolucao pos-auditoria
        com evento RESOLVED real (16/09) — Solicitante = 'Nao disponivel',
        MAS Responsavel = nome de quem resolveu — as duas lacunas sao
        independentes, nunca confundidas."""
        supervisor = _make_supervisor("solresp-c")
        employee = _make_employee_for(supervisor, "solresp-c")
        resolver_admin = _create_user(
            "denise.resolveu@test.com", SystemUser.Role.ADMIN, first_name="Denise"
        )
        line, _ = _make_line("+5511933000003")
        allocation = _allocate(line, self.admin, employee)
        pendency = _make_legacy_pendency(
            employee=employee,
            allocation=allocation,
            action=ActionType.RECONNECT_WHATSAPP,
            last_submitted_action=ActionType.RECONNECT_WHATSAPP,
            pendency_submitted_at=_local_midnight(date(2026, 9, 10)),
        )
        _claim(self.client, resolver_admin, pendency, _local_midnight(date(2026, 9, 15)))
        _resolve(self.client, resolver_admin, pendency, _local_midnight(date(2026, 9, 16)))

        self.client.force_login(self.admin)
        response = self.client.get(_report_url(_base_pairs(linha="933000003")))
        self.assertContains(response, NOT_AVAILABLE_LABEL)
        self.assertContains(response, "Denise")

    def test_fully_pre_audit_resolved_pendency_shows_both_gaps_distinctly(self):
        """Exemplo I de REL-11-C: abertura (02/09) e resolucao (06/09)
        ambas antes do deploy da auditoria — Solicitante E Responsavel
        mostram 'Nao disponivel (anterior a auditoria)', nunca 'Nao
        atribuida' (que so se aplica a pendencia ABERTA nunca assumida)."""
        supervisor = _make_supervisor("solresp-i")
        employee = _make_employee_for(supervisor, "solresp-i")
        line, _ = _make_line("+5511933000004")
        allocation = _allocate(line, self.admin, employee)
        _make_legacy_pendency(
            employee=employee,
            allocation=allocation,
            action=ActionType.NO_ACTION,
            last_submitted_action=ActionType.PENDING,
            pendency_submitted_at=_local_midnight(date(2026, 9, 2)),
            resolved_at=_local_midnight(date(2026, 9, 6)),
        )

        self.client.force_login(self.admin)
        response = self.client.get(_report_url(_base_pairs(linha="933000004")))
        content = response.content.decode()
        self.assertEqual(content.count(NOT_AVAILABLE_LABEL), 2)
        self.assertNotIn(NOT_ASSIGNED_LABEL, content)

    def test_pre_audit_still_open_pendency_shows_solicitante_gap_and_not_assigned_responsavel(self):
        """Exemplo G de REL-11-C, estado (b): aberta antes do deploy da
        auditoria (01/08/2026), ainda aberta hoje, nunca assumida —
        Solicitante = 'Nao disponivel'; Responsavel = 'Nao atribuida'
        (estado aberto nunca depende de auditoria)."""
        supervisor = _make_supervisor("solresp-g-b")
        employee = _make_employee_for(supervisor, "solresp-g-b")
        line, _ = _make_line("+5511933000005")
        allocation = _allocate(line, self.admin, employee)
        _make_legacy_pendency(
            employee=employee,
            allocation=allocation,
            action=ActionType.PENDING,
            last_submitted_action=ActionType.PENDING,
            pendency_submitted_at=_local_midnight(date(2026, 8, 1)),
        )

        self.client.force_login(self.admin)
        response = self.client.get(
            _report_url(_base_pairs(data_inicial="2026-07-01", data_final=PERIOD_END, linha="933000005"))
        )
        self.assertContains(response, NOT_AVAILABLE_LABEL)
        self.assertContains(response, NOT_ASSIGNED_LABEL)

    def test_pre_audit_still_open_pendency_with_current_responsible_shows_name(self):
        """Exemplo G, estado (a): mesma pendencia legada, mas ja assumida
        por um admin ATUAL — Responsavel mostra o nome atual normalmente
        (campo do modelo, nao depende de auditoria), Solicitante continua
        indisponivel."""
        supervisor = _make_supervisor("solresp-g-a")
        employee = _make_employee_for(supervisor, "solresp-g-a")
        responsible_admin = _create_user(
            "fatima.responsavel@test.com", SystemUser.Role.ADMIN, first_name="Fatima"
        )
        line, _ = _make_line("+5511933000006")
        allocation = _allocate(line, self.admin, employee)
        pendency = _make_legacy_pendency(
            employee=employee,
            allocation=allocation,
            action=ActionType.PENDING,
            last_submitted_action=ActionType.PENDING,
            pendency_submitted_at=_local_midnight(date(2026, 8, 1)),
        )
        _claim(self.client, responsible_admin, pendency, _local_midnight(date(2026, 9, 20)))

        self.client.force_login(self.admin)
        response = self.client.get(
            _report_url(_base_pairs(data_inicial="2026-07-01", data_final=PERIOD_END, linha="933000006"))
        )
        self.assertContains(response, NOT_AVAILABLE_LABEL)
        self.assertContains(response, "Fatima")

    def test_multi_cycle_event_selects_only_current_cycle_event_for_solicitante(self):
        """Correlacao exata exigida por REL-11-C: o Solicitante deve vir do
        evento cujo occurred_at bate com o pendency_submitted_at do CICLO
        ATUAL, nunca de um ciclo anterior da mesma pendencia. Primeiro
        ciclo aberto por um supervisor, resolvido, reaberto por OUTRO
        supervisor — Solicitante deve refletir o reabridor, nunca o
        abridor original."""
        first_opener = _make_supervisor("multicycle-first")
        second_opener = _make_supervisor("multicycle-second")
        employee = _make_employee_for(first_opener, "multicycle")
        line, _ = _make_line("+5511933000007")
        allocation = _allocate(line, self.admin, employee)

        pendency = _open_pendency(
            self.client, first_opener, employee, ActionType.PENDING,
            _local_midnight(date(2026, 9, 2)), allocation=allocation,
        )
        _claim(self.client, self.admin, pendency, _local_midnight(date(2026, 9, 3)))
        _resolve(self.client, self.admin, pendency, _local_midnight(date(2026, 9, 4)))
        # segundo_opener precisa enxergar o mesmo funcionario: ajusta o
        # corporate_email do funcionario para o e-mail do segundo supervisor
        # antes de reabrir (scope_employee_queryset exige correspondencia).
        Employee.objects.filter(pk=employee.pk).update(corporate_email=second_opener.email)
        _reopen_pendency(
            self.client, second_opener, pendency, ActionType.NEW_NUMBER,
            _local_midnight(date(2026, 9, 20)),
        )

        self.client.force_login(self.admin)
        response = self.client.get(_report_url(_base_pairs(linha="933000007")))
        second_name = second_opener.get_full_name().strip() or second_opener.email
        first_name = first_opener.get_full_name().strip() or first_opener.email
        self.assertContains(response, second_name)
        self.assertNotContains(response, first_name)

    def test_solicitante_never_confused_with_updated_by(self):
        """Solicitante deve vir do evento OPENED/REOPENED, nunca de
        updated_by (quem salvou por ultimo qualquer campo, inclusive uma
        observacao alterada depois pelo responsavel atual)."""
        opener = _make_supervisor("updatedby")
        employee = _make_employee_for(opener, "updatedby")
        responsible_admin = _create_user(
            "helio.updatedby@test.com", SystemUser.Role.ADMIN, first_name="Helio"
        )
        line, _ = _make_line("+5511933000008")
        allocation = _allocate(line, self.admin, employee)
        pendency = _open_pendency(
            self.client, opener, employee, ActionType.PENDING,
            _local_midnight(date(2026, 9, 5)), allocation=allocation,
        )
        _claim(self.client, responsible_admin, pendency, _local_midnight(date(2026, 9, 6)))
        # responsavel atual altera a observacao: updated_by passa a ser o
        # admin, mas o Solicitante do ciclo continua sendo quem abriu.
        self.client.force_login(responsible_admin)
        _post(
            self.client, "pendencies:update", _local_midnight(date(2026, 9, 7)),
            pendency_id=pendency.pk, action=pendency.action,
            observation="nota do responsavel", line_status="",
        )
        pendency.refresh_from_db()
        self.assertEqual(pendency.updated_by_id, responsible_admin.pk)

        self.client.force_login(self.admin)
        response = self.client.get(_report_url(_base_pairs(linha="933000008")))
        opener_name = opener.get_full_name().strip() or opener.email
        self.assertContains(response, opener_name)
        # Correcao comprovada (REL-11-Q): Helio e o technical_responsible
        # ATUAL desta pendencia aberta (claim antes da edicao de nota) — pelo
        # proprio contrato aprovado (REL-11-C, estado "a" da coluna
        # Responsavel), seu nome aparece legitimamente na coluna Responsavel,
        # sem relacao com updated_by. Um assertNotContains("Helio") global
        # contradiria essa regra ja aprovada; a asserção correta e restrita a
        # coluna Solicitante (celula, nao a pagina inteira), que e o que o
        # requisito desta task realmente exige.
        content = response.content.decode()
        row_start = content.rindex("<tr>", 0, content.index("+5511933000008"))
        row_end = content.index("</tr>", row_start)
        # Extracao tolerante a atributos no <td> (SVI-05 acrescentou um
        # atributo title/coluna de indicador de selo na mesma linha, sem
        # mudar a identidade/ordem das colunas pre-existentes referenciadas
        # por indice aqui); o parsing antigo exigia "<td>" literal, sem
        # nenhum atributo, o que nunca foi o contrato real da tela.
        cells = re.findall(r"<td[^>]*>(.*?)</td>", content[row_start:row_end], re.DOTALL)
        solicitante_cell = cells[2]
        self.assertEqual(solicitante_cell, opener_name)
        self.assertNotEqual(solicitante_cell, "Helio")


class PendenciesReasonAndOpenTimeTests(TestCase):
    """Secao 4 do enunciado: Motivo usa last_submitted_action (nunca 'Sem
    Acao'), e o calculo de tempo em aberto (inicio/termino/unidade/
    arredondamento/reabertura/inconsistencia) integralmente aprovado em
    REL-11-C."""

    def setUp(self):
        self.admin = _create_user("admin.pend.reason@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_motivo_uses_last_submitted_action_never_no_action_after_resolution(self):
        supervisor = _make_supervisor("motivo")
        employee = _make_employee_for(supervisor, "motivo")
        line, _ = _make_line("+5511934000001")
        allocation = _allocate(line, self.admin, employee)
        pendency = _open_pendency(
            self.client, supervisor, employee, ActionType.RECONNECT_WHATSAPP,
            _local_midnight(date(2026, 9, 5)), allocation=allocation,
        )
        self.assertEqual(pendency.action, ActionType.RECONNECT_WHATSAPP)
        _claim(self.client, self.admin, pendency, _local_midnight(date(2026, 9, 6)))
        _resolve(self.client, self.admin, pendency, _local_midnight(date(2026, 9, 7)))
        pendency.refresh_from_db()
        self.assertEqual(pendency.action, ActionType.NO_ACTION)
        self.assertEqual(pendency.last_submitted_action, ActionType.RECONNECT_WHATSAPP)

        self.client.force_login(self.admin)
        response = self.client.get(_report_url(_base_pairs(linha="934000001")))
        content = response.content.decode()
        self.assertIn("<td>Reconectar WhatsApp</td>", content)
        self.assertNotIn("<td>Sem Ação</td>", content)

    def test_open_time_for_resolved_pendency_uses_submission_to_resolution_days_floor(self):
        """Exemplo C de REL-11-C: 10/09 -> 16/09 = 6 dias corridos, valor
        deterministico independente do relogio real (ambas as pontas sao
        fixas)."""
        supervisor = _make_supervisor("tempo-resolvida")
        employee = _make_employee_for(supervisor, "tempo-resolvida")
        line, _ = _make_line("+5511934000002")
        allocation = _allocate(line, self.admin, employee)
        pendency = _open_pendency(
            self.client, supervisor, employee, ActionType.PENDING,
            _local_midnight(date(2026, 9, 10)), allocation=allocation,
        )
        _claim(self.client, self.admin, pendency, _local_midnight(date(2026, 9, 11)))
        _resolve(self.client, self.admin, pendency, _local_midnight(date(2026, 9, 16)))

        self.client.force_login(self.admin)
        response = self.client.get(_report_url(_base_pairs(linha="934000002")))
        self.assertContains(response, "<td>6</td>")

    def test_open_time_for_open_pendency_uses_generation_instant_not_data_final(self):
        """Situacao = Aberta: termino e o instante de geracao da consulta
        (generated_at), NUNCA data_final. Congela o relogio global durante
        a propria requisicao GET para tornar o resultado deterministico e,
        ao mesmo tempo, provar que data_final (24/09) nao e usado: o
        periodo pedido termina dias depois do instante de geracao
        congelado (15/09), mas a contagem deve refletir 15/09, nao 24/09."""
        supervisor = _make_supervisor("tempo-aberta")
        employee = _make_employee_for(supervisor, "tempo-aberta")
        line, _ = _make_line("+5511934000003")
        allocation = _allocate(line, self.admin, employee)
        _open_pendency(
            self.client, supervisor, employee, ActionType.PENDING,
            _local_midnight(date(2026, 9, 5)), allocation=allocation,
        )

        self.client.force_login(self.admin)
        frozen_generation_instant = _local_midnight(date(2026, 9, 15))
        with mock.patch("django.utils.timezone.now", return_value=frozen_generation_instant):
            response = self.client.get(_report_url(_base_pairs(linha="934000003")))
        self.assertContains(response, "<td>10</td>")  # 05/09 -> 15/09
        self.assertNotContains(response, "<td>19</td>")  # 05/09 -> 24/09 (data_final), nao deveria ser usado

    def test_reopening_resets_open_time_count(self):
        """Reabertura reinicia a contagem a partir do novo
        pendency_submitted_at — tempo do ciclo anterior a reabertura nao e
        somado (REL-11-C)."""
        supervisor = _make_supervisor("tempo-reabertura")
        employee = _make_employee_for(supervisor, "tempo-reabertura")
        line, _ = _make_line("+5511934000004")
        allocation = _allocate(line, self.admin, employee)
        pendency = _open_pendency(
            self.client, supervisor, employee, ActionType.PENDING,
            _local_midnight(date(2026, 9, 1)), allocation=allocation,
        )
        _claim(self.client, self.admin, pendency, _local_midnight(date(2026, 9, 2)))
        _resolve(self.client, self.admin, pendency, _local_midnight(date(2026, 9, 3)))
        _reopen_pendency(
            self.client, supervisor, pendency, ActionType.NEW_NUMBER,
            _local_midnight(date(2026, 9, 10)),
        )

        self.client.force_login(self.admin)
        frozen_generation_instant = _local_midnight(date(2026, 9, 15))
        with mock.patch("django.utils.timezone.now", return_value=frozen_generation_instant):
            response = self.client.get(_report_url(_base_pairs(linha="934000004")))
        self.assertContains(response, "<td>5</td>")  # 10/09 -> 15/09, nunca 14 (01/09 -> 15/09)

    def test_inconsistent_dates_show_dash_never_negative_number(self):
        """resolved_at < pendency_submitted_at nao deveria ocorrer pela
        logica de record_action_change, mas nao ha CheckConstraint de banco
        que impeca — simulado por update() direto no queryset, mesmo
        espirito de inconsistencia ja aceito em REL-09-C. Exibe '-', nunca
        um numero negativo."""
        supervisor = _make_supervisor("tempo-inconsistente")
        employee = _make_employee_for(supervisor, "tempo-inconsistente")
        line, _ = _make_line("+5511934000005")
        allocation = _allocate(line, self.admin, employee)
        pendency = _open_pendency(
            self.client, supervisor, employee, ActionType.PENDING,
            _local_midnight(date(2026, 9, 10)), allocation=allocation,
        )
        _claim(self.client, self.admin, pendency, _local_midnight(date(2026, 9, 11)))
        _resolve(self.client, self.admin, pendency, _local_midnight(date(2026, 9, 12)))
        AllocationPendency.objects.filter(pk=pendency.pk).update(
            resolved_at=_local_midnight(date(2026, 9, 5))
        )

        self.client.force_login(self.admin)
        response = self.client.get(_report_url(_base_pairs(linha="934000005")))
        content = response.content.decode()
        self.assertIn("<td>-</td>", content)
        for negative in ("-1", "-2", "-3", "-4", "-5", "-6", "-7"):
            self.assertNotIn(f"<td>{negative}</td>", content)


class PendenciesExclusionTests(TestCase):
    """Secao 5 do enunciado: exclusao logica de linha/SIMcard (so quando ha
    alocacao) e de funcionario (checkbox unico governa as tres), pendencia
    sem alocacao nunca afetada pela parte de linha/SIMcard (exemplo E)."""

    def setUp(self):
        self.admin = _create_user("admin.pend.exclusion@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_line_deleted_hidden_by_default_shown_when_included(self):
        supervisor = _make_supervisor("exclusion-line")
        control_employee = _make_employee_for(supervisor, "exclusion-line-ctl")
        excluded_employee = _make_employee_for(supervisor, "exclusion-line-exc")
        control_line, _ = _make_line("+5511935000098")
        excluded_line, _ = _make_line("+5511935000001")
        control_allocation = _allocate(control_line, self.admin, control_employee)
        excluded_allocation = _allocate(excluded_line, self.admin, excluded_employee)
        _open_pendency(
            self.client, supervisor, control_employee, ActionType.PENDING,
            _local_midnight(date(2026, 9, 10)), allocation=control_allocation,
        )
        _open_pendency(
            self.client, supervisor, excluded_employee, ActionType.PENDING,
            _local_midnight(date(2026, 9, 10)), allocation=excluded_allocation,
        )
        excluded_line.delete(released_by=self.admin)

        self.client.force_login(self.admin)
        default_resp = self.client.get(_report_url(_base_pairs()))
        self.assertContains(default_resp, "+5511935000098")
        self.assertNotContains(default_resp, "+5511935000001")

        included_resp = self.client.get(_report_url(_base_pairs(incluir_excluidos="1")))
        self.assertContains(included_resp, "+5511935000001")
        self.assertContains(included_resp, "Linha excluída")

    def test_simcard_deleted_hidden_by_default_shown_when_included(self):
        supervisor = _make_supervisor("exclusion-sim")
        employee = _make_employee_for(supervisor, "exclusion-sim")
        line, sim = _make_line("+5511935000002")
        allocation = _allocate(line, self.admin, employee)
        _open_pendency(
            self.client, supervisor, employee, ActionType.PENDING,
            _local_midnight(date(2026, 9, 10)), allocation=allocation,
        )
        SIMcard.all_objects.filter(pk=sim.pk).update(is_deleted=True)

        self.client.force_login(self.admin)
        default_resp = self.client.get(_report_url(_base_pairs()))
        self.assertNotContains(default_resp, "+5511935000002")

        included_resp = self.client.get(_report_url(_base_pairs(incluir_excluidos="1")))
        self.assertContains(included_resp, "+5511935000002")
        self.assertContains(included_resp, "SIMcard excluído")

    def test_employee_deleted_hidden_by_default_shown_when_included(self):
        """Decisao do usuario em REL-11-C: mesmo raciocinio ja aceito em
        REL-10-C — funcionario excluido tambem ocultado pelo checkbox
        padrao, porque 'Funcionario' e coluna central do catalogo."""
        supervisor = _make_supervisor("exclusion-emp")
        control_employee = _make_employee_for(supervisor, "exclusion-emp-ctl")
        target_employee = _make_employee_for(supervisor, "exclusion-emp-target")
        control_line, _ = _make_line("+5511935000097")
        target_line, _ = _make_line("+5511935000003")
        control_allocation = _allocate(control_line, self.admin, control_employee)
        target_allocation = _allocate(target_line, self.admin, target_employee)
        _open_pendency(
            self.client, supervisor, control_employee, ActionType.PENDING,
            _local_midnight(date(2026, 9, 10)), allocation=control_allocation,
        )
        _open_pendency(
            self.client, supervisor, target_employee, ActionType.PENDING,
            _local_midnight(date(2026, 9, 10)), allocation=target_allocation,
        )
        target_employee.delete()
        target_employee.refresh_from_db()

        self.client.force_login(self.admin)
        default_resp = self.client.get(_report_url(_base_pairs()))
        self.assertContains(default_resp, "+5511935000097")
        self.assertNotContains(default_resp, "+5511935000003")

        included_resp = self.client.get(_report_url(_base_pairs(incluir_excluidos="1")))
        self.assertContains(included_resp, "+5511935000003")
        self.assertContains(included_resp, "<td>Sim</td>")

    def test_pendency_without_allocation_never_affected_by_line_exclusion_policy(self):
        """Exemplo E de REL-11-C: funcionaria sem alocacao (aguardando
        linha) — Linha = 'Sem linha', Registro = 'Sem linha', nunca um dos
        quatro valores de exclusao, aparece com ou sem 'Incluir
        excluidos'."""
        supervisor = _make_supervisor("exclusion-noline")
        employee = _make_employee_for(supervisor, "exclusion-noline")
        _open_pendency(
            self.client, supervisor, employee, ActionType.PENDING,
            _local_midnight(date(2026, 9, 12)), allocation=None,
        )

        self.client.force_login(self.admin)
        default_resp = self.client.get(_report_url(_base_pairs()))
        self.assertContains(default_resp, employee.full_name)
        content = default_resp.content.decode()
        self.assertIn("<td>Sem linha</td>", content)

    def test_checkbox_included_does_not_restore_any_deleted_flag(self):
        supervisor = _make_supervisor("exclusion-norestore")
        employee = _make_employee_for(supervisor, "exclusion-norestore")
        line, _ = _make_line("+5511935000004")
        allocation = _allocate(line, self.admin, employee)
        _open_pendency(
            self.client, supervisor, employee, ActionType.PENDING,
            _local_midnight(date(2026, 9, 10)), allocation=allocation,
        )
        employee.delete()
        employee.refresh_from_db()
        line.delete(released_by=self.admin)

        self.client.force_login(self.admin)
        response = self.client.get(_report_url(_base_pairs(incluir_excluidos="1")))
        self.assertEqual(response.status_code, 200)

        line.refresh_from_db()
        employee.refresh_from_db()
        self.assertTrue(line.is_deleted)
        self.assertTrue(employee.is_deleted)


class PendenciesColumnsAndTotalsTests(TestCase):
    """Secao 4/5 do enunciado: nove colunas na ordem aprovada (cabecalho da
    tabela) e totalizadores diferenciados (total, linhas distintas,
    funcionarios distintos, abertas/resolvidas, sem responsavel dentro das
    abertas)."""

    def setUp(self):
        self.admin = _create_user("admin.pend.columns@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_nine_column_headers_present_in_approved_order(self):
        supervisor = _make_supervisor("columns")
        employee = _make_employee_for(supervisor, "columns")
        line, _ = _make_line("+5511936000001")
        allocation = _allocate(line, self.admin, employee)
        _open_pendency(
            self.client, supervisor, employee, ActionType.PENDING,
            _local_midnight(date(2026, 9, 10)), allocation=allocation,
        )

        self.client.force_login(self.admin)
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

    def test_totals_differ_from_each_other_with_shared_line_different_employees(self):
        """Reproduz o fechamento do exemplo de REL-11-C: A e H compartilham
        a linha L1 mas tem funcionarios diferentes — total de pendencias
        (2) != linhas distintas (1) != funcionarios distintos (2)."""
        supervisor = _make_supervisor("totals-shared")
        employee_a = _make_employee_for(supervisor, "totals-shared-a")
        employee_h = _make_employee_for(supervisor, "totals-shared-h")
        line, _ = _make_line("+5511936000002")

        allocation_a = _allocate(line, self.admin, employee_a)
        _open_pendency(
            self.client, supervisor, employee_a, ActionType.RECONNECT_WHATSAPP,
            _local_midnight(date(2026, 9, 5)), allocation=allocation_a,
        )
        _release(allocation_a, self.admin)
        line.status = PhoneLine.Status.AVAILABLE
        line.save(update_fields=["status"])

        allocation_h = _allocate(line, self.admin, employee_h)
        _open_pendency(
            self.client, supervisor, employee_h, ActionType.PENDING,
            _local_midnight(date(2026, 9, 22)), allocation=allocation_h,
        )

        self.client.force_login(self.admin)
        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        self.assertEqual(content.count("+5511936000002"), 2)

    def test_open_and_resolved_counts_sum_to_total(self):
        supervisor = _make_supervisor("totals-sum")
        open_employee = _make_employee_for(supervisor, "totals-sum-open")
        resolved_employee = _make_employee_for(supervisor, "totals-sum-resolved")
        open_line, _ = _make_line("+5511936000003")
        resolved_line, _ = _make_line("+5511936000004")
        open_allocation = _allocate(open_line, self.admin, open_employee)
        resolved_allocation = _allocate(resolved_line, self.admin, resolved_employee)
        _open_pendency(
            self.client, supervisor, open_employee, ActionType.PENDING,
            _local_midnight(date(2026, 9, 10)), allocation=open_allocation,
        )
        resolved_pendency = _open_pendency(
            self.client, supervisor, resolved_employee, ActionType.PENDING,
            _local_midnight(date(2026, 9, 11)), allocation=resolved_allocation,
        )
        _claim(self.client, self.admin, resolved_pendency, _local_midnight(date(2026, 9, 12)))
        _resolve(self.client, self.admin, resolved_pendency, _local_midnight(date(2026, 9, 13)))

        self.client.force_login(self.admin)
        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        self.assertIn("+5511936000003", content)
        self.assertIn("+5511936000004", content)

    def test_sem_responsavel_denominator_is_abertas_not_total(self):
        """'Sem responsavel' conta so dentro das ABERTAS sem
        technical_responsible — nunca inclui resolvidas (sempre sem
        responsavel por construcao, REL-11-C)."""
        supervisor = _make_supervisor("totals-semresp")
        open_no_resp = _make_employee_for(supervisor, "totals-semresp-a")
        open_with_resp = _make_employee_for(supervisor, "totals-semresp-b")
        resolved_employee = _make_employee_for(supervisor, "totals-semresp-c")
        line_a, _ = _make_line("+5511936000005")
        line_b, _ = _make_line("+5511936000006")
        line_c, _ = _make_line("+5511936000007")
        alloc_a = _allocate(line_a, self.admin, open_no_resp)
        alloc_b = _allocate(line_b, self.admin, open_with_resp)
        alloc_c = _allocate(line_c, self.admin, resolved_employee)

        _open_pendency(
            self.client, supervisor, open_no_resp, ActionType.PENDING,
            _local_midnight(date(2026, 9, 10)), allocation=alloc_a,
        )
        pendency_b = _open_pendency(
            self.client, supervisor, open_with_resp, ActionType.PENDING,
            _local_midnight(date(2026, 9, 10)), allocation=alloc_b,
        )
        _claim(self.client, self.admin, pendency_b, _local_midnight(date(2026, 9, 11)))
        pendency_c = _open_pendency(
            self.client, supervisor, resolved_employee, ActionType.PENDING,
            _local_midnight(date(2026, 9, 10)), allocation=alloc_c,
        )
        _claim(self.client, self.admin, pendency_c, _local_midnight(date(2026, 9, 11)))
        _resolve(self.client, self.admin, pendency_c, _local_midnight(date(2026, 9, 12)))

        self.client.force_login(self.admin)
        response = self.client.get(_report_url(_base_pairs()))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        for phone in ("+5511936000005", "+5511936000006", "+5511936000007"):
            self.assertIn(phone, content)

    def test_empty_result_set_returns_zero_totals_no_error(self):
        response = self.client.get(
            _report_url(_base_pairs(data_inicial="2020-01-01", data_final="2020-01-02"))
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("erro", response.content.decode().lower())


class PendenciesOrderingPaginationTests(TestCase):
    """Secao 6 do enunciado: pendency_submitted_at decrescente com
    desempate por pk decrescente, paginacao fixa em 50, filtros
    preservados entre paginas."""

    def setUp(self):
        self.admin = _create_user("admin.pend.pagination@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_descending_pendency_submitted_at_order(self):
        supervisor = _make_supervisor("order-desc")
        e1 = _make_employee_for(supervisor, "order-desc-1")
        e2 = _make_employee_for(supervisor, "order-desc-2")
        e3 = _make_employee_for(supervisor, "order-desc-3")
        l1, _ = _make_line("+5511937000001")
        l2, _ = _make_line("+5511937000002")
        l3, _ = _make_line("+5511937000003")
        _open_pendency(self.client, supervisor, e1, ActionType.PENDING, _local_midnight(date(2026, 9, 5)), allocation=_allocate(l1, self.admin, e1))
        _open_pendency(self.client, supervisor, e2, ActionType.PENDING, _local_midnight(date(2026, 9, 20)), allocation=_allocate(l2, self.admin, e2))
        _open_pendency(self.client, supervisor, e3, ActionType.PENDING, _local_midnight(date(2026, 9, 12)), allocation=_allocate(l3, self.admin, e3))

        self.client.force_login(self.admin)
        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        idx2 = content.index("+5511937000002")
        idx3 = content.index("+5511937000003")
        idx1 = content.index("+5511937000001")
        self.assertLess(idx2, idx3)
        self.assertLess(idx3, idx1)

    def test_tie_break_by_descending_pk(self):
        supervisor = _make_supervisor("order-tie")
        e1 = _make_employee_for(supervisor, "order-tie-1")
        e2 = _make_employee_for(supervisor, "order-tie-2")
        l1, _ = _make_line("+5511937000011")
        l2, _ = _make_line("+5511937000012")
        same_moment = _local_midnight(date(2026, 9, 15))
        p1 = _open_pendency(self.client, supervisor, e1, ActionType.PENDING, same_moment, allocation=_allocate(l1, self.admin, e1))
        p2 = _open_pendency(self.client, supervisor, e2, ActionType.PENDING, same_moment, allocation=_allocate(l2, self.admin, e2))
        self.assertLess(p1.pk, p2.pk)

        self.client.force_login(self.admin)
        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        idx2 = content.index("+5511937000012")
        idx1 = content.index("+5511937000011")
        self.assertLess(idx2, idx1)

    def test_first_page_has_50_rows_and_not_the_51st(self):
        supervisor = _make_supervisor("order-page1")
        for index in range(51):
            employee = _make_employee_for(supervisor, f"order-page1-{index}")
            line, _ = _make_line(f"+55119380{index:06d}")
            allocation = _allocate(line, self.admin, employee)
            _open_pendency(
                self.client, supervisor, employee, ActionType.PENDING,
                _local_midnight(date(2026, 9, 1 + (index % 20))), allocation=allocation,
            )
        self.client.force_login(self.admin)
        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        phone_hits = sum(1 for index in range(51) if f"+55119380{index:06d}" in content)
        self.assertEqual(phone_hits, 50)

    def test_filters_preserved_across_pagination_and_second_page_has_distinct_content(self):
        supervisor = _make_supervisor("order-page2")
        for index in range(51):
            employee = _make_employee_for(supervisor, f"order-page2-{index}")
            line, _ = _make_line(f"+55119381{index:06d}")
            allocation = _allocate(line, self.admin, employee)
            _open_pendency(
                self.client, supervisor, employee, ActionType.PENDING,
                _local_midnight(date(2026, 9, 1)) + timedelta(minutes=index), allocation=allocation,
            )

        self.client.force_login(self.admin)
        page1 = self.client.get(_report_url(_base_pairs(page="1")))
        page2 = self.client.get(_report_url(_base_pairs(page="2")))
        self.assertEqual(page1.status_code, 200)
        self.assertEqual(page2.status_code, 200)

        content1 = page1.content.decode()
        content2 = page2.content.decode()
        newest_number = f"+55119381{50:06d}"
        oldest_number = f"+55119381{0:06d}"
        self.assertIn(newest_number, content1)
        self.assertNotIn(newest_number, content2)
        self.assertIn(oldest_number, content2)
        self.assertNotIn(oldest_number, content1)

        self.assertIn(f'name="data_inicial" value="{PERIOD_START}"', content2)
        self.assertIn(f'name="data_final" value="{PERIOD_END}"', content2)

    def test_page_out_of_range_returns_404_not_generic_400(self):
        """Hoje o motor ausente responde 400 (relatorio indisponivel) mesmo
        para page=999, ANTES de qualquer EmptyPage ser avaliado — diferente
        do contrato final (404), que so se aplica quando o motor existe.
        RED real ate REL-11-Q."""
        response = self.client.get(_report_url(_base_pairs(page="999")))
        self.assertEqual(response.status_code, 404)


class PendenciesReadOnlyAndQueryCostTests(TestCase):
    """Secao 6 do enunciado: consulta somente leitura (nao assume, libera,
    resolve ou reabre pendencia) e custo de consulta sem N+1, inclusive na
    recuperacao em lote de Solicitante/Responsavel."""

    def setUp(self):
        self.admin = _create_user("admin.pend.readonly@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_generating_report_does_not_write_business_data(self):
        supervisor = _make_supervisor("readonly")
        employee = _make_employee_for(supervisor, "readonly")
        line, _ = _make_line("+5511939000001")
        allocation = _allocate(line, self.admin, employee)
        pendency = _open_pendency(
            self.client, supervisor, employee, ActionType.PENDING,
            _local_midnight(date(2026, 9, 10)), allocation=allocation,
        )

        events_before = LineDailyActionAuditEvent.objects.count()
        snapshot_before = (
            pendency.action,
            pendency.resolved_at,
            pendency.pendency_submitted_at,
            pendency.technical_responsible_id,
            pendency.last_submitted_action,
        )

        self.client.force_login(self.admin)
        first = self.client.get(_report_url(_base_pairs(incluir_excluidos="1")))
        second = self.client.get(_report_url(_base_pairs()))
        self.assertEqual(first.status_code, 200, "motor deve responder com a tela real, nao um 400 residual")
        self.assertEqual(second.status_code, 200)
        self.assertContains(first, "+5511939000001", msg_prefix="conteudo elegivel real ausente na resposta")

        self.assertEqual(LineDailyActionAuditEvent.objects.count(), events_before)
        pendency.refresh_from_db()
        self.assertEqual(
            (
                pendency.action,
                pendency.resolved_at,
                pendency.pendency_submitted_at,
                pendency.technical_responsible_id,
                pendency.last_submitted_action,
            ),
            snapshot_before,
            "consulta alterou campos de negocio da pendencia",
        )

    def test_query_count_does_not_scale_linearly_with_row_count(self):
        supervisor = _make_supervisor("querycost")

        def _make_batch(prefix, count):
            for index in range(count):
                employee = _make_employee_for(supervisor, f"querycost-{prefix}-{index}")
                line, _ = _make_line(f"+551193{prefix}{index:04d}")
                allocation = _allocate(line, self.admin, employee)
                _open_pendency(
                    self.client, supervisor, employee, ActionType.PENDING,
                    _local_midnight(date(2026, 9, 10)), allocation=allocation,
                )

        _make_batch("0", 3)
        self.client.force_login(self.admin)
        with CaptureQueriesContext(connection) as small:
            small_response = self.client.get(_report_url(_base_pairs()))

        _make_batch("1", 27)
        # Correcao comprovada (REL-11-Q): _open_pendency/_make_batch fazem
        # client.force_login(supervisor) internamente (fixture via endpoint
        # real, nunca ORM direto) — a sessao do client fica autenticada como
        # SUPER apos o batch, nao mais como ADMIN. Sem relogar aqui, a
        # segunda captura cairia em 403 (RoleRequiredMixin) por perda de
        # sessao do teste, nunca por custo de consulta — precisa reautenticar
        # como ADMIN antes de medir a segunda leitura, mesmo padrao ja usado
        # antes da primeira captura.
        self.client.force_login(self.admin)
        with CaptureQueriesContext(connection) as large:
            large_response = self.client.get(_report_url(_base_pairs()))

        self.assertEqual(small_response.status_code, 200, "motor deve responder com a tela real, nao um 400 residual")
        self.assertEqual(large_response.status_code, 200)
        self.assertLessEqual(len(large.captured_queries) - len(small.captured_queries), 4)


class PendenciesExportAuthorizationTests(TestCase):
    """Secao 7 do enunciado: autorizacao no download direto, ambos os
    formatos. RoleRequiredMixin precede a validacao de parametros, entao os
    cenarios negativos sao GREEN real independente do motor de Pendencias
    existir."""

    def setUp(self):
        self.admin = _create_user("admin.pend.exportauth@test.com", SystemUser.Role.ADMIN)

    def test_admin_download_csv_returns_200(self):
        """RED real: motor de exportacao ainda ausente (REL-11-E), ADMIN
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
                user = _create_user(f"pend.export.role{index}@test.com", role)
                self.client.force_login(user)
                response = self.client.get(_export_url("csv", _base_pairs()))
                self.assertEqual(response.status_code, 403)

    def test_anonymous_gets_403_on_export(self):
        response = self.client.get(_export_url("csv", _base_pairs()))
        self.assertEqual(response.status_code, 403)

    def test_invalid_dates_rejected_on_direct_export_access(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            _export_url("csv", [("relatorio", "pendencies"), ("data_inicial", PERIOD_END), ("data_final", PERIOD_START)])
        )
        self.assertEqual(response.status_code, 400)

    def test_unknown_format_returns_404(self):
        """GREEN real: formato e checado antes de qualquer validacao de
        relatorio (ReportsExportView.get), independente de pendencies ter
        motor ou nao."""
        self.client.force_login(self.admin)
        response = self.client.get(_export_url("pdf", _base_pairs()))
        self.assertEqual(response.status_code, 404)


class PendenciesExportContentTests(TestCase):
    """Secao 7 do enunciado (continuacao): conteudo real lido via
    csv/openpyxl, mesmas colunas/granularidade/ordenacao da tela, conjunto
    completo independente de page, dados atuais no momento do download,
    rotulos de lacuna de auditoria preservados no arquivo, protecao de
    formula usando somente uma expressao inofensiva ('=1+1', conforme
    exigido pelo enunciado desta task)."""

    def setUp(self):
        self.admin = _create_user("admin.pend.exportcontent@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def _read_csv_rows(self, response):
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
        supervisor = _make_supervisor("export-columns")
        employee = _make_employee_for(supervisor, "export-columns")
        line, _ = _make_line("+5511940000001")
        allocation = _allocate(line, self.admin, employee)
        _open_pendency(
            self.client, supervisor, employee, ActionType.PENDING,
            _local_midnight(date(2026, 9, 10)), allocation=allocation,
        )

        self.client.force_login(self.admin)
        csv_rows = self._read_csv_rows(self.client.get(_export_url("csv", _base_pairs())))
        self.assertEqual(csv_rows[0], EXPECTED_COLUMN_HEADERS)

        xlsx_rows = self._read_xlsx_rows(self.client.get(_export_url("xlsx", _base_pairs())))
        self.assertEqual(list(xlsx_rows[0]), EXPECTED_COLUMN_HEADERS)

    def test_csv_and_xlsx_contain_all_filtered_rows_regardless_of_page(self):
        supervisor = _make_supervisor("export-allrows")
        for index in range(60):
            employee = _make_employee_for(supervisor, f"export-allrows-{index}")
            line, _ = _make_line(f"+5511941{index:06d}")
            allocation = _allocate(line, self.admin, employee)
            _open_pendency(
                self.client, supervisor, employee, ActionType.PENDING,
                _local_midnight(date(2026, 9, 10)), allocation=allocation,
            )

        self.client.force_login(self.admin)
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
        no momento do download. Resolve a pendencia ENTRE a consulta e o
        clique de exportacao; o arquivo deve refletir 'Resolvida', nao o
        estado 'Aberta' visto na consulta anterior."""
        supervisor = _make_supervisor("export-current")
        employee = _make_employee_for(supervisor, "export-current")
        line, _ = _make_line("+5511942000001")
        allocation = _allocate(line, self.admin, employee)
        pendency = _open_pendency(
            self.client, supervisor, employee, ActionType.PENDING,
            _local_midnight(date(2026, 9, 10)), allocation=allocation,
        )
        self.client.force_login(self.admin)
        self.client.get(_report_url(_base_pairs()))

        _claim(self.client, self.admin, pendency, _local_midnight(date(2026, 9, 11)))
        _resolve(self.client, self.admin, pendency, _local_midnight(date(2026, 9, 12)))

        self.client.force_login(self.admin)
        csv_rows = self._read_csv_rows(self.client.get(_export_url("csv", _base_pairs())))
        matching = [row for row in csv_rows[1:] if row and row[0].lstrip("'") == "+5511942000001"]
        self.assertTrue(matching)
        self.assertEqual(matching[0][4], "Resolvida")

    def test_pre_audit_gap_labels_preserved_in_export(self):
        """Exemplo I de REL-11-C, angulo da exportacao: os rotulos de
        lacuna de auditoria devem aparecer no arquivo baixado, nao apenas
        na tela."""
        supervisor = _make_supervisor("export-preaudit")
        employee = _make_employee_for(supervisor, "export-preaudit")
        line, _ = _make_line("+5511943000001")
        allocation = _allocate(line, self.admin, employee)
        _make_legacy_pendency(
            employee=employee,
            allocation=allocation,
            action=ActionType.NO_ACTION,
            last_submitted_action=ActionType.PENDING,
            pendency_submitted_at=_local_midnight(date(2026, 9, 2)),
            resolved_at=_local_midnight(date(2026, 9, 6)),
        )

        self.client.force_login(self.admin)
        csv_rows = self._read_csv_rows(self.client.get(_export_url("csv", _base_pairs())))
        matching = [row for row in csv_rows[1:] if row and row[0].lstrip("'") == "+5511943000001"]
        self.assertTrue(matching)
        self.assertEqual(matching[0][2], NOT_AVAILABLE_LABEL)
        self.assertEqual(matching[0][3], NOT_AVAILABLE_LABEL)

    def test_accents_in_employee_name_preserved_and_do_not_break_parsing(self):
        """Acentos nao quebram o parsing do CSV (Secao 6 do enunciado desta
        task). Compara contra `employee.full_name` apos `refresh_from_db`
        (mesmo padrao ja usado por
        `test_harmless_formula_like_employee_name_neutralized_in_csv` nesta
        mesma classe), nunca contra o literal passado a `.create()`:
        `Employee.save()` sempre normaliza `full_name` via
        `core/normalization.py::normalize_full_name` (regra pre-existente,
        fora do escopo desta task — REL-11-E nao altera regra de
        empregados), entao o valor persistido pode diferir do literal em
        capitalizacao. O requisito real testado aqui e que os caracteres
        acentuados do valor REALMENTE armazenado sobrevivem integros ao
        arquivo exportado, nunca que a exportacao preserve uma entrada bruta
        que o proprio modelo ja normaliza antes de chegar ao exportador."""
        supervisor = _make_supervisor("export-accents")
        employee = Employee.objects.create(
            full_name="José Ação Ínãti",
            corporate_email=supervisor.email,
            employee_id="PEND-ACC",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )
        employee.refresh_from_db()
        line, _ = _make_line("+5511944000001")
        allocation = _allocate(line, self.admin, employee)
        _open_pendency(
            self.client, supervisor, employee, ActionType.PENDING,
            _local_midnight(date(2026, 9, 10)), allocation=allocation,
        )

        self.client.force_login(self.admin)
        csv_rows = self._read_csv_rows(self.client.get(_export_url("csv", _base_pairs())))
        self.assertEqual(len(csv_rows), 2)
        self.assertIn(employee.full_name, csv_rows[1])

    def test_harmless_formula_like_employee_name_neutralized_in_csv(self):
        """Protecao de formula usando somente uma expressao inofensiva
        ('=1+1', conforme exigido pelo enunciado desta task) — nunca um
        payload de execucao de comando."""
        supervisor = _make_supervisor("export-formula")
        employee = Employee.objects.create(
            full_name="=1+1",
            corporate_email=supervisor.email,
            employee_id="PEND-FORM",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )
        employee.refresh_from_db()
        self.assertTrue(employee.full_name.startswith("="))
        line, _ = _make_line("+5511945000001")
        allocation = _allocate(line, self.admin, employee)
        _open_pendency(
            self.client, supervisor, employee, ActionType.PENDING,
            _local_midnight(date(2026, 9, 10)), allocation=allocation,
        )

        self.client.force_login(self.admin)
        csv_rows = self._read_csv_rows(self.client.get(_export_url("csv", _base_pairs())))
        matching = [row for row in csv_rows[1:] if row and row[0].lstrip("'") == "+5511945000001"]
        self.assertTrue(matching)
        self.assertEqual(matching[0][1], "'" + employee.full_name)


class PendenciesExportSplitBoundaryTests(TestCase):
    """Fronteira de divisao em partes/ZIP (REL-07/REL-11-C), boundary-1/
    boundary/boundary+1 em ambos os formatos. Interface tecnica explicita e
    pequena para reduzir o limiar em teste: o parametro `split_threshold` de
    core.services.pendencies_export_service.generate_pendencies_export,
    chamado diretamente aqui (nao via HTTP). A rota reports_export nunca
    passa esse parametro e usa sempre EXPORT_SPLIT_THRESHOLD (100.000) —
    producao permanece intocada por este teste. Mesmo padrao ja usado em
    AllocationsExportSplitBoundaryTests (test_allocations_report.py)."""

    def setUp(self):
        self.admin = _create_user("admin.pend.split@test.com", SystemUser.Role.ADMIN)

    def _filters(self):
        return dict(
            data_inicial=date(2026, 9, 1),
            data_final=date(2026, 9, 24),
            incluir_excluidos=False,
            situacao_pendencia="",
            motivo_pendencia="",
            com_responsavel="",
            funcionario="",
            linha="",
        )

    def _make_pendencies(self, count, prefix):
        supervisor = _make_supervisor(f"split-{prefix}")
        for index in range(count):
            employee = _make_employee_for(supervisor, f"split-{prefix}-{index}")
            line, _ = _make_line(f"+55119{prefix}{index:04d}")
            allocation = _allocate(line, self.admin, employee)
            _open_pendency(
                self.client, supervisor, employee, ActionType.PENDING,
                _local_midnight(date(2026, 9, 10)), allocation=allocation,
            )

    def _generate(self, formato, threshold):
        from core.services.pendencies_export_service import generate_pendencies_export

        return generate_pendencies_export(
            formato=formato, filters=self._filters(), split_threshold=threshold
        )

    def _read_csv_data_row_counts(self, path):
        with open(path, encoding="utf-8-sig") as handle:
            rows = list(csv.reader(handle, delimiter=";"))
        return rows[0], len(rows) - 1

    def _read_xlsx_data_row_counts(self, path):
        workbook = openpyxl.load_workbook(path)
        sheet = workbook["Pendências"]
        rows = list(sheet.iter_rows(values_only=True))
        return list(rows[0]), len(rows) - 1

    def test_csv_below_threshold_is_single_file(self):
        self._make_pendencies(2, "01")
        export = self._generate("csv", 3)
        try:
            self.assertFalse(export.filename.endswith(".zip"))
            _, count = self._read_csv_data_row_counts(export.path)
            self.assertEqual(count, 2)
        finally:
            shutil.rmtree(export.temp_dir, ignore_errors=True)

    def test_csv_at_threshold_is_single_file(self):
        self._make_pendencies(3, "02")
        export = self._generate("csv", 3)
        try:
            self.assertFalse(export.filename.endswith(".zip"))
            _, count = self._read_csv_data_row_counts(export.path)
            self.assertEqual(count, 3)
        finally:
            shutil.rmtree(export.temp_dir, ignore_errors=True)

    def test_csv_above_threshold_splits_into_zip_without_loss_or_duplication(self):
        from core.services.pendencies_export_service import COLUMNS

        self._make_pendencies(4, "03")
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
        self._make_pendencies(2, "04")
        export = self._generate("xlsx", 3)
        try:
            self.assertFalse(export.filename.endswith(".zip"))
            _, count = self._read_xlsx_data_row_counts(export.path)
            self.assertEqual(count, 2)
        finally:
            shutil.rmtree(export.temp_dir, ignore_errors=True)

    def test_xlsx_at_threshold_is_single_file(self):
        self._make_pendencies(3, "05")
        export = self._generate("xlsx", 3)
        try:
            self.assertFalse(export.filename.endswith(".zip"))
            _, count = self._read_xlsx_data_row_counts(export.path)
            self.assertEqual(count, 3)
        finally:
            shutil.rmtree(export.temp_dir, ignore_errors=True)

    def test_xlsx_above_threshold_splits_into_zip_without_loss_or_duplication(self):
        from core.services.pendencies_export_service import COLUMNS

        self._make_pendencies(4, "06")
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
                    sheet = workbook["Pendências"]
                    rows = list(sheet.iter_rows(values_only=True))
                    self.assertEqual(list(rows[0]), COLUMNS)
                    counts.append(len(rows) - 1)
                self.assertEqual(sorted(counts), [1, 3])
                self.assertEqual(sum(counts), 4)
        finally:
            shutil.rmtree(export.temp_dir, ignore_errors=True)


class PendenciesExportStreamingCleanupTests(TestCase):
    """Prova direta do mecanismo de limpeza de temporarios (REL-07/REL-11-C:
    limpeza em consumo completo, consumo parcial, fechamento antes do
    primeiro chunk, fechamento repetido e falha de geracao). Mesmo
    raciocinio ja comprovado para Selos WhatsApp/Inventario/Alocacoes (ver
    AllocationsExportStreamingCleanupTests)."""

    def setUp(self):
        self.admin = _create_user("admin.pend.cleanup@test.com", SystemUser.Role.ADMIN)
        self.supervisor = _make_supervisor("cleanup")

    def _filters(self):
        return dict(
            data_inicial=date(2026, 9, 1),
            data_final=date(2026, 9, 24),
            incluir_excluidos=False,
            situacao_pendencia="",
            motivo_pendencia="",
            com_responsavel="",
            funcionario="",
            linha="",
        )

    def _make_one(self, phone_number, suffix):
        employee = _make_employee_for(self.supervisor, suffix)
        line, _ = _make_line(phone_number)
        allocation = _allocate(line, self.admin, employee)
        _open_pendency(
            self.client, self.supervisor, employee, ActionType.PENDING,
            _local_midnight(date(2026, 9, 10)), allocation=allocation,
        )
        return line

    def test_temp_dir_removed_after_full_stream_consumption(self):
        from core.services.pendencies_export_service import (
            _stream_and_cleanup,
            generate_pendencies_export,
        )

        self._make_one("+5511960000001", "cleanup-1")
        export = generate_pendencies_export(formato="csv", filters=self._filters())
        self.assertTrue(os.path.isdir(export.temp_dir))

        content = b"".join(_stream_and_cleanup(export.path, export.temp_dir))
        self.assertIn(b"+5511960000001", content)
        self.assertFalse(os.path.exists(export.temp_dir))

    def test_temp_dir_removed_on_early_close_simulating_client_disconnect(self):
        """Consumo PARCIAL: um chunk e lido, depois a conexao 'cai' — o
        servidor WSGI chama generator.close() com o generator ja suspenso
        em algum yield, o que aciona o finally normalmente."""
        from core.services.pendencies_export_service import (
            _stream_and_cleanup,
            generate_pendencies_export,
        )

        self._make_one("+5511960000002", "cleanup-2")
        export = generate_pendencies_export(formato="csv", filters=self._filters())
        stream = _stream_and_cleanup(export.path, export.temp_dir)
        next(stream)
        stream.close()
        self.assertFalse(os.path.exists(export.temp_dir))

    def test_temp_dir_removed_before_first_chunk_consumed_on_close(self):
        """Fechamento ANTES de qualquer iteracao (cliente desconecta antes
        do primeiro byte). streaming_content nunca e tocado."""
        from core.services import pendencies_export_service

        self._make_one("+5511960000004", "cleanup-4")

        captured = {}
        original_mkdtemp = pendencies_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        with mock.patch.object(
            pendencies_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
        ):
            response = pendencies_export_service.build_pendencies_export_response(
                formato="csv", filters=self._filters()
            )

        self.assertIn("temp_dir", captured)
        self.assertTrue(os.path.isdir(captured["temp_dir"]))

        response.close()  # nenhum chunk foi lido ate aqui

        self.assertFalse(os.path.exists(captured["temp_dir"]))

    def test_close_is_idempotent_on_repeated_close_calls(self):
        from core.services import pendencies_export_service

        self._make_one("+5511960000005", "cleanup-5")

        response = pendencies_export_service.build_pendencies_export_response(
            formato="csv", filters=self._filters()
        )
        response.close()
        self.assertFalse(os.path.exists(response._export_temp_dir))
        response.close()  # segunda chamada nao deve levantar excecao
        self.assertFalse(os.path.exists(response._export_temp_dir))

    def test_temp_dir_removed_when_generation_fails(self):
        from core.services import pendencies_export_service

        self._make_one("+5511960000003", "cleanup-3")
        captured = {}
        original_mkdtemp = pendencies_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        with mock.patch.object(
            pendencies_export_service, "_write_csv_chunk", side_effect=RuntimeError("boom")
        ):
            with mock.patch.object(
                pendencies_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
            ):
                with self.assertRaises(RuntimeError):
                    pendencies_export_service.generate_pendencies_export(
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
        from core.services import pendencies_export_service

        self._make_one("+5511960000006", "cleanup-6")
        captured = {}
        original_mkdtemp = pendencies_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        def _boom(worksheet, row):
            raise RuntimeError("boom")

        with mock.patch.object(
            pendencies_export_service, "_row_to_xlsx_cells", side_effect=_boom
        ):
            with mock.patch.object(
                pendencies_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
            ):
                with self.assertRaises(RuntimeError):
                    pendencies_export_service.generate_pendencies_export(
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
        jeito de remover esse arquivo antes de `save()`, ver docstring de
        `_close_abandoned_workbook` em core/services/allocations_export_service)."""
        from core.services import pendencies_export_service
        from openpyxl.worksheet._writer import ALL_TEMP_FILES

        self._make_one("+5511960000007", "cleanup-7")

        def _boom(worksheet, row):
            raise RuntimeError("boom")

        baseline = set(ALL_TEMP_FILES)
        with mock.patch.object(
            pendencies_export_service, "_row_to_xlsx_cells", side_effect=_boom
        ):
            with self.assertRaises(RuntimeError):
                pendencies_export_service.generate_pendencies_export(
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
        from core.services import pendencies_export_service
        from openpyxl.worksheet._writer import ALL_TEMP_FILES

        self._make_one("+5511960000008", "cleanup-8")
        self._make_one("+5511960000009", "cleanup-9")

        real_row_to_xlsx_cells = pendencies_export_service._row_to_xlsx_cells
        calls = {"count": 0}

        def _fail_on_second_row(worksheet, row):
            calls["count"] += 1
            if calls["count"] >= 2:
                raise RuntimeError("boom")
            return real_row_to_xlsx_cells(worksheet, row)

        baseline = set(ALL_TEMP_FILES)
        with mock.patch.object(
            pendencies_export_service, "_row_to_xlsx_cells", side_effect=_fail_on_second_row
        ):
            with self.assertRaises(RuntimeError):
                pendencies_export_service.generate_pendencies_export(
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
        `generate_pendencies_export`, o ZipFile de destino ficava aberto
        (preso pelo traceback) e `temp_dir` sobrevivia no Windows — corrigido
        junto com o achado 2 (mesmo mecanismo de limpeza)."""
        import zipfile

        from core.services import pendencies_export_service
        from openpyxl.worksheet._writer import ALL_TEMP_FILES

        self._make_one("+5511960000010", "cleanup-10")

        def _fail_on_archive_write(self_zip, filename, arcname=None, **kwargs):
            raise RuntimeError("boom-disk-full-during-finalization")

        baseline = set(ALL_TEMP_FILES)
        captured = {}
        original_mkdtemp = pendencies_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        with mock.patch.object(zipfile.ZipFile, "write", new=_fail_on_archive_write):
            with mock.patch.object(
                pendencies_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
            ):
                with self.assertRaises(RuntimeError) as ctx:
                    pendencies_export_service.generate_pendencies_export(
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
        import zipfile

        from core.services import pendencies_export_service
        from openpyxl.worksheet._writer import ALL_TEMP_FILES

        self._make_one("+5511960000011", "cleanup-11")

        def _raise_deep_oserror(archive_ref):
            raise OSError("disk full (simulated, chained)")

        def _fail_with_chained_exception(self_zip, filename, arcname=None, **kwargs):
            try:
                _raise_deep_oserror(self_zip)
            except OSError as cause:
                raise RuntimeError("boom-chained-during-finalization") from cause

        baseline = set(ALL_TEMP_FILES)
        captured = {}
        original_mkdtemp = pendencies_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        exc_holder = {}
        with mock.patch.object(zipfile.ZipFile, "write", new=_fail_with_chained_exception):
            with mock.patch.object(
                pendencies_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
            ):
                try:
                    pendencies_export_service.generate_pendencies_export(
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


class PendenciesExportQueryCostTests(TestCase):
    """Secao 6 do enunciado desta task: consultas em lotes sem N+1 tambem na
    EXPORTACAO (nao so na consulta paginada, ja coberta por
    PendenciesReadOnlyAndQueryCostTests). O numero de consultas nao deve
    escalar com a quantidade de linhas exportadas, dentro de um unico lote
    interno (chunk_size padrao 2000, bem acima dos datasets pequenos usados
    aqui). Mesmo padrao ja usado em AllocationsExportQueryCostTests."""

    def setUp(self):
        self.admin = _create_user("admin.pend.exportquerycost@test.com", SystemUser.Role.ADMIN)
        self.supervisor = _make_supervisor("exportquerycost")

    def _filters(self):
        return dict(
            data_inicial=date(2026, 9, 1),
            data_final=date(2026, 9, 24),
            incluir_excluidos=False,
            situacao_pendencia="",
            motivo_pendencia="",
            com_responsavel="",
            funcionario="",
            linha="",
        )

    def _make(self, count, prefix):
        for index in range(count):
            employee = _make_employee_for(self.supervisor, f"{prefix}-{index}")
            line, _ = _make_line(f"+551196{prefix}{index:04d}")
            allocation = _allocate(line, self.admin, employee)
            _open_pendency(
                self.client, self.supervisor, employee, ActionType.PENDING,
                _local_midnight(date(2026, 9, 10)), allocation=allocation,
            )

    def test_export_query_count_does_not_scale_linearly_with_row_count(self):
        from core.services.pendencies_export_service import generate_pendencies_export

        self._make(3, "1")
        with CaptureQueriesContext(connection) as small:
            export_small = generate_pendencies_export(formato="csv", filters=self._filters())
        try:
            with open(export_small.path, encoding="utf-8-sig") as handle:
                small_count = len(list(csv.reader(handle, delimiter=";"))) - 1
        finally:
            shutil.rmtree(export_small.temp_dir, ignore_errors=True)

        self._make(27, "2")
        with CaptureQueriesContext(connection) as large:
            export_large = generate_pendencies_export(formato="csv", filters=self._filters())
        try:
            with open(export_large.path, encoding="utf-8-sig") as handle:
                large_count = len(list(csv.reader(handle, delimiter=";"))) - 1
        finally:
            shutil.rmtree(export_large.temp_dir, ignore_errors=True)

        self.assertEqual(small_count, 3)
        self.assertEqual(large_count, 30)
        self.assertLessEqual(len(large.captured_queries) - len(small.captured_queries), 4)


class PendenciesExportAuditBatchingTests(TestCase):
    """Secao 4 do enunciado desta task: auditoria em LOTES na exportacao
    integral — busca eventos somente para as entidades do proprio lote,
    nunca por linha nem o historico inteiro em memoria; um resultado
    correto num unico lote nao comprova a iteracao completa (aviso
    explicito do enunciado). Usa o parametro tecnico `chunk_size` de
    `iter_pendencies_report_rows` (interface de teste explicita — nunca
    usada em producao, que usa sempre o padrao real de 2000) para forcar
    multiplos lotes com poucos registros: 7 pendencias, chunk_size=3 (lotes
    de 3+3+1), com casos ANTES e DEPOIS de cada fronteira de lote."""

    def setUp(self):
        self.admin = _create_user("admin.pend.auditbatch@test.com", SystemUser.Role.ADMIN)
        self.supervisor = _make_supervisor("auditbatch")

    def test_solicitante_correct_across_batch_boundary(self):
        """Indices pares (0,2,4,6) tem evento OPENED real (via endpoint,
        Solicitante recuperavel); indices impares (1,3,5,6-1=5) sao legados
        (via _make_legacy_pendency, sem evento, mesma excecao documentada em
        REL-11-T) — garante que a correlacao por (source_object_id,
        occurred_at) nao se perde nem se mistura entre lotes internos."""
        from core.services.pendencies_report_service import (
            NOT_AVAILABLE_LABEL,
            iter_pendencies_report_rows,
        )

        phone_numbers = []
        for index in range(7):
            phone_number = f"+551197{index:07d}"
            phone_numbers.append(phone_number)
            employee = _make_employee_for(self.supervisor, f"auditbatch-{index}")
            line, _ = _make_line(phone_number)
            allocation = _allocate(line, self.admin, employee)
            if index % 2 == 0:
                _open_pendency(
                    self.client, self.supervisor, employee, ActionType.PENDING,
                    _local_midnight(date(2026, 9, 10)), allocation=allocation,
                )
            else:
                _make_legacy_pendency(
                    employee=employee,
                    allocation=allocation,
                    action=ActionType.PENDING,
                    last_submitted_action=ActionType.PENDING,
                    pendency_submitted_at=_local_midnight(date(2026, 9, 10)),
                )

        rows = list(
            iter_pendencies_report_rows(
                data_inicial=date(2026, 9, 1),
                data_final=date(2026, 9, 24),
                chunk_size=3,
            )
        )
        self.assertEqual(len(rows), 7)

        by_phone = {row.phone_number: row for row in rows}
        self.assertEqual(len(by_phone), 7)
        for index, phone_number in enumerate(phone_numbers):
            row = by_phone[phone_number]
            if index % 2 == 0:
                self.assertNotEqual(row.solicitante_label, NOT_AVAILABLE_LABEL)
            else:
                self.assertEqual(row.solicitante_label, NOT_AVAILABLE_LABEL)


class PendenciesExportRealVolumeTests(TestCase):
    """Ensaio de volume REAL na fronteira de producao (100.000/100.001
    linhas de AllocationPendency), exigido pela Secao 7 do enunciado desta
    task antes de liberar REL-11-E — mesmo tipo de ensaio ja feito em
    REL-08-E/09-E/10-E (ver AllocationsExportRealVolumeTests em
    test_allocations_report.py).

    Dataset unico (bulk_create), criado uma vez para toda a classe
    (setUpTestData): pool pequeno de PhoneLine/Employee/admin
    (technical_responsible) reaproveitado por 100.001 AllocationPendency —
    responsaveis/solicitantes compartilhados entre registros. Metade do
    dataset (indices pares) e RESOLVIDA e tem LineDailyActionAuditEvent real
    correlacionado (OPENED + RESOLVED), para que o ensaio meca o CUSTO
    GENUINO da consulta em lote de auditoria — nunca um dataset sem nenhuma
    auditoria apresentado como prova do custo completo (aviso explicito do
    enunciado). A outra metade (indices impares) fica ABERTA, com
    responsavel tecnico atribuido, sem evento de auditoria (perfil legado
    real do dominio, REL-11-C: dado anterior ao deploy da auditoria).

    pendency_submitted_at/resolved_at NAO sao auto_now_add (diferente de
    LineAllocation.allocated_at) — bulk_create grava os valores finais
    diretamente, sem UPDATE por faixa de pk. Cada AllocationPendency
    referencia uma LineAllocation PROPRIA e distinta (OneToOneField: nunca
    compartilhada entre pendencias), tambem criada via bulk_create.

    Tempo e pico de memoria (tracemalloc) medidos em bloco proprio, apos a
    fixture ja criada — mede o processo de exportacao isoladamente. Roda em
    banco de teste isolado; nao acessa PRD. Deliberadamente lento (10^5
    linhas + 10^5 eventos de auditoria); nao e um teste unitario comum e nao
    deve ser lido como prova de comportamento de logica (essa prova esta em
    PendenciesExportSplitBoundaryTests/PendenciesExportAuditBatchingTests).
    Integridade comprovada por CONTAGEM DE REGISTROS efetivamente escritos
    no(s) arquivo(s), mesmo padrao de AllocationsExportRealVolumeTests."""

    BASE_COUNT = 100_000
    LINE_POOL_SIZE = 1000
    EMPLOYEE_POOL_SIZE = 500
    ADMIN_POOL_SIZE = 20

    @classmethod
    def setUpTestData(cls):
        sims = [
            SIMcard(iccid=f"88{i:020d}", carrier="TIM", status=SIMcard.Status.ACTIVE)
            for i in range(cls.LINE_POOL_SIZE)
        ]
        SIMcard.objects.bulk_create(sims, batch_size=2000)
        sim_ids = list(
            SIMcard.objects.order_by("pk").values_list("pk", flat=True)[: cls.LINE_POOL_SIZE]
        )
        lines = [
            PhoneLine(
                phone_number=f"+5511931{index:06d}",
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
                full_name=f"Volume Pendencia {index}",
                corporate_email=f"volume.pend{index}@test.com",
                employee_id=f"VOLPEND-{index}",
                teams="Joinville",
                status=Employee.Status.ACTIVE,
            )
            for index in range(cls.EMPLOYEE_POOL_SIZE)
        ]
        Employee.objects.bulk_create(employees, batch_size=2000)
        employee_ids = list(
            Employee.objects.order_by("pk").values_list("pk", flat=True)[: cls.EMPLOYEE_POOL_SIZE]
        )

        admins = []
        for index in range(cls.ADMIN_POOL_SIZE):
            admin = SystemUser(
                email=f"volume.pend.admin{index}@test.com",
                role=SystemUser.Role.ADMIN,
                is_active=True,
            )
            admin.set_password(PASSWORD)
            admins.append(admin)
        SystemUser.objects.bulk_create(admins, batch_size=200)
        admin_ids = list(
            SystemUser.objects.filter(email__startswith="volume.pend.admin")
            .order_by("pk")
            .values_list("pk", flat=True)[: cls.ADMIN_POOL_SIZE]
        )

        total = cls.BASE_COUNT + 1
        # allocated_at e auto_now_add: bulk_create sempre grava o instante
        # real da insercao nesse campo, entao criamos com is_active=True/
        # released_at=None (satisfaz ck_allocation_active_release_consistency
        # no momento do INSERT) e sobrescrevemos os tres campos DEPOIS via
        # QuerySet.update() (bypassa auto_now_add) — mesma tecnica ja usada
        # em AllocationsExportRealVolumeTests.
        allocations = [
            LineAllocation(
                employee_id=employee_ids[index % cls.EMPLOYEE_POOL_SIZE],
                phone_line_id=line_ids[index % cls.LINE_POOL_SIZE],
                is_active=True,
            )
            for index in range(total)
        ]
        LineAllocation.objects.bulk_create(allocations, batch_size=5000)
        allocation_ids = list(
            LineAllocation.objects.order_by("pk").values_list("pk", flat=True)
        )
        assert len(allocation_ids) == total
        LineAllocation.objects.filter(pk__range=(allocation_ids[0], allocation_ids[-1])).update(
            allocated_at=_local_midnight(date(2026, 8, 1)),
            released_at=_local_midnight(date(2026, 8, 2)),
            is_active=False,
        )

        pendencies = []
        events = []
        for index in range(total):
            resolved = index % 2 == 0
            is_extra = index == cls.BASE_COUNT
            submitted_date = date(2026, 9, 24) if is_extra else date(2026, 9, 10)
            submitted_at = _local_midnight(submitted_date)
            resolved_at = _local_midnight(submitted_date + timedelta(days=5)) if resolved else None
            employee_id = employee_ids[index % cls.EMPLOYEE_POOL_SIZE]

            pendencies.append(
                AllocationPendency(
                    employee_id=employee_id,
                    allocation_id=allocation_ids[index],
                    action=ActionType.NO_ACTION if resolved else ActionType.PENDING,
                    last_submitted_action=ActionType.PENDING,
                    pendency_submitted_at=submitted_at,
                    resolved_at=resolved_at,
                    technical_responsible_id=(
                        None if resolved else admin_ids[index % cls.ADMIN_POOL_SIZE]
                    ),
                )
            )

        AllocationPendency.objects.bulk_create(pendencies, batch_size=5000)
        pendency_ids = list(
            AllocationPendency.objects.order_by("pk").values_list("pk", flat=True)
        )
        assert len(pendency_ids) == total

        for index in range(total):
            if index % 2 != 0:
                continue
            is_extra = index == cls.BASE_COUNT
            submitted_date = date(2026, 9, 24) if is_extra else date(2026, 9, 10)
            submitted_at = _local_midnight(submitted_date)
            resolved_at = _local_midnight(submitted_date + timedelta(days=5))
            pendency_id = pendency_ids[index]
            events.append(
                LineDailyActionAuditEvent(
                    event_type=LineDailyActionAuditEvent.EventType.OPENED,
                    source=LineDailyActionAuditEvent.Source.ALLOCATION_PENDENCY,
                    source_object_id=pendency_id,
                    occurred_at=submitted_at,
                    employee_id=employee_ids[index % cls.EMPLOYEE_POOL_SIZE],
                    performed_by_name_snapshot=f"Solicitante Volume {index}",
                    performed_by_email_snapshot=f"solicitante.vol{index}@test.com",
                    before_state={},
                    after_state={},
                )
            )
            events.append(
                LineDailyActionAuditEvent(
                    event_type=LineDailyActionAuditEvent.EventType.RESOLVED,
                    source=LineDailyActionAuditEvent.Source.ALLOCATION_PENDENCY,
                    source_object_id=pendency_id,
                    occurred_at=resolved_at,
                    employee_id=employee_ids[index % cls.EMPLOYEE_POOL_SIZE],
                    performed_by_name_snapshot=f"Resolvedor Volume {index}",
                    performed_by_email_snapshot=f"resolvedor.vol{index}@test.com",
                    before_state={},
                    after_state={},
                )
            )
        LineDailyActionAuditEvent.objects.bulk_create(events, batch_size=5000)

    def _filters(self, data_final):
        return dict(
            data_inicial=date(2026, 9, 1),
            data_final=data_final,
            incluir_excluidos=False,
            situacao_pendencia="",
            motivo_pendencia="",
            com_responsavel="",
            funcionario="",
            linha="",
        )

    def _measure(self, formato, data_final, expected_total):
        import sys
        import time
        import tracemalloc
        from pathlib import Path

        from core.services.pendencies_export_service import generate_pendencies_export

        filters = self._filters(data_final)
        actual_total = AllocationPendency.objects.filter(
            pendency_submitted_at__gte=_local_midnight(date(2026, 9, 1)),
            pendency_submitted_at__lt=_local_midnight(data_final + timedelta(days=1)),
        ).count()
        self.assertEqual(actual_total, expected_total)

        tracemalloc.start()
        start = time.perf_counter()
        export = generate_pendencies_export(formato=formato, filters=filters)
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
                            sheet = workbook["Pendências"]
                            data_row_count += sum(1 for _ in sheet.iter_rows(min_row=2, values_only=True))
            else:
                if formato == "csv":
                    with open(export.path, encoding="utf-8-sig") as handle:
                        data_row_count = len(list(csv.reader(handle, delimiter=";"))) - 1
                else:
                    workbook = openpyxl.load_workbook(export.path)
                    sheet = workbook["Pendências"]
                    data_row_count = sum(1 for _ in sheet.iter_rows(min_row=2, values_only=True))

            sys.stderr.write(
                "\n[VOLUME REAL PENDENCIAS] formato={} registros={} tempo={:.2f}s "
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

    def test_csv_100000_pendencies_single_file_no_zip(self):
        _, _, is_zip, part_count, data_row_count = self._measure("csv", date(2026, 9, 23), 100_000)
        self.assertFalse(is_zip)
        self.assertEqual(part_count, 1)
        self.assertEqual(data_row_count, 100_000)

    def test_csv_100001_pendencies_splits_into_zip_two_parts(self):
        _, _, is_zip, part_count, data_row_count = self._measure("csv", date(2026, 9, 24), 100_001)
        self.assertTrue(is_zip)
        self.assertEqual(part_count, 2)
        self.assertEqual(data_row_count, 100_001)

    def test_xlsx_100000_pendencies_single_file_no_zip(self):
        _, _, is_zip, part_count, data_row_count = self._measure("xlsx", date(2026, 9, 23), 100_000)
        self.assertFalse(is_zip)
        self.assertEqual(part_count, 1)
        self.assertEqual(data_row_count, 100_000)

    def test_xlsx_100001_pendencies_splits_into_zip_two_parts(self):
        _, _, is_zip, part_count, data_row_count = self._measure("xlsx", date(2026, 9, 24), 100_001)
        self.assertTrue(is_zip)
        self.assertEqual(part_count, 2)
        self.assertEqual(data_row_count, 100_001)
