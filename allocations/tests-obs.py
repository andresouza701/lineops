from django.contrib.auth import get_user_model
from django.db.models import ProtectedError
from django.test import TestCase

from core.exceptions.domain_exceptions import BusinessLogicError
from core.services.allocation_service import AllocationService
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard

from .models import LineAllocation


class LineAllocationFlowTest(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(
            full_name="Ana Souza",
            corporate_email="ana.souza@example.com",
            employee_id="EMP-1001",
            department="Operações",
            status=Employee.Status.ACTIVE,
        )

        self.sim_card = SIMcard.objects.create(
            iccid="8901123456789012349",
            carrier="LinhaTest",
        )

        self.phone_line = PhoneLine.objects.create(
            phone_number="+5511999944440",
            sim_card=self.sim_card,
        )

    def _allocate(self):
        return LineAllocation.objects.create(
            employee=self.employee,
            phone_line=self.phone_line,
        )

    def test_creation_sets_allocated_at_and_string_history(self):
        allocation = self._allocate()

        self.assertIsNotNone(allocation.allocated_at)
        self.assertEqual(allocation.employee, self.employee)
        self.assertEqual(allocation.phone_line, self.phone_line)
        self.assertIn("Ana Souza", str(allocation))

    def test_cannot_delete_employee_with_allocation(self):
        allocation = self._allocate()

        with self.assertRaises(ProtectedError):
            Employee.all_objects.filter(pk=self.employee.pk).delete()

        self.assertTrue(LineAllocation.objects.filter(pk=allocation.pk).exists())

    def test_cannot_delete_phone_line_with_allocation(self):
        allocation = self._allocate()

        with self.assertRaises(ProtectedError):
            self.phone_line.delete()

        self.assertTrue(LineAllocation.objects.filter(pk=allocation.pk).exists())


class AllocationServiceLimitTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="operator@test.com",
            password="pass",
        )
        self.employee = Employee.objects.create(
            full_name="Bruno Lima",
            corporate_email="bruno.lima@example.com",
            employee_id="EMP-2001",
            department="Seguros",
            status=Employee.Status.ACTIVE,
        )
        self.lines = []
        for idx in range(3):
            sim = SIMcard.objects.create(
                iccid=f"89012222222222222{idx}",
                carrier="SegLine",
            )
            line = PhoneLine.objects.create(
                phone_number=f"+551190000100{idx}",
                sim_card=sim,
            )
            self.lines.append(line)

        self.service = AllocationService

    def test_max_two_active_allocations(self):
        self.service.allocate_line(self.employee, self.lines[0], self.user)
        self.service.allocate_line(self.employee, self.lines[1], self.user)

        self.lines[0].refresh_from_db()
        self.lines[1].refresh_from_db()
        self.assertEqual(self.lines[0].status, PhoneLine.Status.ALLOCATED)
        self.assertEqual(self.lines[1].status, PhoneLine.Status.ALLOCATED)

        with self.assertRaises(BusinessLogicError):
            self.service.allocate_line(self.employee, self.lines[2], self.user)

    def test_cannot_allocate_same_phone_line_twice(self):
        other_employee = Employee.objects.create(
            full_name="Catarina Lima",
            corporate_email="catarina.lima@example.com",
            employee_id="EMP-3001",
            department="Logística",
            status=Employee.Status.ACTIVE,
        )

        self.service.allocate_line(self.employee, self.lines[0], self.user)

        with self.assertRaises(BusinessLogicError):
            self.service.allocate_line(other_employee, self.lines[0], self.user)
