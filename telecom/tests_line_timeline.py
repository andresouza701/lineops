"""
Testes da timeline unificada de linha (T6): consulta que mistura
PhoneLineHistory (legado) e LineDailyActionAuditEvent (novo), paginada no
banco, escopada por permissao e com filtros de periodo/tipo/ator/alocacao.

Modulo separado de telecom/tests.py (que ja tem 5000+ linhas) seguindo o
padrao de dashboard/tests/test_*.py. Descoberto por
``manage.py test telecom`` porque o nome comeca com ``test`` (pattern padrao
do DiscoverRunner) — sem criar um pacote ``telecom/tests/`` (telecom so tem
``tests.py``; criar um pacote junto quebraria a descoberta por app label,
como ja documentado para o app dashboard).
"""

import json
from datetime import timedelta

from django.db import transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from allocations.models import LineAllocation
from employees.models import Employee
from telecom.line_timeline import (
    LineTimelineFilters,
    get_line_timeline_filter_options,
    get_line_timeline_page,
    has_line_activity,
)
from telecom.models import LineDailyActionAuditEvent, PhoneLine, PhoneLineHistory, SIMcard
from users.models import SystemUser

_UNSET = object()


class LineTimelineTestBase(TestCase):
    """Fixtures compartilhadas: uma linha visivel ao admin, com alocacao."""

    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="timeline.admin@test.com",
            password="123456",
            role=SystemUser.Role.ADMIN,
        )
        self.other_admin = SystemUser.objects.create_user(
            email="timeline.other.admin@test.com",
            password="123456",
            role=SystemUser.Role.ADMIN,
        )
        self.employee = Employee.objects.create(
            full_name="Timeline Employee",
            corporate_email="timeline.super@corp.com",
            employee_id="EMPTL1",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        self.sim_card = SIMcard.objects.create(
            iccid="8900000000000000401",
            carrier="CarrierTimeline",
            status=SIMcard.Status.AVAILABLE,
        )
        self.phone_line = PhoneLine.objects.create(
            phone_number="+551199999401",
            sim_card=self.sim_card,
            status=PhoneLine.Status.ALLOCATED,
        )
        self.allocation = LineAllocation.objects.create(
            employee=self.employee,
            phone_line=self.phone_line,
            allocated_by=self.admin,
            is_active=True,
        )
        # PhoneLine/LineAllocation emitem PhoneLineHistory via signals
        # (CREATED, ALLOCATED) so a fixture nao fica "limpa": isso ja tem
        # cobertura propria em telecom/tests.py. Aqui a timeline e testada
        # a partir de um estado conhecido e deterministico.
        PhoneLineHistory.objects.filter(phone_line=self.phone_line).delete()

    def _audit_state(self, **overrides):
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

    def _make_legacy(self, *, when, action=PhoneLineHistory.ActionType.STATUS_CHANGED,
                      changed_by=None, old_value="A", new_value="B", description="",
                      phone_line=None):
        history = PhoneLineHistory.objects.create(
            phone_line=phone_line or self.phone_line,
            action=action,
            old_value=old_value,
            new_value=new_value,
            changed_by=changed_by,
            description=description,
        )
        # changed_at usa auto_now_add; forcamos o timestamp de negocio desejado
        # via update() direto na tabela (nao passa pelo guard de imutabilidade,
        # que e do LineDailyActionAuditEvent, nao do PhoneLineHistory).
        PhoneLineHistory.objects.filter(pk=history.pk).update(changed_at=when)
        history.refresh_from_db()
        return history

    def _make_audit(self, *, when, event_type, source, performed_by=None,
                     allocation=_UNSET, employee=_UNSET, phone_line=_UNSET,
                     source_object_id=1, before=None, after=None,
                     allocation_id_snapshot=None, performed_by_name_snapshot="",
                     performed_by_email_snapshot=""):
        before = before if before is not None else self._audit_state()
        after = after if after is not None else self._audit_state(note="mudou")
        allocation = self.allocation if allocation is _UNSET else allocation
        employee = self.employee if employee is _UNSET else employee
        target_line = self.phone_line if phone_line is _UNSET else phone_line
        return LineDailyActionAuditEvent.objects.create(
            phone_line=target_line,
            allocation=allocation,
            employee=employee,
            performed_by=performed_by,
            event_type=event_type,
            source=source,
            source_object_id=source_object_id,
            occurred_at=when,
            allocation_id_snapshot=allocation_id_snapshot
            if allocation_id_snapshot is not None
            else (allocation.pk if allocation else None),
            performed_by_name_snapshot=performed_by_name_snapshot,
            performed_by_email_snapshot=performed_by_email_snapshot,
            before_state=before,
            after_state=after,
        )


class LineTimelineMixingTest(LineTimelineTestBase):
    """1. Timeline mistura PhoneLineHistory + as 3 fontes auditaveis, fonte
    identificada, ordenada globalmente por occurred_at desc."""

    def test_mixes_all_sources_identified_and_globally_ordered(self):
        now = timezone.now()
        legacy = self._make_legacy(when=now - timedelta(minutes=1), changed_by=self.admin)
        daily = self._make_audit(
            when=now - timedelta(minutes=2),
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
            source=LineDailyActionAuditEvent.Source.DAILY_USER_ACTION,
            performed_by=self.admin,
        )
        pendency = self._make_audit(
            when=now - timedelta(minutes=3),
            event_type=LineDailyActionAuditEvent.EventType.RESPONSIBLE_ASSIGNED,
            source=LineDailyActionAuditEvent.Source.ALLOCATION_PENDENCY,
            performed_by=self.admin,
        )
        line_status = self._make_audit(
            when=now,
            event_type=LineDailyActionAuditEvent.EventType.LINE_STATUS_CHANGED,
            source=LineDailyActionAuditEvent.Source.LINE_ALLOCATION,
            performed_by=self.admin,
        )

        page = get_line_timeline_page(self.phone_line, LineTimelineFilters())

        self.assertEqual(len(page.items), 4)
        sources = [item.source for item in page.items]
        self.assertEqual(
            sources,
            [
                LineDailyActionAuditEvent.Source.LINE_ALLOCATION,
                "PHONE_LINE_HISTORY",
                LineDailyActionAuditEvent.Source.DAILY_USER_ACTION,
                LineDailyActionAuditEvent.Source.ALLOCATION_PENDENCY,
            ],
        )
        occurred_ats = [item.occurred_at for item in page.items]
        self.assertEqual(occurred_ats, sorted(occurred_ats, reverse=True))


class LineTimelinePresentationTest(LineTimelineTestBase):
    def test_source_state_changes_are_not_shown_as_user_facing_changes(self):
        self._make_audit(
            when=timezone.now(),
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
            source=LineDailyActionAuditEvent.Source.ALLOCATION_PENDENCY,
            before=self._audit_state(),
            after=self._audit_state(
                source_state={
                    "day": "2026-09-14",
                    "pendency_submitted_at": "2026-09-14T12:00:00+00:00",
                    "last_submitted_action": {
                        "code": "reconnect_whatsapp",
                        "label": "Reconectar WhatsApp",
                    },
                    "is_resolved": False,
                }
            ),
        )

        item = get_line_timeline_page(
            self.phone_line, LineTimelineFilters()
        ).items[0]

        self.assertEqual(item.changes, [])

    def test_audit_event_exposes_changed_fields_with_human_labels(self):
        before = self._audit_state()
        after = self._audit_state(
            action={"code": "reconnect_whatsapp", "label": "Reconectar WhatsApp"},
            note="Trocar aparelho",
            line_status={"code": "under_analysis", "label": "Em análise"},
            technical_responsible={
                "id": self.admin.pk,
                "name": self.admin.email,
                "email": self.admin.email,
            },
        )
        self._make_audit(
            when=timezone.now(),
            event_type=LineDailyActionAuditEvent.EventType.ACTION_CHANGED,
            source=LineDailyActionAuditEvent.Source.ALLOCATION_PENDENCY,
            before=before,
            after=after,
        )

        item = get_line_timeline_page(
            self.phone_line, LineTimelineFilters()
        ).items[0]
        changes = {change.label: (change.before_value, change.after_value) for change in item.changes}

        self.assertEqual(changes["Ação"], ("Sem Acao", "Reconectar WhatsApp"))
        self.assertEqual(changes["Nota"], ("Sem nota", "Trocar aparelho"))
        self.assertEqual(changes["Status da linha"], ("Ativa", "Em análise"))
        self.assertEqual(changes["Responsável técnico"], ("Não atribuído", self.admin.email))

    def test_history_page_renders_changes_without_technical_json(self):
        self._make_audit(
            when=timezone.now(),
            event_type=LineDailyActionAuditEvent.EventType.NOTE_CHANGED,
            source=LineDailyActionAuditEvent.Source.ALLOCATION_PENDENCY,
        )
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("telecom:phoneline_history", args=[self.phone_line.pk])
        )

        self.assertContains(response, "Alterações")
        self.assertContains(response, "Nota")
        self.assertContains(response, "Responsável")
        self.assertNotContains(response, "Ver JSON técnico")
        self.assertNotContains(response, "Detalhes técnicos")


