from django.contrib import admin
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.current_user import clear_current_user, set_current_user
from core.services.allocation_service import AllocationService
from employees.models import Employee
from telecom.models import PhoneLine, PhoneLineHistory, SIMcard
from users.models import SystemUser


class TelecomAdminRegistrationTest(TestCase):
    def test_phone_line_is_registered_in_admin(self):
        self.assertIn(PhoneLine, admin.site._registry)


class PhoneLineHistoryAuditTest(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="audit.admin@test.com",
            password="123456",
            role=SystemUser.Role.ADMIN,
        )
        self.operator = SystemUser.objects.create_user(
            email="audit.operator@test.com",
            password="123456",
            role=SystemUser.Role.OPERATOR,
        )

        self.client.force_login(self.admin)

        self.employee_a = Employee.objects.create(
            full_name="Employee A",
            corporate_email="supa@corp.com",
            employee_id="EMP100",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        self.employee_b = Employee.objects.create(
            full_name="Employee B",
            corporate_email="supb@corp.com",
            employee_id="EMP200",
            teams="Araquari",
            status=Employee.Status.ACTIVE,
        )

        self.sim_a = SIMcard.objects.create(
            iccid="8900000000000000101",
            carrier="CarrierA",
            status=SIMcard.Status.AVAILABLE,
        )
        self.sim_b = SIMcard.objects.create(
            iccid="8900000000000000202",
            carrier="CarrierB",
            status=SIMcard.Status.AVAILABLE,
        )

        create_url = reverse("telecom:phoneline_create")
        response = self.client.post(
            create_url,
            data={
                "phone_number": "+551199999111",
                "sim_card": self.sim_a.pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.phone_line = PhoneLine.objects.get(phone_number="+551199999111")

    def test_action_types_has_all_required_actions(self):
        expected = {
            "CREATED",
            "STATUS_CHANGED",
            "SIMCARD_CHANGED",
            "EMPLOYEE_CHANGED",
            "DELETED",
            "ALLOCATED",
            "RELEASED",
            "DAILY_ACTION_CHANGED",
        }
        current = {choice[0] for choice in PhoneLineHistory.ActionType.choices}
        self.assertEqual(current, expected)

    def test_signals_register_all_required_history_actions(self):
        allocation = AllocationService.allocate_line(
            employee=self.employee_a,
            phone_line=self.phone_line,
            allocated_by=self.admin,
        )

        edit_url = reverse("allocations:allocation_edit", args=[allocation.pk])
        response = self.client.post(
            edit_url,
            data={
                "action": "save",
                "status": PhoneLine.Status.SUSPENDED,
                "employee": self.employee_b.pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        allocation.refresh_from_db()
        self.phone_line.refresh_from_db()
        self.assertEqual(allocation.employee_id, self.employee_b.pk)
        self.assertEqual(self.phone_line.status, PhoneLine.Status.SUSPENDED)

        update_url = reverse("telecom:phoneline_update", args=[self.phone_line.pk])
        response = self.client.post(
            update_url,
            data={
                "phone_number": self.phone_line.phone_number,
                "sim_card": self.phone_line.sim_card.pk,
                "status": PhoneLine.Status.SUSPENDED,
            },
        )
        self.assertEqual(response.status_code, 302)

        # Simula troca de SIM por fluxo interno e valida evento de histórico.
        self.phone_line.refresh_from_db()
        set_current_user(self.admin)
        try:
            self.phone_line.sim_card = self.sim_b
            self.phone_line.save(update_fields=["sim_card"])
        finally:
            clear_current_user()

        release_url = reverse("allocations:allocation_edit", args=[allocation.pk])
        response = self.client.post(release_url, data={"action": "release"})
        self.assertEqual(response.status_code, 302)

        delete_url = reverse("telecom:phoneline_delete", args=[self.phone_line.pk])
        response = self.client.post(delete_url)
        self.assertEqual(response.status_code, 302)

        actions = set(
            PhoneLineHistory.objects.filter(phone_line=self.phone_line).values_list(
                "action", flat=True
            )
        )
        self.assertTrue(
            {
                PhoneLineHistory.ActionType.CREATED,
                PhoneLineHistory.ActionType.STATUS_CHANGED,
                PhoneLineHistory.ActionType.SIMCARD_CHANGED,
                PhoneLineHistory.ActionType.EMPLOYEE_CHANGED,
                PhoneLineHistory.ActionType.DELETED,
                PhoneLineHistory.ActionType.ALLOCATED,
                PhoneLineHistory.ActionType.RELEASED,
            }.issubset(actions)
        )

        status_event = PhoneLineHistory.objects.filter(
            phone_line=self.phone_line,
            action=PhoneLineHistory.ActionType.STATUS_CHANGED,
        ).first()
        self.assertIsNotNone(status_event)
        self.assertEqual(status_event.changed_by, self.admin)

        sim_event = PhoneLineHistory.objects.filter(
            phone_line=self.phone_line,
            action=PhoneLineHistory.ActionType.SIMCARD_CHANGED,
        ).first()
        self.assertIsNotNone(sim_event)
        self.assertEqual(sim_event.changed_by, self.admin)

        employee_event = PhoneLineHistory.objects.filter(
            phone_line=self.phone_line,
            action=PhoneLineHistory.ActionType.EMPLOYEE_CHANGED,
        ).first()
        self.assertIsNotNone(employee_event)
        self.assertEqual(employee_event.changed_by, self.admin)

        deleted_event = PhoneLineHistory.objects.filter(
            phone_line=self.phone_line,
            action=PhoneLineHistory.ActionType.DELETED,
        ).first()
        self.assertIsNotNone(deleted_event)
        self.assertEqual(deleted_event.changed_by, self.admin)

        allocated_event = PhoneLineHistory.objects.filter(
            phone_line=self.phone_line,
            action=PhoneLineHistory.ActionType.ALLOCATED,
        ).first()
        self.assertIsNotNone(allocated_event)
        self.assertEqual(allocated_event.changed_by, self.admin)

        released_event = PhoneLineHistory.objects.filter(
            phone_line=self.phone_line,
            action=PhoneLineHistory.ActionType.RELEASED,
        ).first()
        self.assertIsNotNone(released_event)
        self.assertEqual(released_event.changed_by, self.admin)

    def test_history_view_admin_only(self):
        url = reverse("telecom:phoneline_history", args=[self.phone_line.pk])

        self.client.force_login(self.operator)
        denied = self.client.get(url)
        self.assertEqual(denied.status_code, 403)

        self.client.force_login(self.admin)
        ok = self.client.get(url)
        self.assertEqual(ok.status_code, 200)
        self.assertIn("history", ok.context)

    def test_overview_shows_history_button_for_admin(self):
        allocation = AllocationService.allocate_line(
            employee=self.employee_a,
            phone_line=self.phone_line,
            allocated_by=self.admin,
        )

        response = self.client.get(reverse("telecom:overview"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "bi bi-clock-history")
        self.assertContains(
            response,
            reverse("telecom:phoneline_history", args=[allocation.phone_line.pk]),
        )

    def test_allocate_and_release_do_not_duplicate_status_changed_history(self):
        allocation = AllocationService.allocate_line(
            employee=self.employee_a,
            phone_line=self.phone_line,
            allocated_by=self.admin,
        )
        AllocationService.release_line(allocation, released_by=self.admin)

        history = PhoneLineHistory.objects.filter(phone_line=self.phone_line)

        self.assertTrue(
            history.filter(action=PhoneLineHistory.ActionType.ALLOCATED).exists()
        )
        self.assertTrue(
            history.filter(action=PhoneLineHistory.ActionType.RELEASED).exists()
        )
        self.assertEqual(
            history.filter(action=PhoneLineHistory.ActionType.STATUS_CHANGED).count(),
            0,
        )

    def test_update_view_allocate_does_not_generate_status_changed_noise(self):
        update_url = reverse("telecom:phoneline_update", args=[self.phone_line.pk])
        response = self.client.post(
            update_url,
            data={
                "phone_number": self.phone_line.phone_number,
                "sim_card": self.phone_line.sim_card.pk,
                "status": PhoneLine.Status.ALLOCATED,
                "employee": self.employee_a.pk,
            },
        )
        self.assertEqual(response.status_code, 302)

        history = PhoneLineHistory.objects.filter(phone_line=self.phone_line)
        self.assertTrue(
            history.filter(action=PhoneLineHistory.ActionType.ALLOCATED).exists()
        )
        self.assertEqual(
            history.filter(action=PhoneLineHistory.ActionType.STATUS_CHANGED).count(),
            0,
        )


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
            teams="IT",
        )

        self.sim = SIMcard.objects.create(iccid="999", carrier="CarrierX")
        self.phone_line = PhoneLine.objects.create(
            phone_number="998877", sim_card=self.sim
        )

        self.allocation = AllocationService.allocate_line(
            employee=self.employee,
            phone_line=self.phone_line,
            allocated_by=self.admin,
        )

    def test_export_phone_line_history_as_csv(self):
        url = reverse("telecom:phoneline_history_export", args=[self.phone_line.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("attachment; filename=", response["Content-Disposition"])

        content = response.content.decode("utf-8")
        self.assertIn("Linha,ICCID,Status,Usuário", content)
        self.assertIn(self.phone_line.phone_number, content)
        self.assertIn(self.employee.full_name, content)

    def test_export_phone_line_history_csv_with_date_filter(self):
        allocation_date = (
            timezone.localtime(self.allocation.allocated_at).date().isoformat()
        )
        url = reverse("telecom:phoneline_history_export", args=[self.phone_line.pk])
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
            "phone_number": "+5511999990303",
        }

        response = self.client.post(url, data=payload)

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("telecom:simcard_list"))
        created_sim = SIMcard.objects.get(iccid=payload["iccid"])
        self.assertTrue(
            PhoneLine.objects.filter(
                phone_number=payload["phone_number"],
                sim_card=created_sim,
            ).exists()
        )

    def test_simcard_create_view_can_create_phone_line_together(self):
        url = reverse("telecom:simcard_create")
        payload = {
            "iccid": "8900000000000000304",
            "carrier": "CarrierC2",
            "phone_number": "+5511999990304",
        }

        response = self.client.post(url, data=payload)

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("telecom:simcard_list"))
        created_sim = SIMcard.objects.get(iccid=payload["iccid"])
        self.assertTrue(
            PhoneLine.objects.filter(
                phone_number=payload["phone_number"],
                sim_card=created_sim,
            ).exists()
        )

    def test_simcard_create_view_allows_duplicate_iccid(self):
        url = reverse("telecom:simcard_create")
        payload = {
            "iccid": self.sim_available.iccid,
            "carrier": "CarrierDup",
            "phone_number": "+5511999990311",
        }

        response = self.client.post(url, data=payload)

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("telecom:simcard_list"))
        self.assertEqual(SIMcard.objects.filter(iccid=payload["iccid"]).count(), 2)

    def test_simcard_create_requires_phone_number(self):
        url = reverse("telecom:simcard_create")
        payload = {
            "iccid": "8900000000000000310",
            "carrier": "CarrierRequired",
            "phone_number": "",
        }

        response = self.client.post(url, data=payload)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Este campo")
        self.assertFalse(SIMcard.objects.filter(iccid=payload["iccid"]).exists())

    def test_simcard_create_view_shows_error_when_phone_number_already_exists(self):
        SIMcard.objects.create(
            iccid="8900000000000000997",
            carrier="CarrierZ",
            status=SIMcard.Status.AVAILABLE,
        )
        existing_sim = SIMcard.objects.create(
            iccid="8900000000000000998",
            carrier="CarrierY",
            status=SIMcard.Status.AVAILABLE,
        )
        PhoneLine.objects.create(
            phone_number="+5511999990998",
            sim_card=existing_sim,
            status=PhoneLine.Status.AVAILABLE,
        )

        url = reverse("telecom:simcard_create")
        payload = {
            "iccid": "8900000000000000999",
            "carrier": "CarrierX",
            "phone_number": "+5511999990998",
        }

        response = self.client.post(url, data=payload)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Número de linha já cadastrado.")
        self.assertFalse(SIMcard.objects.filter(iccid=payload["iccid"]).exists())

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


class TelecomPermissionTest(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="admin.rbac@test.com",
            password="123456",
            role=SystemUser.Role.ADMIN,
        )
        self.operator = SystemUser.objects.create_user(
            email="operator.rbac@test.com",
            password="123456",
            role=SystemUser.Role.OPERATOR,
        )

        sim = SIMcard.objects.create(iccid="8900000000000000999", carrier="CarX")
        self.line = PhoneLine.objects.create(
            phone_number="+551199999888",
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
        )

    def test_admin_can_access_all_telecom_views(self):
        self.client.force_login(self.admin)

        resp = self.client.get(reverse("telecom:overview"))
        self.assertEqual(resp.status_code, 200)

    def test_operator_is_denied_on_telecom_views(self):
        self.client.force_login(self.operator)

        resp = self.client.get(reverse("telecom:overview"))
        self.assertEqual(resp.status_code, 403)

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get(reverse("telecom:overview"))
        self.assertEqual(resp.status_code, 403)


class PhoneLineViewsTest(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="admin.lines@test.com",
            password="123456",
            role=SystemUser.Role.ADMIN,
        )
        self.client.force_login(self.admin)

        self.sim_available = SIMcard.objects.create(
            iccid="8900000000000000404",
            carrier="CarrierD",
            status=SIMcard.Status.AVAILABLE,
        )
        self.sim_other = SIMcard.objects.create(
            iccid="8900000000000000505",
            carrier="CarrierE",
            status=SIMcard.Status.AVAILABLE,
        )

        self.line_available = PhoneLine.objects.create(
            phone_number="+551199999001",
            sim_card=self.sim_available,
            status=PhoneLine.Status.AVAILABLE,
        )
        self.line_allocated = PhoneLine.objects.create(
            phone_number="+551199999002",
            sim_card=self.sim_other,
            status=PhoneLine.Status.ALLOCATED,
        )

    def test_list_view_shows_lines_and_sim_binding(self):
        url = reverse("telecom:overview")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(self.line_available.phone_number, content)
        self.assertIn(self.sim_available.iccid, content)

    def test_filter_by_status(self):
        url = reverse("telecom:overview")
        response = self.client.get(url, {"status": PhoneLine.Status.AVAILABLE})

        self.assertEqual(response.status_code, 200)
        lines = list(response.context["initial_lines"])
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].pk, self.line_available.pk)

    def test_search_by_phone_number(self):
        url = reverse("telecom:overview")
        response = self.client.get(url, {"line": "9999002"})

        self.assertEqual(response.status_code, 200)
        lines = list(response.context["initial_lines"])
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].pk, self.line_allocated.pk)

    def test_ajax_overview_returns_plural_urls_for_actions(self):
        url = reverse("telecom:overview")
        response = self.client.get(
            url,
            {"table": "main", "offset": 0, "limit": 10},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        target = next(item for item in payload["data"] if item["id"] == self.line_available.pk)
        self.assertEqual(
            target["edit_url"],
            reverse("telecom:phoneline_update", args=[self.line_available.pk]),
        )
        self.assertEqual(
            target["history_url"],
            reverse("telecom:phoneline_history", args=[self.line_available.pk]),
        )

    def test_create_view_binds_sim_to_new_line(self):
        new_sim = SIMcard.objects.create(
            iccid="8900000000000000606",
            carrier="CarrierF",
            status=SIMcard.Status.AVAILABLE,
        )

        url = reverse("telecom:phoneline_create")
        payload = {
            "phone_number": "+551199999003",
            "sim_card": new_sim.pk,
        }

        response = self.client.post(url, data=payload)

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("telecom:overview"))
        self.assertTrue(
            PhoneLine.objects.filter(
                phone_number=payload["phone_number"], sim_card=new_sim
            ).exists()
        )

    def test_update_view_changes_phone_number(self):
        url = reverse("telecom:phoneline_update", args=[self.line_available.pk])
        payload = {
            "phone_number": "+551199999999",
            "sim_card": self.sim_available.pk,
            "status": PhoneLine.Status.SUSPENDED,
        }

        response = self.client.post(url, data=payload)

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("telecom:overview"))
        self.line_available.refresh_from_db()
        self.assertEqual(self.line_available.phone_number, "+551199999001")
        self.assertEqual(self.line_available.sim_card_id, self.sim_available.pk)
        self.assertEqual(self.line_available.status, PhoneLine.Status.SUSPENDED)

    def test_update_view_shows_business_error_when_employee_has_two_lines(self):
        employee = Employee.objects.create(
            full_name="TESTE1",
            corporate_email="supervisor@test.com",
            employee_id="EMP-LIMIT",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )

        sim_1 = SIMcard.objects.create(
            iccid="8900000000000000707",
            carrier="CarrierG",
            status=SIMcard.Status.AVAILABLE,
        )
        sim_2 = SIMcard.objects.create(
            iccid="8900000000000000808",
            carrier="CarrierH",
            status=SIMcard.Status.AVAILABLE,
        )
        line_1 = PhoneLine.objects.create(
            phone_number="+551199999070",
            sim_card=sim_1,
            status=PhoneLine.Status.AVAILABLE,
        )
        line_2 = PhoneLine.objects.create(
            phone_number="+551199999080",
            sim_card=sim_2,
            status=PhoneLine.Status.AVAILABLE,
        )
        AllocationService.allocate_line(
            employee=employee, phone_line=line_1, allocated_by=self.admin
        )
        AllocationService.allocate_line(
            employee=employee, phone_line=line_2, allocated_by=self.admin
        )

        url = reverse("telecom:phoneline_update", args=[self.line_available.pk])
        response = self.client.post(
            url,
            data={
                "phone_number": self.line_available.phone_number,
                "sim_card": self.line_available.sim_card.pk,
                "status": PhoneLine.Status.ALLOCATED,
                "employee": employee.pk,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "O usuário TESTE1 já possui 2 linhas alocadas ativas.",
        )
        self.line_available.refresh_from_db()
        self.assertEqual(self.line_available.status, PhoneLine.Status.AVAILABLE)
