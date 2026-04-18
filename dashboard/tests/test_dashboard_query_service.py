from django.test import TestCase

from allocations.models import LineAllocation
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser

from dashboard.services.query_service import (
    build_dashboard_status_counts,
    get_pending_action_counts_for_user,
)


class DashboardQueryServiceScopeTests(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="query.admin@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.supervisor_a = SystemUser.objects.create_user(
            email="query.super.a@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.supervisor_b = SystemUser.objects.create_user(
            email="query.super.b@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )

        self.employee_a = Employee.objects.create(
            full_name="Scoped Employee A",
            corporate_email=self.supervisor_a.email,
            employee_id="Portfolio A",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        self.employee_b = Employee.objects.create(
            full_name="Scoped Employee B",
            corporate_email=self.supervisor_b.email,
            employee_id="Portfolio B",
            teams="Araquari",
            status=Employee.Status.ACTIVE,
        )

    def _create_allocated_line(self, *, suffix: str, employee: Employee, status: str):
        sim = SIMcard.objects.create(
            iccid=f"8900000000000099{suffix}",
            carrier="CarrierScope",
            status=SIMcard.Status.AVAILABLE,
        )
        line = PhoneLine.objects.create(
            phone_number=f"+5511999999{suffix}",
            sim_card=sim,
            status=status,
        )
        LineAllocation.objects.create(
            employee=employee,
            phone_line=line,
            allocated_by=self.admin,
            is_active=True,
        )
        return line

    def test_supervisor_line_status_counts_only_include_scoped_lines(self):
        self._create_allocated_line(
            suffix="101",
            employee=self.employee_a,
            status=PhoneLine.Status.SUSPENDED,
        )
        self._create_allocated_line(
            suffix="102",
            employee=self.employee_a,
            status=PhoneLine.Status.CANCELLED,
        )
        self._create_allocated_line(
            suffix="103",
            employee=self.employee_b,
            status=PhoneLine.Status.SUSPENDED,
        )

        result = build_dashboard_status_counts(self.supervisor_a)
        line_status_counts = {item["value"]: item["count"] for item in result["line_status_counts"]}

        self.assertEqual(line_status_counts.get(PhoneLine.Status.SUSPENDED), 1)
        self.assertEqual(line_status_counts.get(PhoneLine.Status.CANCELLED), 1)

    def test_admin_line_status_counts_include_all_lines(self):
        self._create_allocated_line(
            suffix="201",
            employee=self.employee_a,
            status=PhoneLine.Status.SUSPENDED,
        )
        self._create_allocated_line(
            suffix="202",
            employee=self.employee_b,
            status=PhoneLine.Status.SUSPENDED,
        )

        result = build_dashboard_status_counts(self.admin)
        line_status_counts = {item["value"]: item["count"] for item in result["line_status_counts"]}

        self.assertEqual(line_status_counts.get(PhoneLine.Status.SUSPENDED), 2)

    def test_get_pending_action_counts_uses_single_database_query(self):
        """
        get_pending_action_counts_for_user deve usar apenas 1 query via .aggregate()
        em vez de 3 queries separadas com .count() por tipo de acao.
        """
        with self.assertNumQueries(1):
            get_pending_action_counts_for_user(self.admin)
