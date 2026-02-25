from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from users.models import SystemUser

from .models import Employee


class EmployeeModelTest(TestCase):
    def setUp(self):
        self.base_data = {
            "full_name": "Aline Martins",
            "corporate_email": "aline.martins@lineops.tech",
            "employee_id": "EMP-1001",
            "department": "Operações",
            "status": Employee.Status.ACTIVE,
        }

    def test_unique_fields_raise_integrity_error(self):
        Employee.objects.create(**self.base_data)

        with transaction.atomic(), self.assertRaises(IntegrityError):
            Employee.objects.create(**{**self.base_data, "employee_id": "EMP-1002"})

        with transaction.atomic(), self.assertRaises(IntegrityError):
            Employee.objects.create(
                **{**self.base_data, "corporate_email": "outra@lineops.tech"}
            )

    def test_status_is_persisted(self):
        employee = Employee.objects.create(**self.base_data)
        stored = Employee.all_objects.get(pk=employee.pk)
        self.assertEqual(stored.status, Employee.Status.ACTIVE)

    def test_soft_delete_marks_record_and_filters_out(self):
        employee = Employee.objects.create(**self.base_data)
        employee.delete()

        reloaded = Employee.all_objects.get(pk=employee.pk)
        self.assertTrue(reloaded.is_deleted)
        self.assertEqual(Employee.objects.filter(pk=employee.pk).count(), 0)


class EmployeePermissionTest(TestCase):
    def setUp(self):
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
            full_name="Jane Doe",
            corporate_email="jane@corp.com",
            employee_id="EMP-2000",
            department="Ops",
            status=Employee.Status.ACTIVE,
        )

    def test_admin_can_access_employee_views(self):
        self.client.force_login(self.admin)

        list_resp = self.client.get(reverse("employees:employee_list"))
        self.assertEqual(list_resp.status_code, 200)

        detail_resp = self.client.get(
            reverse("employees:employee_detail", args=[self.employee.pk])
        )
        self.assertEqual(detail_resp.status_code, 200)

        create_resp = self.client.get(reverse("employees:employee_create"))
        self.assertEqual(create_resp.status_code, 200)

        update_resp = self.client.get(
            reverse("employees:employee_update", args=[self.employee.pk])
        )
        self.assertEqual(update_resp.status_code, 200)

        delete_resp = self.client.post(
            reverse("employees:employee_deactivate", args=[self.employee.pk])
        )
        self.assertEqual(delete_resp.status_code, 302)

    def test_operator_is_denied_on_employee_views(self):
        self.client.force_login(self.operator)

        list_resp = self.client.get(reverse("employees:employee_list"))
        self.assertEqual(list_resp.status_code, 403)

        detail_resp = self.client.get(
            reverse("employees:employee_detail", args=[self.employee.pk])
        )
        self.assertEqual(detail_resp.status_code, 403)

        create_resp = self.client.get(reverse("employees:employee_create"))
        self.assertEqual(create_resp.status_code, 403)

        update_resp = self.client.get(
            reverse("employees:employee_update", args=[self.employee.pk])
        )
        self.assertEqual(update_resp.status_code, 403)

        delete_resp = self.client.post(
            reverse("employees:employee_deactivate", args=[self.employee.pk])
        )
        self.assertEqual(delete_resp.status_code, 403)
