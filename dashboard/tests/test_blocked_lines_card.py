from django.test import TestCase
from django.urls import reverse

from allocations.models import LineAllocation
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser


class DashboardBlockedLinesCardTest(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="dashboard.blocked@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.supervisor_a = SystemUser.objects.create_user(
            email="super.a.blocked@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.supervisor_b = SystemUser.objects.create_user(
            email="super.b.blocked@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.manager = SystemUser.objects.create_user(
            email="manager.blocked@test.com",
            password="StrongPass123",
            role=SystemUser.Role.GERENTE,
        )
        self.other_manager = SystemUser.objects.create_user(
            email="other.manager.blocked@test.com",
            password="StrongPass123",
            role=SystemUser.Role.GERENTE,
        )
        self.supervisor_a.manager_email = self.manager.email
        self.supervisor_a.save(update_fields=["manager_email"])
        self.supervisor_b.manager_email = self.other_manager.email
        self.supervisor_b.save(update_fields=["manager_email"])
        self.client.force_login(self.admin)

    def _create_blocked_line_for_employee(
        self, *, suffix: str, employee: Employee, line_status: str, sim_status: str
    ):
        sim = SIMcard.objects.create(
            iccid=f"8900000000000013{suffix}",
            carrier="CarrierBlocked",
            status=sim_status,
        )
        line = PhoneLine.objects.create(
            phone_number=f"+5511999913{suffix}",
            sim_card=sim,
            status=line_status,
        )
        LineAllocation.objects.create(
            employee=employee,
            phone_line=line,
            allocated_by=self.admin,
            is_active=True,
        )
        return line

    def _blocked_lines_card_value(self, response):
        cards = response.context["exception_cards"]
        blocked_lines_card = next(
            card for card in cards if card["title"] == "Linhas bloqueadas"
        )
        return blocked_lines_card["value"]

    def test_dashboard_exception_card_counts_suspended_and_cancelled_lines(self):
        suspended_sim = SIMcard.objects.create(
            iccid="8900000000000012997",
            carrier="CarrierBlocked",
            status=SIMcard.Status.BLOCKED,
        )
        cancelled_sim = SIMcard.objects.create(
            iccid="8900000000000012998",
            carrier="CarrierBlocked",
            status=SIMcard.Status.CANCELLED,
        )
        PhoneLine.objects.create(
            phone_number="+5511999912997",
            sim_card=suspended_sim,
            status=PhoneLine.Status.SUSPENDED,
        )
        PhoneLine.objects.create(
            phone_number="+5511999912998",
            sim_card=cancelled_sim,
            status=PhoneLine.Status.CANCELLED,
        )

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._blocked_lines_card_value(response), 2)

    def test_supervisor_counts_only_blocked_lines_from_own_team(self):
        employee_a = Employee.objects.create(
            full_name="Blocked Team A",
            corporate_email=self.supervisor_a.email,
            manager_email=self.manager.email,
            employee_id="Portfolio A",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        employee_b = Employee.objects.create(
            full_name="Blocked Team B",
            corporate_email=self.supervisor_b.email,
            manager_email=self.other_manager.email,
            employee_id="Portfolio B",
            teams="Araquari",
            status=Employee.Status.ACTIVE,
        )

        self._create_blocked_line_for_employee(
            suffix="001",
            employee=employee_a,
            line_status=PhoneLine.Status.SUSPENDED,
            sim_status=SIMcard.Status.BLOCKED,
        )
        self._create_blocked_line_for_employee(
            suffix="002",
            employee=employee_a,
            line_status=PhoneLine.Status.CANCELLED,
            sim_status=SIMcard.Status.CANCELLED,
        )
        self._create_blocked_line_for_employee(
            suffix="003",
            employee=employee_b,
            line_status=PhoneLine.Status.SUSPENDED,
            sim_status=SIMcard.Status.BLOCKED,
        )

        self.client.force_login(self.supervisor_a)
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._blocked_lines_card_value(response), 2)

    def test_manager_counts_only_blocked_lines_from_managed_scope(self):
        employee_managed_supervisor = Employee.objects.create(
            full_name="Blocked Managed Supervisor",
            corporate_email=self.supervisor_a.email,
            manager_email=self.manager.email,
            employee_id="Portfolio C",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        employee_direct_manager = Employee.objects.create(
            full_name="Blocked Direct Manager",
            corporate_email="direct.supervisor@test.com",
            manager_email=self.manager.email,
            employee_id="Portfolio D",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        employee_outside_scope = Employee.objects.create(
            full_name="Blocked Outside Scope",
            corporate_email=self.supervisor_b.email,
            manager_email=self.other_manager.email,
            employee_id="Portfolio E",
            teams="Araquari",
            status=Employee.Status.ACTIVE,
        )

        self._create_blocked_line_for_employee(
            suffix="004",
            employee=employee_managed_supervisor,
            line_status=PhoneLine.Status.SUSPENDED,
            sim_status=SIMcard.Status.BLOCKED,
        )
        self._create_blocked_line_for_employee(
            suffix="005",
            employee=employee_direct_manager,
            line_status=PhoneLine.Status.CANCELLED,
            sim_status=SIMcard.Status.CANCELLED,
        )
        self._create_blocked_line_for_employee(
            suffix="006",
            employee=employee_outside_scope,
            line_status=PhoneLine.Status.SUSPENDED,
            sim_status=SIMcard.Status.BLOCKED,
        )

        self.client.force_login(self.manager)
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._blocked_lines_card_value(response), 2)
