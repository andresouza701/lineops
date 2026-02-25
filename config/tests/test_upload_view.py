import shutil
import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

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
            "type,full_name,corporate_email,employee_id,department,status,iccid,carrier\n"
            "employee,Ana Paula,ana.paula@example.com,EMP-9,Financeiro,active,,\n"
            "simcard,,,,,available,8999999999999999999,Carrier QA\n"
        )
        uploaded_file = SimpleUploadedFile(
            "bulk.csv", csv_content.encode("utf-8"), content_type="text/csv"
        )

        response = self.client.post(reverse("upload"), {"file": uploaded_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Employee.objects.count(), 1)
        self.assertEqual(SIMcard.objects.count(), 1)

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
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)
