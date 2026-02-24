from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from core.services.allocation_service import AllocationService
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser


class PhoneLineHistoryViewTest(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="admin2@test.com", password="123456", role=SystemUser.Role.ADMIN
        )
        self.client.force_login(self.admin)

        self.employee = Employee.objects.create(
            full_name="History User",
            corporate_email="history@corp.com",
            employee_id="EMP100",
            department="IT",
        )

        self.sim = SIMcard.objects.create(iccid="777", carrier="CarrierX")
        self.phone_line = PhoneLine.objects.create(
            phone_number="555123", sim_card=self.sim
        )

        self.first_allocation = AllocationService.allocate_line(
            employee=self.employee, phone_line=self.phone_line, allocated_by=self.admin
        )
        AllocationService.release_line(
            self.first_allocation, released_by=self.admin)

        self.second_allocation = AllocationService.allocate_line(
            employee=self.employee, phone_line=self.phone_line, allocated_by=self.admin
        )

    def test_phone_line_history_returns_all_allocations(self):
        url = reverse("telecom:phoneline_history", args=[self.phone_line.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        allocations = list(response.context["allocations"])
        self.assertEqual(len(allocations), 2)
        self.assertIn(self.employee.full_name, response.content.decode())
        self.assertEqual(
            {allocation.pk for allocation in allocations},
            {self.first_allocation.pk, self.second_allocation.pk},
        )

    def test_phone_line_history_avoid_n_plus_one(self):
        url = reverse("telecom:phoneline_history", args=[self.phone_line.pk])

        with CaptureQueriesContext(connection) as queries:
            self.client.get(url)

        self.assertLessEqual(len(queries), 10)

    def test_filter_phone_line_history_by_period(self):
        admin = SystemUser.objects.create_user(
            email="admin3@test.com", password="123456", role="ADMIN"
        )

        employee = Employee.objects.create(
            full_name="Filter User",
            corporate_email="filter@corp.com",
            employee_id="EMP200",
            department="IT",
        )

        sim = SIMcard.objects.create(iccid="555", carrier="CarrierX")
        line = PhoneLine.objects.create(phone_number="444555", sim_card=sim)

        allocation = AllocationService.allocate_line(
            employee=employee, phone_line=line, allocated_by=admin
        )

        allocation_date = timezone.localtime(
            allocation.allocated_at).date().isoformat()

        self.client.force_login(admin)

        url = reverse("telecom:phoneline_history", args=[line.pk])
        response = self.client.get(f"{url}?start_date={allocation_date}")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Filter User")


class ExportPhoneLineHistoryTest(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="admin4@test.com", password="123456", role=SystemUser.Role.ADMIN
        )
        self.client.force_login(self.admin)

        self.employee = Employee.objects.create(
            full_name="Export User",
            corporate_email="export@corp.com",
            employee_id="EMP300",
            department="IT",
        )

        self.sim = SIMcard.objects.create(iccid="999", carrier="CarrierX")
        self.phone_line = PhoneLine.objects.create(
            phone_number="998877", sim_card=self.sim)

        self.allocation = AllocationService.allocate_line(
            employee=self.employee,
            phone_line=self.phone_line,
            allocated_by=self.admin,
        )

    def test_export_phone_line_history_as_csv(self):
        url = reverse("telecom:phoneline_history_export",
                      args=[self.phone_line.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("attachment; filename=", response["Content-Disposition"])

        content = response.content.decode("utf-8")
        self.assertIn("Linha,ICCID,Status,Colaborador", content)
        self.assertIn(self.phone_line.phone_number, content)
        self.assertIn(self.employee.full_name, content)

    def test_export_phone_line_history_csv_with_date_filter(self):
        allocation_date = timezone.localtime(
            self.allocation.allocated_at).date().isoformat()
        url = reverse("telecom:phoneline_history_export",
                      args=[self.phone_line.pk])
        response = self.client.get(f"{url}?start_date={allocation_date}")

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn(self.employee.full_name, content)


class SIMcardViewsTest(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="admin.sim@test.com",
            password="123456",
            role=SystemUser.Role.ADMIN,
        )
        self.client.force_login(self.admin)

        self.sim_available = SIMcard.objects.create(
            iccid="8900000000000000101",
            carrier="CarrierA",
            status=SIMcard.Status.AVAILABLE,
        )
        self.sim_active = SIMcard.objects.create(
            iccid="8900000000000000202",
            carrier="CarrierB",
            status=SIMcard.Status.ACTIVE,
        )

    def test_simcard_list_view(self):
        url = reverse("telecom:simcard_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.sim_available.iccid)
        self.assertContains(response, self.sim_active.iccid)

    def test_simcard_create_view(self):
        url = reverse("telecom:simcard_create")
        payload = {
            "iccid": "8900000000000000303",
            "carrier": "CarrierC",
        }

        response = self.client.post(url, data=payload)

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("telecom:simcard_list"))
        self.assertTrue(SIMcard.objects.filter(iccid=payload["iccid"]).exists())

    def test_simcard_update_view(self):
        url = reverse("telecom:simcard_update", args=[self.sim_available.pk])
        payload = {
            "iccid": self.sim_available.iccid,
            "carrier": "CarrierUpdated",
            "status": SIMcard.Status.CANCELLED,
        }

        response = self.client.post(url, data=payload)

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("telecom:simcard_list"))
        self.sim_available.refresh_from_db()
        self.assertEqual(self.sim_available.carrier, "CarrierUpdated")
        self.assertEqual(self.sim_available.status, SIMcard.Status.CANCELLED)

    def test_simcard_filter_by_status(self):
        url = reverse("telecom:simcard_list")
        response = self.client.get(url, {"status": SIMcard.Status.AVAILABLE})

        self.assertEqual(response.status_code, 200)
        simcards = list(response.context["simcards"])
        self.assertEqual(len(simcards), 1)
        self.assertEqual(simcards[0].pk, self.sim_available.pk)

    def test_simcard_search_by_iccid(self):
        url = reverse("telecom:simcard_list")
        response = self.client.get(url, {"search": "000000000000202"})

        self.assertEqual(response.status_code, 200)
        simcards = list(response.context["simcards"])
        self.assertEqual(len(simcards), 1)
        self.assertEqual(simcards[0].pk, self.sim_active.pk)
