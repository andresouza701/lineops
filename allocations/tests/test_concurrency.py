import threading

from django.test import TransactionTestCase as Transaction

from core.services.allocation_service import AllocationService
from dashboard.models import DailyUserAction
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser
from whatsapp.choices import WhatsAppSessionStatus
from whatsapp.models import MeowInstance, WhatsAppSession


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
            teams="IT",
            status=Employee.Status.ACTIVE,
        )
        sim = SIMcard.objects.create(iccid="8900000000000000999", carrier="CarrierX")
        self.line = PhoneLine.objects.create(
            phone_number="+5511999990000", sim_card=sim
        )
        self.meow = MeowInstance.objects.create(
            name="Concurrent Meow",
            base_url="http://concurrent-meow.local",
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

    def test_concurrent_allocation_creates_single_whatsapp_pending_and_session(self):
        results = []

        def attempt():
            try:
                allocation = AllocationService.allocate_line(
                    employee=self.employee,
                    phone_line=self.line,
                    allocated_by=self.admin,
                )
                results.append(("success", allocation.pk))
            except Exception as exc:
                results.append(("error", str(exc)))

        t1 = threading.Thread(target=attempt)
        t2 = threading.Thread(target=attempt)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        successful_allocations = [value for status, value in results if status == "success"]
        self.assertEqual(len(successful_allocations), 1)
        self.assertEqual(
            self.line.allocations.filter(is_active=True).count(),
            1,
        )

        session = WhatsAppSession.objects.get(line=self.line)
        self.assertEqual(session.meow_instance, self.meow)
        self.assertEqual(session.status, WhatsAppSessionStatus.NEW)

        action = DailyUserAction.objects.get(allocation_id=successful_allocations[0])
        self.assertEqual(action.action_type, DailyUserAction.ActionType.NEW_NUMBER)
        self.assertFalse(action.is_resolved)
        self.assertEqual(WhatsAppSession.objects.filter(line=self.line).count(), 1)


