"""
Correcoes P1/P2 da auditoria de Acoes do Dia:
- LINE_STATUS_CHANGED nao depende de existir DailyUserAction (source
  LINE_ALLOCATION, source_object_id = allocation.pk).
- Lock (select_for_update) da LineAllocation/Employee/DailyUserAction antes
  de montar snapshot ou decidir o tipo de evento.
"""
from unittest.mock import patch

from django.contrib.messages import get_messages
from django.db.models.query import QuerySet
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from allocations.models import LineAllocation
from dashboard.models import DailyUserAction
from employees.models import Employee
from telecom.models import (
    LineDailyActionAuditEvent,
    PhoneLine,
    PhoneLineHistory,
    SIMcard,
)
from users.models import SystemUser


class LineStatusSourceFixTest(TestCase):
    """Correcao 1: LINE_STATUS_CHANGED sempre usa source=LINE_ALLOCATION."""

    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="line.status.fix.admin@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.client.force_login(self.admin)
        self.employee = Employee.objects.create(
            full_name="Line Status Fix Employee",
            corporate_email="line.status.fix.super@test.com",
            employee_id="LSFIX1",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )
        self.sim = SIMcard.objects.create(
            iccid="8900000000000099901",
            carrier="CarrierLineStatusFix",
            status=SIMcard.Status.AVAILABLE,
        )
        self.phone_line = PhoneLine.objects.create(
            phone_number="+5511977777901",
            sim_card=self.sim,
            status=PhoneLine.Status.ALLOCATED,
        )
        self.allocation = LineAllocation.objects.create(
            employee=self.employee,
            phone_line=self.phone_line,
            allocated_by=self.admin,
            is_active=True,
        )
        self.url = reverse("daily_user_action_board")

    def _post(self, **overrides):
        data = {
            "day": timezone.localdate().isoformat(),
            "employee_id": self.employee.pk,
            "allocation_id": str(self.allocation.pk),
            "action_type": "",
            "note": "",
            "line_status": "",
        }
        data.update(overrides)
        return self.client.post(self.url, data=data)

    def _line_allocation_events(self):
        return LineDailyActionAuditEvent.objects.filter(
            source=LineDailyActionAuditEvent.Source.LINE_ALLOCATION
        ).order_by("id")

    def test_line_status_only_without_prior_daily_action_records_one_event(self):
        self.assertFalse(DailyUserAction.objects.filter(employee=self.employee).exists())

        response = self._post(line_status="restricted")
        self.assertEqual(response.status_code, 302)

        self.assertFalse(
            DailyUserAction.objects.filter(employee=self.employee).exists(),
            "POST so-com-line_status nao deve criar DailyUserAction.",
        )
        events = self._line_allocation_events()
        self.assertEqual(events.count(), 1)
        event = events.first()
        self.assertEqual(
            event.event_type, LineDailyActionAuditEvent.EventType.LINE_STATUS_CHANGED
        )
        self.assertEqual(event.source_object_id, self.allocation.pk)
        self.assertEqual(event.allocation_id, self.allocation.pk)
        self.assertEqual(event.phone_line_id, self.phone_line.pk)
        self.assertEqual(event.before_state["line_status"]["code"], "active")
        self.assertEqual(event.after_state["line_status"]["code"], "restricted")

        daily_user_action_events = LineDailyActionAuditEvent.objects.filter(
            source=LineDailyActionAuditEvent.Source.DAILY_USER_ACTION
        )
        self.assertEqual(daily_user_action_events.count(), 0)

    def test_new_action_with_line_status_records_line_status_then_opened(self):
        response = self._post(
            action_type=DailyUserAction.ActionType.PENDING,
            note="obs",
            line_status="restricted",
        )
        self.assertEqual(response.status_code, 302)

        action = DailyUserAction.objects.get(employee=self.employee)
        events = list(
            LineDailyActionAuditEvent.objects.filter(
                source_object_id__in=[self.allocation.pk, action.pk]
            ).order_by("id")
        )
        self.assertEqual(len(events), 2)

        line_status_event, opened_event = events
        self.assertEqual(
            line_status_event.event_type,
            LineDailyActionAuditEvent.EventType.LINE_STATUS_CHANGED,
        )
        self.assertEqual(
            line_status_event.source, LineDailyActionAuditEvent.Source.LINE_ALLOCATION
        )
        self.assertEqual(line_status_event.source_object_id, self.allocation.pk)

        self.assertEqual(opened_event.event_type, LineDailyActionAuditEvent.EventType.OPENED)
        self.assertEqual(
            opened_event.source, LineDailyActionAuditEvent.Source.DAILY_USER_ACTION
        )
        self.assertEqual(opened_event.source_object_id, action.pk)

        self.assertEqual(line_status_event.operation_id, opened_event.operation_id)

    def test_existing_action_with_line_status_records_only_line_status_changed(self):
        self._post(action_type=DailyUserAction.ActionType.PENDING, note="obs")
        action = DailyUserAction.objects.get(employee=self.employee)
        marker = LineDailyActionAuditEvent.objects.order_by("-id").first().pk

        response = self._post(
            action_type=DailyUserAction.ActionType.PENDING,
            note="obs",
            line_status="restricted",
        )
        self.assertEqual(response.status_code, 302)

        new_events = LineDailyActionAuditEvent.objects.filter(pk__gt=marker).order_by("id")
        self.assertEqual(new_events.count(), 1)
        event = new_events.first()
        self.assertEqual(
            event.event_type, LineDailyActionAuditEvent.EventType.LINE_STATUS_CHANGED
        )
        self.assertEqual(event.source, LineDailyActionAuditEvent.Source.LINE_ALLOCATION)
        self.assertEqual(event.source_object_id, self.allocation.pk)
        self.assertNotEqual(event.source, LineDailyActionAuditEvent.Source.DAILY_USER_ACTION)

    def test_employee_only_line_status_without_allocation_has_no_line_audit(self):
        """Status de Employee sem Allocation nao e auditoria de linha."""
        lone_employee = Employee.objects.create(
            full_name="Lone Employee",
            corporate_email="lone.employee.fix@test.com",
            employee_id="LSFIXLONE",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )
        response = self.client.post(
            self.url,
            data={
                "day": timezone.localdate().isoformat(),
                "employee_id": lone_employee.pk,
                "allocation_id": "",
                "action_type": "",
                "note": "",
                "line_status": "restricted",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(LineDailyActionAuditEvent.objects.count(), 0)


class DailyUserActionLockingTest(TestCase):
    """Correcao 3: lock antes de ler/decidir estado (contrato via spy,
    seguindo o padrao de PhoneLine.create_or_reuse — concorrencia real nao e
    confiavel em SQLite)."""

    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="lock.fix.admin@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.client.force_login(self.admin)
        self.employee = Employee.objects.create(
            full_name="Lock Fix Employee",
            corporate_email="lock.fix.super@test.com",
            employee_id="LOCKFIX1",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )
        self.sim = SIMcard.objects.create(
            iccid="8900000000000099902",
            carrier="CarrierLockFix",
            status=SIMcard.Status.AVAILABLE,
        )
        self.phone_line = PhoneLine.objects.create(
            phone_number="+5511977777902",
            sim_card=self.sim,
            status=PhoneLine.Status.ALLOCATED,
        )
        self.allocation = LineAllocation.objects.create(
            employee=self.employee,
            phone_line=self.phone_line,
            allocated_by=self.admin,
            is_active=True,
        )
        self.url = reverse("daily_user_action_board")

    def _post(self, **overrides):
        data = {
            "day": timezone.localdate().isoformat(),
            "employee_id": self.employee.pk,
            "allocation_id": str(self.allocation.pk),
            "action_type": "",
            "note": "",
            "line_status": "",
        }
        data.update(overrides)
        return self.client.post(self.url, data=data)

    def test_creating_action_with_allocation_locks_allocation_row(self):
        original = QuerySet.select_for_update
        with patch.object(
            QuerySet, "select_for_update", autospec=True, side_effect=original
        ) as spy:
            response = self._post(
                action_type=DailyUserAction.ActionType.PENDING, note="obs"
            )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(spy.called)
        self.assertTrue(DailyUserAction.objects.filter(employee=self.employee).exists())

    def test_creating_action_without_allocation_locks_employee_row(self):
        lone_employee = Employee.objects.create(
            full_name="Lock Fix Lone Employee",
            corporate_email="lock.fix.lone@test.com",
            employee_id="LOCKFIXLONE",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )
        original = QuerySet.select_for_update
        with patch.object(
            QuerySet, "select_for_update", autospec=True, side_effect=original
        ) as spy:
            response = self.client.post(
                self.url,
                data={
                    "day": timezone.localdate().isoformat(),
                    "employee_id": lone_employee.pk,
                    "allocation_id": "",
                    "action_type": DailyUserAction.ActionType.PENDING,
                    "note": "obs sem linha",
                    "line_status": "",
                },
            )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(spy.called)
        self.assertTrue(DailyUserAction.objects.filter(employee=lone_employee).exists())

    def test_resolving_action_locks_daily_user_action_row(self):
        self._post(action_type=DailyUserAction.ActionType.PENDING, note="obs")

        original = QuerySet.select_for_update
        with patch.object(
            QuerySet, "select_for_update", autospec=True, side_effect=original
        ) as spy:
            response = self._post(action_type="", note="resolvido")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(spy.called)
        action = DailyUserAction.objects.get(employee=self.employee)
        self.assertTrue(action.is_resolved)


class ResolveRaceConditionFixTest(TestCase):
    """P1: acao resolvida entre get_open_action_for_resolution() (sem lock)
    e o select_for_update() nao pode ser resolvida de novo (segundo RESOLVED
    fantasma). Corrida simulada de forma deterministica, sem threads: o
    patch de get_open_action_for_resolution resolve a acao "por fora" (via
    update direto, simulando outra requisicao/script concorrente) antes de
    devolver a candidata pra view."""

    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="resolve.race.admin@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.client.force_login(self.admin)
        self.employee = Employee.objects.create(
            full_name="Resolve Race Employee",
            corporate_email="resolve.race.super@test.com",
            employee_id="RACEFIX1",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )
        self.sim = SIMcard.objects.create(
            iccid="8900000000000099903",
            carrier="CarrierResolveRace",
            status=SIMcard.Status.AVAILABLE,
        )
        self.phone_line = PhoneLine.objects.create(
            phone_number="+5511977777903",
            sim_card=self.sim,
            status=PhoneLine.Status.ALLOCATED,
        )
        self.allocation = LineAllocation.objects.create(
            employee=self.employee,
            phone_line=self.phone_line,
            allocated_by=self.admin,
            is_active=True,
        )
        self.url = reverse("daily_user_action_board")

    def _post(self, **overrides):
        data = {
            "day": timezone.localdate().isoformat(),
            "employee_id": self.employee.pk,
            "allocation_id": str(self.allocation.pk),
            "action_type": "",
            "note": "",
            "line_status": "",
        }
        data.update(overrides)
        return self.client.post(self.url, data=data)

    def test_action_resolved_between_lookup_and_lock_is_not_resolved_twice(self):
        self._post(action_type=DailyUserAction.ActionType.PENDING, note="obs original")
        action = DailyUserAction.objects.get(employee=self.employee)
        self.assertFalse(action.is_resolved)

        events_before = LineDailyActionAuditEvent.objects.count()
        history_before = PhoneLineHistory.objects.filter(
            phone_line=self.phone_line,
            action=PhoneLineHistory.ActionType.DAILY_ACTION_CHANGED,
        ).count()

        def _race_and_return_stale_candidate(employee, allocation_id=None):
            # Simula outra requisicao (ou resolve_old_daily_user_actions())
            # resolvendo a mesma acao entre o lookup sem lock e o
            # select_for_update() da view — via update direto no banco,
            # sem tocar no objeto Python `action` capturado acima (que
            # continua com is_resolved=False em memoria, como o objeto real
            # que get_open_action_for_resolution() teria devolvido).
            DailyUserAction.objects.filter(pk=action.pk).update(is_resolved=True)
            return action

        with patch(
            "dashboard.views.get_open_action_for_resolution",
            side_effect=_race_and_return_stale_candidate,
        ):
            response = self._post(action_type="", note="tentativa apos corrida")

        self.assertEqual(response.status_code, 302)

        action.refresh_from_db()
        self.assertTrue(action.is_resolved)
        self.assertEqual(action.note, "obs original")

        self.assertEqual(LineDailyActionAuditEvent.objects.count(), events_before)
        self.assertEqual(
            LineDailyActionAuditEvent.objects.filter(
                event_type=LineDailyActionAuditEvent.EventType.RESOLVED
            ).count(),
            0,  # "outro processo" resolveu via update() direto: sem evento nenhum
        )
        self.assertEqual(
            PhoneLineHistory.objects.filter(
                phone_line=self.phone_line,
                action=PhoneLineHistory.ActionType.DAILY_ACTION_CHANGED,
            ).count(),
            history_before,
        )

        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertTrue(
            any("Nenhuma ação aberta para resolver" in m for m in messages)
        )
