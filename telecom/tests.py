from django.utils import timezone
from datetime import timedelta
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.services.allocation_service import AllocationService
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser


class PhoneLineHistoryViewTest(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="admin2@test.com",
            password="123456",
            role=SystemUser.Role.ADMIN
        )
        self.client.force_login(self.admin)

        self.employee = Employee.objects.create(
            full_name="History User",
            corporate_email="history@corp.com",
            employee_id="EMP100",
            department="IT"
        )

        self.sim = SIMcard.objects.create(iccid="777", carrier="CarrierX")
        self.phone_line = PhoneLine.objects.create(
            phone_number="555123",
            sim_card=self.sim
        )

        self.first_allocation = AllocationService.allocate_line(
            employee=self.employee,
            phone_line=self.phone_line,
            allocated_by=self.admin
        )
        AllocationService.release_line(
            self.first_allocation,
            released_by=self.admin
        )

        self.second_allocation = AllocationService.allocate_line(
            employee=self.employee,
            phone_line=self.phone_line,
            allocated_by=self.admin
        )

    def test_phone_line_history_returns_all_allocations(self):
        url = reverse('telecom:phoneline_history', args=[self.phone_line.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        allocations = list(response.context['allocations'])
        self.assertEqual(len(allocations), 2)
        self.assertIn(self.employee.full_name, response.content.decode())

        self.assertEqual(allocations[0].pk, self.second_allocation.pk)
        self.assertEqual(allocations[1].pk, self.first_allocation.pk)

    def test_phone_line_history_avoid_n_plus_one(self):
        url = reverse('telecom:phoneline_history', args=[self.phone_line.pk])

        with CaptureQueriesContext(connection) as queries:
            self.client.get(url)

        self.assertLessEqual(len(queries), 10)

    def test_filter_phone_line_history_by_period(self):
        admin = SystemUser.objects.create_user(
            email="admin3@test.com",
            password="123456",
            role="ADMIN"
        )

        employee = Employee.objects.create(
            full_name="Filter User",
            corporate_email="filter@corp.com",
            employee_id="EMP200",
            department="IT"
        )

        sim = SIMcard.objects.create(iccid="555", carrier="CarrierX")
        line = PhoneLine.objects.create(
            phone_number="444555",
            sim_card=sim
        )

        allocation = AllocationService.allocate_line(
            employee=employee,
            phone_line=line,
            allocated_by=admin
        )

        today = timezone.now().date().isoformat()

        self.client.force_login(admin)

        url = reverse('telecom:phoneline_history', args=[line.pk])
        response = self.client.get(f"{url}?start_date={today}")

        self.client.force_login(admin)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Filter User")
