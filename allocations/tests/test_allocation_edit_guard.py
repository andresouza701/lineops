from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from allocations.models import LineAllocation
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser


class AllocationEditGuardTests(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="admin.edit@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.client.force_login(self.admin)

        self.first_employee = Employee.objects.create(
            full_name="Primeiro Usuario",
            corporate_email="supervisor@test.com",
            employee_id="EMP-1",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )
        self.second_employee = Employee.objects.create(
            full_name="Segundo Usuario",
            corporate_email="supervisor@test.com",
            employee_id="EMP-2",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )
        self.simcard = SIMcard.objects.create(
            iccid="8999999999999991234",
            carrier="Carrier Guard",
            status=SIMcard.Status.ACTIVE,
        )
        self.line = PhoneLine.objects.create(
            phone_number="+5511999991234",
            sim_card=self.simcard,
            status=PhoneLine.Status.ALLOCATED,
        )

    def test_release_action_rejects_historical_allocation(self):
        old_allocation = LineAllocation.objects.create(
            employee=self.first_employee,
            phone_line=self.line,
            allocated_by=self.admin,
            is_active=True,
        )
        old_allocation.is_active = False
        old_allocation.released_at = timezone.now()
        old_allocation.released_by = self.admin
        old_allocation.save(update_fields=["is_active", "released_at", "released_by"])

        current_allocation = LineAllocation.objects.create(
            employee=self.second_employee,
            phone_line=self.line,
            allocated_by=self.admin,
            is_active=True,
        )

        response = self.client.post(
            reverse("allocations:allocation_edit", args=[old_allocation.pk]),
            {"action": "release"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Apenas alocacoes ativas podem ser liberadas.")
        self.line.refresh_from_db()
        current_allocation.refresh_from_db()
        old_allocation.refresh_from_db()
        self.assertEqual(self.line.status, PhoneLine.Status.ALLOCATED)
        self.assertTrue(current_allocation.is_active)
        self.assertFalse(old_allocation.is_active)
