from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from employees.models import Employee
from telecom.models import SIMcard


class NormalizeDomainDataCommandTest(TestCase):
    def test_command_dry_run_reports_without_persisting(self):
        Employee.all_objects.bulk_create(
            [
                Employee(
                    full_name="  maria   da   silva  ",
                    corporate_email="  SUPERVISOR@TEST.COM ",
                    manager_email="  GERENTE@TEST.COM ",
                    employee_id=" viasata ",
                    teams=" joinville ",
                    status=Employee.Status.ACTIVE,
                    pa="  PA   01  ",
                )
            ]
        )
        SIMcard.all_objects.bulk_create(
            [
                SIMcard(
                    iccid="8900000000000000101",
                    carrier=" tim ",
                    status=SIMcard.Status.AVAILABLE,
                )
            ]
        )

        output = StringIO()
        call_command("normalize_domain_data", stdout=output)

        employee = Employee.all_objects.get()
        simcard = SIMcard.all_objects.get()

        self.assertEqual(employee.full_name, "  maria   da   silva  ")
        self.assertEqual(employee.corporate_email, "  SUPERVISOR@TEST.COM ")
        self.assertEqual(employee.employee_id, " viasata ")
        self.assertEqual(employee.teams, " joinville ")
        self.assertEqual(simcard.carrier, " tim ")
        self.assertIn("[DRY-RUN]", output.getvalue())
        self.assertIn("Employee id=", output.getvalue())
        self.assertIn("SIMcard id=", output.getvalue())

    def test_command_apply_normalizes_safe_rows_and_skips_name_collisions(self):
        Employee.all_objects.bulk_create(
            [
                Employee(
                    full_name="  joao   da   silva  ",
                    corporate_email="  SUPERVISOR@TEST.COM ",
                    manager_email="  GERENTE@TEST.COM ",
                    employee_id=" viasata ",
                    teams=" joinville ",
                    status=Employee.Status.ACTIVE,
                    pa="  PA   01  ",
                ),
                Employee(
                    full_name="Ana Paula",
                    corporate_email="ana1@test.com",
                    employee_id="Ambiental",
                    teams="Joinville",
                    status=Employee.Status.ACTIVE,
                ),
                Employee(
                    full_name="Ana   Paula",
                    corporate_email="ana2@test.com",
                    employee_id="Ambiental",
                    teams="Joinville",
                    status=Employee.Status.ACTIVE,
                ),
            ]
        )
        SIMcard.all_objects.bulk_create(
            [
                SIMcard(
                    iccid="8900000000000000102",
                    carrier=" tim ",
                    status=SIMcard.Status.AVAILABLE,
                )
            ]
        )

        output = StringIO()
        call_command("normalize_domain_data", "--apply", stdout=output)

        normalized_employee = Employee.all_objects.get(
            corporate_email="supervisor@test.com"
        )
        first_conflict = Employee.all_objects.get(corporate_email="ana1@test.com")
        second_conflict = Employee.all_objects.get(corporate_email="ana2@test.com")
        simcard = SIMcard.all_objects.get()

        self.assertEqual(normalized_employee.full_name, "Joao da Silva")
        self.assertEqual(normalized_employee.manager_email, "gerente@test.com")
        self.assertEqual(normalized_employee.employee_id, "ViaSat")
        self.assertEqual(normalized_employee.teams, "Joinville")
        self.assertEqual(normalized_employee.pa, "PA 01")
        self.assertEqual(first_conflict.full_name, "Ana Paula")
        self.assertEqual(second_conflict.full_name, "Ana   Paula")
        self.assertEqual(simcard.carrier, "TIM")
        self.assertIn("[APPLY]", output.getvalue())
        self.assertIn("ignorado por colisao", output.getvalue())