class LineTimelinePaginationTest(LineTimelineTestBase):
    """2. Paginacao no banco: > 50 itens entre fontes, pagina 1 e 2 sem
    sobreposicao, ordenacao estavel."""

    def setUp(self):
        super().setUp()
        now = timezone.now()
        for i in range(30):
            self._make_legacy(when=now - timedelta(minutes=i), changed_by=self.admin)
        for i in range(30):
            self._make_audit(
                when=now - timedelta(minutes=i, seconds=30),
                event_type=LineDailyActionAuditEvent.EventType.NOTE_CHANGED,
                source=LineDailyActionAuditEvent.Source.DAILY_USER_ACTION,
                performed_by=self.admin,
                source_object_id=i + 1,
            )

    def test_pages_do_not_overlap_and_stay_ordered(self):
        filters_p1 = LineTimelineFilters(page=1)
        filters_p2 = LineTimelineFilters(page=2)

        page1 = get_line_timeline_page(self.phone_line, filters_p1)
        page2 = get_line_timeline_page(self.phone_line, filters_p2)

        self.assertEqual(page1.page_obj.paginator.count, 60)
        self.assertEqual(len(page1.items), 50)
        self.assertEqual(len(page2.items), 10)

        key1 = {(item.source, item.occurred_at) for item in page1.items}
        key2 = {(item.source, item.occurred_at) for item in page2.items}
        self.assertEqual(key1 & key2, set())

        all_occurred = [item.occurred_at for item in page1.items + page2.items]
        self.assertEqual(all_occurred, sorted(all_occurred, reverse=True))

    def test_pagination_is_database_driven_not_full_materialization(self):
        # A pagina 1 nao pode disparar mais queries que a pagina 2, mesmo com
        # o mesmo volume total de dados: se a implementacao paginasse uma
        # lista python completa, o custo cresceria com o dataset, nao com a
        # pagina pedida.
        with self.assertNumQueries(4):
            get_line_timeline_page(self.phone_line, LineTimelineFilters(page=1))
        with self.assertNumQueries(4):
            get_line_timeline_page(self.phone_line, LineTimelineFilters(page=2))


