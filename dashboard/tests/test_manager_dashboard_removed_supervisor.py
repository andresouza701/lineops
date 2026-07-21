from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from dashboard.models import DailyUserAction
from employees.models import Employee
from users.models import SystemUser


class ManagerDashboardRemovedSupervisorTest(TestCase):
    def setUp(self):
        self.manager = SystemUser.objects.create_user(
            email="gerente.removed.super@test.com",
            password="StrongPass123",
            role=SystemUser.Role.GERENTE,
        )
        self.supervisor = SystemUser.objects.create_user(
            email="super.removed.super@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
            manager_email=self.manager.email,
        )
        self.client.force_login(self.manager)

    def test_manager_dashboard_does_not_show_removed_supervisor_email(self):
        removed_supervisor_email = "barbara.fonseca@somosglobal.com.br"
        Employee.objects.create(
            full_name="Usuario de Supervisor Removido",
            corporate_email=removed_supervisor_email,
            manager_email=self.manager.email,
            employee_id="Incubadora",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )

        response = self.client.get(reverse("manager_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, f"Supervisor {removed_supervisor_email}")
        self.assertContains(response, "Supervisor Sem supervisor")
        self.assertContains(response, "Incubadora")

    def test_manager_dashboard_actions_use_sem_supervisor_for_removed_supervisor(self):
        removed_supervisor_email = "barbara.fonseca@somosglobal.com.br"
        employee = Employee.objects.create(
            full_name="Usuario de Supervisor Removido",
            corporate_email=removed_supervisor_email,
            manager_email=self.manager.email,
            employee_id="Incubadora",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=employee,
            action_type=DailyUserAction.ActionType.NEW_NUMBER,
            is_resolved=False,
        )

        response = self.client.get(reverse("manager_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, f"Supervisor {removed_supervisor_email}")
        sem_supervisor = next(
            group
            for group in response.context["supervisor_dashboards"]
            if group["supervisor"] == "Sem supervisor"
        )
        row = next(
            item
            for item in sem_supervisor["rows"]
            if item["portfolio"] == "Incubadora"
        )
        self.assertEqual(row["new_number_count"], 1)

    def test_managed_supervisor_emails_ignore_removed_supervisor_from_employee(self):
        removed_supervisor_email = "barbara.fonseca@somosglobal.com.br"
        Employee.objects.create(
            full_name="Usuario de Supervisor Removido",
            corporate_email=removed_supervisor_email,
            manager_email=self.manager.email,
            employee_id="Incubadora",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )

        managed_supervisors = self.manager.get_managed_supervisor_emails()

        self.assertIn(self.supervisor.email, managed_supervisors)
        self.assertNotIn(removed_supervisor_email, managed_supervisors)
