import json

from django.test import Client, TestCase
from django.urls import reverse

from allocations.models import LineAllocation
from employees.models import Employee
from pendencies.models import AllocationPendency, PendencyObservationNotification
from pendencies.services import notify_observation_change
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser


def _make_user(email, role, active=True):
    u = SystemUser.objects.create_user(email=email, password="pass", role=role)
    u.is_active = active
    u.save(update_fields=["is_active"])
    return u


def _make_employee(email="super@corp.com", eid="E01"):
    return Employee.objects.create(
        full_name="Test Employee",
        corporate_email=email,
        employee_id=eid,
    )


class NotifyObservationChangeServiceTest(TestCase):
    """Unit tests for the notify_observation_change service function."""

    def setUp(self):
        self.admin = _make_user("admin@t.com", SystemUser.Role.ADMIN)
        self.super_user = _make_user("super@t.com", SystemUser.Role.SUPER)
        self.backoffice = _make_user("bo@t.com", SystemUser.Role.BACKOFFICE)
        self.gerente = _make_user("gerente@t.com", SystemUser.Role.GERENTE)
        self.operator = _make_user("op@t.com", SystemUser.Role.OPERATOR)
        self.employee = _make_employee()
        self.pendency = AllocationPendency.objects.create(
            employee=self.employee,
            allocation=None,
        )

    def test_admin_notifies_super_backoffice_gerente(self):
        count = notify_observation_change(self.pendency, self.admin, "nova obs")
        recipients = set(
            PendencyObservationNotification.objects.filter(
                pendency=self.pendency
            ).values_list("recipient_id", flat=True)
        )
        self.assertEqual(count, 3)
        self.assertIn(self.super_user.pk, recipients)
        self.assertIn(self.backoffice.pk, recipients)
        self.assertIn(self.gerente.pk, recipients)
        self.assertNotIn(self.admin.pk, recipients)
        self.assertNotIn(self.operator.pk, recipients)

    def test_super_notifies_admins(self):
        count = notify_observation_change(self.pendency, self.super_user, "nova obs")
        recipients = set(
            PendencyObservationNotification.objects.filter(
                pendency=self.pendency
            ).values_list("recipient_id", flat=True)
        )
        self.assertEqual(count, 1)
        self.assertIn(self.admin.pk, recipients)
        self.assertNotIn(self.super_user.pk, recipients)

    def test_backoffice_notifies_admins(self):
        count = notify_observation_change(self.pendency, self.backoffice, "obs")
        recipients = set(
            PendencyObservationNotification.objects.filter(
                pendency=self.pendency
            ).values_list("recipient_id", flat=True)
        )
        self.assertEqual(count, 1)
        self.assertIn(self.admin.pk, recipients)

    def test_gerente_notifies_admins(self):
        count = notify_observation_change(self.pendency, self.gerente, "obs")
        recipients = set(
            PendencyObservationNotification.objects.filter(
                pendency=self.pendency
            ).values_list("recipient_id", flat=True)
        )
        self.assertEqual(count, 1)
        self.assertIn(self.admin.pk, recipients)

    def test_operator_does_not_trigger_notifications(self):
        count = notify_observation_change(self.pendency, self.operator, "obs")
        self.assertEqual(count, 0)
        self.assertEqual(PendencyObservationNotification.objects.count(), 0)

    def test_empty_text_creates_no_notifications(self):
        count = notify_observation_change(self.pendency, self.admin, "")
        self.assertEqual(count, 0)
        self.assertEqual(PendencyObservationNotification.objects.count(), 0)

    def test_notification_stores_text_snapshot(self):
        notify_observation_change(self.pendency, self.admin, "snapshot text")
        notif = PendencyObservationNotification.objects.filter(
            recipient=self.super_user
        ).first()
        self.assertIsNotNone(notif)
        self.assertEqual(notif.observation_text, "snapshot text")

    def test_notification_stores_sender(self):
        notify_observation_change(self.pendency, self.admin, "obs")
        notif = PendencyObservationNotification.objects.filter(
            recipient=self.super_user
        ).first()
        self.assertEqual(notif.sent_by, self.admin)

    def test_notification_is_unread_by_default(self):
        notify_observation_change(self.pendency, self.admin, "obs")
        notif = PendencyObservationNotification.objects.filter(
            recipient=self.super_user
        ).first()
        self.assertFalse(notif.is_read)

    def test_inactive_users_not_notified(self):
        inactive_super = _make_user("inactive@t.com", SystemUser.Role.SUPER, active=False)
        notify_observation_change(self.pendency, self.admin, "obs")
        recipients = set(
            PendencyObservationNotification.objects.values_list("recipient_id", flat=True)
        )
        self.assertNotIn(inactive_super.pk, recipients)

    def test_multiple_admins_each_get_notification(self):
        admin2 = _make_user("admin2@t.com", SystemUser.Role.ADMIN)
        count = notify_observation_change(self.pendency, self.super_user, "obs")
        self.assertEqual(count, 2)
        self.assertEqual(
            PendencyObservationNotification.objects.filter(
                pendency=self.pendency
            ).count(),
            2,
        )
        recipients = set(
            PendencyObservationNotification.objects.values_list("recipient_id", flat=True)
        )
        self.assertIn(self.admin.pk, recipients)
        self.assertIn(admin2.pk, recipients)


