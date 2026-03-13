import shutil
import tempfile
from pathlib import Path

from django.test import TestCase

from core.services.upload_service import process_upload_file
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard


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
            "type,full_name,corporate_email,employee_id,teams,pa,status,iccid,carrier,phone_number,origem\n"
            "employee,Alice Smith,,EMP-1,Joinville,PA-10,ativo,,,,\n"
            "simcard,,,,,,,8999999999999999999,Carrier A,+5511999990000,SRVMEMU-01\n"
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
        self.assertEqual(employee.pa, "PA-10")
        self.assertEqual(simcard.status, SIMcard.Status.AVAILABLE)
        phone_line = PhoneLine.objects.get(phone_number="+5511999990000")
        self.assertEqual(phone_line.origem, "SRVMEMU-01")

        update_csv = (
            "type,full_name,corporate_email,employee_id,teams,pa,status,iccid,carrier,phone_number,origem\n"
            "employee,Alice Updated,,EMP-1,Araquari,,inativo,,,,\n"
            "simcard,,,,,,,8999999999999999999,Carrier B,,\n"
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

    def test_process_collects_errors(self):
        broken_csv = (
            "type,full_name,corporate_email,employee_id,teams,status,iccid,carrier\n"
            "employee,,,,,,\n"
            "simcard,,,,,invalid,123,\n"
        )
        path = self._write("broken.csv", broken_csv)
        summary = process_upload_file(path)

        self.assertEqual(summary.rows_processed, 0)
        self.assertEqual(len(summary.errors), 2)
        self.assertEqual(Employee.objects.count(), 0)
        self.assertEqual(SIMcard.objects.count(), 0)

    def test_process_reports_duplicate_employee_name_with_different_employee_id(self):
        Employee.objects.create(
            full_name="Teste Super 01",
            corporate_email="supervisor1@test.com",
            employee_id="EMP-DUP-1",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )

        csv_content = (
            "type,full_name,corporate_email,employee_id,teams,status,iccid,carrier\n"
            "employee,teste super 01,,"
            "EMP-DUP-2,Joinville,ativo,,\n"
        )
        path = self._write("duplicate_name.csv", csv_content)

        summary = process_upload_file(path)

        self.assertEqual(summary.rows_processed, 0)
        self.assertEqual(len(summary.errors), 1)
        self.assertIn(
            "Ja existe um usuario cadastrado com este nome.", summary.errors[0]
        )
        self.assertEqual(Employee.objects.filter(is_deleted=False).count(), 1)

    def test_process_accepts_semicolon_delimited_csv(self):
        header = (
            "type;full_name;corporate_email;employee_id;"
            "teams;pa;status;iccid;carrier;phone_number;origem\n"
        )
        emp_row = "employee;Ana Paula;;EMP-9;Joinville;;ativo;;;;\n"
        sim_row = (
            "simcard;;;;;;AVAILABLE;8999999999999999999;"
            "Carrier QA;+5511999990001;APARELHO\n"
        )
        csv_content = header + emp_row + sim_row
        path = self._write("semicolon.csv", csv_content)

        summary = process_upload_file(path)

        self.assertEqual(summary.rows_processed, 2)
        self.assertFalse(summary.errors)
        self.assertEqual(Employee.objects.count(), 1)
        self.assertEqual(SIMcard.objects.count(), 1)
        phone_line = PhoneLine.objects.get(phone_number="+5511999990001")
        self.assertEqual(phone_line.origem, "APARELHO")

    def test_invalid_origem_raises_error(self):
        header = (
            "type;full_name;corporate_email;employee_id;"
            "teams;pa;status;iccid;carrier;phone_number;origem\n"
        )
        sim_row = (
            "simcard;;;;;;AVAILABLE;8999999999999999998;"
            "Carrier QA;+5511999990002;INVALID\n"
        )
        csv_content = header + sim_row
        path = self._write("bad_origem.csv", csv_content)

        summary = process_upload_file(path)

        self.assertEqual(summary.rows_processed, 0)
        self.assertEqual(len(summary.errors), 1)
        self.assertIn("Origem inválida", summary.errors[0])

    def test_reuses_existing_line_linked_to_same_sim(self):
        sim = SIMcard.objects.create(iccid="8900000000000000001", carrier="Carrier X")
        line = PhoneLine.objects.create(
            phone_number="+5511999991000",
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
        )

        csv_content = (
            "type;full_name;corporate_email;employee_id;"
            "teams;pa;status;iccid;carrier;phone_number;origem\n"
            "simcard;;;;;;AVAILABLE;8900000000000000001;"
            "Carrier X;+5511999992000;SRVMEMU-01\n"
        )
        path = self._write("same_sim_new_number.csv", csv_content)

        summary = process_upload_file(path)

        self.assertEqual(summary.rows_processed, 1)
        self.assertFalse(summary.errors)
        line.refresh_from_db()
        self.assertEqual(line.phone_number, "+5511999992000")
        self.assertEqual(line.origem, "SRVMEMU-01")

    def test_reports_conflict_when_sim_and_number_belong_to_different_lines(self):
        sim_a = SIMcard.objects.create(iccid="8900000000000000010", carrier="Carrier A")
        sim_b = SIMcard.objects.create(iccid="8900000000000000020", carrier="Carrier B")
        PhoneLine.objects.create(
            phone_number="+5511999993000",
            sim_card=sim_a,
            status=PhoneLine.Status.AVAILABLE,
        )
        PhoneLine.objects.create(
            phone_number="+5511999994000",
            sim_card=sim_b,
            status=PhoneLine.Status.AVAILABLE,
        )

        csv_content = (
            "type;full_name;corporate_email;employee_id;"
            "teams;pa;status;iccid;carrier;phone_number;origem\n"
            "simcard;;;;;;AVAILABLE;8900000000000000010;"
            "Carrier A;+5511999994000;SRVMEMU-01\n"
        )
        path = self._write("sim_number_conflict.csv", csv_content)

        summary = process_upload_file(path)

        self.assertEqual(summary.rows_processed, 0)
        self.assertEqual(len(summary.errors), 1)
        self.assertIn("Conflito de vínculo", summary.errors[0])

    def test_virtual_iccid_creates_distinct_lines_per_phone(self):
        csv_content = (
            "type;full_name;corporate_email;employee_id;"
            "teams;pa;status;iccid;carrier;phone_number;origem\n"
            "simcard;;;;;;AVAILABLE;VIRTUAL;ALGAR;4730260539;SRVMEMU-01\n"
            "simcard;;;;;;AVAILABLE;VIRTUAL;ALGAR;4735113591;SRVMEMU-01\n"
        )
        path = self._write("virtual_iccid.csv", csv_content)

        summary = process_upload_file(path)

        self.assertEqual(summary.rows_processed, 2)
        self.assertFalse(summary.errors)
        self.assertEqual(SIMcard.objects.count(), 2)
        self.assertEqual(PhoneLine.objects.count(), 2)

    def test_virtual_iccid_without_phone_number_returns_error(self):
        csv_content = (
            "type;full_name;corporate_email;employee_id;"
            "teams;pa;status;iccid;carrier;phone_number;origem\n"
            "simcard;;;;;;AVAILABLE;VIRTUAL;ALGAR;;SRVMEMU-01\n"
        )
        path = self._write("virtual_without_phone.csv", csv_content)

        summary = process_upload_file(path)

        self.assertEqual(summary.rows_processed, 0)
        self.assertEqual(len(summary.errors), 1)
        self.assertIn("Quando ICCID for 'VIRTUAL'", summary.errors[0])
