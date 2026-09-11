import json

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from allocations.models import LineAllocation
from dashboard.models import DailyUserAction
from employees.models import Employee
from telecom.models import LineDailyActionAuditEvent, PhoneLine, PhoneLineHistory, SIMcard
from users.models import SystemUser


class DailyLineActionAuditTest(TestCase):
    """Integracao: daily_user_action_board audita mudancas materiais."""

    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="daily.audit.admin@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.client.force_login(self.admin)
        self.employee = Employee.objects.create(
            full_name="Daily Audit Employee",
            corporate_email="daily.audit.super@test.com",
            employee_id="DAILYAUD1",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )
        self.sim = SIMcard.objects.create(
            iccid="8900000000000088801",
            carrier="CarrierDailyAudit",
            status=SIMcard.Status.AVAILABLE,
        )
        self.phone_line = PhoneLine.objects.create(
            phone_number="+5511988888801",
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

    def _events(self):
        return LineDailyActionAuditEvent.objects.filter(
            source=LineDailyActionAuditEvent.Source.DAILY_USER_ACTION
        ).order_by("id")

    def _mark(self):
        """Marca o maior id de evento existente, pra isolar a rodada de
        interesse sem apagar historico (eventos sao append-only/imutaveis)."""
        last = LineDailyActionAuditEvent.objects.order_by("-id").first()
        return last.pk if last else 0

    def _events_since(self, marker):
        return self._events().filter(pk__gt=marker)

    def test_create_action_records_opened_event(self):
        response = self._post(action_type=DailyUserAction.ActionType.PENDING, note="obs")
        self.assertEqual(response.status_code, 302)

        action = DailyUserAction.objects.get(employee=self.employee)
        events = self._events()
        self.assertEqual(events.count(), 1)
        event = events.first()
        self.assertEqual(event.event_type, LineDailyActionAuditEvent.EventType.OPENED)
        self.assertEqual(event.source_object_id, action.pk)
        self.assertEqual(event.performed_by, self.admin)
        self.assertEqual(event.phone_line_id, self.phone_line.pk)
        self.assertEqual(event.after_state["note"], "obs")

    def test_change_action_and_note_records_two_events_with_one_operation_id(self):
        self._post(action_type=DailyUserAction.ActionType.PENDING, note="obs original")
        action = DailyUserAction.objects.get(employee=self.employee)
        marker = self._mark()

        response = self._post(
            action_type=DailyUserAction.ActionType.RECONNECT_WHATSAPP,
            note="obs nova",
        )
        self.assertEqual(response.status_code, 302)

        events = self._events_since(marker)
        self.assertEqual(events.count(), 2)
        event_types = {event.event_type for event in events}
        self.assertEqual(
            event_types,
            {
                LineDailyActionAuditEvent.EventType.ACTION_CHANGED,
                LineDailyActionAuditEvent.EventType.NOTE_CHANGED,
            },
        )
        operation_ids = {event.operation_id for event in events}
        self.assertEqual(len(operation_ids), 1)
        for event in events:
            self.assertEqual(event.source_object_id, action.pk)

    def test_resolve_action_records_note_changed_then_resolved_event(self):
        self._post(action_type=DailyUserAction.ActionType.PENDING, note="obs original")
        action = DailyUserAction.objects.get(employee=self.employee)
        marker = self._mark()

        response = self._post(action_type="", note="obs de resolucao")
        self.assertEqual(response.status_code, 302)

        events = list(self._events_since(marker))
        self.assertEqual(len(events), 2)
        self.assertEqual(
            events[0].event_type, LineDailyActionAuditEvent.EventType.NOTE_CHANGED
        )
        self.assertEqual(
            events[1].event_type, LineDailyActionAuditEvent.EventType.RESOLVED
        )
        self.assertEqual(events[0].operation_id, events[1].operation_id)
        self.assertTrue(events[1].after_state["resolution"]["is_resolved"])

        action.refresh_from_db()
        self.assertTrue(action.is_resolved)

    def test_reactivate_resolved_same_day_action_records_reopened_event(self):
        self._post(action_type=DailyUserAction.ActionType.PENDING, note="obs original")
        action = DailyUserAction.objects.get(employee=self.employee)
        action.is_resolved = True
        action.save(update_fields=["is_resolved"])
        marker = self._mark()

        response = self._post(
            action_type=DailyUserAction.ActionType.PENDING, note="obs original"
        )
        self.assertEqual(response.status_code, 302)

        events = self._events_since(marker)
        self.assertEqual(events.count(), 1)
        event = events.first()
        self.assertEqual(event.event_type, LineDailyActionAuditEvent.EventType.REOPENED)
        self.assertFalse(event.after_state["resolution"]["is_resolved"])

    def test_line_status_change_records_line_status_changed_event(self):
        self._post(action_type=DailyUserAction.ActionType.PENDING, note="obs")
        marker = self._mark()

        response = self._post(
            action_type=DailyUserAction.ActionType.PENDING,
            note="obs",
            line_status="restricted",
        )
        self.assertEqual(response.status_code, 302)

        events = LineDailyActionAuditEvent.objects.filter(pk__gt=marker).order_by("id")
        self.assertEqual(events.count(), 1)
        event = events.first()
        self.assertEqual(
            event.event_type, LineDailyActionAuditEvent.EventType.LINE_STATUS_CHANGED
        )
        self.assertEqual(event.source, LineDailyActionAuditEvent.Source.LINE_ALLOCATION)
        self.assertEqual(event.source_object_id, self.allocation.pk)
        self.assertEqual(event.allocation_id, self.allocation.pk)
        self.assertEqual(event.phone_line_id, self.phone_line.pk)
        self.assertEqual(event.after_state["line_status"]["code"], "restricted")

        # Efeitos colaterais legados preservados.
        self.assertTrue(
            PhoneLineHistory.objects.filter(
                phone_line=self.phone_line,
                action=PhoneLineHistory.ActionType.STATUS_CHANGED,
            ).exists()
        )

    def test_action_without_allocation_has_null_phone_line_event(self):
        response = self._post(
            allocation_id="",
            action_type=DailyUserAction.ActionType.PENDING,
            note="obs sem linha",
        )
        self.assertEqual(response.status_code, 302)

        action = DailyUserAction.objects.get(employee=self.employee, allocation__isnull=True)
        events = self._events()
        self.assertEqual(events.count(), 1)
        event = events.first()
        self.assertIsNone(event.phone_line_id)
        self.assertEqual(event.phone_number_snapshot, "")
        self.assertEqual(event.source_object_id, action.pk)
        self.assertEqual(event.employee_id, self.employee.pk)
        self.assertEqual(event.performed_by_id, self.admin.pk)
