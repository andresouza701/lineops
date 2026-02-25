import threading

from django.test import TransactionTestCase as Transaction

from core.services.allocation_service import AllocationService
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser


class AllocationConcurrencyTest(Transaction):
    reset_sequences = True

    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="admin.concurrent@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.employee = Employee.objects.create(
            full_name="Concurrent User",
            corporate_email="concurrent@corp.com",
            employee_id="EMP-CONCURRENT",
            department="IT",
            status=Employee.Status.ACTIVE,
        )
        sim = SIMcard.objects.create(iccid="8900000000000000999", carrier="CarrierX")
        self.line = PhoneLine.objects.create(
            phone_number="+5511999990000", sim_card=sim
        )

    def test_concurrent_allocation(self):
        results = []

        def attempt():
            try:
                AllocationService.allocate_line(
                    employee=self.employee,
                    phone_line=self.line,
                    allocated_by=self.admin,
                )
                results.append("success")
            except Exception as e:
                results.append(f"error: {str(e)}")

        t1 = threading.Thread(target=attempt)
        t2 = threading.Thread(target=attempt)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(len(results), 2)
        self.assertLessEqual(results.count("success"), 1)
