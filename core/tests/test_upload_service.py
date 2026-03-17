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
            "type,full_name,corporate_email,manager_email,employee_id,teams,pa,status,iccid,carrier,phone_number,origem\n"
            "employee,Alice Smith,,gerente@test.com,Pepsico,Joinville,PA-10,ativo,,,,\n"
            "simcard,,,,,,,,8999999999999999999,Carrier A,+5511999990000,SRVMEMU-01\n"
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
        self.assertEqual(employee.manager_email, "gerente@test.com")
        self.assertEqual(simcard.status, SIMcard.Status.AVAILABLE)
        phone_line = PhoneLine.objects.get(phone_number="+5511999990000")
        self.assertEqual(phone_line.status, PhoneLine.Status.AVAILABLE)
        self.assertEqual(phone_line.origem, "SRVMEMU-01")

        # Update by same full_name — changes carteira and status
        update_csv = (
            "type,full_name,corporate_email,manager_email,employee_id,teams,pa,status,iccid,carrier,phone_number,origem\n"
            "employee,Alice Smith,,gerente-2@test.com,Natura,Araquari,,inativo,,,,\n"
            "simcard,,,,,,,,8999999999999999999,Carrier B,,\n"
        )
        update_path = self._write("update.csv", update_csv)
        update_summary = process_upload_file(update_path)

        self.assertEqual(update_summary.employees_updated, 1)
        self.assertEqual(update_summary.simcards_updated, 1)
        employee.refresh_from_db()
        simcard.refresh_from_db()
        self.assertEqual(employee.employee_id, "Natura")
        self.assertEqual(employee.status, Employee.Status.INACTIVE)
        self.assertEqual(employee.manager_email, "gerente-2@test.com")
        self.assertEqual(simcard.carrier, "Carrier B")

    def test_process_collects_errors(self):
        broken_csv = (
            "type,full_name,corporate_email,manager_email,employee_id,teams,status,iccid,carrier\n"
            "employee,,,,,,\n"
            "simcard,,,,,invalid,123,\n"
        )
        path = self._write("broken.csv", broken_csv)
        summary = process_upload_file(path)

        self.assertEqual(summary.rows_processed, 0)
        self.assertEqual(len(summary.errors), 2)
        self.assertEqual(Employee.objects.count(), 0)
        self.assertEqual(SIMcard.objects.count(), 0)

    def test_multiple_employees_same_carteira_each_created(self):
        """Two employees sharing the same portfolio (employee_id) must each
        get their own record since the unique key is full_name, not employee_id."""
        csv_content = (
            "type,full_name,corporate_email,manager_email,employee_id,teams,status,iccid,carrier\n"
            "employee,Joana Silva,,Pepsico,Joinville,ativo,,\n"
            "employee,Carlos Souza,,Pepsico,Joinville,ativo,,\n"
        )
        path = self._write("same_carteira.csv", csv_content)

        summary = process_upload_file(path)

        self.assertEqual(summary.rows_processed, 2)
        self.assertFalse(summary.errors)
        self.assertEqual(summary.employees_created, 2)
        self.assertEqual(Employee.objects.count(), 2)

    def test_process_accepts_semicolon_delimited_csv(self):
        header = (
            "type;full_name;corporate_email;manager_email;employee_id;"
            "teams;pa;status;iccid;carrier;phone_number;origem\n"
        )
        emp_row = "employee;Ana Paula;;gerente@corp.com;EMP-9;Joinville;;ativo;;;;\n"
        sim_row = (
            "simcard;;;;;;;AVAILABLE;8999999999999999999;"
            "Carrier QA;+5511999990001;APARELHO\n"
        )
        csv_content = header + emp_row + sim_row
        path = self._write("semicolon.csv", csv_content)

        summary = process_upload_file(path)

        self.assertEqual(summary.rows_processed, 2)
        self.assertFalse(summary.errors)
        self.assertEqual(Employee.objects.count(), 1)
        self.assertEqual(Employee.objects.get().manager_email, "gerente@corp.com")
        self.assertEqual(SIMcard.objects.count(), 1)
        phone_line = PhoneLine.objects.get(phone_number="+5511999990001")
        self.assertEqual(phone_line.origem, "APARELHO")

    def test_invalid_origem_raises_error(self):
        header = (
            "type;full_name;corporate_email;manager_email;employee_id;"
            "teams;pa;status;iccid;carrier;phone_number;origem\n"
        )
        sim_row = (
            "simcard;;;;;;;AVAILABLE;8999999999999999998;"
            "Carrier QA;+5511999990002;INVALID\n"
        )
        csv_content = header + sim_row
        path = self._write("bad_origem.csv", csv_content)

        summary = process_upload_file(path)

        self.assertEqual(summary.rows_processed, 0)
        self.assertEqual(len(summary.errors), 1)
        self.assertIn("Origem inválida", summary.errors[0])

    def test_same_phone_number_reuses_existing_line_and_updates_simcard(self):
        sim = SIMcard.objects.create(iccid="VIRTUAL-4730260539", carrier="Carrier X")
        line = PhoneLine.objects.create(
            phone_number="+5511999991000",
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
        )

        csv_content = (
            "type;full_name;corporate_email;manager_email;employee_id;"
            "teams;pa;status;iccid;carrier;phone_number;origem\n"
            "simcard;;;;;;;AVAILABLE;VIRTUAL;"
            "Carrier Y;+5511999991000;SRVMEMU-02\n"
        )
        path = self._write("same_phone_update.csv", csv_content)

        summary = process_upload_file(path)

        self.assertEqual(summary.rows_processed, 1)
        self.assertFalse(summary.errors)
        # Same simcard re-used, iccid and carrier updated from CSV
        self.assertEqual(SIMcard.objects.count(), 1)
        sim.refresh_from_db()
        self.assertEqual(sim.iccid, "VIRTUAL")
        self.assertEqual(sim.carrier, "Carrier Y")
        # Same phone line kept, origem updated
        line.refresh_from_db()
        self.assertEqual(line.status, PhoneLine.Status.AVAILABLE)
        self.assertEqual(line.origem, "SRVMEMU-02")

    def test_simcard_upload_uses_phone_line_status_choices(self):
        csv_content = (
            "type;full_name;corporate_email;manager_email;employee_id;"
            "teams;pa;status;iccid;carrier;phone_number;origem\n"
            "simcard;;;;;;;quarentena;8999999999999997777;"
            "Carrier Z;+5511999997777;SRVMEMU-03\n"
        )
        path = self._write("line_status_alias.csv", csv_content)

        summary = process_upload_file(path)

        self.assertEqual(summary.rows_processed, 1)
        self.assertFalse(summary.errors)
        simcard = SIMcard.objects.get(iccid="8999999999999997777")
        phone_line = PhoneLine.objects.get(phone_number="+5511999997777")
        self.assertEqual(phone_line.status, PhoneLine.Status.SUSPENDED)
        self.assertEqual(simcard.status, SIMcard.Status.BLOCKED)

    def test_different_phone_numbers_same_iccid_each_create_own_sim_and_line(self):
        csv_content = (
            "type;full_name;corporate_email;manager_email;employee_id;"
            "teams;pa;status;iccid;carrier;phone_number;origem\n"
            "simcard;;;;;;;AVAILABLE;VIRTUAL;ALGAR;4730260539;SRVMEMU-01\n"
            "simcard;;;;;;;AVAILABLE;VIRTUAL;ALGAR;4735113591;SRVMEMU-01\n"
            "simcard;;;;;;;AVAILABLE;VIRTUAL;ALGAR;4730260547;SRVMEMU-01\n"
        )
        path = self._write("virtual_multi.csv", csv_content)

        summary = process_upload_file(path)

        self.assertEqual(summary.rows_processed, 3)
        self.assertFalse(summary.errors)
        self.assertEqual(SIMcard.objects.count(), 3)
        self.assertEqual(PhoneLine.objects.count(), 3)

    def test_iccid_accepts_alphanumeric_value(self):
        csv_content = (
            "type;full_name;corporate_email;manager_email;employee_id;"
            "teams;pa;status;iccid;carrier;phone_number;origem\n"
            "simcard;;;;;;;AVAILABLE;VIRTUALABC123;ALGAR;4730260539;SRVMEMU-01\n"
        )
        path = self._write("alphanumeric_iccid.csv", csv_content)

        summary = process_upload_file(path)

        self.assertEqual(summary.rows_processed, 1)
        self.assertFalse(summary.errors)
        self.assertEqual(SIMcard.objects.count(), 1)
        self.assertEqual(SIMcard.objects.get().iccid, "VIRTUALABC123")
        self.assertEqual(PhoneLine.objects.count(), 1)

    def test_iccid_is_required(self):
        csv_content = (
            "type;full_name;corporate_email;manager_email;employee_id;"
            "teams;pa;status;iccid;carrier;phone_number;origem\n"
            "simcard;;;;;;;AVAILABLE;;ALGAR;4730260539;SRVMEMU-01\n"
        )
        path = self._write("missing_iccid.csv", csv_content)

        summary = process_upload_file(path)

        self.assertEqual(summary.rows_processed, 0)
        self.assertEqual(len(summary.errors), 1)
        self.assertIn(
            "Colunas obrigatórias ausentes ou vazias: iccid.", summary.errors[0]
        )
