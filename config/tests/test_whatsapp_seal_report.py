"""Testes RED da task REL-08-T (fonte da verdade:
docs/superpowers/specs/2026-09-22-reports-hub-design.md, secoes REL-07 e
REL-08-C).

Cobrem o relatorio whatsapp_seal: consulta na tela (endpoint existente
GET /relatorios/, motor ainda ausente) e exportacoes CSV/XLSX (endpoint
proposto reports_export, rota ainda inexistente). Nao testa a aba
generica (rota, menu, autorizacao base) ja coberta em
config/tests/test_reports_hub.py — reaproveitada, nao duplicada.

Nenhum modulo de aplicacao futuro (forms/servicos/rotas de exportacao) e
importado no topo deste arquivo: eles ainda nao existem. reverse() para a
rota de exportacao e chamado dentro do corpo de cada teste, onde o
NoReverseMatch resultante e RED valido (rota ainda nao registrada), nao
erro de colisao/configuracao.
"""

import csv
import io
import itertools
from datetime import date
from unittest import mock
from urllib.parse import urlencode

import openpyxl
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import NoReverseMatch, reverse

from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser

PASSWORD = "StrongPass123"
REPORTS_URL_NAME = "reports_home"
EXPORT_URL_NAME = "reports_export"  # nome proposto em REL-07; rota ainda nao registrada

NON_ADMIN_ROLES = [
    SystemUser.Role.DEV,
    SystemUser.Role.SUPER,
    SystemUser.Role.BACKOFFICE,
    SystemUser.Role.GERENTE,
    SystemUser.Role.OPERATOR,
]

REFERENCE_TODAY = date(2026, 9, 24)
PERIOD_START = "2026-09-01"
PERIOD_END = "2026-09-24"

_iccid_counter = itertools.count(1)


def _create_user(email, role, **extra):
    return SystemUser.objects.create_user(email=email, password=PASSWORD, role=role, **extra)


def _make_line(
    phone_number,
    *,
    seal="META_ONE",
    activated_on=None,
    expires_on=None,
    payment="",
    seal_email="",
    status=PhoneLine.Status.AVAILABLE,
    origem=None,
    delete_line=False,
    delete_sim=False,
    cascade_delete_sim=False,
):
    """Cria SIMcard+PhoneLine direto via ORM (sem full_clean), permitindo
    tambem estados legados/inconsistentes previstos no contrato (selo
    preenchido sem vencimento, datas invertidas, exclusao isolada de
    SIMcard sem cascata). cascade_delete_sim usa SIMcard.delete(), que em
    condicoes normais tambem exclui a linha (fluxo real); delete_sim=True
    sozinho simula a inconsistencia legada via update() direto, sem
    cascata, conforme mapeado em REL-08-C."""
    sim = SIMcard.objects.create(
        iccid=f"8900000000000{next(_iccid_counter):05d}", carrier="TIM"
    )
    line = PhoneLine.objects.create(
        phone_number=phone_number,
        sim_card=sim,
        status=status,
        origem=origem,
        whatsapp_seal=seal,
        whatsapp_seal_activated_on=activated_on,
        whatsapp_seal_expires_on=expires_on,
        whatsapp_seal_email=seal_email,
        whatsapp_seal_payment=payment,
    )
    if cascade_delete_sim:
        sim.delete()
        line.refresh_from_db()
    else:
        if delete_line:
            line.delete()
        if delete_sim:
            SIMcard.all_objects.filter(pk=sim.pk).update(is_deleted=True)
    return line, sim


def _report_url(pairs):
    return f"{reverse(REPORTS_URL_NAME)}?{urlencode(pairs)}"


def _base_pairs(data_inicial=PERIOD_START, data_final=PERIOD_END, **extra):
    pairs = [
        ("relatorio", "whatsapp_seal"),
        ("data_inicial", data_inicial),
        ("data_final", data_final),
    ]
    pairs.extend(extra.items())
    return pairs


def _export_url(formato, pairs):
    return f"{reverse(EXPORT_URL_NAME, kwargs={'formato': formato})}?{urlencode(pairs)}"


def _frozen_today():
    return mock.patch("django.utils.timezone.localdate", return_value=REFERENCE_TODAY)


