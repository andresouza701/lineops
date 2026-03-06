from django.test import TestCase
from django.urls import reverse

from allocations.models import LineAllocation
from core.current_user import clear_current_user, set_current_user
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser

from .forms import EmployeeForm
from .models import Employee, EmployeeHistory


class EmployeeModelTest(TestCase):
    def setUp(self) -> None:
        self.base_data = {
            "full_name": "Aline Martins",
            "corporate_email": "aline.martins@lineops.tech",
            "employee_id": "EMP-1001",
            "teams": Employee.UnitChoices.JOINVILLE,
            "status": Employee.Status.ACTIVE,
        }

    def test_status_is_persisted(self) -> None:
        employee = Employee.objects.create(**self.base_data)
        stored = Employee.all_objects.get(pk=employee.pk)
        self.assertEqual(stored.status, Employee.Status.ACTIVE)

    def test_soft_delete_marks_record_and_filters_out(self) -> None:
        employee = Employee.objects.create(**self.base_data)
        employee.delete()

        reloaded = Employee.all_objects.get(pk=employee.pk)
        self.assertTrue(reloaded.is_deleted)
        self.assertEqual(Employee.objects.filter(pk=employee.pk).count(), 0)


class EmployeeListViewTest(TestCase):
    def setUp(self) -> None:
        self.admin = SystemUser.objects.create_user(
            email="admin@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.operator = SystemUser.objects.create_user(
            email="operator@test.com",
            password="StrongPass123",
            role=SystemUser.Role.OPERATOR,
        )
        self.supervisor = SystemUser.objects.create_user(
            email="super@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.employee = Employee.objects.create(
            full_name="Aline Martins",
            corporate_email="aline.martins@lineops.tech",
            employee_id="EMP-1001",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )

        sim = SIMcard.objects.create(
            iccid="12345678901234567890",
            carrier="CarrierX",
            status=SIMcard.Status.AVAILABLE,
        )
        line = PhoneLine.objects.create(
            phone_number="+5511999999999",
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
        )
        LineAllocation.objects.create(
            employee=self.employee,
            phone_line=line,
            is_active=True,
        )

    def test_admin_can_filter_by_name(self) -> None:
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("employees:employee_list"), {"name": "Aline"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aline Martins")

    def test_admin_can_filter_by_line(self) -> None:
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("employees:employee_list"), {"line": "999999999"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aline Martins")

    def test_employee_list_shows_line_column_with_linked_line(self) -> None:
        self.client.force_login(self.admin)
        response = self.client.get(reverse("employees:employee_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<th>Linha</th>", html=False)
        self.assertContains(response, "+5511999999999")

    def test_admin_can_filter_by_team(self) -> None:
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("employees:employee_list"), {"team": "Joinville"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aline Martins")

    def test_operator_cannot_access_employee_list(self) -> None:
        self.client.force_login(self.operator)
        response = self.client.get(reverse("employees:employee_list"))
        self.assertEqual(response.status_code, 403)

    def test_super_can_access_employee_list(self) -> None:
        self.client.force_login(self.supervisor)
        response = self.client.get(reverse("employees:employee_list"))
        self.assertEqual(response.status_code, 200)

    def test_super_can_access_employee_update(self) -> None:
        self.client.force_login(self.supervisor)
        response = self.client.get(
            reverse("employees:employee_update", args=[self.employee.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_super_does_not_see_history_button(self) -> None:
        self.client.force_login(self.supervisor)
        response = self.client.get(reverse("employees:employee_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("employees:employee_update", args=[self.employee.pk]),
        )
        self.assertNotContains(
            response,
            reverse("employees:employee_history", args=[self.employee.pk]),
        )

    def test_anonymous_cannot_access_employee_list(self) -> None:
        response = self.client.get(reverse("employees:employee_list"))
        self.assertEqual(response.status_code, 403)

    def test_employee_list_shows_history_button_for_admin(self) -> None:
        self.client.force_login(self.admin)
        response = self.client.get(reverse("employees:employee_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("employees:employee_history", args=[self.employee.pk]),
        )


class EmployeeHistoryAuditTest(TestCase):
    def setUp(self) -> None:
        self.admin = SystemUser.objects.create_user(
            email="admin.history@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.operator = SystemUser.objects.create_user(
            email="operator.history@test.com",
            password="StrongPass123",
            role=SystemUser.Role.OPERATOR,
        )
        self.employee = Employee.objects.create(
            full_name="Usuario Historico",
            corporate_email="historico@lineops.tech",
            employee_id="EMP-H-01",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )

    def test_history_is_created_for_create_update_status_and_delete(self) -> None:
        set_current_user(self.admin)
        try:
            self.employee.full_name = "Usuario Historico Atualizado"
            self.employee.save(update_fields=["full_name"])

            self.employee.status = Employee.Status.INACTIVE
            self.employee.save(update_fields=["status"])

            self.employee.delete()
        finally:
            clear_current_user()

        actions = set(
            EmployeeHistory.objects.filter(employee=self.employee).values_list(
                "action", flat=True
            )
        )
        self.assertIn(EmployeeHistory.ActionType.CREATED, actions)
        self.assertIn(EmployeeHistory.ActionType.UPDATED, actions)
        self.assertIn(EmployeeHistory.ActionType.STATUS_CHANGED, actions)
        self.assertIn(EmployeeHistory.ActionType.DELETED, actions)

    def test_history_view_admin_only(self) -> None:
        url = reverse("employees:employee_history", args=[self.employee.pk])

        self.client.force_login(self.operator)
        denied = self.client.get(url)
        self.assertEqual(denied.status_code, 403)

        self.client.force_login(self.admin)
        ok = self.client.get(url)
        self.assertEqual(ok.status_code, 200)
        self.assertIn("history", ok.context)

    def test_history_view_denies_super_user(self) -> None:
        url = reverse("employees:employee_history", args=[self.employee.pk])
        self.client.force_login(
            SystemUser.objects.create_user(
                email="super.history@test.com",
                password="StrongPass123",
                role=SystemUser.Role.SUPER,
            )
        )
        denied = self.client.get(url)
        self.assertEqual(denied.status_code, 403)

    def test_pa_change_is_recorded_in_updated_history(self) -> None:
        set_current_user(self.admin)
        try:
            self.employee.pa = "PA-123"
            self.employee.save(update_fields=["pa"])
        finally:
            clear_current_user()

        updated_event = EmployeeHistory.objects.filter(
            employee=self.employee,
            action=EmployeeHistory.ActionType.UPDATED,
        ).first()

        self.assertIsNotNone(updated_event)
        self.assertIn("PA:", updated_event.new_value)
        self.assertIn("PA-123", updated_event.new_value)


class EmployeeFormPortfolioChoicesTest(TestCase):
    def test_form_shows_b2c_portfolios_in_employee_id_choices(self) -> None:
        form = EmployeeForm()
        portfolio_html = str(form["employee_id"])

        for portfolio in ["Ambiental", "Natura", "ViaSat", "Opera", "Valid"]:
            self.assertIn(portfolio, portfolio_html)

    def test_form_requires_portfolio_and_team(self) -> None:
        form = EmployeeForm(
            data={
                "full_name": "New User",
                "corporate_email": "supervisor@test.com",
                "employee_id": "",
                "teams": "",
                "status": Employee.Status.ACTIVE,
                "pa": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("employee_id", form.errors)
        self.assertIn("teams", form.errors)
