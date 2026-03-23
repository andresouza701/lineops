import shutil
import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from allocations.models import LineAllocation
from config.forms import UploadForm
from employees.models import Employee
from telecom.models import SIMcard
from users.models import SystemUser


class UploadViewTests(TestCase):
    def setUp(self):
        self.temp_media = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.temp_media, ignore_errors=True))

        self.override = override_settings(MEDIA_ROOT=self.temp_media)
        self.override.enable()
        self.addCleanup(self.override.disable)

        self.admin = SystemUser.objects.create_user(
            email="upload@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.operator = SystemUser.objects.create_user(
            email="upload-operator@test.com",
            password="StrongPass123",
            role=SystemUser.Role.OPERATOR,
        )
        self.client.force_login(self.admin)

    def test_upload_creates_records_and_renders_summary(self):
        csv_content = (
            "type,full_name,corporate_email,manager_email,employee_id,teams,status,iccid,carrier\n"
            "employee,Ana Paula,,gerente@corp.com,EMP-9,Joinville,ativo,,\n"
            "simcard,,,,,AVAILABLE,8999999999999999999,Carrier QA\n"
        )
        uploaded_file = SimpleUploadedFile(
            "bulk.csv", csv_content.encode("utf-8"), content_type="text/csv"
        )

        response = self.client.post(reverse("upload"), {"file": uploaded_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Employee.objects.count(), 1)
        self.assertEqual(SIMcard.objects.count(), 1)
        self.assertEqual(Employee.objects.get().manager_email, "gerente@corp.com")

        summary = response.context.get("summary")
        self.assertIsNotNone(summary)
        self.assertEqual(summary.rows_processed, 2)
        self.assertFalse(summary.errors)
        self.assertContains(response, "Linhas processadas")

    def test_operator_cannot_access_upload(self):
        self.client.force_login(self.operator)
        response = self.client.get(reverse("upload"))
        self.assertEqual(response.status_code, 403)

    def test_anonymous_redirected_to_login(self):
        self.client.logout()
        response = self.client.get(reverse("upload"))
        self.assertEqual(response.status_code, 403)

    def test_upload_form_rejects_binary_csv_payload(self):
        uploaded_file = SimpleUploadedFile(
            "bulk.csv",
            b"\x00\x01\x02\x03",
            content_type="text/csv",
        )
        form = UploadForm(files={"file": uploaded_file})

        self.assertFalse(form.is_valid())
        self.assertIn("Arquivo CSV invalido.", form.errors["file"])

    def test_upload_form_rejects_invalid_xlsx_signature(self):
        uploaded_file = SimpleUploadedFile(
            "bulk.xlsx",
            b"not-a-zip-file",
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
        form = UploadForm(files={"file": uploaded_file})

        self.assertFalse(form.is_valid())
        self.assertIn("Arquivo XLSX invalido ou corrompido.", form.errors["file"])

    def test_upload_accepts_semicolon_delimited_csv(self):
        csv_content = (
            "type;full_name;corporate_email;manager_email;employee_id;teams;pa;status;iccid;carrier;phone_number;origem\n"
            "employee;Ana Paula;;gerente@corp.com;EMP-9;Joinville;;ativo;;;;\n"
            "simcard;;;;;;AVAILABLE;8999999999999999999;Carrier QA;+5511999990001;\n"
        )
        uploaded_file = SimpleUploadedFile(
            "bulk.csv", csv_content.encode("utf-8"), content_type="text/csv"
        )

        response = self.client.post(reverse("upload"), {"file": uploaded_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Employee.objects.count(), 1)
        self.assertEqual(SIMcard.objects.count(), 1)
        self.assertEqual(Employee.objects.get().manager_email, "gerente@corp.com")

    def test_upload_can_create_line_allocation_from_simcard_row(self):
        csv_content = (
            "type;full_name;corporate_email;manager_email;employee_id;teams;pa;status;iccid;carrier;phone_number;origem\n"
            "employee;Ana Paula;;gerente@corp.com;EMP-9;Joinville;;ativo;;;;\n"
            "simcard;Ana Paula;;;;;;ALLOCATED;8999999999999991003;Carrier QA;+5511999991003;SRVMEMU-01\n"
        )
        uploaded_file = SimpleUploadedFile(
            "bulk.csv", csv_content.encode("utf-8"), content_type="text/csv"
        )

        response = self.client.post(reverse("upload"), {"file": uploaded_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(LineAllocation.objects.count(), 1)
        self.assertEqual(response.context["summary"].allocations_created, 1)
