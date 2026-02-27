from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from allocations.models import LineAllocation
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser

from .models import Employee


class EmployeeModelTest(TestCase):
    def setUp(self) -> None:
        self.base_data = {
            "full_name": "Aline Martins",
            "corporate_email": "aline.martins@lineops.tech",
            "employee_id": "EMP-1001",
            "teams": Employee.UnitChoices.JOINVILLE,
            "status": Employee.Status.ACTIVE,
        }

    def test_employee_id_is_unique(self) -> None:
        Employee.objects.create(**self.base_data)

        with transaction.atomic(), self.assertRaises(IntegrityError):
            Employee.objects.create(**self.base_data)

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

    def test_anonymous_cannot_access_employee_list(self) -> None:
        response = self.client.get(reverse("employees:employee_list"))
        self.assertEqual(response.status_code, 403)
