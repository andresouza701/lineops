from django.test import TestCase
from django.urls import reverse

from core.exceptions.domain_exceptions import BusinessRuleException
from core.services.allocation_service import AllocationService
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser


class AllocationRulesTestCase(TestCase):

    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="admin@test.com",
            password="123456",
            role="ADMIN",
        )

        self.employee = Employee.objects.create(
            full_name="John Doe",
            corporate_email="john@corp.com",
            employee_id="EMP001",
            department="IT",
        )

        # Criar 3 linhas
        self.lines = []
        for i in range(3):
            sim = SIMcard.objects.create(
                iccid=f"890000000000000000{i}", carrier="CarrierX"
            )

            line = PhoneLine.objects.create(
                phone_number=f"+55119999999{i}", sim_card=sim
            )

            self.lines.append(line)

    def test_employee_cannot_have_more_than_two_active_lines(self):

        # Primeira alocação
        AllocationService.allocate_line(
            employee=self.employee,
            phone_line=self.lines[0],
            allocated_by=self.admin
        )

        # Segunda alocação
        AllocationService.allocate_line(
            employee=self.employee,
            phone_line=self.lines[1],
            allocated_by=self.admin
        )

        # Terceira deve falhar
        with self.assertRaises(BusinessRuleException):
            AllocationService.allocate_line(
                employee=self.employee,
                phone_line=self.lines[2],
                allocated_by=self.admin
            )

    # def test_phone_line_cannot_be_allocated_to_two_employees(self):
    #     employee_2 = Employee.objects.create(
    #         full_name="Jane Smith",
    #         corporate_email="jane@corp.com",
    #         employee_id="EMP002",
    #         department="HR"
    #     )

    # line = self.lines[0]

    # AllocationService.allocate_line(
    #     employee=self.employee,
    #     phone_line=line,
    #     allocated_by=self.admin
    # )

    # with self.assertRaises(BusinessRuleException):
    #     AllocationService.allocate_line(
    #         employee=employee_2,
    #         phone_line=line,
    #         allocated_by=self.admin
    #     )

    def test_full_allocation_flow(self):

        line = self.lines[0]

        allocation = AllocationService.allocate_line(
            employee=self.employee, phone_line=line, allocated_by=self.admin
        )

        self.assertTrue(allocation.is_active)
        self.assertIsNone(allocation.released_at)

        line.refresh_from_db()
        self.assertEqual(line.status, PhoneLine.Status.ALLOCATED)

        AllocationService.release_line(
            allocation=allocation, released_by=self.admin)

        allocation.refresh_from_db()
        self.assertFalse(allocation.is_active)
        self.assertIsNotNone(allocation.released_at)

        line.refresh_from_db()
        self.assertEqual(line.status, PhoneLine.Status.AVAILABLE)

        total_allocations = type(allocation).objects.filter(
            employee=allocation.employee
        ).count()
        self.assertEqual(total_allocations, 1)

        total_releases = type(allocation).objects.filter(
            employee=allocation.employee, released_at__isnull=False
        ).count()
        self.assertEqual(total_releases, 1)


class AllocationReleaseViewTestCase(TestCase):

    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="admin@test.com",
            password="123456",
            role="ADMIN",
        )

        self.employee = Employee.objects.create(
            full_name="John Doe",
            corporate_email="john@corp.com",
            employee_id="EMP001",
            department="IT",
        )

        sim = SIMcard.objects.create(
            iccid="8900000000000000000", carrier="CarrierX")
        self.phone_line = PhoneLine.objects.create(
            phone_number="+551199999990", sim_card=sim, status=PhoneLine.Status.AVAILABLE
        )

        self.allocation = AllocationService.allocate_line(
            employee=self.employee, phone_line=self.phone_line, allocated_by=self.admin
        )

        self.client.force_login(self.admin)

    def test_release_view_deactivates_allocation(self):
        url = reverse("allocations:allocation_release",
                      args=[self.allocation.pk])
        response = self.client.post(url, follow=True)

        self.assertRedirects(response, reverse("allocations:allocation_list"))

        self.allocation.refresh_from_db()
        self.assertFalse(self.allocation.is_active)
        self.assertIsNotNone(self.allocation.released_at)

        self.phone_line.refresh_from_db()
        self.assertEqual(self.phone_line.status, PhoneLine.Status.AVAILABLE)