class PendencyUpdateViewNotificationTest(TestCase):
    """Integration tests: PendencyUpdateView triggers notifications correctly."""

    def setUp(self):
        self.admin = _make_user("admin@t.com", SystemUser.Role.ADMIN)
        self.super_user = _make_user("super@t.com", SystemUser.Role.SUPER)
        self.employee = _make_employee(email="super@t.com")
        self.pendency = AllocationPendency.objects.create(
            employee=self.employee,
            allocation=None,
        )
        self.client = Client()
        self.url = reverse("pendencies:update")

    def _post(self, user, observation, action="", line_status=""):
        self.client.force_login(user)
        return self.client.post(
            self.url,
            data=json.dumps(
                {
                    "pendency_id": self.pendency.pk,
                    "action": action,
                    "observation": observation,
                    "line_status": line_status,
                }
            ),
            content_type="application/json",
        )

    def test_detail_exposes_waiting_operator_line_status_choice(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("pendencies:detail"),
            data={"employee_id": self.employee.pk},
        )

        self.assertEqual(response.status_code, 200)
        choices = {
            item["value"]: item["label"]
            for item in response.json()["line_status_choices"]
        }
        self.assertIn("waiting_operator", choices)
        self.assertEqual(choices["waiting_operator"], "Aguardando operador")

    def test_detail_marks_observation_locked_when_line_is_under_analysis(self):
        simcard = SIMcard.objects.create(
            iccid="8900000000000012351",
            carrier="CarrierTest",
            status=SIMcard.Status.AVAILABLE,
        )
        phone_line = PhoneLine.objects.create(
            phone_number="+5547999990051",
            sim_card=simcard,
            status=PhoneLine.Status.ALLOCATED,
        )
        allocation = LineAllocation.objects.create(
            employee=self.employee,
            phone_line=phone_line,
            allocated_by=self.admin,
            is_active=True,
            line_status=LineAllocation.LineStatus.UNDER_ANALYSIS,
        )
        AllocationPendency.objects.create(
            employee=self.employee,
            allocation=allocation,
            observation="observacao original",
        )

        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("pendencies:detail"),
            data={
                "employee_id": self.employee.pk,
                "allocation_id": allocation.pk,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["observation_locked"])
        self.assertIn("Em analise", payload["observation_locked_reason"])

    def test_update_rejects_observation_change_when_line_is_under_analysis(self):
        simcard = SIMcard.objects.create(
            iccid="8900000000000012352",
            carrier="CarrierTest",
            status=SIMcard.Status.AVAILABLE,
        )
        phone_line = PhoneLine.objects.create(
            phone_number="+5547999990052",
            sim_card=simcard,
            status=PhoneLine.Status.ALLOCATED,
        )
        allocation = LineAllocation.objects.create(
            employee=self.employee,
            phone_line=phone_line,
            allocated_by=self.admin,
            is_active=True,
            line_status=LineAllocation.LineStatus.UNDER_ANALYSIS,
        )
        pendency = AllocationPendency.objects.create(
            employee=self.employee,
            allocation=allocation,
            observation="observacao original",
        )

        self.client.force_login(self.admin)
        response = self.client.post(
            self.url,
            data=json.dumps(
                {
                    "pendency_id": pendency.pk,
                    "action": pendency.action,
                    "observation": "observacao alterada",
                    "line_status": LineAllocation.LineStatus.UNDER_ANALYSIS,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        pendency.refresh_from_db()
        self.assertEqual(pendency.observation, "observacao original")
        self.assertEqual(PendencyObservationNotification.objects.count(), 0)

    def test_update_allows_observation_change_after_line_leaves_under_analysis(self):
        simcard = SIMcard.objects.create(
            iccid="8900000000000012353",
            carrier="CarrierTest",
            status=SIMcard.Status.AVAILABLE,
        )
        phone_line = PhoneLine.objects.create(
            phone_number="+5547999990053",
            sim_card=simcard,
            status=PhoneLine.Status.ALLOCATED,
        )
        allocation = LineAllocation.objects.create(
            employee=self.employee,
            phone_line=phone_line,
            allocated_by=self.admin,
            is_active=True,
            line_status=LineAllocation.LineStatus.RESTRICTED,
        )
        pendency = AllocationPendency.objects.create(
            employee=self.employee,
            allocation=allocation,
            observation="observacao original",
        )

        self.client.force_login(self.admin)
        response = self.client.post(
            self.url,
            data=json.dumps(
                {
                    "pendency_id": pendency.pk,
                    "action": pendency.action,
                    "observation": "observacao liberada",
                    "line_status": LineAllocation.LineStatus.RESTRICTED,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        pendency.refresh_from_db()
        self.assertEqual(pendency.observation, "observacao liberada")

    def test_admin_can_update_allocation_line_status_to_waiting_operator(self):
        simcard = SIMcard.objects.create(
            iccid="8900000000000012345",
            carrier="CarrierTest",
            status=SIMcard.Status.AVAILABLE,
        )
        phone_line = PhoneLine.objects.create(
            phone_number="+5547999990001",
            sim_card=simcard,
            status=PhoneLine.Status.ALLOCATED,
        )
        allocation = LineAllocation.objects.create(
            employee=self.employee,
            phone_line=phone_line,
            allocated_by=self.admin,
            is_active=True,
        )
        pendency = AllocationPendency.objects.create(
            employee=self.employee,
            allocation=allocation,
        )

        self.client.force_login(self.admin)
        response = self.client.post(
            self.url,
            data=json.dumps(
                {
                    "pendency_id": pendency.pk,
                    "action": "",
                    "observation": "",
                    "line_status": "waiting_operator",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        allocation.refresh_from_db()
        self.assertEqual(allocation.line_status, "waiting_operator")

    def test_admin_setting_line_status_active_with_no_action_clears_technical_responsible(self):
        simcard = SIMcard.objects.create(
            iccid="8900000000000012346",
            carrier="CarrierTest",
            status=SIMcard.Status.AVAILABLE,
        )
        phone_line = PhoneLine.objects.create(
            phone_number="+5547999990002",
            sim_card=simcard,
            status=PhoneLine.Status.ALLOCATED,
        )
        allocation = LineAllocation.objects.create(
            employee=self.employee,
            phone_line=phone_line,
            allocated_by=self.admin,
            is_active=True,
            line_status="restricted",
        )
        pendency = AllocationPendency.objects.create(
            employee=self.employee,
            allocation=allocation,
            action=AllocationPendency.ActionType.NO_ACTION,
            technical_responsible=self.admin,
        )

        self.client.force_login(self.admin)
        response = self.client.post(
            self.url,
            data=json.dumps(
                {
                    "pendency_id": pendency.pk,
                    "action": "no_action",
                    "observation": "",
                    "line_status": "active",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        pendency.refresh_from_db()
        allocation.refresh_from_db()
        self.assertEqual(allocation.line_status, "active")
        self.assertIsNone(pendency.technical_responsible)

    def test_admin_setting_non_active_line_status_keeps_technical_responsible(self):
        simcard = SIMcard.objects.create(
            iccid="8900000000000012347",
            carrier="CarrierTest",
            status=SIMcard.Status.AVAILABLE,
        )
        phone_line = PhoneLine.objects.create(
            phone_number="+5547999990003",
            sim_card=simcard,
            status=PhoneLine.Status.ALLOCATED,
        )
        allocation = LineAllocation.objects.create(
            employee=self.employee,
            phone_line=phone_line,
            allocated_by=self.admin,
            is_active=True,
            line_status="under_analysis",
        )
        pendency = AllocationPendency.objects.create(
            employee=self.employee,
            allocation=allocation,
            action=AllocationPendency.ActionType.NO_ACTION,
            technical_responsible=self.admin,
        )

        self.client.force_login(self.admin)
        response = self.client.post(
            self.url,
            data=json.dumps(
                {
                    "pendency_id": pendency.pk,
                    "action": "no_action",
                    "observation": "",
                    "line_status": "restricted",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        pendency.refresh_from_db()
        allocation.refresh_from_db()
        self.assertEqual(allocation.line_status, "restricted")
        self.assertEqual(pendency.technical_responsible, self.admin)

    def test_admin_save_clears_technical_responsible_when_active_and_no_action(self):
        simcard = SIMcard.objects.create(
            iccid="8900000000000012348",
            carrier="CarrierTest",
            status=SIMcard.Status.AVAILABLE,
        )
        phone_line = PhoneLine.objects.create(
            phone_number="+5547999990004",
            sim_card=simcard,
            status=PhoneLine.Status.ALLOCATED,
        )
        allocation = LineAllocation.objects.create(
            employee=self.employee,
            phone_line=phone_line,
            allocated_by=self.admin,
            is_active=True,
            line_status="active",
        )
        pendency = AllocationPendency.objects.create(
            employee=self.employee,
            allocation=allocation,
            action=AllocationPendency.ActionType.NO_ACTION,
            technical_responsible=self.admin,
        )

        self.client.force_login(self.admin)
        response = self.client.post(
            self.url,
            data=json.dumps(
                {
                    "pendency_id": pendency.pk,
                    "action": "no_action",
                    "observation": "",
                    "line_status": "active",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        pendency.refresh_from_db()
        self.assertIsNone(pendency.technical_responsible)

    def test_admin_saving_new_observation_notifies_super(self):
        resp = self._post(self.admin, "nova obs")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            PendencyObservationNotification.objects.filter(
                pendency=self.pendency, recipient=self.super_user
            ).count(),
            1,
        )

    def test_super_saving_new_observation_notifies_admin(self):
        resp = self._post(self.super_user, "obs do super")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            PendencyObservationNotification.objects.filter(
                pendency=self.pendency, recipient=self.admin
            ).count(),
            1,
        )

    def test_unchanged_observation_creates_no_notification(self):
        self.pendency.observation = "mesma obs"
        self.pendency.save(update_fields=["observation"])
        resp = self._post(self.admin, "mesma obs")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PendencyObservationNotification.objects.count(), 0)

    def test_clearing_observation_creates_no_notification(self):
        self.pendency.observation = "tinha texto"
        self.pendency.save(update_fields=["observation"])
        resp = self._post(self.admin, "")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PendencyObservationNotification.objects.count(), 0)

    def test_response_includes_notifications_sent_count(self):
        resp = self._post(self.admin, "nova obs")
        data = resp.json()
        self.assertIn("notifications_sent", data)
        self.assertEqual(data["notifications_sent"], 1)


class PendencyDetailViewNotificationReadTest(TestCase):
    """Integration tests: opening detail marks matching notifications as read."""

    def setUp(self):
        self.admin = _make_user("admin@t.com", SystemUser.Role.ADMIN)
        self.super_user = _make_user("super@t.com", SystemUser.Role.SUPER)
        self.employee_a = _make_employee(email="super@t.com", eid="EA")
        self.employee_b = Employee.objects.create(
            full_name="Test Employee B",
            corporate_email="super@t.com",
            employee_id="EB",
        )

        self.pendency_a = AllocationPendency.objects.create(
            employee=self.employee_a,
            allocation=None,
        )
        self.pendency_b = AllocationPendency.objects.create(
            employee=self.employee_b,
            allocation=None,
        )

        self.notification_a = PendencyObservationNotification.objects.create(
            pendency=self.pendency_a,
            recipient=self.super_user,
            sent_by=self.admin,
            observation_text="obs a",
        )
        self.notification_b = PendencyObservationNotification.objects.create(
            pendency=self.pendency_b,
            recipient=self.super_user,
            sent_by=self.admin,
            observation_text="obs b",
        )

        self.client = Client()
        self.url = reverse("pendencies:detail")

    def test_detail_marks_only_opened_employee_notifications_as_read(self):
        self.client.force_login(self.super_user)
        response = self.client.get(
            self.url,
            data={"employee_id": self.employee_a.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.notification_a.refresh_from_db()
        self.notification_b.refresh_from_db()
        self.assertTrue(self.notification_a.is_read)
        self.assertFalse(self.notification_b.is_read)


class PendencyNotificationsViewTest(TestCase):
    """Tests for the GET /pendencies/api/notifications/ endpoint."""

    def setUp(self):
        self.admin = _make_user("admin@t.com", SystemUser.Role.ADMIN)
        self.super_user = _make_user("super@t.com", SystemUser.Role.SUPER)
        self.employee = _make_employee(email="super@t.com")
        self.pendency = AllocationPendency.objects.create(
            employee=self.employee, allocation=None
        )
        self.notif = PendencyObservationNotification.objects.create(
            pendency=self.pendency,
            recipient=self.super_user,
            sent_by=self.admin,
            observation_text="hello",
        )
        self.client = Client()
        self.url = reverse("pendencies:notifications")

    def test_returns_unread_notifications_for_user(self):
        self.client.force_login(self.super_user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data["notifications"]), 1)
        self.assertEqual(data["notifications"][0]["text"], "hello")

    def test_marks_notifications_as_read_after_fetch(self):
        self.client.force_login(self.super_user)
        self.client.get(self.url)
        self.notif.refresh_from_db()
        self.assertTrue(self.notif.is_read)

    def test_already_read_notifications_not_returned(self):
        self.notif.is_read = True
        self.notif.save(update_fields=["is_read"])
        self.client.force_login(self.super_user)
        resp = self.client.get(self.url)
        data = resp.json()
        self.assertEqual(len(data["notifications"]), 0)

    def test_user_only_sees_own_notifications(self):
        self.client.force_login(self.admin)
        resp = self.client.get(self.url)
        data = resp.json()
        self.assertEqual(len(data["notifications"]), 0)

    def test_unauthenticated_redirects(self):
        resp = self.client.get(self.url)
        # login_required redirects to login page
        self.assertIn(resp.status_code, [302, 403])

    def test_notification_payload_has_expected_fields(self):
        self.client.force_login(self.super_user)
        resp = self.client.get(self.url)
        notif = resp.json()["notifications"][0]
        self.assertIn("id", notif)
        self.assertIn("text", notif)
        self.assertIn("sent_by", notif)
        self.assertIn("employee_name", notif)
        self.assertIn("created_at", notif)
