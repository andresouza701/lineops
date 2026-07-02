import json

from django.test import TestCase
from django.urls import reverse

from allocations.models import LineAllocation
from employees.models import Employee
from pendencies.models import AllocationPendency
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser


class PendencyWebRestrictionLineStatusTests(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="web.restriction.admin@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.supervisor = SystemUser.objects.create_user(
            email="web.restriction.super@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.employee = Employee.objects.create(
            full_name="Web Restriction User",
            corporate_email=self.supervisor.email,
            employee_id="Web Restriction Portfolio",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )
        self.sim = SIMcard.objects.create(
            iccid="8955000000000000901",
            carrier="WebRestrictionCarrier",
            status=SIMcard.Status.AVAILABLE,
        )
        self.phone_line = PhoneLine.objects.create(
            phone_number="+5547999990901",
            sim_card=self.sim,
            status=PhoneLine.Status.ALLOCATED,
        )
        self.allocation = LineAllocation.objects.create(
            employee=self.employee,
            phone_line=self.phone_line,
            allocated_by=self.admin,
            is_active=True,
            line_status=LineAllocation.LineStatus.ACTIVE,
        )
        self.pendency = AllocationPendency.objects.create(
            employee=self.employee,
            allocation=self.allocation,
            action=AllocationPendency.ActionType.PENDING,
        )

    def test_line_status_choices_include_web_restriction(self):
        self.assertIn(
            (Employee.LineStatus.WEB_RESTRICTION, "Restrição WEB"),
            Employee.LineStatus.choices,
        )
        self.assertIn(
            (LineAllocation.LineStatus.WEB_RESTRICTION, "Restrição WEB"),
            LineAllocation.LineStatus.choices,
        )

    def test_pendency_detail_exposes_web_restriction_choice(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("pendencies:detail"),
            {"employee_id": self.employee.pk, "allocation_id": self.allocation.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            {
                "value": Employee.LineStatus.WEB_RESTRICTION,
                "label": "Restrição WEB",
            },
            response.json()["line_status_choices"],
        )

    def test_admin_can_set_web_restriction_from_pendency_status(self):
        self.client.force_login(self.admin)
        payload = {
            "pendency_id": self.pendency.pk,
            "action": self.pendency.action,
            "observation": self.pendency.observation,
            "line_status": Employee.LineStatus.WEB_RESTRICTION,
        }

        response = self.client.post(
            reverse("pendencies:update"),
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.allocation.refresh_from_db()
        self.assertEqual(
            self.allocation.line_status,
            LineAllocation.LineStatus.WEB_RESTRICTION,
        )
        self.assertEqual(response.json()["line_status_display"], "Restrição WEB")