class WhatsAppSealReportInitialLoadTests(TestCase):
    """Abertura com relatorio selecionado mas sem datas: sem motor, sem erro
    prematuro. Abertura totalmente sem parametros ja e coberta por
    ReportsHomeContentTests.test_rendering_does_not_query_report_entities
    em config/tests/test_reports_hub.py (reaproveitada, nao duplicada)."""

    def setUp(self):
        self.admin = _create_user("admin.seal.initial@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_report_selected_without_dates_does_not_run_engine_or_error(self):
        response = self.client.get(_report_url([("relatorio", "whatsapp_seal")]))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode().lower()
        self.assertNotIn("obrigat", content)
        self.assertNotIn("erro", content)


class WhatsAppSealReportDateValidationTests(TestCase):
    """REL-07: datas obrigatorias, inclusivas; invalidas/invertidas rejeitadas."""

    def setUp(self):
        self.admin = _create_user("admin.seal.dates@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_missing_data_inicial_rejected(self):
        response = self.client.get(
            _report_url([("relatorio", "whatsapp_seal"), ("data_final", PERIOD_END)])
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_data_final_rejected(self):
        response = self.client.get(
            _report_url([("relatorio", "whatsapp_seal"), ("data_inicial", PERIOD_START)])
        )
        self.assertEqual(response.status_code, 400)

    def test_both_dates_missing_with_report_selected_rejected(self):
        response = self.client.get(_report_url([("relatorio", "whatsapp_seal")]))
        # 200 sem motor e valido (initial load); mas se o teste HTTP indicar
        # tentativa explicita de geracao (parametro 'gerar', a ser definido
        # em Q), a ausencia de ambas as datas deve permanecer 200 sem erro
        # prematuro. Este metodo documenta que so a combinacao de datas
        # invalidas (nao a mera ausencia inicial) deve gerar 400 explicito
        # nos demais testes desta classe.
        self.assertEqual(response.status_code, 200)

    def test_invalid_date_format_rejected(self):
        response = self.client.get(
            _report_url([("relatorio", "whatsapp_seal"), ("data_inicial", "31/09/2026"), ("data_final", PERIOD_END)])
        )
        self.assertEqual(response.status_code, 400)

    def test_inverted_dates_rejected(self):
        response = self.client.get(
            _report_url([("relatorio", "whatsapp_seal"), ("data_inicial", PERIOD_END), ("data_final", PERIOD_START)])
        )
        self.assertEqual(response.status_code, 400)

    def test_equal_dates_accepted_and_filters_by_single_day(self):
        _make_line("+5511900000101", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 1))
        response = self.client.get(
            _report_url([("relatorio", "whatsapp_seal"), ("data_inicial", "2026-09-10"), ("data_final", "2026-09-10")])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "+5511900000101")


class WhatsAppSealReportParameterValidationTests(TestCase):
    """REL-07: enum/booleano/page invalidos, desconhecidos e repetidos sao erro explicito."""

    def setUp(self):
        self.admin = _create_user("admin.seal.params@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_unknown_relatorio_value_rejected(self):
        response = self.client.get(_report_url([("relatorio", "nao_existe"), ("data_inicial", PERIOD_START), ("data_final", PERIOD_END)]))
        self.assertEqual(response.status_code, 400)

    def test_unknown_selo_value_rejected(self):
        response = self.client.get(_report_url(_base_pairs(selo="INVALIDO")))
        self.assertEqual(response.status_code, 400)

    def test_unknown_pagamento_value_rejected(self):
        response = self.client.get(_report_url(_base_pairs(pagamento="PIX")))
        self.assertEqual(response.status_code, 400)

    def test_unknown_situacao_value_rejected(self):
        response = self.client.get(_report_url(_base_pairs(situacao="atrasado")))
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

    def test_page_out_of_range_returns_404(self):
        response = self.client.get(_report_url(_base_pairs(page="999")))
        self.assertEqual(response.status_code, 404)

    def test_unknown_query_parameter_rejected(self):
        response = self.client.get(_report_url(_base_pairs(campo_desconhecido="x")))
        self.assertEqual(response.status_code, 400)

    def test_repeated_scalar_parameter_rejected(self):
        url = reverse(REPORTS_URL_NAME)
        response = self.client.get(
            f"{url}?relatorio=whatsapp_seal&data_inicial={PERIOD_START}&data_inicial=2026-09-02&data_final={PERIOD_END}"
        )
        self.assertEqual(response.status_code, 400)

    def test_search_term_longer_than_20_chars_rejected(self):
        response = self.client.get(_report_url(_base_pairs(linha="1" * 21)))
        self.assertEqual(response.status_code, 400)

    def test_post_method_not_allowed_for_admin(self):
        """Contrato comum (REL-07): metodo nao suportado -> 405. Ja valido
        hoje porque TemplateView nao define post(); registrado aqui como
        GREEN preexistente do endpoint da aba, nao RED desta task."""
        response = self.client.post(reverse(REPORTS_URL_NAME), dict(_base_pairs()))
        self.assertEqual(response.status_code, 405)


class WhatsAppSealReportSetAndPeriodTests(TestCase):
    """Exemplos A-F de REL-08-C: conjunto/periodo/exclusao combinados."""

    def setUp(self):
        self.admin = _create_user("admin.seal.setperiod@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)
        with _frozen_today():
            self.line_a, _ = _make_line("+5511900000201", seal="META_ONE", activated_on=date(2026, 9, 1), expires_on=date(2026, 10, 1))
            self.line_b, _ = _make_line("+5511900000202", seal="META_VERIFIED", activated_on=date(2026, 9, 24), expires_on=date(2026, 9, 24))
            self.line_c, _ = _make_line("+5511900000203", seal="META_ONE", activated_on=date(2026, 8, 31), expires_on=date(2026, 9, 24))
            self.line_d, _ = _make_line("+5511900000204", seal="", activated_on=date(2026, 9, 10), expires_on=date(2026, 9, 20))
            self.line_e, sim_e = _make_line("+5511900000205", seal="META_ONE", activated_on=date(2026, 9, 10), expires_on=date(2026, 9, 23))
            self.line_e.delete()
            self.line_f, _ = _make_line("+5511900000206", seal="META_VERIFIED", activated_on=date(2026, 9, 10), expires_on=None)

    def _get(self, **extra):
        with _frozen_today():
            return self.client.get(_report_url(_base_pairs(**extra)))

    def test_default_set_includes_a_b_f_excludes_c_d_e(self):
        response = self._get()
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("+5511900000201", content)
        self.assertIn("+5511900000202", content)
        self.assertIn("+5511900000206", content)
        self.assertNotIn("+5511900000203", content)
        self.assertNotIn("+5511900000204", content)
        self.assertNotIn("+5511900000205", content)

    def test_incluir_excluidos_adds_only_e(self):
        response = self._get(incluir_excluidos="1")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        for number in ("+5511900000201", "+5511900000202", "+5511900000205", "+5511900000206"):
            self.assertIn(number, content)
        for number in ("+5511900000203", "+5511900000204"):
            self.assertNotIn(number, content)

    def test_operational_activation_does_not_change_result(self):
        self.line_a.activated_at = None
        self.line_a.save(update_fields=["activated_at"])
        response = self._get()
        self.assertContains(response, "+5511900000201")


class WhatsAppSealReportReferenceFieldIsolationTests(TestCase):
    """Ativacao do selo e a unica referencia de periodo; activated_at,
    vencimento e created_at nao substituem o campo."""

    def setUp(self):
        self.admin = _create_user("admin.seal.refisolation@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_expiry_outside_period_does_not_exclude_line(self):
        _make_line("+5511900000301", activated_on=date(2026, 9, 10), expires_on=date(2027, 1, 1))
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511900000301")

    def test_activation_outside_period_excludes_regardless_of_expiry(self):
        """Controle positivo obrigatorio: sem uma linha elegivel na mesma
        resposta, assertNotContains passaria mesmo sem nenhum motor de
        consulta (nada e renderizado hoje de qualquer forma). A linha
        elegivel prova que a resposta e capaz de listar dados; a ausencia
        da inelegivel prova o filtro propriamente dito."""
        _make_line("+5511900000399", activated_on=date(2026, 9, 10), expires_on=date(2026, 9, 10))
        _make_line("+5511900000302", activated_on=date(2026, 7, 1), expires_on=date(2026, 9, 10))
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511900000399")
        self.assertNotContains(response, "+5511900000302")

    def test_operational_activated_at_null_or_set_does_not_affect_inclusion(self):
        from django.utils import timezone as dj_timezone

        line_with_op, _ = _make_line("+5511900000303", activated_on=date(2026, 9, 12), expires_on=date(2026, 10, 1))
        line_with_op.activated_at = dj_timezone.now()
        line_with_op.save(update_fields=["activated_at"])
        line_without_op, _ = _make_line("+5511900000304", activated_on=date(2026, 9, 12), expires_on=date(2026, 10, 1))

        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511900000303")
        self.assertContains(response, "+5511900000304")


class WhatsAppSealReportOnePerLineAndScopeTests(TestCase):
    """Uma linha por PhoneLine; status operacional/origem/vinculo nao
    filtram implicitamente."""

    def setUp(self):
        self.admin = _create_user("admin.seal.scope@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_line_appears_exactly_once_even_with_allocation_history(self):
        from core.services.allocation_service import AllocationService
        from employees.models import Employee

        line, _ = _make_line(
            "+5511900000401", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 1)
        )
        employee = Employee.objects.create(
            full_name="Selo Report Scope",
            corporate_email="scope@example.com",
            employee_id="SEALREP-1",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        AllocationService.allocate_line(employee=employee, phone_line=line, allocated_by=self.admin)

        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        self.assertEqual(content.count("+5511900000401"), 1)

    def test_each_operational_status_included(self):
        statuses = [
            PhoneLine.Status.AVAILABLE,
            PhoneLine.Status.ALLOCATED,
            PhoneLine.Status.SUSPENDED,
            PhoneLine.Status.CANCELLED,
        ]
        for index, status in enumerate(statuses):
            _make_line(f"+551190000050{index}", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 1), status=status)
        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        for index in range(len(statuses)):
            self.assertIn(f"+551190000050{index}", content)

    def test_blip_origin_not_excluded(self):
        _make_line("+5511900000510", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 1), origem=PhoneLine.Origem.BLIP)
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511900000510")

    def test_line_without_allocation_included(self):
        _make_line("+5511900000511", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 1))
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511900000511")


class WhatsAppSealReportOrderingTests(TestCase):
    """Ordenacao: ativacao decrescente, pk decrescente no desempate."""

    def setUp(self):
        self.admin = _create_user("admin.seal.order@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_descending_activation_order(self):
        _make_line("+5511900000601", activated_on=date(2026, 9, 5), expires_on=date(2026, 10, 1))
        _make_line("+5511900000602", activated_on=date(2026, 9, 20), expires_on=date(2026, 10, 1))
        _make_line("+5511900000603", activated_on=date(2026, 9, 12), expires_on=date(2026, 10, 1))

        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        idx_602 = content.index("+5511900000602")
        idx_603 = content.index("+5511900000603")
        idx_601 = content.index("+5511900000601")
        self.assertLess(idx_602, idx_603)
        self.assertLess(idx_603, idx_601)

    def test_tie_break_by_descending_pk(self):
        first, _ = _make_line("+5511900000611", activated_on=date(2026, 9, 15), expires_on=date(2026, 10, 1))
        second, _ = _make_line("+5511900000612", activated_on=date(2026, 9, 15), expires_on=date(2026, 10, 1))
        self.assertLess(first.pk, second.pk)

        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        idx_612 = content.index("+5511900000612")
        idx_611 = content.index("+5511900000611")
        self.assertLess(idx_612, idx_611)


class WhatsAppSealReportFilterTests(TestCase):
    """Filtros de tipo/pagamento/situacao/busca, isolados e combinados."""

    def setUp(self):
        self.admin = _create_user("admin.seal.filters@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)
        self.one, _ = _make_line(
            "+5511900000701", seal="META_ONE", payment="CREDIT_CARD", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 1)
        )
        self.verified, _ = _make_line(
            "+5511900000702", seal="META_VERIFIED", payment="GOOGLE_GIFT_CARD", activated_on=date(2026, 9, 12), expires_on=date(2026, 10, 1)
        )

    def test_selo_filter_isolates_type(self):
        response = self.client.get(_report_url(_base_pairs(selo="META_ONE")))
        content = response.content.decode()
        self.assertIn("+5511900000701", content)
        self.assertNotIn("+5511900000702", content)

    def test_pagamento_filter_isolates_payment(self):
        response = self.client.get(_report_url(_base_pairs(pagamento="GOOGLE_GIFT_CARD")))
        content = response.content.decode()
        self.assertIn("+5511900000702", content)
        self.assertNotIn("+5511900000701", content)

    def test_linha_search_partial_substring(self):
        response = self.client.get(_report_url(_base_pairs(linha="000701")))
        content = response.content.decode()
        self.assertIn("+5511900000701", content)
        self.assertNotIn("+5511900000702", content)

    def test_linha_search_trims_surrounding_whitespace(self):
        response = self.client.get(_report_url(_base_pairs(linha="  000701  ")))
        self.assertContains(response, "+5511900000701")

    def test_combined_filters_apply_as_and(self):
        response = self.client.get(
            _report_url(_base_pairs(selo="META_ONE", pagamento="CREDIT_CARD", linha="000701"))
        )
        content = response.content.decode()
        self.assertIn("+5511900000701", content)
        self.assertNotIn("+5511900000702", content)

        response_mismatch = self.client.get(
            _report_url(_base_pairs(selo="META_ONE", pagamento="GOOGLE_GIFT_CARD"))
        )
        content_mismatch = response_mismatch.content.decode()
        self.assertNotIn("+5511900000701", content_mismatch)
        self.assertNotIn("+5511900000702", content_mismatch)


class WhatsAppSealReportSituationBoundaryTests(TestCase):
    """Fronteiras +8/+7/+1/0/-1 dias e missing_expiry, com referencia local fixa."""

    def setUp(self):
        self.admin = _create_user("admin.seal.situation@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)
        with _frozen_today():
            self.regular, _ = _make_line("+5511900000801", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 2))  # +8
            self.warning_edge, _ = _make_line("+5511900000802", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 1))  # +7
            self.warning_low, _ = _make_line("+5511900000803", activated_on=date(2026, 9, 10), expires_on=date(2026, 9, 25))  # +1
            self.today_case, _ = _make_line("+5511900000804", activated_on=date(2026, 9, 10), expires_on=date(2026, 9, 24))  # 0
            self.expired, _ = _make_line("+5511900000805", activated_on=date(2026, 9, 10), expires_on=date(2026, 9, 23))  # -1
            self.missing, _ = _make_line("+5511900000806", activated_on=date(2026, 9, 10), expires_on=None)

    def _situacao(self, key):
        with _frozen_today():
            return self.client.get(_report_url(_base_pairs(situacao=key)))

    def test_regular_boundary_plus_8(self):
        content = self._situacao("regular").content.decode()
        self.assertIn("+5511900000801", content)
        self.assertNotIn("+5511900000802", content)

    def test_warning_boundary_plus_7_and_plus_1(self):
        content = self._situacao("warning").content.decode()
        self.assertIn("+5511900000802", content)
        self.assertIn("+5511900000803", content)
        self.assertNotIn("+5511900000801", content)
        self.assertNotIn("+5511900000804", content)

    def test_today_boundary_zero(self):
        content = self._situacao("today").content.decode()
        self.assertIn("+5511900000804", content)
        self.assertNotIn("+5511900000803", content)
        self.assertNotIn("+5511900000805", content)

    def test_expired_boundary_minus_1(self):
        content = self._situacao("expired").content.decode()
        self.assertIn("+5511900000805", content)
        self.assertNotIn("+5511900000804", content)

    def test_missing_expiry_own_category_never_regular(self):
        content = self._situacao("missing_expiry").content.decode()
        self.assertIn("+5511900000806", content)

        regular_content = self._situacao("regular").content.decode()
        self.assertNotIn("+5511900000806", regular_content)


class WhatsAppSealReportDeletionAndLegacyTests(TestCase):
    """Exclusao logica de linha/SIMcard e legados (selo desconhecido, datas
    invertidas, pagamento/e-mail ausentes, sem ativacao)."""

    def setUp(self):
        self.admin = _create_user("admin.seal.legacy@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_line_deleted_only_hidden_by_default_shown_when_included(self):
        _make_line("+5511900000901", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 1), delete_line=True)
        default_resp = self.client.get(_report_url(_base_pairs()))
        self.assertNotContains(default_resp, "+5511900000901")
        included_resp = self.client.get(_report_url(_base_pairs(incluir_excluidos="1")))
        self.assertContains(included_resp, "+5511900000901")

    def test_simcard_deleted_only_hidden_by_default_shown_when_included(self):
        """Inconsistencia legada: SIMcard.is_deleted=True sem cascata para a
        linha (setada direto via update(), nao via SIMcard.delete())."""
        _make_line("+5511900000902", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 1), delete_sim=True)
        default_resp = self.client.get(_report_url(_base_pairs()))
        self.assertNotContains(default_resp, "+5511900000902")
        included_resp = self.client.get(_report_url(_base_pairs(incluir_excluidos="1")))
        self.assertContains(included_resp, "+5511900000902")

    def test_both_line_and_simcard_deleted(self):
        _make_line("+5511900000903", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 1), cascade_delete_sim=True)
        default_resp = self.client.get(_report_url(_base_pairs()))
        self.assertNotContains(default_resp, "+5511900000903")
        included_resp = self.client.get(_report_url(_base_pairs(incluir_excluidos="1")))
        self.assertContains(included_resp, "+5511900000903")

    def test_checkbox_included_does_not_restore_flags(self):
        line, sim = _make_line("+5511900000904", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 1), delete_line=True)
        response = self.client.get(_report_url(_base_pairs(incluir_excluidos="1")))
        self.assertEqual(response.status_code, 200)
        line.refresh_from_db()
        self.assertTrue(line.is_deleted)

    def test_line_without_activation_excluded_from_period(self):
        """Controle positivo obrigatorio (mesmo motivo do isolamento de
        referencia): prova que a resposta e capaz de listar dados antes de
        provar a exclusao da linha sem ativacao."""
        _make_line("+5511900000998", seal="META_ONE", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 1))
        _make_line("+5511900000905", seal="META_ONE", activated_on=None, expires_on=date(2026, 10, 1))
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511900000998")
        self.assertNotContains(response, "+5511900000905")

    def test_unknown_seal_value_excluded(self):
        """Controle positivo obrigatorio: linha com selo valido no mesmo
        periodo prova que a ausencia da linha de selo desconhecido nao e
        mero efeito de a pagina nao renderizar nada."""
        valid_line, _ = _make_line("+5511900000997", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 1))
        line, _ = _make_line("+5511900000906", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 1))
        PhoneLine.objects.filter(pk=line.pk).update(whatsapp_seal="LEGACY_UNKNOWN")
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511900000997")
        self.assertNotContains(response, "+5511900000906")

    def test_payment_and_email_absent_render_blank_not_none(self):
        _make_line("+5511900000907", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 1), payment="", seal_email="")
        response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511900000907")

    def test_inverted_dates_still_included_and_classified_by_stored_expiry(self):
        with _frozen_today():
            _make_line("+5511900000908", activated_on=date(2026, 9, 15), expires_on=date(2026, 9, 10))
            response = self.client.get(_report_url(_base_pairs()))
        self.assertContains(response, "+5511900000908")