class LineTimelineScopeTest(LineTimelineTestBase):
    """3. Escopo: usuario com acesso -> 200; sem escopo -> 404; eventos de
    outra linha nunca aparecem."""

    def setUp(self):
        super().setUp()
        self.operator = SystemUser.objects.create_user(
            email="timeline.operator@test.com",
            password="123456",
            role=SystemUser.Role.OPERATOR,
        )
        self.other_sim = SIMcard.objects.create(
            iccid="8900000000000000402",
            carrier="CarrierTimeline2",
            status=SIMcard.Status.AVAILABLE,
        )
        self.other_line = PhoneLine.objects.create(
            phone_number="+551199999402",
            sim_card=self.other_sim,
            status=PhoneLine.Status.AVAILABLE,
        )

    def test_user_with_access_gets_200(self):
        self.client.force_login(self.admin)
        resp = self.client.get(
            reverse("telecom:phoneline_history", args=[self.phone_line.pk])
        )
        self.assertEqual(resp.status_code, 200)

    def test_user_without_scope_gets_404(self):
        self.client.force_login(self.operator)
        resp = self.client.get(
            reverse("telecom:phoneline_history", args=[self.phone_line.pk])
        )
        self.assertEqual(resp.status_code, 404)

    def test_events_from_other_line_never_appear(self):
        now = timezone.now()
        self._make_legacy(when=now, phone_line=self.other_line, changed_by=self.admin)
        self._make_audit(
            when=now,
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
            source=LineDailyActionAuditEvent.Source.DAILY_USER_ACTION,
            performed_by=self.admin,
            phone_line=self.other_line,
            allocation=None,
            employee=None,
        )

        page = get_line_timeline_page(self.phone_line, LineTimelineFilters())
        self.assertEqual(page.items, [])


