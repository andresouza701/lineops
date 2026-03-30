from django.contrib import admin
from django.test import RequestFactory
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from allocations.forms import TelephonyAssignmentForm
from core.current_user import clear_current_user, set_current_user
from core.services.allocation_service import AllocationService
from employees.models import Employee
from telecom.forms import BlipConfigurationForm
from telecom.models import BlipConfiguration, PhoneLine, PhoneLineHistory, SIMcard
from users.models import SystemUser


class TelecomAdminRegistrationTest(TestCase):
    def test_phone_line_is_not_registered_in_admin(self):
        self.assertNotIn(PhoneLine, admin.site._registry)

    def test_simcard_is_registered_in_admin(self):
        self.assertIn(SIMcard, admin.site._registry)

    def test_blip_configuration_is_registered_in_admin(self):
        self.assertIn(BlipConfiguration, admin.site._registry)

    def test_simcard_admin_form_hides_soft_delete_flag(self):
        admin_user = SystemUser.objects.create_user(
            email="simcard.admin.form@test.com",
            password="123456",
            role=SystemUser.Role.ADMIN,
        )
        request = RequestFactory().get("/admin/telecom/simcard/add/")
        request.user = admin_user

        form_class = admin.site._registry[SIMcard].get_form(request)

        self.assertNotIn("is_deleted", form_class.base_fields)


class TelecomAdminDeleteTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin_user = SystemUser.objects.create_user(
            email="telecom.admin@test.com",
            password="123456",
            role=SystemUser.Role.ADMIN,
        )
        self.model_admin = admin.site._registry[SIMcard]

    def _build_sim_with_active_line(self, suffix):
        employee = Employee.objects.create(
            full_name=f"Delete Admin User {suffix}",
            corporate_email=f"delete-admin-{suffix}@corp.com",
            employee_id=f"EMP-ADM-{suffix}",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        sim_card = SIMcard.objects.create(
            iccid=f"8900000000000009{suffix:03d}",
            carrier="CarrierA",
            status=SIMcard.Status.AVAILABLE,
        )
        phone_line = PhoneLine.objects.create(
            phone_number=f"+551199990{suffix:04d}",
            sim_card=sim_card,
            status=PhoneLine.Status.AVAILABLE,
        )
        allocation = AllocationService.allocate_line(
            employee=employee,
            phone_line=phone_line,
            allocated_by=self.admin_user,
        )
        return sim_card, phone_line, allocation

    def test_simcard_admin_delete_model_releases_active_allocation_and_soft_deletes(self):
        sim_card, phone_line, allocation = self._build_sim_with_active_line(1)
        request = self.factory.post("/admin/telecom/simcard/")
        request.user = self.admin_user

        set_current_user(self.admin_user)
        try:
            self.model_admin.delete_model(request, sim_card)
        finally:
            clear_current_user()

        sim_card.refresh_from_db()
        phone_line.refresh_from_db()
        allocation.refresh_from_db()
        self.assertTrue(sim_card.is_deleted)
        self.assertTrue(phone_line.is_deleted)
        self.assertFalse(allocation.is_active)
        self.assertEqual(phone_line.status, PhoneLine.Status.AVAILABLE)

    def test_simcard_admin_delete_queryset_releases_active_allocations_and_soft_deletes(self):
        first_sim, first_line, first_allocation = self._build_sim_with_active_line(2)
        second_sim, second_line, second_allocation = self._build_sim_with_active_line(3)
        request = self.factory.post("/admin/telecom/simcard/")
        request.user = self.admin_user

        set_current_user(self.admin_user)
        try:
            queryset = SIMcard.objects.filter(pk__in=[first_sim.pk, second_sim.pk])
            self.model_admin.delete_queryset(request, queryset)
        finally:
            clear_current_user()

        for sim_card, phone_line, allocation in [
            (first_sim, first_line, first_allocation),
            (second_sim, second_line, second_allocation),
        ]:
            sim_card.refresh_from_db()
            phone_line.refresh_from_db()
            allocation.refresh_from_db()
            self.assertTrue(sim_card.is_deleted)
            self.assertTrue(phone_line.is_deleted)
            self.assertFalse(allocation.is_active)
            self.assertEqual(phone_line.status, PhoneLine.Status.AVAILABLE)

    def test_simcard_admin_delete_confirmation_has_no_protected_blockers(self):
        sim_card, phone_line, _ = self._build_sim_with_active_line(4)
        request = self.factory.get(f"/admin/telecom/simcard/{sim_card.pk}/delete/")
        request.user = self.admin_user

        deleted_objects, model_count, perms_needed, protected = (
            self.model_admin.get_deleted_objects([sim_card], request)
        )

        self.assertFalse(perms_needed)
        self.assertEqual(protected, [])
        self.assertIn(str(sim_card), deleted_objects)
        self.assertIn(
            f"Linha vinculada (soft delete): {phone_line.phone_number}",
            deleted_objects,
        )
        self.assertEqual(model_count["simcards"], 1)
        self.assertEqual(model_count["phone lines"], 1)

    def test_simcard_admin_reuses_soft_deleted_phone_line_number(self):
        old_sim = SIMcard.objects.create(
            iccid="8900000000000010001",
            carrier="CarrierOld",
            status=SIMcard.Status.AVAILABLE,
        )
        old_line = PhoneLine.objects.create(
            phone_number="+551199991111",
            sim_card=old_sim,
            status=PhoneLine.Status.AVAILABLE,
        )
        old_line.delete()
        old_sim.delete()

        request = self.factory.post("/admin/telecom/simcard/add/")
        request.user = self.admin_user
        form_class = self.model_admin.get_form(request)
        form = form_class(
            data={
                "iccid": "8900000000000010002",
                "carrier": "CarrierNew",
                "status": SIMcard.Status.AVAILABLE,
                "activated_at": "",
                "phone_number": old_line.phone_number,
                "origem": PhoneLine.Origem.APARELHO,
                "line_status": PhoneLine.Status.AVAILABLE,
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        new_sim = form.save(commit=False)
        self.model_admin.save_model(request, new_sim, form, change=False)

        reused_line = PhoneLine.all_objects.get(pk=old_line.pk)
        self.assertFalse(reused_line.is_deleted)
        self.assertEqual(reused_line.sim_card_id, new_sim.pk)
        self.assertEqual(reused_line.phone_number, old_line.phone_number)
        self.assertEqual(reused_line.origem, PhoneLine.Origem.APARELHO)

    def test_manager_create_reuses_soft_deleted_phone_line_number(self):
        old_sim = SIMcard.objects.create(
            iccid="8900000000000010101",
            carrier="CarrierLegacy",
            status=SIMcard.Status.AVAILABLE,
        )
        old_line = PhoneLine.objects.create(
            phone_number="+5511999910101",
            sim_card=old_sim,
            status=PhoneLine.Status.AVAILABLE,
        )
        old_line.delete()
        old_sim.delete()

        new_sim = SIMcard.objects.create(
            iccid="8900000000000010102",
            carrier="CarrierCurrent",
            status=SIMcard.Status.AVAILABLE,
        )

        reused_line = PhoneLine.objects.create(
            phone_number=old_line.phone_number,
            sim_card=new_sim,
            status=PhoneLine.Status.AVAILABLE,
        )

        self.assertEqual(reused_line.pk, old_line.pk)
        self.assertFalse(reused_line.is_deleted)
        self.assertEqual(reused_line.sim_card_id, new_sim.pk)
        self.assertEqual(
            PhoneLine.all_objects.filter(phone_number=old_line.phone_number).count(),
            1,
        )

    def test_simcard_queryset_delete_releases_active_allocation_and_soft_deletes(self):
        sim_card, phone_line, allocation = self._build_sim_with_active_line(5)

        deleted_count, details = SIMcard.objects.filter(pk=sim_card.pk).delete()

        sim_card.refresh_from_db()
        phone_line.refresh_from_db()
        allocation.refresh_from_db()
        self.assertEqual(deleted_count, 1)
        self.assertEqual(details["telecom.SIMcard"], 1)
        self.assertTrue(sim_card.is_deleted)
        self.assertTrue(phone_line.is_deleted)
        self.assertFalse(allocation.is_active)


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
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        allocation.refresh_from_db()
        self.phone_line.refresh_from_db()
        self.assertEqual(allocation.employee_id, self.employee_a.pk)
        self.assertEqual(self.phone_line.status, PhoneLine.Status.ALLOCATED)
        self.assertContains(response, "Edi")

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
                PhoneLineHistory.ActionType.SIMCARD_CHANGED,
                PhoneLineHistory.ActionType.DELETED,
                PhoneLineHistory.ActionType.ALLOCATED,
                PhoneLineHistory.ActionType.RELEASED,
            }.issubset(actions)
        )

        sim_event = PhoneLineHistory.objects.filter(
            phone_line=self.phone_line,
            action=PhoneLineHistory.ActionType.SIMCARD_CHANGED,
        ).first()
        self.assertIsNotNone(sim_event)
        self.assertEqual(sim_event.changed_by, self.admin)

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

    def test_simcard_create_view_accepts_textual_iccid(self):
        url = reverse("telecom:simcard_create")
        payload = {
            "iccid": "VIRTUAL",
            "carrier": "CCCC",
            "phone_number": "111111111111",
            "origem": PhoneLine.Origem.SRVMEMU_01,
        }

        response = self.client.post(url, data=payload)

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("telecom:simcard_list"))
        created_sim = SIMcard.objects.get(iccid=payload["iccid"])
        line = PhoneLine.objects.get(sim_card=created_sim)
        self.assertEqual(line.phone_number, payload["phone_number"])
        self.assertEqual(line.origem, payload["origem"])

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

    def test_simcard_create_view_reuses_soft_deleted_phone_line_number(self):
        old_sim = SIMcard.objects.create(
            iccid="8900000000000000312",
            carrier="CarrierOld",
            status=SIMcard.Status.AVAILABLE,
        )
        old_line = PhoneLine.objects.create(
            phone_number="+5511999990312",
            sim_card=old_sim,
            status=PhoneLine.Status.AVAILABLE,
        )
        old_line.delete()

        response = self.client.post(
            reverse("telecom:simcard_create"),
            data={
                "iccid": "8900000000000001312",
                "carrier": "CarrierNew",
                "phone_number": old_line.phone_number,
                "origem": PhoneLine.Origem.APARELHO,
            },
        )

        self.assertEqual(response.status_code, 302)
        reused_line = PhoneLine.all_objects.get(pk=old_line.pk)
        self.assertFalse(reused_line.is_deleted)
        self.assertEqual(reused_line.sim_card.iccid, "8900000000000001312")
        self.assertEqual(reused_line.origem, PhoneLine.Origem.APARELHO)
        self.assertEqual(
            PhoneLine.all_objects.filter(phone_number=old_line.phone_number).count(),
            1,
        )

    def test_simcard_create_view_reuses_line_from_soft_deleted_simcard(self):
        old_sim = SIMcard.objects.create(
            iccid="8900000000000000313",
            carrier="CarrierLegacy",
            status=SIMcard.Status.AVAILABLE,
        )
        old_line = PhoneLine.objects.create(
            phone_number="+5511999990313",
            sim_card=old_sim,
            status=PhoneLine.Status.AVAILABLE,
        )
        old_sim.is_deleted = True
        old_sim.save(update_fields=["is_deleted"])

        response = self.client.post(
            reverse("telecom:simcard_create"),
            data={
                "iccid": "8900000000000001313",
                "carrier": "CarrierRecovered",
                "phone_number": old_line.phone_number,
                "origem": PhoneLine.Origem.SRVMEMU_01,
            },
        )

        self.assertEqual(response.status_code, 302)
        reused_line = PhoneLine.all_objects.get(pk=old_line.pk)
        self.assertFalse(reused_line.is_deleted)
        self.assertEqual(reused_line.sim_card.iccid, "8900000000000001313")
        self.assertEqual(reused_line.origem, PhoneLine.Origem.SRVMEMU_01)

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
        self.operator = SystemUser.objects.create_user(
            email="operator.lines@test.com",
            password="123456",
            role=SystemUser.Role.OPERATOR,
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
        self.blip_sim = SIMcard.objects.create(
            iccid="8900000000000000515",
            carrier="CarrierBlip",
            status=SIMcard.Status.AVAILABLE,
        )
        self.blip_line = PhoneLine.objects.create(
            phone_number="+551199999515",
            sim_card=self.blip_sim,
            status=PhoneLine.Status.AVAILABLE,
            origem=PhoneLine.Origem.BLIP,
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
        self.assertEqual(len(lines), 2)
        self.assertIn(self.line_available.pk, [line.pk for line in lines])
        self.assertIn(self.blip_line.pk, [line.pk for line in lines])

    def test_search_by_phone_number(self):
        url = reverse("telecom:overview")
        response = self.client.get(url, {"line": "9999002"})

        self.assertEqual(response.status_code, 200)
        lines = list(response.context["initial_lines"])
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].pk, self.line_allocated.pk)

    def test_overview_hides_line_when_related_simcard_is_soft_deleted(self):
        self.sim_available.delete()

        response = self.client.get(reverse("telecom:overview"))

        self.assertEqual(response.status_code, 200)
        lines = list(response.context["initial_lines"])
        self.assertNotIn(self.line_available.pk, [line.pk for line in lines])
        self.assertNotContains(response, self.line_available.phone_number)

    def test_ajax_overview_returns_plural_urls_for_actions(self):
        url = reverse("telecom:overview")
        response = self.client.get(
            url,
            {"table": "main", "offset": 0, "limit": 10},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        target = next(
            item for item in payload["data"] if item["id"] == self.line_available.pk
        )
        self.assertEqual(
            target["edit_url"],
            reverse("telecom:phoneline_update", args=[self.line_available.pk]),
        )
        self.assertEqual(
            target["history_url"],
            reverse("telecom:phoneline_history", args=[self.line_available.pk]),
        )

    def test_ajax_overview_ignores_invalid_offset_and_limit(self):
        url = reverse("telecom:overview")
        response = self.client.get(
            url,
            {"table": "main", "offset": "abc", "limit": "xyz"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("data", payload)
        self.assertGreaterEqual(len(payload["data"]), 1)

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

    def test_create_view_shows_form_error_when_phone_number_already_exists(self):
        new_sim = SIMcard.objects.create(
            iccid="8900000000000000607",
            carrier="CarrierG",
            status=SIMcard.Status.AVAILABLE,
        )

        url = reverse("telecom:phoneline_create")
        payload = {
            "phone_number": self.line_available.phone_number,
            "sim_card": new_sim.pk,
        }

        response = self.client.post(url, data=payload)

        self.assertEqual(response.status_code, 200)
        self.assertIn("phone_number", response.context["form"].errors)
        self.assertFalse(
            PhoneLine.objects.filter(
                phone_number=self.line_available.phone_number,
                sim_card=new_sim,
            ).exists()
        )

    def test_create_view_reuses_soft_deleted_line_with_same_simcard(self):
        recycled_sim = SIMcard.objects.create(
            iccid="8900000000000000608",
            carrier="CarrierRecycle",
            status=SIMcard.Status.AVAILABLE,
        )
        deleted_line = PhoneLine.objects.create(
            phone_number="+5511999990608",
            sim_card=recycled_sim,
            status=PhoneLine.Status.AVAILABLE,
            origem=PhoneLine.Origem.APARELHO,
        )
        deleted_line.delete()

        response = self.client.get(reverse("telecom:phoneline_create"))
        form_queryset = response.context["form"].fields["sim_card"].queryset
        self.assertIn(recycled_sim.pk, list(form_queryset.values_list("pk", flat=True)))

        response = self.client.post(
            reverse("telecom:phoneline_create"),
            data={
                "phone_number": deleted_line.phone_number,
                "sim_card": recycled_sim.pk,
                "origem": PhoneLine.Origem.SRVMEMU_01,
            },
        )

        self.assertEqual(response.status_code, 302)
        reused_line = PhoneLine.all_objects.get(pk=deleted_line.pk)
        self.assertFalse(reused_line.is_deleted)
        self.assertEqual(reused_line.sim_card_id, recycled_sim.pk)
        self.assertEqual(reused_line.origem, PhoneLine.Origem.SRVMEMU_01)

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

    def test_update_view_shows_business_error_when_employee_has_four_lines(self):
        employee = Employee.objects.create(
            full_name="TESTE1",
            corporate_email="supervisor@test.com",
            employee_id="EMP-LIMIT",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )

        for suffix in range(4):
            sim = SIMcard.objects.create(
                iccid=f"89000000000000007{suffix:02d}",
                carrier=f"Carrier{suffix}",
                status=SIMcard.Status.AVAILABLE,
            )
            line = PhoneLine.objects.create(
                phone_number=f"+55119999907{suffix:02d}",
                sim_card=sim,
                status=PhoneLine.Status.AVAILABLE,
            )
            AllocationService.allocate_line(
                employee=employee,
                phone_line=line,
                allocated_by=self.admin,
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
        self.assertContains(response, "4 linhas alocadas ativas.")
        self.line_available.refresh_from_db()
        self.assertEqual(self.line_available.status, PhoneLine.Status.AVAILABLE)

    def test_delete_view_releases_active_allocation_before_soft_delete(self):
        employee = Employee.objects.create(
            full_name="Delete Release User",
            corporate_email="delete@corp.com",
            employee_id="EMP-DEL-1",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        allocation = AllocationService.allocate_line(
            employee=employee,
            phone_line=self.line_available,
            allocated_by=self.admin,
        )

        response = self.client.post(
            reverse("telecom:phoneline_delete", args=[self.line_available.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.line_available.refresh_from_db()
        allocation.refresh_from_db()
        self.assertTrue(self.line_available.is_deleted)
        self.assertFalse(allocation.is_active)
        self.assertEqual(self.line_available.status, PhoneLine.Status.AVAILABLE)

    def test_operator_telephony_form_hides_blip_lines(self):
        form = TelephonyAssignmentForm(user=self.operator)

        self.assertNotIn(
            self.blip_line.pk,
            list(form.fields["phone_line"].queryset.values_list("pk", flat=True)),
        )
        self.assertNotIn(
            self.blip_line.pk,
            list(form.fields["phone_line_status"].queryset.values_list("pk", flat=True)),
        )

    def test_admin_telephony_form_shows_blip_lines(self):
        form = TelephonyAssignmentForm(user=self.admin)

        self.assertIn(
            self.blip_line.pk,
            list(form.fields["phone_line"].queryset.values_list("pk", flat=True)),
        )


class BlipConfigurationViewsTest(TestCase):
    def setUp(self):
        self.dev = SystemUser.objects.create_user(
            email="dev.blip@test.com",
            password="123456",
            role=SystemUser.Role.DEV,
        )
        self.admin = SystemUser.objects.create_user(
            email="admin.blip@test.com",
            password="123456",
            role=SystemUser.Role.ADMIN,
        )
        self.blip_sim = SIMcard.objects.create(
            iccid="8900000000000002121",
            carrier="CarrierBlip",
            status=SIMcard.Status.AVAILABLE,
        )
        self.blip_line = PhoneLine.objects.create(
            phone_number="5547999999999",
            sim_card=self.blip_sim,
            status=PhoneLine.Status.AVAILABLE,
            origem=PhoneLine.Origem.BLIP,
        )
        self.other_sim = SIMcard.objects.create(
            iccid="8900000000000002222",
            carrier="CarrierOther",
            status=SIMcard.Status.AVAILABLE,
        )
        self.other_line = PhoneLine.objects.create(
            phone_number="5547988887777",
            sim_card=self.other_sim,
            status=PhoneLine.Status.AVAILABLE,
            origem=PhoneLine.Origem.APARELHO,
        )

    def test_dev_can_list_blip_configurations(self):
        configuration = BlipConfiguration.objects.create(
            blip_id="blip-flow-01",
            type=BlipConfiguration.ConfigurationType.FLOW,
            description="Fluxo principal",
            phone_number=5547999999999,
            key=BlipConfiguration.KeyType.ACCESS,
            value="token-123",
        )
        self.client.force_login(self.dev)

        response = self.client.get(reverse("telecom:blip_configuration_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, configuration.blip_id)
        self.assertContains(response, "Novo cadastro")

    def test_dev_can_create_blip_configuration(self):
        self.client.force_login(self.dev)

        response = self.client.post(
            reverse("telecom:blip_configuration_create"),
            data={
                "blip_id": "router-02",
                "type": BlipConfiguration.ConfigurationType.ROUTER,
                "description": "Roteador para fallback",
                "phone_number": self.blip_line.phone_number,
                "key": BlipConfiguration.KeyType.HTTP,
                "value": "https://example.test/router",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("telecom:blip_configuration_list"))
        self.assertTrue(
            BlipConfiguration.objects.filter(
                blip_id="router-02",
                type=BlipConfiguration.ConfigurationType.ROUTER,
            ).exists()
        )

    def test_blip_configuration_form_phone_number_shows_only_blip_lines(self):
        form = BlipConfigurationForm(user=self.dev)

        self.assertIn(
            (self.blip_line.phone_number, self.blip_line.phone_number),
            list(form.fields["phone_number"].choices),
        )
        self.assertNotIn(
            (self.other_line.phone_number, self.other_line.phone_number),
            list(form.fields["phone_number"].choices),
        )

    def test_blip_configuration_create_rejects_non_blip_phone_number(self):
        self.client.force_login(self.dev)

        response = self.client.post(
            reverse("telecom:blip_configuration_create"),
            data={
                "blip_id": "router-03",
                "type": BlipConfiguration.ConfigurationType.ROUTER,
                "description": "Roteador invalido",
                "phone_number": self.other_line.phone_number,
                "key": BlipConfiguration.KeyType.HTTP,
                "value": "https://example.test/router-invalid",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("phone_number", response.context["form"].errors)

    def test_non_dev_cannot_access_blip_configuration_area(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("telecom:blip_configuration_list"))

        self.assertEqual(response.status_code, 403)

    def test_dev_root_dashboard_redirects_to_blip_configuration_list(self):
        self.client.force_login(self.dev)

        response = self.client.get(reverse("dashboard"))

        self.assertRedirects(response, reverse("telecom:blip_configuration_list"))

    def test_dev_navigation_shows_only_blip_entry(self):
        self.client.force_login(self.dev)

        response = self.client.get(reverse("telecom:blip_configuration_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("telecom:blip_configuration_list"))
        self.assertNotContains(response, 'aria-label="Dashboard"', html=False)
        self.assertNotContains(response, 'aria-label="Ações do Dia"', html=False)

    def test_dev_can_filter_blip_configurations_by_blip_id(self):
        target = BlipConfiguration.objects.create(
            blip_id="blip-flow-01",
            type=BlipConfiguration.ConfigurationType.FLOW,
            description="Fluxo principal",
            phone_number=5547999999999,
            key=BlipConfiguration.KeyType.ACCESS,
            value="token-123",
        )
        BlipConfiguration.objects.create(
            blip_id="router-02",
            type=BlipConfiguration.ConfigurationType.ROUTER,
            description="Roteador",
            phone_number=5547988887777,
            key=BlipConfiguration.KeyType.HTTP,
            value="https://example.test/router",
        )
        self.client.force_login(self.dev)

        response = self.client.get(
            reverse("telecom:blip_configuration_list"),
            {"blip_id": "flow-01"},
        )

        self.assertEqual(response.status_code, 200)
        configurations = list(response.context["configurations"])
        self.assertEqual(len(configurations), 1)
        self.assertEqual(configurations[0].pk, target.pk)

    def test_dev_can_filter_blip_configurations_by_phone_number(self):
        BlipConfiguration.objects.create(
            blip_id="blip-flow-01",
            type=BlipConfiguration.ConfigurationType.FLOW,
            description="Fluxo principal",
            phone_number=5547999999999,
            key=BlipConfiguration.KeyType.ACCESS,
            value="token-123",
        )
        target = BlipConfiguration.objects.create(
            blip_id="router-02",
            type=BlipConfiguration.ConfigurationType.ROUTER,
            description="Roteador",
            phone_number=5547988887777,
            key=BlipConfiguration.KeyType.HTTP,
            value="https://example.test/router",
        )
        self.client.force_login(self.dev)

        response = self.client.get(
            reverse("telecom:blip_configuration_list"),
            {"phone_number": "88887777"},
        )

        self.assertEqual(response.status_code, 200)
        configurations = list(response.context["configurations"])
        self.assertEqual(len(configurations), 1)
        self.assertEqual(configurations[0].pk, target.pk)