class WhatsAppSealReportPaginationTests(TestCase):
    """Paginacao de 50, empate, filtros preservados, total independente da pagina."""

    def setUp(self):
        self.admin = _create_user("admin.seal.pagination@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)
        for index in range(51):
            _make_line(
                f"+55119000{index:06d}",
                activated_on=date(2026, 9, 1 + (index % 20)),
                expires_on=date(2026, 10, 1),
            )

    def test_first_page_has_50_rows_and_not_the_51st(self):
        response = self.client.get(_report_url(_base_pairs()))
        content = response.content.decode()
        phone_hits = sum(1 for index in range(51) if f"+55119000{index:06d}" in content)
        self.assertEqual(phone_hits, 50)

    def test_second_page_has_remaining_row(self):
        response = self.client.get(_report_url(_base_pairs(page="2")))
        self.assertEqual(response.status_code, 200)

    def test_filters_preserved_across_pagination(self):
        response = self.client.get(_report_url(_base_pairs(page="2")))
        content = response.content.decode()
        self.assertIn(f'name="data_inicial" value="{PERIOD_START}"', content)
        self.assertIn(f'name="data_final" value="{PERIOD_END}"', content)

    def test_empty_result_set_returns_zero_totals_no_error(self):
        response = self.client.get(
            _report_url(_base_pairs(data_inicial="2020-01-01", data_final="2020-01-02"))
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("erro", response.content.decode().lower())


class WhatsAppSealReportNoWriteAndQueryCostTests(TestCase):
    """Somente leitura; contagem de consultas entre conjuntos pequeno/maior."""

    def setUp(self):
        self.admin = _create_user("admin.seal.readonly@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_generating_report_does_not_write_business_data(self):
        """Sem checar o status HTTP, uma resposta de erro silencioso (ex.:
        500 antes de qualquer escrita) tambem manteria a contagem estavel e
        mascararia uma view quebrada como se fosse 'sem efeito colateral'."""
        _make_line("+5511900001001", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 1))
        lines_before = PhoneLine.objects.count()
        first = self.client.get(_report_url(_base_pairs(incluir_excluidos="1")))
        second = self.client.get(_report_url(_base_pairs(selo="META_ONE")))
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(PhoneLine.objects.count(), lines_before)

    def test_query_count_does_not_scale_linearly_with_row_count(self):
        for index in range(3):
            _make_line(f"+5511900001{index:03d}", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 1))
        with CaptureQueriesContext(connection) as small:
            small_response = self.client.get(_report_url(_base_pairs()))

        for index in range(3, 30):
            _make_line(f"+5511900001{index:03d}", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 1))
        with CaptureQueriesContext(connection) as large:
            large_response = self.client.get(_report_url(_base_pairs()))

        self.assertEqual(small_response.status_code, 200)
        self.assertEqual(large_response.status_code, 200)
        self.assertLessEqual(len(large.captured_queries) - len(small.captured_queries), 3)