class LineTimelineFiltersTest(LineTimelineTestBase):
    """4. Filtros: periodo inclusivo, tipo, ator (legado e auditoria),
    alocacao so retorna evento novo e exclui legado, filtro invalido/de
    outra linha nao vaza."""

    def test_start_and_end_date_are_inclusive(self):
        day = timezone.now().replace(hour=12, minute=0, second=0, microsecond=0)
        in_range = self._make_legacy(when=day, changed_by=self.admin)
        before_range = self._make_legacy(
            when=day - timedelta(days=2), changed_by=self.admin
        )
        after_range = self._make_legacy(
            when=day + timedelta(days=2), changed_by=self.admin
        )

        filters = LineTimelineFilters(
            start_date=day.date(), end_date=day.date()
        )
        page = get_line_timeline_page(self.phone_line, filters)
        ids = {item.occurred_at for item in page.items}
        self.assertIn(in_range.changed_at, ids)
        self.assertNotIn(before_range.changed_at, ids)
        self.assertNotIn(after_range.changed_at, ids)

    def test_event_type_filters_both_sources_independently(self):
        now = timezone.now()
        self._make_legacy(
            when=now, action=PhoneLineHistory.ActionType.CREATED, changed_by=self.admin
        )
        self._make_legacy(
            when=now, action=PhoneLineHistory.ActionType.DELETED, changed_by=self.admin
        )
        self._make_audit(
            when=now,
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
            source=LineDailyActionAuditEvent.Source.DAILY_USER_ACTION,
            performed_by=self.admin,
        )
        self._make_audit(
            when=now,
            event_type=LineDailyActionAuditEvent.EventType.RESOLVED,
            source=LineDailyActionAuditEvent.Source.DAILY_USER_ACTION,
            performed_by=self.admin,
        )

        page = get_line_timeline_page(
            self.phone_line,
            LineTimelineFilters(event_type=PhoneLineHistory.ActionType.CREATED),
        )
        self.assertEqual(len(page.items), 1)
        self.assertEqual(page.items[0].event_type, PhoneLineHistory.ActionType.CREATED)

        page = get_line_timeline_page(
            self.phone_line,
            LineTimelineFilters(event_type=LineDailyActionAuditEvent.EventType.OPENED),
        )
        self.assertEqual(len(page.items), 1)
        self.assertEqual(
            page.items[0].event_type, LineDailyActionAuditEvent.EventType.OPENED
        )

    def test_actor_filter_applies_to_legacy_changed_by_and_audit_performed_by(self):
        now = timezone.now()
        self._make_legacy(when=now, changed_by=self.admin)
        self._make_legacy(when=now, changed_by=self.other_admin)
        self._make_audit(
            when=now,
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
            source=LineDailyActionAuditEvent.Source.DAILY_USER_ACTION,
            performed_by=self.admin,
        )
        self._make_audit(
            when=now,
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
            source=LineDailyActionAuditEvent.Source.DAILY_USER_ACTION,
            performed_by=self.other_admin,
        )

        page = get_line_timeline_page(
            self.phone_line, LineTimelineFilters(actor_id=self.admin.pk)
        )
        self.assertEqual(len(page.items), 2)
        for item in page.items:
            self.assertEqual(item.actor_label, self.admin.get_full_name().strip() or self.admin.email)

    def test_allocation_filter_returns_only_matching_new_event_and_excludes_legacy(self):
        now = timezone.now()
        other_allocation = LineAllocation.objects.create(
            employee=self.employee,
            phone_line=self.phone_line,
            allocated_by=self.admin,
            is_active=True,
        )
        LineAllocation.objects.filter(pk=other_allocation.pk).update(
            is_active=False, released_at=timezone.now()
        )
        other_allocation.refresh_from_db()
        self._make_legacy(when=now, changed_by=self.admin)
        matching = self._make_audit(
            when=now,
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
            source=LineDailyActionAuditEvent.Source.ALLOCATION_PENDENCY,
            performed_by=self.admin,
            allocation=self.allocation,
        )
        self._make_audit(
            when=now,
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
            source=LineDailyActionAuditEvent.Source.ALLOCATION_PENDENCY,
            performed_by=self.admin,
            allocation=other_allocation,
        )

        page = get_line_timeline_page(
            self.phone_line, LineTimelineFilters(allocation_id=self.allocation.pk)
        )
        self.assertEqual(len(page.items), 1)
        self.assertEqual(page.items[0].source, LineDailyActionAuditEvent.Source.ALLOCATION_PENDENCY)
        self.assertEqual(page.items[0].occurred_at, matching.occurred_at)

    def test_allocation_filter_from_other_line_never_leaks_data(self):
        now = timezone.now()
        other_sim = SIMcard.objects.create(
            iccid="8900000000000000403",
            carrier="CarrierTimeline3",
            status=SIMcard.Status.AVAILABLE,
        )
        other_line = PhoneLine.objects.create(
            phone_number="+551199999403",
            sim_card=other_sim,
            status=PhoneLine.Status.ALLOCATED,
        )
        other_allocation = LineAllocation.objects.create(
            employee=self.employee,
            phone_line=other_line,
            allocated_by=self.admin,
            is_active=True,
        )
        self._make_audit(
            when=now,
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
            source=LineDailyActionAuditEvent.Source.ALLOCATION_PENDENCY,
            performed_by=self.admin,
            allocation=self.allocation,
        )

        page = get_line_timeline_page(
            self.phone_line, LineTimelineFilters(allocation_id=other_allocation.pk)
        )
        self.assertEqual(page.items, [])

    def test_invalid_allocation_id_does_not_crash_or_leak(self):
        filters = LineTimelineFilters.from_get_params({"allocation_id": "not-a-number"})
        self.assertIsNone(filters.allocation_id)
        page = get_line_timeline_page(self.phone_line, filters)
        self.assertEqual(page.items, [])


