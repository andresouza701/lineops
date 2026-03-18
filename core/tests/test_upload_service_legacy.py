import shutil
import tempfile
from pathlib import Path

from django.test import TestCase

from core.services.upload_service import process_upload_file
from telecom.models import SIMcard


class UploadServiceLegacyFormatTests(TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))

    def _write(self, name: str, content: str) -> Path:
        path = self.temp_dir / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_legacy_simcard_csv_without_phone_number_columns_still_imports(self):
        csv_content = (
            "type,full_name,corporate_email,manager_email,employee_id,teams,status,iccid,carrier\n"
            "simcard,,,,,AVAILABLE,8999999999999999999,Carrier QA\n"
        )
        path = self._write("legacy_simcard.csv", csv_content)

        summary = process_upload_file(path)

        self.assertEqual(summary.rows_processed, 1)
        self.assertFalse(summary.errors)
        self.assertEqual(SIMcard.objects.count(), 1)
        simcard = SIMcard.objects.get()
        self.assertEqual(simcard.iccid, "8999999999999999999")
        self.assertEqual(simcard.carrier, "Carrier QA")
        self.assertEqual(simcard.status, SIMcard.Status.AVAILABLE)