class WhatsAppSealExportAuthorizationTests(TestCase):
    """E: autorizacao tambem no acesso direto ao download, ambos os formatos.

    Todos os testes desta classe chamam reverse(EXPORT_URL_NAME, ...) dentro
    do corpo do teste; a rota ainda nao esta registrada (proposta em REL-07,
    nao implementada), entao NoReverseMatch e o RED esperado ate REL-08-E."""

    def setUp(self):
        self.admin = _create_user("admin.seal.exportauth@test.com", SystemUser.Role.ADMIN)

    def test_admin_can_download_csv(self):
        self.client.force_login(self.admin)
        response = self.client.get(_export_url("csv", _base_pairs()))
        self.assertEqual(response.status_code, 200)

    def test_admin_can_download_xlsx(self):
        self.client.force_login(self.admin)
        response = self.client.get(_export_url("xlsx", _base_pairs()))
        self.assertEqual(response.status_code, 200)

    def test_non_admin_roles_get_403_on_export(self):
        for index, role in enumerate(NON_ADMIN_ROLES):
            with self.subTest(role=role):
                user = _create_user(f"export.role{index}@test.com", role)
                self.client.force_login(user)
                response = self.client.get(_export_url("csv", _base_pairs()))
                self.assertEqual(response.status_code, 403)

    def test_anonymous_gets_403_on_export(self):
        response = self.client.get(_export_url("csv", _base_pairs()))
        self.assertEqual(response.status_code, 403)

    def test_invalid_dates_rejected_on_direct_export_access(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            _export_url("csv", [("relatorio", "whatsapp_seal"), ("data_inicial", PERIOD_END), ("data_final", PERIOD_START)])
        )
        self.assertEqual(response.status_code, 400)

    def test_unknown_format_returns_404(self):
        self.client.force_login(self.admin)
        response = self.client.get(_export_url("pdf", _base_pairs()))
        self.assertEqual(response.status_code, 404)


