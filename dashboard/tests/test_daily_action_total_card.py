from django.test import TestCase
from django.urls import reverse

from allocations.models import LineAllocation
from employees.models import Employee
from pendencies.models import AllocationPendency
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser


class DailyUserActionTotalCardTest(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="daily.action.total.admin@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.client.force_login(self.admin)

    def _create_active_allocation(self, employee, suffix):
        sim = SIMcard.objects.create(
            iccid=f"8900000000000077{suffix}",
            carrier="CarrierTotalCard",
            status=SIMcard.Status.AVAILABLE,
        )
        line = PhoneLine.objects.create(
            phone_number=f"+5511988877{suffix}",
            sim_card=sim,
            status=PhoneLine.Status.ALLOCATED,
        )
        return LineAllocation.objects.create(
            employee=employee,
            phone_line=line,
            allocated_by=self.admin,
            is_active=True,
        )

    def test_daily_user_action_board_total_card_sums_pending_types(self):
        employee_new = Employee.objects.create(
            full_name="Employee Total New",
            corporate_email="supervisor.total.new@test.com",
            employee_id="Portfolio Total New",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )
        employee_reconnect = Employee.objects.create(
            full_name="Employee Total Reconnect",
            corporate_email="supervisor.total.reconnect@test.com",
            employee_id="Portfolio Total Reconnect",
            teams=Employee.UnitChoices.ARAQUARI,
            status=Employee.Status.ACTIVE,
        )
        employee_pending = Employee.objects.create(
            full_name="Employee Total Pending",
            corporate_email="supervisor.total.pending@test.com",
            employee_id="Portfolio Total Pending",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )

        allocation_new = self._create_active_allocation(employee_new, "101")
        allocation_reconnect = self._create_active_allocation(employee_reconnect, "102")

        AllocationPendency.objects.create(
            employee=employee_new,
            allocation=allocation_new,
            action=AllocationPendency.ActionType.NEW_NUMBER,
        )
        AllocationPendency.objects.create(
            employee=employee_reconnect,
            allocation=allocation_reconnect,
            action=AllocationPendency.ActionType.RECONNECT_WHATSAPP,
        )
        AllocationPendency.objects.create(
            employee=employee_pending,
            allocation=None,
            action=AllocationPendency.ActionType.PENDING,
        )

        response = self.client.get(reverse("daily_user_action_board"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["action_counts"]["new_number"], 1)
        self.assertEqual(response.context["action_counts"]["reconnect_whatsapp"], 1)
        self.assertEqual(response.context["action_counts"]["pending"], 1)
        self.assertEqual(response.context["action_counts"]["total"], 3)
        self.assertContains(response, "Total")
        self.assertContains(response, '<p class="text-muted mb-1">Total</p>', html=False)
        self.assertNotContains(
            response,
            '<p class="text-muted mb-1">Status da Linha</p>',
            html=False,
        )