class LineTimelineNoLineTest(LineTimelineTestBase):
    """5. Evento auditavel sem phone_line nunca aparece em timeline nenhuma."""

    def test_event_without_phone_line_never_appears(self):
        self._make_audit(
            when=timezone.now(),
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
            source=LineDailyActionAuditEvent.Source.DAILY_USER_ACTION,
            performed_by=self.admin,
            phone_line=None,
            allocation=None,
            employee=None,
        )
        page = get_line_timeline_page(self.phone_line, LineTimelineFilters())
        self.assertEqual(page.items, [])


class LineTimelineCompatibilityTest(LineTimelineTestBase):
    """6. Item legado continua exibindo acao/valores/descricao; item
    auditavel mostra source/ator snapshot/before-after; PhoneLineHistory
    original permanece intacto."""

    def test_legacy_item_shows_action_values_and_description(self):
        legacy = self._make_legacy(
            when=timezone.now(),
            action=PhoneLineHistory.ActionType.STATUS_CHANGED,
            changed_by=self.admin,
            old_value="Disponivel",
            new_value="Alocado",
            description="Linha alocada",
        )

        page = get_line_timeline_page(self.phone_line, LineTimelineFilters())
        item = page.items[0]

        self.assertEqual(item.source, "PHONE_LINE_HISTORY")
        self.assertEqual(item.event_type, PhoneLineHistory.ActionType.STATUS_CHANGED)
        self.assertEqual(item.before_display, "Disponivel")
        self.assertEqual(item.after_display, "Alocado")
        self.assertEqual(item.details, "Linha alocada")

        legacy.refresh_from_db()
        self.assertEqual(legacy.old_value, "Disponivel")
        self.assertEqual(legacy.new_value, "Alocado")
        self.assertEqual(legacy.description, "Linha alocada")

    def test_audit_item_shows_source_actor_snapshot_and_before_after(self):
        self._make_audit(
            when=timezone.now(),
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
            source=LineDailyActionAuditEvent.Source.ALLOCATION_PENDENCY,
            performed_by=None,
            performed_by_name_snapshot="Ana Removida",
            performed_by_email_snapshot="ana.removida@corp.com",
            before=self._audit_state(note=""),
            after=self._audit_state(note="pendencia aberta"),
        )

        page = get_line_timeline_page(self.phone_line, LineTimelineFilters())
        item = page.items[0]

        self.assertEqual(item.source, LineDailyActionAuditEvent.Source.ALLOCATION_PENDENCY)
        self.assertEqual(item.actor_label, "Ana Removida")
        self.assertIn('"note": ""', item.before_display)
        self.assertIn('"note": "pendencia aberta"', item.after_display)

    def test_actor_falls_back_to_email_snapshot_then_sistema(self):
        self._make_audit(
            when=timezone.now(),
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
            source=LineDailyActionAuditEvent.Source.ALLOCATION_PENDENCY,
            performed_by=None,
            performed_by_name_snapshot="",
            performed_by_email_snapshot="only.email@corp.com",
        )
        self._make_audit(
            when=timezone.now(),
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
            source=LineDailyActionAuditEvent.Source.ALLOCATION_PENDENCY,
            performed_by=None,
            performed_by_name_snapshot="",
            performed_by_email_snapshot="",
        )

        page = get_line_timeline_page(self.phone_line, LineTimelineFilters())
        labels = {item.actor_label for item in page.items}
        self.assertIn("only.email@corp.com", labels)
        self.assertIn("Sistema", labels)