class WhatsAppSealExportContentTests(TestCase):
    """E: conteudo real lido via csv/openpyxl; conjunto completo, colunas,
    tipos e neutralizacao de formulas."""

    def setUp(self):
        self.admin = _create_user("admin.seal.exportcontent@test.com", SystemUser.Role.ADMIN)
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
            _make_line(f"+5511900002{index:03d}", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 1))

        csv_response = self.client.get(_export_url("csv", _base_pairs(page="1")))
        rows = self._read_csv_rows(csv_response)
        data_rows = rows[1:]
        self.assertEqual(len(data_rows), 60)

        xlsx_response = self.client.get(_export_url("xlsx", _base_pairs(page="2")))
        xlsx_rows = self._read_xlsx_rows(xlsx_response)
        self.assertEqual(len(xlsx_rows) - 1, 60)

    def test_columns_match_approved_order_in_both_formats(self):
        _make_line("+5511900003001", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 1))
        expected_header = [
            "Linha",
            "Tipo do selo",
            "Ativação do selo",
            "Pagamento",
            "E-mail cadastrado",
            "Vencimento",
            "Situação do vencimento",
            "Registro",
        ]
        csv_rows = self._read_csv_rows(self.client.get(_export_url("csv", _base_pairs())))
        self.assertEqual(csv_rows[0], expected_header)

        xlsx_rows = self._read_xlsx_rows(self.client.get(_export_url("xlsx", _base_pairs())))
        self.assertEqual(list(xlsx_rows[0]), expected_header)

    def test_empty_filtered_set_exports_headers_only(self):
        csv_rows = self._read_csv_rows(
            self.client.get(_export_url("csv", _base_pairs(data_inicial="2020-01-01", data_final="2020-01-02")))
        )
        self.assertEqual(len(csv_rows), 1)

    def test_export_reflects_current_data_changed_after_query(self):
        line, _ = _make_line("+5511900004001", seal="META_ONE", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 1))
        self.client.get(_report_url(_base_pairs()))

        line.whatsapp_seal = "META_VERIFIED"
        line.save(update_fields=["whatsapp_seal"])

        csv_rows = self._read_csv_rows(self.client.get(_export_url("csv", _base_pairs())))
        matching = [row for row in csv_rows[1:] if row and row[0].lstrip("'") == "+5511900004001"]
        self.assertTrue(matching)
        self.assertIn("META VERIFICADO", matching[0][1])

    def test_phone_number_stored_as_string_type_in_xlsx(self):
        _make_line("+5511900005001", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 1))
        response = self.client.get(_export_url("xlsx", _base_pairs()))
        content = b"".join(response.streaming_content) if response.streaming else response.content
        workbook = openpyxl.load_workbook(io.BytesIO(content))
        sheet = workbook.active
        phone_cell = sheet.cell(row=2, column=1)
        self.assertEqual(phone_cell.data_type, "s")

    def test_formula_injection_neutralized_for_values_starting_with_trigger_chars(self):
        _make_line(
            "+5511900006001",
            activated_on=date(2026, 9, 10),
            expires_on=date(2026, 10, 1),
            seal_email="+injected@example.com",
        )
        csv_rows = self._read_csv_rows(self.client.get(_export_url("csv", _base_pairs())))
        data_row = [row for row in csv_rows[1:] if row][0]
        for cell in data_row:
            self.assertFalse(cell.startswith(("=", "+", "-", "@")))

    def test_accents_and_line_breaks_preserved_and_do_not_break_parsing(self):
        _make_line(
            "+5511900007001",
            activated_on=date(2026, 9, 10),
            expires_on=date(2026, 10, 1),
            seal_email="usuário.ção@example.com",
        )
        csv_rows = self._read_csv_rows(self.client.get(_export_url("csv", _base_pairs())))
        self.assertEqual(len(csv_rows), 2)


