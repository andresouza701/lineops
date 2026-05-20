from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from allocations.models import LineAllocation
from dashboard import views as dashboard_views
from dashboard.models import DashboardDailySnapshot
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser


class DashboardCountsPerformanceTest(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="dashboard.counts.admin@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.employee = Employee.objects.create(
            full_name="Dashboard Counts User",
            corporate_email="dashboard-counts@corp.com",
            employee_id="Natura",
            teams="B2C Squad",
            status=Employee.Status.ACTIVE,
        )

        available_sim = SIMcard.objects.create(
            iccid="8900000000000088001",
            carrier="CarrierCounts",
            status=SIMcard.Status.AVAILABLE,
        )
        self.available_line = PhoneLine.objects.create(
            phone_number="+5511988888001",
            sim_card=available_sim,
            status=PhoneLine.Status.AVAILABLE,
        )

        allocated_sim = SIMcard.objects.create(
            iccid="8900000000000088002",
            carrier="CarrierCounts",
            status=SIMcard.Status.AVAILABLE,
        )
        self.allocated_line = PhoneLine.objects.create(
            phone_number="+5511988888002",
            sim_card=allocated_sim,
            status=PhoneLine.Status.ALLOCATED,
        )
        self.allocation = LineAllocation.objects.create(
            employee=self.employee,
            phone_line=self.allocated_line,
            allocated_by=self.admin,
            is_active=True,
        )

    def test_summary_indicator_does_not_build_number_detail_lists(self):
        detail_patch = patch.object(
            dashboard_views,
            "build_number_details_for_day",
            side_effect=AssertionError("summary path must not build details"),
        )
        reconnect_patch = patch.object(
            dashboard_views,
            "build_reconnected_numbers_for_day",
            side_effect=AssertionError("summary path must not build reconnect details"),
        )
        with detail_patch, reconnect_patch:
            indicator = dashboard_views.build_indicator_for_day(timezone.localdate())

        self.assertEqual(indicator["numeros_disponiveis"], 1)
        self.assertEqual(indicator["numeros_entregues"], 1)
        self.assertEqual(indicator["novos"], 2)
        self.assertEqual(indicator["available_numbers"], [])
        self.assertEqual(indicator["delivered_numbers"], [])
        self.assertEqual(indicator["new_numbers"], [])

    def test_current_day_snapshot_does_not_build_number_detail_lists(self):
        detail_patch = patch.object(
            dashboard_views,
            "build_number_details_for_day",
            side_effect=AssertionError("snapshot path must not build details"),
        )
        reconnect_patch = patch.object(
            dashboard_views,
            "build_reconnected_numbers_for_day",
            side_effect=AssertionError("snapshot path must not build reconnect details"),
        )
        with detail_patch, reconnect_patch:
            indicator = dashboard_views.get_dashboard_indicator_for_day(
                timezone.localdate()
            )

        snapshot = DashboardDailySnapshot.objects.get(date=timezone.localdate())
        self.assertEqual(indicator["numeros_disponiveis"], 1)
        self.assertEqual(snapshot.numbers_available, 1)
        self.assertEqual(snapshot.numbers_delivered, 1)
        self.assertEqual(snapshot.numbers_new, 2)

    def test_summary_counts_match_breakdown_detail_lengths(self):
        day = timezone.localdate()

        summary = dashboard_views.build_indicator_for_day(day)
        breakdown = dashboard_views.build_indicator_for_day(
            day,
            include_users=True,
            user=self.admin,
        )

        self.assertEqual(summary["numeros_disponiveis"], len(breakdown["available_numbers"]))
        self.assertEqual(summary["numeros_entregues"], len(breakdown["delivered_numbers"]))
        self.assertEqual(summary["reconectados"], len(breakdown["reconnected_numbers"]))
        self.assertEqual(summary["novos"], len(breakdown["new_numbers"]))
        self.assertEqual(breakdown["available_numbers"][0], self.available_line.phone_number)
        self.assertEqual(
            breakdown["delivered_numbers"][0]["numero"],
            self.allocated_line.phone_number,
        )
