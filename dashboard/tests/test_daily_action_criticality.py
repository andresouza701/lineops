from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from allocations.models import LineAllocation
from dashboard.views import apply_daily_user_action_criticality
from employees.models import Employee
from pendencies.models import AllocationPendency
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser


class DailyUserActionCriticalityTests(SimpleTestCase):
    def _row(self, employee_id, *, line_status=None, action=None):
        has_line = line_status is not None
        allocation = (
            SimpleNamespace(line_status=line_status)
            if has_line
            else None
        )
        pendency = (
            SimpleNamespace(action=action)
            if action is not None
            else None
        )
        return {
            "employee": SimpleNamespace(id=employee_id),
            "has_line": has_line,
            "allocation": allocation,
            "pendency": pendency,
        }

    def _levels_for_employee(self, rows, employee_id):
        return {
            row["criticality_level"]
            for row in rows
            if row["employee"].id == employee_id
        }

    def _row_classes_for_employee(self, rows, employee_id):
        return {
            row["criticality_row_class"]
            for row in rows
            if row["employee"].id == employee_id
        }

    def test_user_without_line_is_high(self):
        rows = [self._row(1)]

        apply_daily_user_action_criticality(rows)

        self.assertEqual(self._levels_for_employee(rows, 1), {"high"})
        self.assertEqual(
            self._row_classes_for_employee(rows, 1),
            {"daily-action-criticality-high"},
        )

    def test_user_with_all_lines_pending_is_high(self):
        rows = [
            self._row(
                1,
                line_status=LineAllocation.LineStatus.RESTRICTED,
                action=AllocationPendency.ActionType.NEW_NUMBER,
            ),
            self._row(
                1,
                line_status=LineAllocation.LineStatus.UNDER_ANALYSIS,
                action=AllocationPendency.ActionType.RECONNECT_WHATSAPP,
            ),
        ]

        apply_daily_user_action_criticality(rows)

        self.assertEqual(self._levels_for_employee(rows, 1), {"high"})

    def test_user_with_two_lines_and_one_pending_is_medium(self):
        rows = [
            self._row(
                1,
                line_status=LineAllocation.LineStatus.RESTRICTED,
                action=AllocationPendency.ActionType.PENDING,
            ),
            self._row(
                1,
                line_status=LineAllocation.LineStatus.ACTIVE,
                action=AllocationPendency.ActionType.NO_ACTION,
            ),
        ]

        apply_daily_user_action_criticality(rows)

        self.assertEqual(self._levels_for_employee(rows, 1), {"medium"})
        self.assertEqual(
            self._row_classes_for_employee(rows, 1),
            {"daily-action-criticality-medium"},
        )

    def test_user_with_two_or_more_lines_without_pending_is_low(self):
        rows = [
            self._row(
                1,
                line_status=LineAllocation.LineStatus.ACTIVE,
                action=AllocationPendency.ActionType.NO_ACTION,
            ),
            self._row(
                1,
                line_status=LineAllocation.LineStatus.ACTIVE,
                action=AllocationPendency.ActionType.NO_ACTION,
            ),
            self._row(
                1,
                line_status=LineAllocation.LineStatus.RESTRICTED,
                action=AllocationPendency.ActionType.NO_ACTION,
            ),
        ]

        apply_daily_user_action_criticality(rows)

        self.assertEqual(self._levels_for_employee(rows, 1), {"low"})
        self.assertEqual(
            self._row_classes_for_employee(rows, 1),
            {"daily-action-criticality-low"},
        )

    def test_pending_requires_status_issue_and_non_empty_action(self):
        rows = [
            self._row(
                1,
                line_status=LineAllocation.LineStatus.RESTRICTED,
                action=AllocationPendency.ActionType.NO_ACTION,
            ),
            self._row(
                1,
                line_status=LineAllocation.LineStatus.ACTIVE,
                action=AllocationPendency.ActionType.PENDING,
            ),
        ]

        apply_daily_user_action_criticality(rows)

        self.assertEqual(self._levels_for_employee(rows, 1), {"low"})

    def test_user_with_single_active_line_is_high_fallback(self):
        rows = [
            self._row(
                1,
                line_status=LineAllocation.LineStatus.ACTIVE,
                action=AllocationPendency.ActionType.NO_ACTION,
            ),
        ]

        apply_daily_user_action_criticality(rows)

        self.assertEqual(self._levels_for_employee(rows, 1), {"high"})


class DailyUserActionCriticalityBoardRenderingTests(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="criticality.admin@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.supervisor = SystemUser.objects.create_user(
            email="criticality.supervisor@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.client.force_login(self.supervisor)
        self.employee = Employee.objects.create(
            full_name="Criticality Medium User",
            corporate_email=self.supervisor.email,
            employee_id="Portfolio Criticality",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )

    def _create_allocation(self, suffix, line_status):
        sim = SIMcard.objects.create(
            iccid=f"8900000000000088{suffix}",
            carrier="CarrierCriticality",
            status=SIMcard.Status.AVAILABLE,
        )
        line = PhoneLine.objects.create(
            phone_number=f"+5511988888{suffix}",
            sim_card=sim,
            status=PhoneLine.Status.ALLOCATED,
        )
        return LineAllocation.objects.create(
            employee=self.employee,
            phone_line=line,
            allocated_by=self.supervisor,
            is_active=True,
            line_status=line_status,
        )

    def _create_medium_criticality_dataset(self):
        restricted_allocation = self._create_allocation(
            "101",
            LineAllocation.LineStatus.RESTRICTED,
        )
        self._create_allocation("102", LineAllocation.LineStatus.ACTIVE)
        AllocationPendency.objects.create(
            employee=self.employee,
            allocation=restricted_allocation,
            action=AllocationPendency.ActionType.PENDING,
        )

    def test_action_board_hides_criticality_column_for_non_admin(self):
        self._create_medium_criticality_dataset()

        response = self.client.get(reverse("daily_user_action_board"))

        self.assertEqual(response.status_code, 200)
        matching_rows = [
            row
            for row in response.context["rows"]
            if row["employee"].id == self.employee.id
        ]
        self.assertEqual(len(matching_rows), 2)
        self.assertEqual(
            {row["criticality_level"] for row in matching_rows},
            {"medium"},
        )
        self.assertEqual(
            {row["criticality_row_class"] for row in matching_rows},
            {"daily-action-criticality-medium"},
        )
        self.assertNotContains(response, "Criticidade")
        self.assertContains(response, "daily-action-criticality-medium")
        self.assertContains(response, "daily-action-table")
        self.assertContains(
            response,
            "box-shadow: inset 5px 0 0 var(--criticality-accent)",
        )
        self.assertNotContains(response, "criticality-row-bg")

    def test_action_board_renders_criticality_column_for_admin(self):
        self._create_medium_criticality_dataset()
        self.client.force_login(self.admin)

        response = self.client.get(reverse("daily_user_action_board"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Criticidade")
