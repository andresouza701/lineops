from django.test import TestCase

from allocations.models import LineAllocation
from core.exceptions.domain_exceptions import BusinessRuleException
from core.services.telephony_use_case import TelephonyUseCase
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser


class TelephonyUseCaseTests(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="admin.usecase@test.com",
            password="123456",
            role=SystemUser.Role.ADMIN,
        )
        self.employee = Employee.objects.create(
            full_name="Use Case Employee",
            corporate_email="supervisor.usecase@test.com",
            employee_id="UC-001",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )
        self.sim = SIMcard.objects.create(
            iccid="8900000000000000420",
            carrier="CarrierUC",
            status=SIMcard.Status.AVAILABLE,
        )
        self.line = PhoneLine.objects.create(
            phone_number="+5511999990420",
            sim_card=self.sim,
            status=PhoneLine.Status.AVAILABLE,
        )

    def test_change_line_status_blocks_non_allocated_target_when_line_has_active_allocation(
        self,
    ):
        LineAllocation.objects.create(
            employee=self.employee,
            phone_line=self.line,
            allocated_by=self.admin,
            is_active=True,
        )
        self.line.status = PhoneLine.Status.ALLOCATED
        self.line.save(update_fields=["status"])

        with self.assertRaises(BusinessRuleException) as exc:
            TelephonyUseCase.change_line_status(
                phone_line_id=self.line.pk,
                new_status=PhoneLine.Status.AVAILABLE,
                actor=self.admin,
            )

        self.assertIn("Libere a linha primeiro e tente novamente", str(exc.exception))
        self.line.refresh_from_db()
        self.assertEqual(self.line.status, PhoneLine.Status.ALLOCATED)

    def test_change_line_status_blocks_allocated_target_without_active_allocation(self):
        with self.assertRaises(BusinessRuleException) as exc:
            TelephonyUseCase.change_line_status(
                phone_line_id=self.line.pk,
                new_status=PhoneLine.Status.ALLOCATED,
                actor=self.admin,
            )

        self.assertIn("Use o vinculo com usuario para deixar ALLOCATED.", str(exc.exception))
        self.line.refresh_from_db()
        self.assertEqual(self.line.status, PhoneLine.Status.AVAILABLE)

    def test_change_line_status_updates_line_when_status_is_consistent_with_allocation_state(
        self,
    ):
        result = TelephonyUseCase.change_line_status(
            phone_line_id=self.line.pk,
            new_status=PhoneLine.Status.SUSPENDED,
            actor=self.admin,
        )

        self.assertTrue(result.success)
        self.line.refresh_from_db()
        self.assertEqual(self.line.status, PhoneLine.Status.SUSPENDED)
