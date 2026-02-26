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
            "teams": "Operações",
            "status": Employee.Status.ACTIVE,
        }

    def test_unique_fields_raise_integrity_error(self) -> None:
        Employee.objects.create(**self.base_data)

        with transaction.atomic(), self.assertRaises(IntegrityError):
            Employee.objects.create(**{**self.base_data, "employee_id": "EMP-1002"})

        with transaction.atomic(), self.assertRaises(IntegrityError):
            Employee.objects.create(
                **{**self.base_data, "corporate_email": "outra@lineops.tech"}
            )

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
        self.user = SystemUser.objects.create_user(
            email="user@test.com",
            password="StrongPass123",
            role=SystemUser.Role.USER,
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
            teams="Operações",
            status=Employee.Status.ACTIVE,
        )

        sim = SIMcard.objects.create(
            iccid="12345678901234567890",
        )
        line = PhoneLine.objects.create(
            number="+5511999999999",
            sim_card=sim,
        )
        LineAllocation.objects.create(
            employee=self.employee,
            line=line,
        )

        def test_filters_by_name(self) -> None:
            self.client.force_login(self.user)
            response = self.client.get(reverse("employee-list"), {"search": "Aline"})
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Aline Martins")
            self.assertNotContains(response, "Maria Silva")

        def test_filters_by_line(self) -> None:
            self.client.force_login(self.admin)
            response = self.client.get(
                reverse("employee-list"), {"search": "999999999"}
            )
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Aline Martins")
            self.assertNotContains(response, "Maria Silva")

        def test_combined_filters(self) -> None:
            self.client.force_login(self.admin)
            response = self.client.get(reverse("employee-list"), {"teams": "Comercial"})
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, "Aline Martins")
            self.assertContains(response, "Maria Silva")

        def test_shows_edit_buttom_for_admin(self) -> None:
            self.client.force_login(self.admin)
            response = self.client.get(reverse("employee-list"))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Limpar filtros")
            self.assertContains(
                response, reverse("employee:employee_update", args=[self.employee.pk])
            )

        def test_hides_edit_buttom_for_user(self) -> None:
            self.client.force_login(self.user)
            response = self.client.get(reverse("employee-list"))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Limpar filtros")
            self.assertNotContains(
                response, reverse("employee:employee_update", args=[self.employee.pk])
            )

        def test_hides_edit_buttom_for_operator(self) -> None:
            self.client.force_login(self.operator)
            response = self.client.get(reverse("employee-list"))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Limpar filtros")
            self.assertNotContains(
                response, reverse("employee:employee_update", args=[self.employee.pk])
            )