class LineTimelineNPlusOneTest(LineTimelineTestBase):
    """7. Sem N+1: multiplos eventos de ambas as fontes e atores, quantidade
    de queries constante ao renderizar a timeline."""

    def _seed(self, count):
        now = timezone.now()
        for i in range(count):
            self._make_legacy(when=now - timedelta(minutes=i), changed_by=self.admin)
            self._make_audit(
                when=now - timedelta(minutes=i, seconds=15),
                event_type=LineDailyActionAuditEvent.EventType.NOTE_CHANGED,
                source=LineDailyActionAuditEvent.Source.DAILY_USER_ACTION,
                performed_by=self.other_admin,
                source_object_id=i + 1,
            )

    def test_query_count_is_constant_regardless_of_rendered_item_count(self):
        self.client.force_login(self.admin)
        url = reverse("telecom:phoneline_history", args=[self.phone_line.pk])

        # Numero exato nao importa (auth/sessao/RoleRequiredMixin somam
        # queries fixas); o que prova ausencia de N+1 e o MESMO numero se
        # repetir com 4x mais itens de origem, provando que o custo nao
        # escala com o volume total de dados nem com o template.
        self._seed(5)
        with self.assertNumQueries(13):
            small_resp = self.client.get(url)
        self.assertEqual(small_resp.status_code, 200)

        self._seed(20)
        with self.assertNumQueries(13):
            big_resp = self.client.get(url)
        self.assertEqual(big_resp.status_code, 200)


