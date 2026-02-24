from django.db import IntegrityError, transaction
from django.test import TestCase

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
