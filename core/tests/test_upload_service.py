import shutil
import tempfile
from pathlib import Path

from django.test import TestCase

from core.services.upload_service import process_upload_file
from employees.models import Employee
from telecom.models import SIMcard


class UploadServiceTests(TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))

    def _write(self, name: str, content: str) -> Path:
        path = self.temp_dir / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_process_creates_and_updates_entities(self):
        initial_csv = (
            "type,full_name,corporate_email,employee_id,department,status,iccid,carrier\n"
            "employee,Alice Smith,alice@example.com,EMP-1,Tech,active,,\n"
            "simcard,,,,,available,8999999999999999999,Carrier A\n"
        )
        path = self._write("initial.csv", initial_csv)
        summary = process_upload_file(path)

        self.assertEqual(summary.rows_processed, 2)
        self.assertFalse(summary.errors)
        self.assertEqual(Employee.objects.count(), 1)
        self.assertEqual(SIMcard.objects.count(), 1)
        employee = Employee.objects.first()
        simcard = SIMcard.objects.first()
        self.assertEqual(employee.status, Employee.Status.ACTIVE)
        self.assertEqual(simcard.status, SIMcard.Status.AVAILABLE)

        update_csv = (
            "type,full_name,corporate_email,employee_id,department,status,iccid,carrier\n"
            "employee,Alice Updated,alice@example.com,EMP-1,Operacoes,inactive,,\n"
            "simcard,,,,,blocked,8999999999999999999,Carrier B\n"
        )
        update_path = self._write("update.csv", update_csv)
        update_summary = process_upload_file(update_path)

        self.assertEqual(update_summary.employees_updated, 1)
        self.assertEqual(update_summary.simcards_updated, 1)
        employee.refresh_from_db()
        simcard.refresh_from_db()
        self.assertEqual(employee.full_name, "Alice Updated")
        self.assertEqual(employee.status, Employee.Status.INACTIVE)
        self.assertEqual(simcard.carrier, "Carrier B")
        self.assertEqual(simcard.status, SIMcard.Status.BLOCKED)

    def test_process_collects_errors(self):
        broken_csv = (
            "type,full_name,corporate_email,employee_id,department,status,iccid,carrier\n"
            "employee,,,,inactive,,\n"
            "simcard,,,,,invalid,123,\n"
        )
        path = self._write("broken.csv", broken_csv)
        summary = process_upload_file(path)

        self.assertEqual(summary.rows_processed, 0)
        self.assertEqual(len(summary.errors), 2)
        self.assertEqual(Employee.objects.count(), 0)
        self.assertEqual(SIMcard.objects.count(), 0)
