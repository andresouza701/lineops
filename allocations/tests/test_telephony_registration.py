from django.test import TestCase
from django.urls import reverse

from allocations.models import LineAllocation
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser


class TelephonyRegistrationFlowTests(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="admin.telephony@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.client.force_login(self.admin)

        self.employee = Employee.objects.create(
            full_name="Telephony User",
            corporate_email="supervisor@test.com",
            employee_id="EMP-TEL-1",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )

        self.sim = SIMcard.objects.create(
            iccid="8900000000000000707",
            carrier="CarrierG",
            status=SIMcard.Status.AVAILABLE,
        )
        self.line = PhoneLine.objects.create(
            phone_number="+5511999990707",
            sim_card=self.sim,
            status=PhoneLine.Status.AVAILABLE,
        )

    def test_existing_line_links_employee_and_updates_line_status(self):
        response = self.client.post(
            reverse("allocations:allocation_list"),
            {
                "action": "telephony",
                "line_action": "existing",
                "employee": self.employee.pk,
                "phone_line": self.line.pk,
            },
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            LineAllocation.objects.filter(
                employee=self.employee,
                phone_line=self.line,
                is_active=True,
            ).exists()
        )
        self.line.refresh_from_db()
        self.assertEqual(self.line.status, PhoneLine.Status.ALLOCATED)

    def test_change_status_updates_line_when_no_active_allocation(self):
        response = self.client.post(
            reverse("allocations:allocation_list"),
            {
                "action": "telephony",
                "line_action": "change_status",
                "phone_line_status": self.line.pk,
                "status_line": PhoneLine.Status.SUSPENDED,
            },
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        self.line.refresh_from_db()
        self.assertEqual(self.line.status, PhoneLine.Status.SUSPENDED)

    def test_change_status_does_not_break_active_allocation_consistency(self):
        LineAllocation.objects.create(
            employee=self.employee,
            phone_line=self.line,
            allocated_by=self.admin,
            is_active=True,
        )
        self.line.status = PhoneLine.Status.ALLOCATED
        self.line.save(update_fields=["status"])

        response = self.client.post(
            reverse("allocations:allocation_list"),
            {
                "action": "telephony",
                "line_action": "change_status",
                "phone_line_status": self.line.pk,
                "status_line": PhoneLine.Status.AVAILABLE,
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.line.refresh_from_db()
        self.assertEqual(self.line.status, PhoneLine.Status.ALLOCATED)
