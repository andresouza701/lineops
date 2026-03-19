from unittest.mock import patch

from django.contrib import admin
from django.db import IntegrityError
from django.test import RequestFactory, TestCase
from django.urls import reverse

from allocations.models import LineAllocation
from core.current_user import clear_current_user, set_current_user
from core.services.allocation_service import AllocationService
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser

from .admin import EmployeeAdmin, EmployeeAdminForm
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

    def test_active_employees_cannot_repeat_full_name_case_insensitive(self) -> None:
        Employee.objects.create(**self.base_data)

        with self.assertRaises(IntegrityError):
            Employee.objects.create(
                full_name="aline martins",
                corporate_email="aline.dup@lineops.tech",
                employee_id="EMP-1002",
                teams=Employee.UnitChoices.ARAQUARI,
                status=Employee.Status.ACTIVE,
            )


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
            manager_email="gerente@test.com",
        )
        self.manager = SystemUser.objects.create_user(
            email="gerente@test.com",
            password="StrongPass123",
            role=SystemUser.Role.GERENTE,
        )
        self.other_supervisor = SystemUser.objects.create_user(
            email="outro.super@test.com",
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
        self.supervisor_employee = Employee.objects.create(
            full_name="Usuario do Super",
            corporate_email=self.supervisor.email,
            employee_id="EMP-1002",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )
        self.manager_employee = Employee.objects.create(
            full_name="Usuario do Gerente",
            corporate_email=self.supervisor.email,
            employee_id="EMP-1003",
            teams=Employee.UnitChoices.ARAQUARI,
            status=Employee.Status.ACTIVE,
        )
        self.unrelated_manager_employee = Employee.objects.create(
            full_name="Usuario de Outro Super",
            corporate_email=self.other_supervisor.email,
            employee_id="EMP-1004",
            teams=Employee.UnitChoices.ARAQUARI,
            status=Employee.Status.ACTIVE,
            manager_email="outro.gerente@test.com",
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
            reverse("employees:employee_update", args=[self.supervisor_employee.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_manager_can_access_employee_list(self) -> None:
        self.client.force_login(self.manager)
        response = self.client.get(reverse("employees:employee_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Usuario do Gerente")
        self.assertContains(response, "Usuario do Super")
        self.assertNotContains(response, "Usuario de Outro Super")

    def test_manager_can_access_employee_update(self) -> None:
        self.client.force_login(self.manager)
        response = self.client.get(
            reverse("employees:employee_update", args=[self.manager_employee.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_manager_cannot_access_unrelated_employee_update(self) -> None:
        self.client.force_login(self.manager)
        response = self.client.get(
            reverse(
                "employees:employee_update", args=[self.unrelated_manager_employee.pk]
            )
        )
        self.assertEqual(response.status_code, 404)

    def test_manager_does_not_see_history_button(self) -> None:
        self.client.force_login(self.manager)
        response = self.client.get(reverse("employees:employee_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("employees:employee_update", args=[self.manager_employee.pk]),
        )
        self.assertNotContains(
            response,
            reverse("employees:employee_history", args=[self.manager_employee.pk]),
        )

    def test_super_does_not_see_history_button(self) -> None:
        self.client.force_login(self.supervisor)
        response = self.client.get(reverse("employees:employee_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("employees:employee_update", args=[self.supervisor_employee.pk]),
        )
        self.assertNotContains(
            response,
            reverse("employees:employee_history", args=[self.supervisor_employee.pk]),
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

    def test_history_view_denies_manager_user(self) -> None:
        url = reverse("employees:employee_history", args=[self.employee.pk])
        self.client.force_login(
            SystemUser.objects.create_user(
                email="gerente.history@test.com",
                password="StrongPass123",
                role=SystemUser.Role.GERENTE,
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

    def test_deactivate_view_releases_active_allocations_before_soft_delete(
        self,
    ) -> None:
        self.client.force_login(self.admin)
        sim = SIMcard.objects.create(
            iccid="8900000000000012345",
            carrier="Carrier Rel",
            status=SIMcard.Status.AVAILABLE,
        )
        line = PhoneLine.objects.create(
            phone_number="+5511999994321",
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
        )
        allocation = AllocationService.allocate_line(
            employee=self.employee,
            phone_line=line,
            allocated_by=self.admin,
        )

        response = self.client.post(
            reverse("employees:employee_deactivate", args=[self.employee.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.employee.refresh_from_db()
        allocation.refresh_from_db()
        line.refresh_from_db()
        self.assertTrue(self.employee.is_deleted)
        self.assertFalse(allocation.is_active)
        self.assertEqual(line.status, PhoneLine.Status.AVAILABLE)


class EmployeeFormPortfolioChoicesTest(TestCase):
    def test_form_shows_manager_choices_when_manager_users_exist(self) -> None:
        SystemUser.objects.create_user(
            email="gerente.form@test.com",
            password="StrongPass123",
            role=SystemUser.Role.GERENTE,
        )

        form = EmployeeForm()

        self.assertIn("gerente.form@test.com", str(form["manager_email"]))

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

    def test_form_blocks_duplicate_full_name(self) -> None:
        Employee.objects.create(
            full_name="Maria Silva",
            corporate_email="maria@lineops.tech",
            employee_id="Carteira A",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )

        form = EmployeeForm(
            data={
                "full_name": "  maria silva  ",
                "corporate_email": "supervisor@test.com",
                "employee_id": "Ambiental",
                "teams": Employee.UnitChoices.JOINVILLE,
                "status": Employee.Status.ACTIVE,
                "pa": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("full_name", form.errors)

    def test_form_allows_updating_same_employee_name(self) -> None:
        employee = Employee.objects.create(
            full_name="Carlos Dias",
            corporate_email="carlos@lineops.tech",
            employee_id="Carteira B",
            teams=Employee.UnitChoices.ARAQUARI,
            status=Employee.Status.ACTIVE,
        )

        form = EmployeeForm(
            data={
                "full_name": " carlos dias ",
                "corporate_email": "supervisor@test.com",
                "employee_id": "Ambiental",
                "teams": Employee.UnitChoices.ARAQUARI,
                "status": Employee.Status.ACTIVE,
                "pa": "",
            },
            instance=employee,
        )

        self.assertTrue(form.is_valid())


class EmployeeCreateUpdateIntegrityHandlingTest(TestCase):
    def setUp(self) -> None:
        self.admin = SystemUser.objects.create_user(
            email="admin.integrity@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.employee = Employee.objects.create(
            full_name="Usuario Original",
            corporate_email="supervisor@test.com",
            employee_id="EMP-I-01",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )
        self.client.force_login(self.admin)

    def test_create_view_handles_duplicate_full_name_integrity_error(self) -> None:
        with patch(
            "employees.views.CreateView.form_valid",
            side_effect=IntegrityError(
                "duplicate key value violates unique constraint "
                "employees_employee_unique_active_full_name_ci"
            ),
        ):
            response = self.client.post(
                reverse("employees:employee_create"),
                {
                    "full_name": "Usuario Novo",
                    "corporate_email": "supervisor@test.com",
                    "employee_id": "Ambiental",
                    "teams": Employee.UnitChoices.JOINVILLE,
                    "status": Employee.Status.ACTIVE,
                    "pa": "",
                },
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Corrija os erros do usuário.")
        self.assertContains(response, "Já existe um usuário cadastrado com este nome.")

    def test_update_view_handles_duplicate_full_name_integrity_error(self) -> None:
        with patch(
            "employees.views.UpdateView.form_valid",
            side_effect=IntegrityError(
                "duplicate key value violates unique constraint "
                "employees_employee_unique_active_full_name_ci"
            ),
        ):
            response = self.client.post(
                reverse("employees:employee_update", args=[self.employee.pk]),
                {
                    "full_name": "Usuario Original",
                    "corporate_email": "supervisor@test.com",
                    "employee_id": "Ambiental",
                    "teams": Employee.UnitChoices.JOINVILLE,
                    "status": Employee.Status.ACTIVE,
                    "pa": "",
                },
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Corrija os erros do usuário.")
        self.assertContains(response, "Já existe um usuário cadastrado com este nome.")


class EmployeeAdminFormValidationTest(TestCase):
    def test_admin_form_rejects_duplicate_full_name_case_insensitive(self) -> None:
        Employee.objects.create(
            full_name="Teste Super 01",
            corporate_email="supervisor1@test.com",
            employee_id="EMP-ADM-1",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )

        form = EmployeeAdminForm(
            data={
                "full_name": " teste super 01 ",
                "corporate_email": "supervisor2@test.com",
                "employee_id": "EMP-ADM-2",
                "teams": Employee.UnitChoices.JOINVILLE,
                "status": Employee.Status.ACTIVE,
                "line_status": Employee.LineStatus.ACTIVE,
                "pa": "",
                "is_deleted": False,
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("full_name", form.errors)

    def test_admin_form_allows_same_name_for_same_instance(self) -> None:
        employee = Employee.objects.create(
            full_name="Teste Super 02",
            corporate_email="supervisor1@test.com",
            employee_id="EMP-ADM-3",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )

        form = EmployeeAdminForm(
            data={
                "full_name": " teste super 02 ",
                "corporate_email": "supervisor1@test.com",
                "employee_id": "EMP-ADM-3",
                "teams": Employee.UnitChoices.JOINVILLE,
                "status": Employee.Status.ACTIVE,
                "line_status": Employee.LineStatus.ACTIVE,
                "pa": "",
                "is_deleted": False,
            },
            instance=employee,
        )

        self.assertTrue(form.is_valid())


class EmployeeAdminDeleteBehaviorTest(TestCase):
    def setUp(self) -> None:
        self.request = RequestFactory().get("/admin/employees/employee/")
        self.employee_admin = EmployeeAdmin(Employee, admin.site)

        self.employee = Employee.objects.create(
            full_name="Negociador Admin",
            corporate_email="supervisor@test.com",
            employee_id="Pepsico",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )
        self.sim = SIMcard.objects.create(
            iccid="8900000000000099999",
            carrier="Carrier Admin",
            status=SIMcard.Status.AVAILABLE,
        )
        self.line = PhoneLine.objects.create(
            phone_number="+5511999997788",
            sim_card=self.sim,
            status=PhoneLine.Status.AVAILABLE,
        )
        LineAllocation.objects.create(
            employee=self.employee,
            phone_line=self.line,
            is_active=True,
        )

    def test_get_deleted_objects_does_not_report_protected_relations(self) -> None:
        _, _, _, protected = self.employee_admin.get_deleted_objects(
            [self.employee],
            self.request,
        )
        self.assertEqual(protected, [])

    def test_delete_model_soft_deletes_even_with_allocation(self) -> None:
        self.employee_admin.delete_model(self.request, self.employee)
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.is_deleted)