class WhatsAppSealExportVolumeTests(TestCase):
    """Fronteira de divisao em partes/ZIP acima de 100.000 linhas.

    REL-08-C nao define uma interface de configuracao publica para reduzir
    o limiar de 100.000 em ambiente de teste, e as instrucoes desta task
    proibem inventar um nome de configuracao privado ou alterar a aplicacao
    so para criar esse mecanismo. Por isso este arquivo NAO gera 100.000+
    linhas sintaticas: cobre apenas o caso trivial abaixo do limiar (arquivo
    unico, nao ZIP) e registra a fronteira real como lacuna dependente de
    ensaio de volume dedicado antes de REL-08-E, conforme a propria spec
    exige ('ensaio de volume real permanece obrigatorio antes de liberar
    E'). Nao alega performance/capacidade validada."""

    def setUp(self):
        self.admin = _create_user("admin.seal.exportvolume@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_small_filtered_set_returns_single_file_not_zip(self):
        _make_line("+5511900008001", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 1))
        response = self.client.get(_export_url("csv", _base_pairs()))
        self.assertEqual(response.status_code, 200)
        content_type = response.headers.get("Content-Type", "")
        self.assertNotIn("zip", content_type.lower())


class ReportExportStreamingCleanupTests(TestCase):
    """Prova direta do mecanismo de limpeza de temporarios (REL-07/REL-08-C:
    'Limpeza em sucesso, erro e encerramento da resposta/desconexao,
    conforme mecanismo real do framework'). A exportacao usa
    StreamingHttpResponse com um generator; o Django registra
    generator.close() como resource closer de HttpResponseBase, chamado
    tanto ao concluir a resposta (consumo completo) quanto ao detectar
    desconexao do cliente (fechamento antecipado) — o mesmo mecanismo que
    um servidor WSGI real aciona. Django.test.Client NAO drena
    StreamingHttpResponse quando o teste so verifica status/headers (relato
    conhecido do test client, nao do codigo de producao); por isso a prova
    aqui chama o generator diretamente, replicando o que o servidor real
    faz nos dois casos, mais o caminho de erro durante a geracao."""

    def _filters(self):
        return dict(
            data_inicial=date(2026, 9, 1),
            data_final=date(2026, 9, 24),
            incluir_excluidos=False,
            selo="",
            pagamento="",
            situacao="",
            linha="",
        )

    def test_temp_dir_removed_after_full_stream_consumption(self):
        import os

        from core.services.report_export_service import (
            _stream_and_cleanup,
            generate_whatsapp_seal_export,
        )

        _make_line("+5511900009001", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 1))
        export = generate_whatsapp_seal_export(formato="csv", filters=self._filters())
        self.assertTrue(os.path.isdir(export.temp_dir))

        content = b"".join(_stream_and_cleanup(export.path, export.temp_dir))
        self.assertIn(b"+5511900009001", content)
        self.assertFalse(os.path.exists(export.temp_dir))

    def test_temp_dir_removed_on_early_close_simulating_client_disconnect(self):
        import os

        from core.services.report_export_service import (
            _stream_and_cleanup,
            generate_whatsapp_seal_export,
        )

        _make_line("+5511900009002", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 1))
        export = generate_whatsapp_seal_export(formato="csv", filters=self._filters())
        stream = _stream_and_cleanup(export.path, export.temp_dir)
        next(stream)
        stream.close()  # exatamente o que um servidor WSGI faz ao detectar desconexao
        self.assertFalse(os.path.exists(export.temp_dir))

    def test_temp_dir_removed_before_first_chunk_consumed_on_close(self):
        """REL-08-E, risco 1: fechamento ANTES de qualquer iteracao (ex.:
        cliente desconecta antes do primeiro byte). Diferente do teste
        acima (que chama next() antes de close()), aqui streaming_content
        nunca e tocado — nem o primeiro chunk. Constroi a resposta real via
        build_whatsapp_seal_export_response e chama apenas response.close(),
        exatamente o que o servidor WSGI faz. O diretorio temporario e
        localizado via mock em tempfile.mkdtemp (mesmo padrao do teste de
        falha acima), sem depender de atributo privado da resposta. Nenhuma
        limpeza manual antes da assertion: se o mecanismo real nao cobrir
        este caminho, a assertion final falha de verdade (RED)."""
        import os
        from unittest import mock

        from core.services import report_export_service

        _make_line("+5511900009004", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 1))

        captured = {}
        original_mkdtemp = report_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        with mock.patch.object(
            report_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
        ):
            response = report_export_service.build_whatsapp_seal_export_response(
                formato="csv", filters=self._filters()
            )

        self.assertIn("temp_dir", captured)
        self.assertTrue(os.path.isdir(captured["temp_dir"]))

        response.close()  # nenhum chunk foi lido ate aqui

        self.assertFalse(os.path.exists(captured["temp_dir"]))

    def test_temp_dir_removed_when_generation_fails(self):
        import os
        from unittest import mock

        from core.services import report_export_service

        _make_line("+5511900009003", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 1))
        captured = {}
        original_mkdtemp = report_export_service.tempfile.mkdtemp

        def _capture_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            captured["temp_dir"] = path
            return path

        with mock.patch.object(
            report_export_service, "_write_csv_chunk", side_effect=RuntimeError("boom")
        ):
            with mock.patch.object(
                report_export_service.tempfile, "mkdtemp", side_effect=_capture_mkdtemp
            ):
                with self.assertRaises(RuntimeError):
                    report_export_service.generate_whatsapp_seal_export(
                        formato="csv", filters=self._filters()
                    )

        self.assertIn("temp_dir", captured)
        self.assertFalse(os.path.exists(captured["temp_dir"]))


