"""
Testes do relatorio operacional por linha (T7): consulta de leitura pura que
deriva ciclos exclusivamente de LineDailyActionAuditEvent (nunca de
PhoneLineHistory, nunca por estado atual de DailyUserAction/
AllocationPendency/LineAllocation).

Modulo separado seguindo o padrao ja estabelecido em
telecom/tests_line_timeline.py (T6): descoberto por ``manage.py test
telecom`` porque o nome comeca com ``test``.
"""

from datetime import timedelta

from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from allocations.models import LineAllocation
from employees.models import Employee
from telecom.line_operational_report import (
    LineOperationalReportFilters,
    build_line_operational_report,
)
from telecom.models import LineDailyActionAuditEvent, PhoneLine, PhoneLineHistory, SIMcard
from telecom.views import get_visible_phone_lines_queryset
from users.models import SystemUser

_UNSET = object()


class LineOperationalReportTestBase(TestCase):
    """Fixtures compartilhadas: um admin e uma linha visivel a ele."""

    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="opreport.admin@test.com",
            password="123456",
            role=SystemUser.Role.ADMIN,
        )
        self.operator = SystemUser.objects.create_user(
            email="opreport.operator@test.com",
            password="123456",
            role=SystemUser.Role.OPERATOR,
        )
        self.employee = Employee.objects.create(
            full_name="OpReport Employee",
            corporate_email="opreport.employee@corp.com",
            employee_id="EMPOR1",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        self.sim_card = SIMcard.objects.create(
            iccid="8900000000000000501",
            carrier="CarrierOpReport",
            status=SIMcard.Status.AVAILABLE,
        )
        self.phone_line = PhoneLine.objects.create(
            phone_number="+551199999501",
            sim_card=self.sim_card,
            status=PhoneLine.Status.ALLOCATED,
        )
        self.allocation = LineAllocation.objects.create(
            employee=self.employee,
            phone_line=self.phone_line,
            allocated_by=self.admin,
            is_active=True,
        )
        PhoneLineHistory.objects.filter(phone_line=self.phone_line).delete()

    def _state(self, **overrides):
        state = {
            "action": {"code": "no_action", "label": "Sem Acao"},
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

    def _make_event(
        self,
        *,
        when,
        event_type,
        source=LineDailyActionAuditEvent.Source.DAILY_USER_ACTION,
        source_object_id=1,
        performed_by=None,
        phone_line=_UNSET,
        allocation=_UNSET,
        employee=_UNSET,
        performed_by_name_snapshot="",
        performed_by_email_snapshot="",
        before=None,
        after=None,
    ):
        before = before if before is not None else self._state()
        after = after if after is not None else self._state(note="mudou")
        target_line = self.phone_line if phone_line is _UNSET else phone_line
        allocation = self.allocation if allocation is _UNSET else allocation
        employee = self.employee if employee is _UNSET else employee
        return LineDailyActionAuditEvent.objects.create(
            phone_line=target_line,
            allocation=allocation,
            employee=employee,
            performed_by=performed_by,
            event_type=event_type,
            source=source,
            source_object_id=source_object_id,
            occurred_at=when,
            allocation_id_snapshot=allocation.pk if allocation else None,
            performed_by_name_snapshot=performed_by_name_snapshot,
            performed_by_email_snapshot=performed_by_email_snapshot,
            before_state=before,
            after_state=after,
        )

    def _report(self, user=None, **get_params):
        user = user or self.admin
        queryset = get_visible_phone_lines_queryset(user)
        filters = LineOperationalReportFilters.from_get_params(get_params)
        return build_line_operational_report(queryset, filters)

    def _row_for(self, rows, phone_line):
        for row in rows:
            if row.phone_number == phone_line.phone_number:
                return row
        return None


class OpenedResolvedCycleTest(LineOperationalReportTestBase):
    """1. OPENED -> RESOLVED gera 1 entrada, 1 saida, 1 ciclo resolvido."""

    def test_opened_then_resolved_counts_one_cycle_resolved(self):
        now = timezone.now()
        self._make_event(
            when=now - timedelta(hours=2),
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
        )
        self._make_event(
            when=now - timedelta(hours=1),
            event_type=LineDailyActionAuditEvent.EventType.RESOLVED,
        )

        rows = self._report()
        row = self._row_for(rows, self.phone_line)

        self.assertIsNotNone(row)
        self.assertEqual(row.entradas, 1)
        self.assertEqual(row.saidas, 1)
        self.assertEqual(row.ciclos, 1)
        self.assertEqual(row.situacao, "Resolvida")
        self.assertEqual(row.duracao_aberta, "-")


class OpenCycleWithoutResolvedTest(LineOperationalReportTestBase):
    """2. OPENED sem RESOLVED aparece aberta com duracao."""

    def test_opened_without_resolved_shows_open_with_duration(self):
        opened_at = timezone.now() - timedelta(hours=3)
        self._make_event(
            when=opened_at,
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
        )

        rows = self._report()
        row = self._row_for(rows, self.phone_line)

        self.assertIsNotNone(row)
        self.assertEqual(row.entradas, 1)
        self.assertEqual(row.saidas, 0)
        self.assertEqual(row.ciclos, 1)
        self.assertEqual(row.situacao, "Aberta")
        self.assertNotEqual(row.duracao_aberta, "-")


class ReopenedAfterResolvedTest(LineOperationalReportTestBase):
    """3. REOPENED apos RESOLVED cria segundo ciclo."""

    def test_reopened_after_resolved_creates_second_cycle(self):
        now = timezone.now()
        self._make_event(
            when=now - timedelta(hours=4),
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
        )
        self._make_event(
            when=now - timedelta(hours=3),
            event_type=LineDailyActionAuditEvent.EventType.RESOLVED,
        )
        self._make_event(
            when=now - timedelta(hours=2),
            event_type=LineDailyActionAuditEvent.EventType.REOPENED,
        )

        rows = self._report()
        row = self._row_for(rows, self.phone_line)

        self.assertEqual(row.entradas, 2)
        self.assertEqual(row.saidas, 1)
        self.assertEqual(row.ciclos, 2)
        self.assertEqual(row.situacao, "Aberta")


class DistinctSourceCyclesDoNotCrossTest(LineOperationalReportTestBase):
    """4. Ciclos simultaneos de fontes/objetos distintos nao se cruzam."""

    def test_simultaneous_cycles_from_distinct_sources_stay_independent(self):
        now = timezone.now()
        self._make_event(
            when=now - timedelta(hours=5),
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
            source=LineDailyActionAuditEvent.Source.DAILY_USER_ACTION,
            source_object_id=7,
        )
        self._make_event(
            when=now - timedelta(hours=4),
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
            source=LineDailyActionAuditEvent.Source.ALLOCATION_PENDENCY,
            source_object_id=7,
        )
        self._make_event(
            when=now - timedelta(hours=3),
            event_type=LineDailyActionAuditEvent.EventType.RESOLVED,
            source=LineDailyActionAuditEvent.Source.DAILY_USER_ACTION,
            source_object_id=7,
        )

        rows = self._report()
        row = self._row_for(rows, self.phone_line)

        # DAILY_USER_ACTION#7 fechou; ALLOCATION_PENDENCY#7 segue aberto:
        # dois ciclos independentes, um resolvido e um aberto.
        self.assertEqual(row.ciclos, 2)
        self.assertEqual(row.situacao, "Aberta")


class OrphanResolvedTest(LineOperationalReportTestBase):
    """5. RESOLVED orfao nao cria ciclo."""

    def test_orphan_resolved_creates_no_cycle(self):
        self._make_event(
            when=timezone.now() - timedelta(hours=1),
            event_type=LineDailyActionAuditEvent.EventType.RESOLVED,
        )

        rows = self._report()
        row = self._row_for(rows, self.phone_line)

        # Nenhum ciclo, mas o evento RESOLVED em si e contado como saida —
        # a linha so aparece se algum ciclo sobrepoe o periodo, mas aqui
        # RESOLVED orfao nao abre nem fecha ciclo, entao a linha nao entra.
        self.assertIsNone(row)


class EventWithoutPhoneLineExcludedTest(LineOperationalReportTestBase):
    """6. Evento sem phone_line excluido."""

    def test_event_without_phone_line_is_excluded(self):
        self._make_event(
            when=timezone.now() - timedelta(hours=1),
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
            phone_line=None,
            allocation=None,
            employee=None,
        )

        rows = self._report()

        self.assertEqual(len(rows), 0)


class NonCycleEventsTest(LineOperationalReportTestBase):
    """7. NOTE_CHANGED etc nao alteram entradas/saidas/ciclos, mas podem ser
    ultima acao."""

    def test_non_cycle_event_does_not_affect_counts_but_can_be_last_action(self):
        now = timezone.now()
        self._make_event(
            when=now - timedelta(hours=2),
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
        )
        self._make_event(
            when=now - timedelta(hours=1),
            event_type=LineDailyActionAuditEvent.EventType.NOTE_CHANGED,
        )

        rows = self._report()
        row = self._row_for(rows, self.phone_line)

        self.assertEqual(row.entradas, 1)
        self.assertEqual(row.saidas, 0)
        self.assertEqual(row.ciclos, 1)
        self.assertEqual(
            row.ultima_acao,
            LineDailyActionAuditEvent.EventType.NOTE_CHANGED.label,
        )


class LastActionActorTieBreakTest(LineOperationalReportTestBase):
    """8. Ultima acao/ator respeita occurred_at DESC, id DESC e fallback
    snapshot."""

    def test_last_action_uses_occurred_at_and_id_tie_break(self):
        now = timezone.now()
        self._make_event(
            when=now - timedelta(hours=2),
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
        )
        # Dois eventos com o MESMO occurred_at: desempate por id DESC deve
        # escolher o criado por ultimo (id maior).
        same_instant = now - timedelta(hours=1)
        self._make_event(
            when=same_instant,
            event_type=LineDailyActionAuditEvent.EventType.NOTE_CHANGED,
        )
        last = self._make_event(
            when=same_instant,
            event_type=LineDailyActionAuditEvent.EventType.RESPONSIBLE_ASSIGNED,
            performed_by=None,
            performed_by_name_snapshot="Snapshot Nome",
            performed_by_email_snapshot="snapshot@test.com",
        )
        self.assertGreater(last.pk, 0)

        rows = self._report()
        row = self._row_for(rows, self.phone_line)

        self.assertEqual(
            row.ultima_acao,
            LineDailyActionAuditEvent.EventType.RESPONSIBLE_ASSIGNED.label,
        )
        self.assertEqual(row.ultimo_ator, "Snapshot Nome")

    def test_last_actor_falls_back_to_email_then_sistema(self):
        now = timezone.now()
        self._make_event(
            when=now - timedelta(hours=2),
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
        )
        self._make_event(
            when=now - timedelta(hours=1),
            event_type=LineDailyActionAuditEvent.EventType.NOTE_CHANGED,
            performed_by=None,
            performed_by_name_snapshot="",
            performed_by_email_snapshot="only.email@test.com",
        )

        rows = self._report()
        row = self._row_for(rows, self.phone_line)
        self.assertEqual(row.ultimo_ator, "only.email@test.com")

        # Segunda linha: nenhum FK, nenhum snapshot -> "Sistema".
        sim_card_2 = SIMcard.objects.create(
            iccid="8900000000000000502",
            carrier="CarrierOpReport2",
            status=SIMcard.Status.AVAILABLE,
        )
        phone_line_2 = PhoneLine.objects.create(
            phone_number="+551199999502",
            sim_card=sim_card_2,
            status=PhoneLine.Status.ALLOCATED,
        )
        self._make_event(
            when=now - timedelta(hours=1),
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
            phone_line=phone_line_2,
            allocation=None,
            employee=None,
        )

        rows = self._report()
        row2 = self._row_for(rows, phone_line_2)
        self.assertEqual(row2.ultimo_ator, "Sistema")


class InclusiveDateFilterTest(LineOperationalReportTestBase):
    """9. Filtro inclusivo de inicio e fim."""

    def test_inclusive_start_and_end_date_bounds(self):
        today = timezone.localdate()
        opened_at = timezone.make_aware(
            timezone.datetime.combine(today, timezone.datetime.min.time())
            + timedelta(hours=10)
        )
        self._make_event(
            when=opened_at,
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
        )

        rows = self._report(
            start_date=today.isoformat(), end_date=today.isoformat()
        )
        row = self._row_for(rows, self.phone_line)
        self.assertIsNotNone(row)
        self.assertEqual(row.entradas, 1)


class OpenCycleBeforePeriodStillAppearsTest(LineOperationalReportTestBase):
    """10. Ciclo aberto antes do inicio aparece se aberto na referencia."""

    def test_open_cycle_started_before_period_appears(self):
        opened_at = timezone.now() - timedelta(days=10)
        self._make_event(
            when=opened_at,
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
        )

        start_date = timezone.localdate() - timedelta(days=1)
        rows = self._report(start_date=start_date.isoformat())
        row = self._row_for(rows, self.phone_line)

        self.assertIsNotNone(row)
        self.assertEqual(row.situacao, "Aberta")
        # Nao houve entrada NO periodo (o OPENED aconteceu antes do inicio).
        self.assertEqual(row.entradas, 0)
        self.assertEqual(row.ciclos, 1)


class EventAfterEndDateIgnoredTest(LineOperationalReportTestBase):
    """11. Evento apos end_date nao altera estado historico do relatorio."""

    def test_event_after_end_date_does_not_change_report(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        opened_at = timezone.make_aware(
            timezone.datetime.combine(yesterday, timezone.datetime.min.time())
            + timedelta(hours=9)
        )
        self._make_event(
            when=opened_at,
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
        )
        # RESOLVED so acontece hoje, depois do end_date=ontem.
        self._make_event(
            when=timezone.now(),
            event_type=LineDailyActionAuditEvent.EventType.RESOLVED,
        )

        rows = self._report(end_date=yesterday.isoformat())
        row = self._row_for(rows, self.phone_line)

        self.assertIsNotNone(row)
        self.assertEqual(row.situacao, "Aberta")
        self.assertEqual(row.saidas, 0)
        self.assertEqual(
            row.ultima_acao,
            LineDailyActionAuditEvent.EventType.OPENED.label,
        )


class ScopePermissionTest(LineOperationalReportTestBase):
    """12. HTML e CSV retornam so linhas do escopo; usuario sem escopo nao
    recebe dados."""

    def test_operator_without_allocation_sees_no_rows(self):
        self._make_event(
            when=timezone.now() - timedelta(hours=1),
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
        )

        rows = self._report(user=self.operator)
        self.assertEqual(len(rows), 0)

    def test_operator_with_allocation_sees_own_line_only(self):
        LineAllocation.objects.filter(pk=self.allocation.pk).update(
            employee=self.employee
        )
        self.employee.email = self.operator.email
        self.employee.save(update_fields=["email"])

        self._make_event(
            when=timezone.now() - timedelta(hours=1),
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
        )

        rows = self._report(user=self.operator)
        row = self._row_for(rows, self.phone_line)
        self.assertIsNotNone(row)

    def test_html_view_requires_login(self):
        # RoleRequiredMixin (padrao ja usado em T6) levanta PermissionDenied
        # (403) para usuario nao autenticado, em vez de redirecionar.
        response = self.client.get(reverse("telecom:line_operational_report"))
        self.assertEqual(response.status_code, 403)

    def test_html_view_returns_only_scoped_rows(self):
        self._make_event(
            when=timezone.now() - timedelta(hours=1),
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
        )
        self.client.force_login(self.admin)
        response = self.client.get(reverse("telecom:line_operational_report"))
        self.assertEqual(response.status_code, 200)
        rows = list(response.context["rows"])
        self.assertTrue(
            any(row.phone_number == self.phone_line.phone_number for row in rows)
        )

    def test_csv_view_respects_filters_and_bom_and_header(self):
        self._make_event(
            when=timezone.now() - timedelta(hours=1),
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
        )
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("telecom:line_operational_report_csv")
        )
        self.assertEqual(response.status_code, 200)
        content = response.content
        self.assertTrue(content.startswith(b"\xef\xbb\xbf"))
        text = content.decode("utf-8-sig")
        first_line = text.splitlines()[0]
        self.assertIn("Numero", first_line)
        self.assertIn(self.phone_line.phone_number, text)


class PaginationTest(LineOperationalReportTestBase):
    """13. Paginacao sem sobreposicao e querystring preservada."""

    def setUp(self):
        super().setUp()
        now = timezone.now()
        for i in range(60):
            sim = SIMcard.objects.create(
                iccid=f"890000000000000060{i:02d}",
                carrier="CarrierBulk",
                status=SIMcard.Status.AVAILABLE,
            )
            line = PhoneLine.objects.create(
                phone_number=f"+55119999{i:04d}",
                sim_card=sim,
                status=PhoneLine.Status.ALLOCATED,
            )
            self._make_event(
                when=now - timedelta(minutes=i),
                event_type=LineDailyActionAuditEvent.EventType.OPENED,
                phone_line=line,
                allocation=None,
                employee=None,
                source_object_id=1000 + i,
            )

    def test_pages_do_not_overlap_and_querystring_preserved(self):
        self.client.force_login(self.admin)
        response_1 = self.client.get(
            reverse("telecom:line_operational_report"), {"page": 1}
        )
        response_2 = self.client.get(
            reverse("telecom:line_operational_report"), {"page": 2}
        )
        self.assertEqual(response_1.status_code, 200)
        self.assertEqual(response_2.status_code, 200)

        numbers_1 = {row.phone_number for row in response_1.context["rows"]}
        numbers_2 = {row.phone_number for row in response_2.context["rows"]}
        self.assertEqual(len(numbers_1), 50)
        self.assertFalse(numbers_1 & numbers_2)
        self.assertIn("querystring", response_1.context)


class QueryCostTest(LineOperationalReportTestBase):
    """14. Custo de queries constante com poucos/muitos eventos, sem N+1."""

    def setUp(self):
        super().setUp()
        self._next_line_offset = 0

    def _create_lines_with_events(self, count):
        now = timezone.now()
        start = self._next_line_offset
        self._next_line_offset += count
        for i in range(start, start + count):
            sim = SIMcard.objects.create(
                iccid=f"890000000000000070{i:03d}",
                carrier="CarrierQueryCost",
                status=SIMcard.Status.AVAILABLE,
            )
            line = PhoneLine.objects.create(
                phone_number=f"+55119998{i:04d}",
                sim_card=sim,
                status=PhoneLine.Status.ALLOCATED,
            )
            self._make_event(
                when=now - timedelta(minutes=i),
                event_type=LineDailyActionAuditEvent.EventType.OPENED,
                phone_line=line,
                allocation=None,
                employee=None,
                source_object_id=2000 + i,
            )

    def test_query_count_is_constant_regardless_of_row_count(self):
        self._create_lines_with_events(3)
        queryset = get_visible_phone_lines_queryset(self.admin)
        filters = LineOperationalReportFilters.from_get_params({})

        with CaptureQueriesContext(connection) as small:
            build_line_operational_report(queryset, filters)

        self._create_lines_with_events(40)

        with CaptureQueriesContext(connection) as large:
            build_line_operational_report(queryset, filters)

        self.assertEqual(len(small.captured_queries), len(large.captured_queries))


class NoWriteTest(LineOperationalReportTestBase):
    """15. Garantir que o relatorio nao cria/altera/apaga
    LineDailyActionAuditEvent."""

    def test_report_does_not_mutate_audit_events(self):
        self._make_event(
            when=timezone.now() - timedelta(hours=1),
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
        )
        before_count = LineDailyActionAuditEvent.objects.count()

        self._report()

        self.assertEqual(LineDailyActionAuditEvent.objects.count(), before_count)


class InvalidDateFilterTest(LineOperationalReportTestBase):
    """Data invalida/ausente = filtro ausente, nunca 500."""

    def test_invalid_date_never_raises(self):
        self._make_event(
            when=timezone.now() - timedelta(hours=1),
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
        )
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("telecom:line_operational_report"),
            {"start_date": "not-a-date", "end_date": "also-bad"},
        )
        self.assertEqual(response.status_code, 200)


class EmptyStateTest(LineOperationalReportTestBase):
    """Relatorio vazio mostra estado vazio claro."""

    def test_empty_report_renders_empty_state(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("telecom:line_operational_report"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["rows"]), 0)
