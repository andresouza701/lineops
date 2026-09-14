"""Contrato da central de relatorios individuais de linha."""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from allocations.models import LineAllocation
from employees.models import Employee
from telecom.models import LineDailyActionAuditEvent, PhoneLine, PhoneLineHistory, SIMcard
from users.models import SystemUser


class LineReportsTestBase(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="line-reports-admin@test.com",
            password="123456",
            role=SystemUser.Role.ADMIN,
        )
        self.operator = SystemUser.objects.create_user(
            email="line-reports-operator@test.com",
            password="123456",
            role=SystemUser.Role.OPERATOR,
        )
        self.employee = Employee.objects.create(
            full_name="Line Reports Employee",
            corporate_email="line-reports@corp.com",
            employee_id="EMPLR1",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        self.sim_card = SIMcard.objects.create(
            iccid="8900000000000000601",
            carrier="CarrierLineReports",
            status=SIMcard.Status.AVAILABLE,
        )
        self.phone_line = PhoneLine.objects.create(
            phone_number="+551199999601",
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

    def _event(self, *, when, event_type):
        return LineDailyActionAuditEvent.objects.create(
            phone_line=self.phone_line,
            allocation=self.allocation,
            employee=self.employee,
            performed_by=self.admin,
            event_type=event_type,
            source=LineDailyActionAuditEvent.Source.ALLOCATION_PENDENCY,
            source_object_id=1,
            occurred_at=when,
            allocation_id_snapshot=self.allocation.pk,
            performed_by_email_snapshot=self.admin.email,
            before_state=self._state(),
            after_state=self._state(note="mudou"),
        )

    def _params(self):
        day = timezone.localdate()
        return {
            "phone_number": self.phone_line.phone_number,
            "start_date": day.isoformat(),
            "end_date": day.isoformat(),
        }


class LineReportsViewTest(LineReportsTestBase):
    def test_overview_keeps_individual_and_consolidated_report_entry_points(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("telecom:overview"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("telecom:line_reports"))
        self.assertContains(response, reverse("telecom:line_operational_report"))

    def test_requires_line_and_period_before_generating_reports(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("telecom:line_reports"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Informe uma linha e o período")
        self.assertNotIn("operational_row", response.context)

    def test_generates_operational_report_and_timeline_for_same_line_and_period(self):
        now = timezone.now()
        self._event(
            when=now - timedelta(minutes=2),
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
        )
        self._event(
            when=now - timedelta(minutes=1),
            event_type=LineDailyActionAuditEvent.EventType.RESOLVED,
        )
        legacy = PhoneLineHistory.objects.create(
            phone_line=self.phone_line,
            action=PhoneLineHistory.ActionType.STATUS_CHANGED,
            old_value="Ativa",
            new_value="Em analise",
            changed_by=self.admin,
        )
        PhoneLineHistory.objects.filter(pk=legacy.pk).update(changed_at=now)

        self.client.force_login(self.admin)
        response = self.client.get(reverse("telecom:line_reports"), self._params())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["operational_row"].entradas, 1)
        self.assertEqual(response.context["operational_row"].saidas, 1)
        self.assertEqual(response.context["operational_row"].situacao, "Resolvida")
        self.assertEqual(len(response.context["timeline_items"]), 3)
        self.assertContains(response, "Relatório Operacional")
        self.assertContains(response, "Timeline da Linha")

    def test_rejects_line_outside_current_user_scope(self):
        self.client.force_login(self.operator)

        response = self.client.get(reverse("telecom:line_reports"), self._params())

        self.assertEqual(response.status_code, 404)

    def test_csv_uses_same_required_line_and_period_filters(self):
        self._event(
            when=timezone.now(),
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
        )
        self.client.force_login(self.admin)

        response = self.client.get(reverse("telecom:line_reports_csv"), self._params())

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"\xef\xbb\xbf"))
        self.assertIn(self.phone_line.phone_number, response.content.decode("utf-8-sig"))