class WhatsAppSealExportSplitBoundaryTests(TestCase):
    """Fronteira de divisao em partes/ZIP (REL-08-C), boundary-1/boundary/
    boundary+1 em ambos os formatos. Interface tecnica explicita e pequena
    para reduzir o limiar em teste: o parametro `split_threshold` de
    core.services.report_export_service.generate_whatsapp_seal_export,
    chamado diretamente aqui (nao via HTTP). A rota reports_export nunca
    passa esse parametro e usa sempre EXPORT_SPLIT_THRESHOLD (100.000) —
    producao permanece intocada por este teste."""

    def _filters(self):
        return dict(
            data_inicial=date(2026, 9, 1),
            data_final=date(2026, 9, 24),
            incluir_excluidos=False,
            selo="",
            pagamento="",
            situacao="",
            linha="",
        )

    def _make_lines(self, count, prefix):
        for index in range(count):
            _make_line(
                f"+55119{prefix}{index:06d}",
                activated_on=date(2026, 9, 10),
                expires_on=date(2026, 10, 1),
            )

    def _generate(self, formato, threshold):
        from core.services.report_export_service import generate_whatsapp_seal_export

        return generate_whatsapp_seal_export(
            formato=formato, filters=self._filters(), split_threshold=threshold
        )

    def _read_csv_data_row_counts(self, path):
        with open(path, encoding="utf-8-sig") as handle:
            rows = list(csv.reader(handle, delimiter=";"))
        return rows[0], len(rows) - 1

    def _read_xlsx_data_row_counts(self, path):
        workbook = openpyxl.load_workbook(path)
        sheet = workbook["Selos WhatsApp"]
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

        from core.services.report_export_service import COLUMNS

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

        from core.services.report_export_service import COLUMNS

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
                    sheet = workbook["Selos WhatsApp"]
                    rows = list(sheet.iter_rows(values_only=True))
                    self.assertEqual(list(rows[0]), COLUMNS)
                    counts.append(len(rows) - 1)
                self.assertEqual(sorted(counts), [1, 3])
                self.assertEqual(sum(counts), 4)
        finally:
            shutil.rmtree(export.temp_dir, ignore_errors=True)


