from django.test import TestCase
from django.utils import timezone

from allocations.models import LineAllocation
from dashboard.services.metrics_service import build_pendency_metrics
from employees.models import Employee
from pendencies.models import AllocationPendency
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser


class PendencyMetricsServiceTests(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="metrics.admin@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
            first_name="Metrics",
            last_name="Admin",
        )
        self.tech_a = SystemUser.objects.create_user(
            email="tech.a@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
            first_name="Tech",
            last_name="A",
        )
        self.tech_b = SystemUser.objects.create_user(
            email="tech.b@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
            first_name="Tech",
            last_name="B",
        )
        self.supervisor_a = SystemUser.objects.create_user(
            email="super.a@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.supervisor_b = SystemUser.objects.create_user(
            email="super.b@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.employee_a = Employee.objects.create(
            full_name="Metric Employee A",
            corporate_email=self.supervisor_a.email,
            employee_id="Portfolio A",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        self.employee_b = Employee.objects.create(
            full_name="Metric Employee B",
            corporate_email=self.supervisor_b.email,
            employee_id="Portfolio B",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )

    def _create_allocation(self, employee, suffix, line_status):
        sim = SIMcard.objects.create(
            iccid=f"89000000000011{suffix}",
            carrier="MetricCarrier",
            status=SIMcard.Status.AVAILABLE,
        )
        line = PhoneLine.objects.create(
            phone_number=f"+5511999911{suffix}",
            sim_card=sim,
            status=PhoneLine.Status.ALLOCATED,
        )
        return LineAllocation.objects.create(
            employee=employee,
            phone_line=line,
            allocated_by=self.admin,
            is_active=True,
            line_status=line_status,
        )

    def test_admin_metrics_rank_responsibles_by_open_assigned_pendencies(self):
        restricted = self._create_allocation(
            self.employee_a,
            "001",
            LineAllocation.LineStatus.RESTRICTED,
        )
        banned = self._create_allocation(
            self.employee_a,
            "002",
            LineAllocation.LineStatus.PERMANENTLY_BANNED,
        )
        waiting = self._create_allocation(
            self.employee_b,
            "003",
            LineAllocation.LineStatus.WAITING_OPERATOR,
        )

        AllocationPendency.objects.create(
            employee=self.employee_a,
            allocation=restricted,
            action=AllocationPendency.ActionType.PENDING,
            technical_responsible=self.tech_a,
        )
        AllocationPendency.objects.create(
            employee=self.employee_a,
            allocation=banned,
            action=AllocationPendency.ActionType.RECONNECT_WHATSAPP,
            technical_responsible=self.tech_a,
        )
        AllocationPendency.objects.create(
            employee=self.employee_b,
            allocation=waiting,
            action=AllocationPendency.ActionType.NEW_NUMBER,
            technical_responsible=self.tech_b,
        )

        result = build_pendency_metrics(self.admin)

        self.assertEqual(result["summary"]["open_total"], 3)
        self.assertEqual(result["summary"]["assigned_total"], 3)
        self.assertEqual(result["summary"]["unassigned_total"], 0)
        self.assertEqual(result["summary"]["restricted_assigned_total"], 1)
        self.assertEqual(result["summary"]["banned_assigned_total"], 1)
        self.assertEqual(result["responsible_rankings"][0]["responsible_id"], self.tech_a.id)
        self.assertEqual(result["responsible_rankings"][0]["total"], 2)
        self.assertEqual(result["responsible_rankings"][0]["restricted"], 1)
        self.assertEqual(result["responsible_rankings"][0]["permanently_banned"], 1)
        self.assertEqual(result["responsible_rankings"][0]["reconnect_whatsapp"], 1)
        self.assertEqual(result["responsible_rankings"][1]["responsible_id"], self.tech_b.id)
        self.assertEqual(result["responsible_rankings"][1]["total"], 1)

    def test_metrics_group_unassigned_and_count_actions_board_responsible(self):
        allocation = self._create_allocation(
            self.employee_a,
            "101",
            LineAllocation.LineStatus.RESTRICTED,
        )
        ignored = self._create_allocation(
            self.employee_a,
            "102",
            LineAllocation.LineStatus.PERMANENTLY_BANNED,
        )
        AllocationPendency.objects.create(
            employee=self.employee_a,
            allocation=allocation,
            action=AllocationPendency.ActionType.PENDING,
        )
        AllocationPendency.objects.create(
            employee=self.employee_a,
            allocation=ignored,
            action=AllocationPendency.ActionType.NO_ACTION,
            technical_responsible=self.tech_a,
        )

        result = build_pendency_metrics(self.admin)

        self.assertEqual(result["summary"]["open_total"], 1)
        self.assertEqual(result["summary"]["assigned_total"], 1)
        self.assertEqual(result["summary"]["unassigned_total"], 1)
        self.assertEqual(result["unassigned_breakdown"]["total"], 1)
        self.assertEqual(result["unassigned_breakdown"]["restricted"], 1)
        self.assertEqual(result["unassigned_breakdown"]["permanently_banned"], 0)
        self.assertEqual(result["responsible_rankings"][0]["responsible_id"], self.tech_a.id)
        self.assertEqual(result["responsible_rankings"][0]["total"], 1)

    def test_metrics_use_employee_line_status_without_allocation(self):
        self.employee_a.line_status = Employee.LineStatus.PERMANENTLY_BANNED
        self.employee_a.save(update_fields=["line_status"])
        AllocationPendency.objects.create(
            employee=self.employee_a,
            allocation=None,
            action=AllocationPendency.ActionType.PENDING,
            technical_responsible=self.tech_a,
        )

        result = build_pendency_metrics(self.admin)

        self.assertEqual(result["summary"]["banned_assigned_total"], 1)
        self.assertEqual(result["responsible_rankings"][0]["permanently_banned"], 1)

    def test_supervisor_scope_only_includes_their_employees(self):
        allocation_a = self._create_allocation(
            self.employee_a,
            "201",
            LineAllocation.LineStatus.RESTRICTED,
        )
        allocation_b = self._create_allocation(
            self.employee_b,
            "202",
            LineAllocation.LineStatus.PERMANENTLY_BANNED,
        )
        AllocationPendency.objects.create(
            employee=self.employee_a,
            allocation=allocation_a,
            action=AllocationPendency.ActionType.PENDING,
            technical_responsible=self.tech_a,
        )
        AllocationPendency.objects.create(
            employee=self.employee_b,
            allocation=allocation_b,
            action=AllocationPendency.ActionType.PENDING,
            technical_responsible=self.tech_b,
        )

        result = build_pendency_metrics(self.supervisor_a)

        self.assertEqual(result["summary"]["open_total"], 1)
        self.assertEqual(result["responsible_rankings"][0]["responsible_id"], self.tech_a.id)

    def test_filters_apply_to_summary_and_ranking(self):
        restricted = self._create_allocation(
            self.employee_a,
            "301",
            LineAllocation.LineStatus.RESTRICTED,
        )
        banned = self._create_allocation(
            self.employee_a,
            "302",
            LineAllocation.LineStatus.PERMANENTLY_BANNED,
        )
        AllocationPendency.objects.create(
            employee=self.employee_a,
            allocation=restricted,
            action=AllocationPendency.ActionType.PENDING,
            technical_responsible=self.tech_a,
        )
        AllocationPendency.objects.create(
            employee=self.employee_a,
            allocation=banned,
            action=AllocationPendency.ActionType.RECONNECT_WHATSAPP,
            technical_responsible=self.tech_a,
        )

        result = build_pendency_metrics(
            self.admin,
            filters={"line_status": LineAllocation.LineStatus.RESTRICTED},
        )

        self.assertEqual(result["summary"]["open_total"], 1)
        self.assertEqual(result["summary"]["restricted_assigned_total"], 1)
        self.assertEqual(result["summary"]["banned_assigned_total"], 0)
        self.assertEqual(result["responsible_rankings"][0]["total"], 1)
        self.assertEqual(result["responsible_rankings"][0]["restricted"], 1)

    def test_metrics_include_resolved_total_since_start_by_user(self):
        current = self._create_allocation(
            self.employee_a,
            "401",
            LineAllocation.LineStatus.RESTRICTED,
        )
        resolved = self._create_allocation(
            self.employee_b,
            "402",
            LineAllocation.LineStatus.PERMANENTLY_BANNED,
        )
        AllocationPendency.objects.create(
            employee=self.employee_a,
            allocation=current,
            action=AllocationPendency.ActionType.PENDING,
            technical_responsible=self.tech_a,
        )
        AllocationPendency.objects.create(
            employee=self.employee_b,
            allocation=resolved,
            action=AllocationPendency.ActionType.NO_ACTION,
            resolved_at=timezone.now(),
            updated_by=self.tech_b,
            last_submitted_action=AllocationPendency.ActionType.RECONNECT_WHATSAPP,
        )

        result = build_pendency_metrics(self.admin)

        rankings_by_id = {
            row["responsible_id"]: row for row in result["responsible_rankings"]
        }
        self.assertEqual(rankings_by_id[self.tech_a.id]["total"], 1)
        self.assertEqual(rankings_by_id[self.tech_a.id]["resolved_total"], 0)
        self.assertEqual(rankings_by_id[self.tech_b.id]["total"], 0)
        self.assertEqual(rankings_by_id[self.tech_b.id]["resolved_total"], 1)

    def test_current_total_matches_actions_board_technical_responsible_rows(self):
        restricted = self._create_allocation(
            self.employee_a,
            "501",
            LineAllocation.LineStatus.RESTRICTED,
        )
        AllocationPendency.objects.create(
            employee=self.employee_a,
            allocation=restricted,
            action=AllocationPendency.ActionType.NO_ACTION,
            technical_responsible=self.tech_a,
        )

        result = build_pendency_metrics(self.admin)

        self.assertEqual(result["summary"]["assigned_total"], 1)
        self.assertEqual(result["responsible_rankings"][0]["responsible_id"], self.tech_a.id)
        self.assertEqual(result["responsible_rankings"][0]["total"], 1)