class LineTimelineUITest(LineTimelineTestBase):
    """8. Resposta possui fontes, filtros, eventos das duas tabelas e
    paginacao com querystring preservada."""

    def setUp(self):
        super().setUp()
        now = timezone.now()
        self._make_legacy(when=now, changed_by=self.admin)
        for i in range(55):
            self._make_audit(
                when=now - timedelta(minutes=i + 1),
                event_type=LineDailyActionAuditEvent.EventType.NOTE_CHANGED,
                source=LineDailyActionAuditEvent.Source.DAILY_USER_ACTION,
                performed_by=self.admin,
                source_object_id=i + 1,
            )

    def test_response_shows_sources_filters_events_and_paginated_querystring(self):
        self.client.force_login(self.admin)
        url = reverse("telecom:phoneline_history", args=[self.phone_line.pk])

        resp = self.client.get(url, {"event_type": PhoneLineHistory.ActionType.STATUS_CHANGED})

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Histórico da linha")
        self.assertContains(resp, "start_date")
        self.assertContains(resp, "end_date")
        self.assertContains(resp, "event_type")
        self.assertContains(resp, "actor_id")
        self.assertContains(resp, ">Responsável<", html=False)
        self.assertNotContains(resp, ">Ator<", html=False)
        self.assertContains(resp, "allocation_id")
        self.assertIn("timeline_items", resp.context)
        self.assertIn("page_obj", resp.context)
        # Filtro aplicado continua marcado como selecionado no form.
        self.assertContains(
            resp,
            f'<option value="{PhoneLineHistory.ActionType.STATUS_CHANGED}" selected>',
        )

        # 56 itens no total (setUp) + o filtro por ator ainda deixa > 50,
        # entao a paginacao aparece e o link da pagina 2 preserva o filtro.
        paged_resp = self.client.get(url, {"actor_id": self.admin.pk})
        self.assertContains(paged_resp, "page=2")
        self.assertContains(paged_resp, f"actor_id={self.admin.pk}&page=2")

    def test_empty_state_distinguishes_no_activity_from_no_filtered_items(self):
        self.client.force_login(self.admin)

        other_sim = SIMcard.objects.create(
            iccid="8900000000000000404",
            carrier="CarrierTimeline4",
            status=SIMcard.Status.AVAILABLE,
        )
        empty_line = PhoneLine.objects.create(
            phone_number="+551199999404",
            sim_card=other_sim,
            status=PhoneLine.Status.AVAILABLE,
        )
        # A criacao da linha emite um evento CREATED via signal (comportamento
        # de producao legitimo). Para exercitar o estado "sem atividade
        # nenhuma" — alcancavel na pratica por dados legados sem esse
        # historico — removemos o unico fato que a linha teria.
        PhoneLineHistory.objects.filter(phone_line=empty_line).delete()
        resp = self.client.get(
            reverse("telecom:phoneline_history", args=[empty_line.pk])
        )
        self.assertFalse(has_line_activity(empty_line))
        self.assertContains(resp, "Nenhuma atividade")

        resp2 = self.client.get(
            reverse("telecom:phoneline_history", args=[self.phone_line.pk]),
            {"event_type": "NONEXISTENT_CODE"},
        )
        self.assertTrue(has_line_activity(self.phone_line))
        self.assertContains(resp2, "Nenhum item")