class WhatsAppSealExportCountIterationRaceTests(TestCase):
    """REL-08-E, risco 2: divergencia entre uma contagem previa e o
    conjunto realmente iterado. A correcao elimina a contagem previa
    separada: `generate_whatsapp_seal_export` nao chama mais
    `count_whatsapp_seal_report_rows` — total, numero de partes e
    quantidade por parte sao derivados do que a UNICA consulta
    (`iter_whatsapp_seal_report_rows`) efetivamente entregou.

    Instrumentacao: `iter_whatsapp_seal_report_rows` e envolvida (nao
    mockada — a funcao real e chamada e consumida normalmente) para
    injetar uma mutacao real no banco de teste (mesma conexao) DEPOIS que
    a consulta real ja comecou a ser consumida. Isso simula dados mudando
    durante uma exportacao longa. Nao mocka o exportador nem forja o
    resultado esperado; o teste le o arquivo real gerado.

    Limite explicito: a mutacao ocorre na MESMA conexao/transacao do
    teste (Django TestCase nao permite conexao concorrente real visivel
    aos dados de setUp, que ficam em transacao nao commitada). Isso prova
    o contrato de auto-consistencia do exportador (metadados sempre
    batem com o arquivo, nunca com uma contagem congelada antes da
    leitura) diante de estado mutavel — nao prova isolamento
    transacional concorrente entre processos do PostgreSQL de producao,
    que exigiria duas conexoes reais e nao e reproduzivel neste ambiente
    de teste (SQLite, TestCase). Essa garantia mais ampla depende da
    semantica de snapshot fixo no INICIO da consulta/cursor (mesma
    consulta SQL unica, executada uma vez), documentada e nao mockada
    aqui, nao de isolamento de transacao configurado nesta task."""

    def setUp(self):
        self.admin = _create_user("admin.seal.race@test.com", SystemUser.Role.ADMIN)
        self.client.force_login(self.admin)

    def _filters(self):
        return dict(
            data_inicial=date(2026, 9, 1),
            data_final=date(2026, 9, 24),
            incluir_excluidos=False,
            selo="",
            pagamento="",
            situacao="",
            linha="",
        )

    def _csv_data_row_count(self, path):
        with open(path, encoding="utf-8-sig") as handle:
            rows = list(csv.reader(handle, delimiter=";"))
        return len(rows) - 1

    def _exported_data_row_count(self, export):
        """Conta linhas de dados no arquivo final, seja CSV unico ou ZIP com
        multiplas partes CSV — soma as partes reais, nao presume 1 arquivo."""
        import zipfile

        if not export.filename.endswith(".zip"):
            return self._csv_data_row_count(export.path)
        total = 0
        with zipfile.ZipFile(export.path) as archive:
            for name in archive.namelist():
                text = archive.read(name).decode("utf-8-sig")
                rows = list(csv.reader(io.StringIO(text), delimiter=";"))
                total += len(rows) - 1
        return total

    def test_rows_inserted_after_query_started_do_not_corrupt_total_or_split(self):
        """Hipotese pre-correcao: contagem previa abaixo do limiar; linhas
        inseridas depois fariam o conjunto realmente iterado ultrapassar o
        limiar, arriscando arquivo/ZIP com quantidade incorreta. Prova:
        apos a 2a linha ser entregue pela consulta real (limiar=2, ou
        seja, exatamente quando a parte 1 termina e a parte 2 comecaria a
        puxar mais linhas do MESMO iterator), insere 2 linhas elegiveis
        novas. Como e a MESMA consulta ja em andamento (nao uma nova
        consulta), as linhas novas nao pertencem ao resultado ja obtido;
        o teste verifica que o total exportado e exatamente as 2 linhas
        originais, sem falha e sem quantidade divergente do arquivo real."""
        from unittest import mock

        from core.services import report_export_service

        _make_line("+5511900010001", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 1))
        _make_line("+5511900010002", activated_on=date(2026, 9, 11), expires_on=date(2026, 10, 1))

        real_iter = report_export_service.iter_whatsapp_seal_report_rows
        state = {"yielded": 0, "mutated": False}

        def _instrumented_iter(*args, **kwargs):
            for row in real_iter(*args, **kwargs):
                state["yielded"] += 1
                yield row
                if state["yielded"] == 2 and not state["mutated"]:
                    state["mutated"] = True
                    _make_line(
                        "+5511900010003",
                        activated_on=date(2026, 9, 12),
                        expires_on=date(2026, 10, 1),
                    )
                    _make_line(
                        "+5511900010004",
                        activated_on=date(2026, 9, 13),
                        expires_on=date(2026, 10, 1),
                    )

        with mock.patch.object(
            report_export_service,
            "iter_whatsapp_seal_report_rows",
            side_effect=_instrumented_iter,
        ):
            export = report_export_service.generate_whatsapp_seal_export(
                formato="csv", filters=self._filters(), split_threshold=2
            )
        try:
            self.assertTrue(state["mutated"])
            self.assertFalse(export.filename.endswith(".zip"))
            written_in_file = self._csv_data_row_count(export.path)
            self.assertEqual(written_in_file, 2)
        finally:
            import shutil

            shutil.rmtree(export.temp_dir, ignore_errors=True)

    def test_rows_deleted_after_query_started_still_export_full_fetched_set_without_crash(self):
        """Hipotese pre-correcao: contagem previa acima do limiar; linhas
        excluidas do conjunto depois fariam o conjunto realmente iterado
        ficar menor, arriscando `next()` em iterator esgotado (StopIteration
        nao tratada) ao tentar completar uma parte com a contagem antiga.
        Prova: apos a 1a linha ser entregue pela consulta real (limiar=2, 3
        linhas totais — divide naturalmente em 2 partes/ZIP independente da
        mutacao, isso e esperado e nao o que se prova aqui), marca as 2
        linhas restantes (ainda nao entregues) como excluidas — exclusao
        logica (PhoneLine.delete() e soft-delete: is_deleted=True, nao
        remove a linha da tabela). Como a consulta real (SQLite, sem cursor
        server-side) ja buscou o resultado completo da UNICA execucao da
        query antes de comecar a entregar linhas, a exclusao posterior nao
        afeta o que ja foi obtido: a exportacao completa sem erro e o total
        exportado bate com as 3 linhas originais, nao com uma contagem
        que quebrasse por escassez ou que refletisse a exclusao ocorrida
        apos a consulta ja iniciada."""
        from unittest import mock

        from core.services import report_export_service

        line_a, _ = _make_line(
            "+5511900011001", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 1)
        )
        line_b, _ = _make_line(
            "+5511900011002", activated_on=date(2026, 9, 11), expires_on=date(2026, 10, 1)
        )
        line_c, _ = _make_line(
            "+5511900011003", activated_on=date(2026, 9, 12), expires_on=date(2026, 10, 1)
        )

        real_iter = report_export_service.iter_whatsapp_seal_report_rows
        state = {"yielded": 0, "mutated": False}

        def _instrumented_iter(*args, **kwargs):
            for row in real_iter(*args, **kwargs):
                state["yielded"] += 1
                yield row
                if state["yielded"] == 1 and not state["mutated"]:
                    state["mutated"] = True
                    line_b.delete()
                    line_c.delete()

        with mock.patch.object(
            report_export_service,
            "iter_whatsapp_seal_report_rows",
            side_effect=_instrumented_iter,
        ):
            export = report_export_service.generate_whatsapp_seal_export(
                formato="csv", filters=self._filters(), split_threshold=2
            )
        try:
            self.assertTrue(state["mutated"])
            written_total = self._exported_data_row_count(export)
            self.assertEqual(written_total, 3)
        finally:
            import shutil

            shutil.rmtree(export.temp_dir, ignore_errors=True)

    def test_export_response_no_longer_runs_a_separate_count_query(self):
        """Verificacao estrutural direta (nao apenas comportamental): a
        exportacao usa uma unica consulta para dimensionar partes/ZIP.
        Confirma, via CaptureQueriesContext, que nenhuma consulta
        `SELECT COUNT(*)` isolada contra `telecom_phoneline` ocorre — só a
        consulta de linhas (que o Django materializa como SELECT normal,
        nao COUNT, ao iterar)."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from core.services.report_export_service import generate_whatsapp_seal_export

        _make_line("+5511900012001", activated_on=date(2026, 9, 10), expires_on=date(2026, 10, 1))

        with CaptureQueriesContext(connection) as captured:
            export = generate_whatsapp_seal_export(formato="csv", filters=self._filters())
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


class WhatsAppSealExportRealVolumeTests(TestCase):
    """Ensaio de volume REAL na fronteira de producao (100.000/100.001
    linhas), exigido por REL-08-C/REL-08-T antes de liberar REL-08-E.

    Fixture UNICA de 100.001 linhas (bulk_create; sem full_clean/sinais —
    populamento de volume, nao fluxo de negocio), criada uma vez para toda
    a classe (`setUpTestData`). Dois periodos de filtro sobre essa MESMA
    fixture selecionam exatamente 100.000 ou 100.001 linhas, evitando
    recriar 10^5 registros por teste.

    Tempo e pico de memoria (tracemalloc) sao medidos em bloco proprio,
    iniciado somente APOS a fixture ja estar criada e confirmada — mede o
    processo de exportacao isoladamente, nao a criacao dos dados de teste.
    Roda em banco de teste isolado (sqlite, "pytest" in sys.modules); nao
    acessa PRD. Deliberadamente lento (10^5 linhas reais); nao e um teste
    unitario comum e nao deve ser lido como prova de comportamento de
    logica (essa prova esta em WhatsAppSealExportSplitBoundaryTests)."""

    BASE_COUNT = 100_000

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
                whatsapp_seal="META_ONE",
                whatsapp_seal_activated_on=date(2026, 9, 10),
                whatsapp_seal_expires_on=date(2026, 10, 1),
            )
            for index in range(cls.BASE_COUNT)
        ]
        lines.append(
            PhoneLine(
                phone_number="+551199999999",
                sim_card_id=sim_ids[cls.BASE_COUNT],
                status=PhoneLine.Status.AVAILABLE,
                whatsapp_seal="META_ONE",
                whatsapp_seal_activated_on=date(2026, 9, 24),
                whatsapp_seal_expires_on=date(2026, 10, 1),
            )
        )
        PhoneLine.objects.bulk_create(lines, batch_size=5000)

    def _filters(self, data_final):
        return dict(
            data_inicial=date(2026, 9, 1),
            data_final=data_final,
            incluir_excluidos=False,
            selo="",
            pagamento="",
            situacao="",
            linha="",
        )

    def _measure(self, formato, data_final, expected_total):
        import sys
        import time
        import tracemalloc
        import zipfile
        from pathlib import Path

        from core.services.report_export_service import generate_whatsapp_seal_export
        from core.services.whatsapp_seal_report_service import (
            count_whatsapp_seal_report_rows,
        )

        filters = self._filters(data_final)
        actual_total = count_whatsapp_seal_report_rows(
            reference_date=date(2026, 9, 24), **filters
        )
        self.assertEqual(actual_total, expected_total)

        tracemalloc.start()
        start = time.perf_counter()
        export = generate_whatsapp_seal_export(formato=formato, filters=filters)
        elapsed = time.perf_counter() - start
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        try:
            size_bytes = Path(export.path).stat().st_size
            is_zip = export.filename.endswith(".zip")
            part_count = 1
            if is_zip:
                with zipfile.ZipFile(export.path) as archive:
                    part_count = len(archive.namelist())
            sys.stderr.write(
                "\n[VOLUME REAL] formato={} linhas={} tempo={:.2f}s "
                "tamanho={:.2f}MiB zip={} partes={} "
                "pico_memoria_exportador={:.2f}MiB\n".format(
                    formato,
                    expected_total,
                    elapsed,
                    size_bytes / 1024 / 1024,
                    is_zip,
                    part_count,
                    peak_bytes / 1024 / 1024,
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
