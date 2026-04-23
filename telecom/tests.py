from datetime import timedelta

from django.contrib import admin
from django.test import RequestFactory
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from unittest.mock import ANY, patch

from allocations.forms import TelephonyAssignmentForm
from core.current_user import clear_current_user, set_current_user
from core.exceptions.domain_exceptions import BusinessRuleException
from core.services.allocation_service import AllocationService
from employees.models import Employee
from telecom import history as telecom_history
from telecom.forms import BlipConfigurationForm
from telecom.models import BlipConfiguration, PhoneLine, PhoneLineHistory, SIMcard, WhatsappReconnectHistory
from users.models import SystemUser


class TelecomAdminRegistrationTest(TestCase):
    def test_phone_line_is_not_registered_in_admin(self):
        self.assertNotIn(PhoneLine, admin.site._registry)

    def test_simcard_is_registered_in_admin(self):
        self.assertIn(SIMcard, admin.site._registry)

    def test_blip_configuration_is_registered_in_admin(self):
        self.assertIn(BlipConfiguration, admin.site._registry)

    def test_legacy_history_module_exports_canonical_model(self):
        self.assertIs(telecom_history.PhoneLineHistory, PhoneLineHistory)

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


class SIMcardNormalizationTest(TestCase):
    def test_save_normalizes_carrier_name(self):
        sim_card = SIMcard.objects.create(
            iccid="8900000000000000001",
            carrier=" tim ",
            status=SIMcard.Status.AVAILABLE,
        )

        sim_card.refresh_from_db()

        self.assertEqual(sim_card.carrier, "TIM")


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
                "canal": PhoneLine.Canal.WEB,
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
        self.assertEqual(reused_line.canal, PhoneLine.Canal.WEB)

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
        line = PhoneLine.objects.get(
            phone_number=payload["phone_number"],
            sim_card=created_sim,
        )
        self.assertIsNone(line.canal)

    def test_simcard_create_view_accepts_textual_iccid(self):
        url = reverse("telecom:simcard_create")
        payload = {
            "iccid": "VIRTUAL",
            "carrier": "CCCC",
            "phone_number": "111111111111",
            "origem": PhoneLine.Origem.SRVMEMU_01,
            "canal": PhoneLine.Canal.MYLOOP,
        }

        response = self.client.post(url, data=payload)

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("telecom:simcard_list"))
        created_sim = SIMcard.objects.get(iccid=payload["iccid"])
        line = PhoneLine.objects.get(sim_card=created_sim)
        self.assertEqual(line.phone_number, payload["phone_number"])
        self.assertEqual(line.origem, payload["origem"])
        self.assertEqual(line.canal, payload["canal"])

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
                "canal": PhoneLine.Canal.WEB,
            },
        )

        self.assertEqual(response.status_code, 302)
        reused_line = PhoneLine.all_objects.get(pk=old_line.pk)
        self.assertFalse(reused_line.is_deleted)
        self.assertEqual(reused_line.sim_card.iccid, "8900000000000001312")
        self.assertEqual(reused_line.origem, PhoneLine.Origem.APARELHO)
        self.assertEqual(reused_line.canal, PhoneLine.Canal.WEB)
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
                "canal": PhoneLine.Canal.MYLOOP,
            },
        )

        self.assertEqual(response.status_code, 302)
        reused_line = PhoneLine.all_objects.get(pk=old_line.pk)
        self.assertFalse(reused_line.is_deleted)
        self.assertEqual(reused_line.sim_card.iccid, "8900000000000001313")
        self.assertEqual(reused_line.origem, PhoneLine.Origem.SRVMEMU_01)
        self.assertEqual(reused_line.canal, PhoneLine.Canal.MYLOOP)

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
        self.supervisor = SystemUser.objects.create_user(
            email="super.rbac@test.com",
            password="123456",
            role=SystemUser.Role.SUPER,
        )
        self.backoffice = SystemUser.objects.create_user(
            email="backoffice.rbac@test.com",
            password="123456",
            role=SystemUser.Role.BACKOFFICE,
            supervisor_email="super.rbac@test.com",
        )
        self.manager = SystemUser.objects.create_user(
            email="manager.rbac@test.com",
            password="123456",
            role=SystemUser.Role.GERENTE,
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

    def test_super_can_access_telecom_overview(self):
        self.client.force_login(self.supervisor)

        resp = self.client.get(reverse("telecom:overview"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'aria-label="Telecom"', html=False)

    def test_backoffice_can_access_telecom_overview(self):
        self.client.force_login(self.backoffice)

        resp = self.client.get(reverse("telecom:overview"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'aria-label="Telecom"', html=False)

    def test_manager_can_access_telecom_overview(self):
        self.client.force_login(self.manager)

        resp = self.client.get(reverse("telecom:overview"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'aria-label="Telecom"', html=False)

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
            origem=PhoneLine.Origem.SRVMEMU_01,
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

    @override_settings(RECONNECT_ENABLED=True)
    def test_overview_shows_reconnect_button_when_feature_enabled(self):
        response = self.client.get(reverse("telecom:overview"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reconnect")
        self.assertContains(
            response,
            f'{reverse("telecom:phoneline_detail", args=[self.line_available.pk])}#reconnect-whatsapp',
            html=False,
        )
        self.assertNotContains(
            response,
            f'{reverse("telecom:phoneline_detail", args=[self.blip_line.pk])}#reconnect-whatsapp',
            html=False,
        )

    @override_settings(RECONNECT_ENABLED=True)
    def test_ajax_overview_returns_reconnect_url_when_feature_enabled(self):
        response = self.client.get(
            reverse("telecom:overview"),
            {"table": "main", "offset": 0, "limit": 10},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        target = next(
            item for item in payload["data"] if item["id"] == self.line_available.pk
        )
        self.assertEqual(
            target["reconnect_url"],
            f'{reverse("telecom:phoneline_detail", args=[self.line_available.pk])}#reconnect-whatsapp',
        )
        non_eligible_target = next(
            item for item in payload["data"] if item["id"] == self.blip_line.pk
        )
        self.assertNotIn("reconnect_url", non_eligible_target)

    @override_settings(RECONNECT_ENABLED=True)
    def test_detail_hides_reconnect_section_for_non_srvmemu_01_origin(self):
        response = self.client.get(
            reverse("telecom:phoneline_detail", args=[self.blip_line.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Reconexao WhatsApp")

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
            "canal": PhoneLine.Canal.WEB,
        }

        response = self.client.post(url, data=payload)

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("telecom:overview"))
        line = PhoneLine.objects.get(
            phone_number=payload["phone_number"],
            sim_card=new_sim,
        )
        self.assertEqual(line.canal, PhoneLine.Canal.WEB)

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
                "canal": PhoneLine.Canal.MYLOOP,
            },
        )

        self.assertEqual(response.status_code, 302)
        reused_line = PhoneLine.all_objects.get(pk=deleted_line.pk)
        self.assertFalse(reused_line.is_deleted)
        self.assertEqual(reused_line.sim_card_id, recycled_sim.pk)
        self.assertEqual(reused_line.origem, PhoneLine.Origem.SRVMEMU_01)
        self.assertEqual(reused_line.canal, PhoneLine.Canal.MYLOOP)

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

    def test_update_view_keeps_canal_editable_for_admin(self):
        self.line_available.canal = PhoneLine.Canal.WEB
        self.line_available.save(update_fields=["canal"])

        response = self.client.get(
            reverse("telecom:phoneline_update", args=[self.line_available.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["form"].fields["canal"].disabled)

    def test_update_view_persists_canal_changes_for_admin(self):
        url = reverse("telecom:phoneline_update", args=[self.line_available.pk])
        payload = {
            "phone_number": self.line_available.phone_number,
            "sim_card": self.line_available.sim_card.pk,
            "status": PhoneLine.Status.AVAILABLE,
            "canal": PhoneLine.Canal.MYLOOP,
        }

        response = self.client.post(url, data=payload)

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("telecom:overview"))
        self.line_available.refresh_from_db()
        self.assertEqual(self.line_available.canal, PhoneLine.Canal.MYLOOP)

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


class BackofficePhoneLineVisibilityTests(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="admin.backoffice.line@test.com",
            password="123456",
            role=SystemUser.Role.ADMIN,
        )
        self.manager = SystemUser.objects.create_user(
            email="manager.line@test.com",
            password="123456",
            role=SystemUser.Role.GERENTE,
        )
        self.supervisor = SystemUser.objects.create_user(
            email="super.line@test.com",
            password="123456",
            role=SystemUser.Role.SUPER,
            manager_email="manager.line@test.com",
        )
        self.backoffice = SystemUser.objects.create_user(
            email="backoffice.line@test.com",
            password="123456",
            role=SystemUser.Role.BACKOFFICE,
            supervisor_email="super.line@test.com",
        )
        self.other_supervisor = SystemUser.objects.create_user(
            email="other.super.line@test.com",
            password="123456",
            role=SystemUser.Role.SUPER,
        )
        self.managed_employee = Employee.objects.create(
            full_name="Usuario Vinculado",
            corporate_email=self.supervisor.email,
            employee_id="Ambiental",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        self.unmanaged_employee = Employee.objects.create(
            full_name="Usuario Nao Vinculado",
            corporate_email=self.other_supervisor.email,
            employee_id="Natura",
            teams="Araquari",
            status=Employee.Status.ACTIVE,
        )

        managed_sim = SIMcard.objects.create(
            iccid="8900000000000099001",
            carrier="CarrierBackoffice",
            status=SIMcard.Status.AVAILABLE,
        )
        unmanaged_sim = SIMcard.objects.create(
            iccid="8900000000000099002",
            carrier="CarrierBackoffice",
            status=SIMcard.Status.AVAILABLE,
        )
        self.managed_line = PhoneLine.objects.create(
            phone_number="+5511999999901",
            sim_card=managed_sim,
            status=PhoneLine.Status.AVAILABLE,
            origem=PhoneLine.Origem.SRVMEMU_01,
        )
        self.unmanaged_line = PhoneLine.objects.create(
            phone_number="+5511999999902",
            sim_card=unmanaged_sim,
            status=PhoneLine.Status.AVAILABLE,
            origem=PhoneLine.Origem.SRVMEMU_02,
        )
        AllocationService.allocate_line(
            employee=self.managed_employee,
            phone_line=self.managed_line,
            allocated_by=self.admin,
        )
        AllocationService.allocate_line(
            employee=self.unmanaged_employee,
            phone_line=self.unmanaged_line,
            allocated_by=self.admin,
        )

    def test_backoffice_visible_to_user_only_returns_linked_supervisor_lines(self):
        visible_lines = PhoneLine.visible_to_user(self.backoffice).values_list(
            "pk", flat=True
        )

        self.assertIn(self.managed_line.pk, visible_lines)
        self.assertNotIn(self.unmanaged_line.pk, visible_lines)

    def test_backoffice_can_access_linked_phone_line_detail_only(self):
        self.client.force_login(self.backoffice)

        allowed_response = self.client.get(
            reverse("telecom:phoneline_detail", args=[self.managed_line.pk])
        )
        denied_response = self.client.get(
            reverse("telecom:phoneline_detail", args=[self.unmanaged_line.pk])
        )

        self.assertEqual(allowed_response.status_code, 200)
        self.assertEqual(denied_response.status_code, 404)

    @override_settings(RECONNECT_ENABLED=True)
    def test_backoffice_overview_shows_only_reconnect_action_for_scoped_lines(self):
        self.client.force_login(self.backoffice)

        response = self.client.get(reverse("telecom:overview"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.managed_line.phone_number)
        self.assertNotContains(response, self.unmanaged_line.phone_number)
        self.assertContains(
            response,
            f'{reverse("telecom:phoneline_detail", args=[self.managed_line.pk])}#reconnect-whatsapp',
            html=False,
        )
        self.assertNotContains(
            response,
            reverse("telecom:phoneline_update", args=[self.managed_line.pk]),
        )
        self.assertNotContains(
            response,
            reverse("telecom:phoneline_history", args=[self.managed_line.pk]),
        )

    @override_settings(RECONNECT_ENABLED=True)
    def test_backoffice_ajax_overview_returns_reconnect_url_without_admin_actions(self):
        self.client.force_login(self.backoffice)

        response = self.client.get(
            reverse("telecom:overview"),
            {"table": "main", "offset": 0, "limit": 10},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        target = next(
            item for item in payload["data"] if item["id"] == self.managed_line.pk
        )
        self.assertEqual(
            target["reconnect_url"],
            f'{reverse("telecom:phoneline_detail", args=[self.managed_line.pk])}#reconnect-whatsapp',
        )
        self.assertNotIn("edit_url", target)
        self.assertNotIn("history_url", target)

    @override_settings(RECONNECT_ENABLED=True)
    def test_backoffice_detail_hides_admin_only_buttons(self):
        self.client.force_login(self.backoffice)

        response = self.client.get(
            reverse("telecom:phoneline_detail", args=[self.managed_line.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reconexao WhatsApp")
        self.assertNotContains(
            response,
            reverse("telecom:phoneline_update", args=[self.managed_line.pk]),
        )
        self.assertNotContains(
            response,
            reverse("telecom:phoneline_history", args=[self.managed_line.pk]),
        )

    @override_settings(RECONNECT_ENABLED=True)
    def test_manager_overview_scopes_lines_and_shows_only_reconnect_action(self):
        self.client.force_login(self.manager)

        response = self.client.get(reverse("telecom:overview"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.managed_line.phone_number)
        self.assertNotContains(response, self.unmanaged_line.phone_number)
        self.assertContains(
            response,
            f'{reverse("telecom:phoneline_detail", args=[self.managed_line.pk])}#reconnect-whatsapp',
            html=False,
        )
        self.assertNotContains(
            response,
            reverse("telecom:phoneline_update", args=[self.managed_line.pk]),
        )

    @override_settings(RECONNECT_ENABLED=True)
    def test_supervisor_overview_scopes_lines_and_shows_only_reconnect_action(self):
        self.client.force_login(self.supervisor)

        response = self.client.get(reverse("telecom:overview"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.managed_line.phone_number)
        self.assertNotContains(response, self.unmanaged_line.phone_number)
        self.assertContains(
            response,
            f'{reverse("telecom:phoneline_detail", args=[self.managed_line.pk])}#reconnect-whatsapp',
            html=False,
        )
        self.assertNotContains(
            response,
            reverse("telecom:phoneline_update", args=[self.managed_line.pk]),
        )


class FakeReconnectRepository:
    def __init__(self):
        self.created_documents = []
        self.submit_calls = []
        self.cancel_calls = []
        self.active_by_phone = {}
        self.restricted_by_phone = {}
        self.latest_terminal_by_phone = {}
        self.by_id = {}
        self.submit_modified = True
        self.cancel_modified = True
        self.active_session_unique_index_present = True

    def find_active_session_by_phone(self, phone_number):
        return self.active_by_phone.get(phone_number)

    def find_recent_restricted_session_by_phone(self, phone_number):
        return self.restricted_by_phone.get(phone_number)

    def find_latest_terminal_session_by_phone(self, phone_number):
        return self.latest_terminal_by_phone.get(phone_number)

    def create_session(self, document):
        created = dict(document)
        self.created_documents.append(created)
        self.by_id[created["_id"]] = created
        self.active_by_phone[created["phone_number"]] = created
        return created

    def has_active_session_unique_index(self):
        return self.active_session_unique_index_present

    def get_session(self, session_id):
        return self.by_id.get(session_id)

    def submit_pair_code(self, *, session_id, attempt, pair_code, submitted_at):
        self.submit_calls.append(
            {
                "session_id": session_id,
                "attempt": attempt,
                "pair_code": pair_code,
                "submitted_at": submitted_at,
            }
        )
        return self.submit_modified

    def cancel_session(self, *, session_id, requested_at):
        self.cancel_calls.append(
            {
                "session_id": session_id,
                "requested_at": requested_at,
            }
        )
        session = self.by_id.get(session_id)
        if not session:
            return False

        if session.get("status") == "QUEUED" and session.get("active_lock", True):
            session.update(
                {
                    "status": "CANCELLED",
                    "cancel_requested_at": requested_at,
                    "finished_at": requested_at,
                    "active_lock": False,
                    "updated_at": requested_at,
                    "error_code": "cancel_requested",
                    "error_message": "Sessao cancelada pela plataforma",
                }
            )
            phone_number = session.get("phone_number")
            if phone_number and self.active_by_phone.get(phone_number) is session:
                self.active_by_phone.pop(phone_number, None)
            return True

        if self.cancel_modified:
            session["cancel_requested_at"] = requested_at
            session["updated_at"] = requested_at
        return self.cancel_modified


class ReconnectServiceTests(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="reconnect.admin@test.com",
            password="123456",
            role=SystemUser.Role.ADMIN,
        )
        self.employee = Employee.objects.create(
            full_name="Rafael Gomes",
            corporate_email="rafael.gomes@test.com",
            employee_id="EMP-RECON-1",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        self.sim = SIMcard.objects.create(
            iccid="8900000000000008801",
            carrier="CarrierReconnect",
            status=SIMcard.Status.AVAILABLE,
        )
        self.line = PhoneLine.objects.create(
            phone_number="+5511999991000",
            sim_card=self.sim,
            status=PhoneLine.Status.AVAILABLE,
            origem=PhoneLine.Origem.SRVMEMU_01,
            canal=PhoneLine.Canal.WEB,
        )
        AllocationService.allocate_line(
            employee=self.employee,
            phone_line=self.line,
            allocated_by=self.admin,
        )

    def test_start_for_line_builds_initial_document_from_line_context(self):
        from telecom.services.reconnect_service import ReconnectService

        repository = FakeReconnectRepository()
        service = ReconnectService(
            repository=repository,
            target_server_by_origem={PhoneLine.Origem.SRVMEMU_01: "rafael"},
        )

        session = service.start_for_line(self.line)

        self.assertEqual(session["status"], "QUEUED")
        self.assertEqual(len(repository.created_documents), 1)
        created = repository.created_documents[0]
        self.assertTrue(created["_id"].startswith("manual_reconnect_"))
        self.assertEqual(created["phone_number"], "5511999991000")
        self.assertEqual(created["vm_name"], "5511999991000")
        self.assertEqual(created["target_server"], "rafael")
        self.assertEqual(created["assigned_server"], None)
        self.assertEqual(created["attempt"], 0)
        self.assertTrue(created["active_lock"])
        self.assertEqual(created["device_name"], "Rafael Gomes")

    def test_start_for_line_reuses_existing_active_session(self):
        from telecom.services.reconnect_service import ReconnectService

        repository = FakeReconnectRepository()
        repository.active_by_phone["5511999991000"] = {
            "_id": "sess-001",
            "phone_number": "5511999991000",
            "status": "WAITING_FOR_CODE",
            "attempt": 2,
            "device_name": "Rafael Gomes",
        }
        service = ReconnectService(
            repository=repository,
            target_server_by_origem={PhoneLine.Origem.SRVMEMU_01: "rafael"},
        )

        session = service.start_for_line(self.line)

        self.assertEqual(session["session_id"], "sess-001")
        self.assertEqual(session["status"], "WAITING_FOR_CODE")
        self.assertEqual(repository.created_documents, [])

    def test_submit_code_uppercases_and_uses_current_attempt(self):
        from telecom.services.reconnect_service import ReconnectService

        repository = FakeReconnectRepository()
        repository.by_id["sess-002"] = {
            "_id": "sess-002",
            "phone_number": "5511999991000",
            "status": "WAITING_FOR_CODE",
            "attempt": 2,
            "device_name": "Rafael Gomes",
        }
        service = ReconnectService(
            repository=repository,
            target_server_by_origem={PhoneLine.Origem.SRVMEMU_01: "rafael"},
        )

        result = service.submit_code_for_line(
            self.line,
            session_id="sess-002",
            pair_code="ab12cd34",
        )

        self.assertTrue(result["code_accepted"])
        self.assertEqual(repository.submit_calls[0]["pair_code"], "AB12CD34")
        self.assertEqual(repository.submit_calls[0]["attempt"], 2)

    def test_submit_code_returns_current_session_when_repository_does_not_modify(self):
        from telecom.services.reconnect_service import ReconnectService

        repository = FakeReconnectRepository()
        repository.submit_modified = False
        repository.by_id["sess-003"] = {
            "_id": "sess-003",
            "phone_number": "5511999991000",
            "status": "WAITING_FOR_CODE",
            "attempt": 3,
            "error_code": "pair_code_rejected",
            "error_message": "Codigo expirado.",
            "device_name": "Rafael Gomes",
        }
        service = ReconnectService(
            repository=repository,
            target_server_by_origem={PhoneLine.Origem.SRVMEMU_01: "rafael"},
        )

        result = service.submit_code_for_line(
            self.line,
            session_id="sess-003",
            pair_code="xyzz9999",
        )

        self.assertFalse(result["code_accepted"])
        self.assertEqual(result["status"], "WAITING_FOR_CODE")
        self.assertEqual(result["attempt"], 3)
        self.assertEqual(result["error_code"], "pair_code_rejected")

    def test_start_for_line_blocks_origin_without_target_server_mapping(self):
        from telecom.services.reconnect_service import ReconnectService

        self.line.origem = PhoneLine.Origem.APARELHO
        self.line.save(update_fields=["origem"])
        repository = FakeReconnectRepository()
        service = ReconnectService(
            repository=repository,
            target_server_by_origem={PhoneLine.Origem.SRVMEMU_01: "rafael"},
        )

        with self.assertRaises(BusinessRuleException):
            service.start_for_line(self.line)

    def test_start_for_line_blocks_ineligible_origin_even_when_mapped(self):
        from telecom.services.reconnect_service import ReconnectService

        self.line.origem = PhoneLine.Origem.APARELHO
        self.line.save(update_fields=["origem"])
        repository = FakeReconnectRepository()
        service = ReconnectService(
            repository=repository,
            target_server_by_origem={
                PhoneLine.Origem.SRVMEMU_01: "rafael",
                PhoneLine.Origem.APARELHO: "srv-aparelho",
            },
        )

        with self.assertRaises(BusinessRuleException):
            service.start_for_line(self.line)

        self.assertEqual(repository.created_documents, [])

    def test_start_for_line_blocks_srvmemu_02_even_when_mapped(self):
        from telecom.services.reconnect_service import ReconnectService

        self.line.origem = PhoneLine.Origem.SRVMEMU_02
        self.line.save(update_fields=["origem"])
        repository = FakeReconnectRepository()
        service = ReconnectService(
            repository=repository,
            target_server_by_origem={
                PhoneLine.Origem.SRVMEMU_01: "rafael",
                PhoneLine.Origem.SRVMEMU_02: "srv02",
            },
        )

        with self.assertRaises(BusinessRuleException):
            service.start_for_line(self.line)

        self.assertEqual(repository.created_documents, [])

    def test_start_for_line_blocks_when_active_session_unique_index_is_missing(self):
        from telecom.services.reconnect_service import ReconnectService

        repository = FakeReconnectRepository()
        repository.active_session_unique_index_present = False
        service = ReconnectService(
            repository=repository,
            target_server_by_origem={PhoneLine.Origem.SRVMEMU_01: "rafael"},
        )

        with self.assertRaises(BusinessRuleException):
            service.start_for_line(self.line)

        self.assertEqual(repository.created_documents, [])

    def test_get_status_for_line_returns_terminal_session_by_id_when_not_active(self):
        from telecom.services.reconnect_service import ReconnectService

        repository = FakeReconnectRepository()
        repository.by_id["sess-terminal-001"] = {
            "_id": "sess-terminal-001",
            "phone_number": "5511999991000",
            "status": "CONNECTED",
            "attempt": 1,
            "device_name": "Rafael Gomes",
        }
        service = ReconnectService(
            repository=repository,
            target_server_by_origem={PhoneLine.Origem.SRVMEMU_01: "rafael"},
        )

        payload = service.get_status_for_line(
            self.line,
            session_id="sess-terminal-001",
        )

        self.assertEqual(payload["session_id"], "sess-terminal-001")
        self.assertEqual(payload["status"], "CONNECTED")
        self.assertTrue(payload["is_terminal"])

    def test_get_status_for_line_treats_success_alias_as_terminal_connected(self):
        from telecom.services.reconnect_service import ReconnectService

        repository = FakeReconnectRepository()
        repository.by_id["sess-terminal-success"] = {
            "_id": "sess-terminal-success",
            "phone_number": "5511999991000",
            "status": "SUCCESS",
            "attempt": 1,
            "device_name": "Rafael Gomes",
        }
        service = ReconnectService(
            repository=repository,
            target_server_by_origem={PhoneLine.Origem.SRVMEMU_01: "rafael"},
        )

        payload = service.get_status_for_line(
            self.line,
            session_id="sess-terminal-success",
        )

        self.assertEqual(payload["session_id"], "sess-terminal-success")
        self.assertEqual(payload["status"], "CONNECTED")
        self.assertEqual(payload["raw_status"], "CONNECTED")
        self.assertTrue(payload["is_terminal"])

    def test_get_status_for_line_normalizes_status_spacing_and_case(self):
        from telecom.services.reconnect_service import ReconnectService

        repository = FakeReconnectRepository()
        repository.by_id["sess-terminal-failed"] = {
            "_id": "sess-terminal-failed",
            "phone_number": "5511999991000",
            "status": " failed ",
            "attempt": 1,
            "device_name": "Rafael Gomes",
        }
        service = ReconnectService(
            repository=repository,
            target_server_by_origem={PhoneLine.Origem.SRVMEMU_01: "rafael"},
        )

        payload = service.get_status_for_line(
            self.line,
            session_id="sess-terminal-failed",
        )

        self.assertEqual(payload["status"], "FAILED")
        self.assertEqual(payload["raw_status"], "FAILED")
        self.assertTrue(payload["is_terminal"])

    def test_get_status_for_line_returns_recent_restricted_terminal_when_no_active_session(
        self,
    ):
        from telecom.services.reconnect_service import ReconnectService

        repository = FakeReconnectRepository()
        restriction_until = timezone.now() + timedelta(minutes=12)
        repository.restricted_by_phone["5511999991000"] = {
            "_id": "sess-restricted-001",
            "phone_number": "5511999991000",
            "status": "FAILED",
            "attempt": 1,
            "error_code": "whatsapp_account_restricted",
            "error_message": "Conta restrita temporariamente.",
            "account_state": "RESTRICTED",
            "restriction_seconds_remaining": 720,
            "restriction_until": restriction_until,
            "device_name": "Rafael Gomes",
            "active_lock": False,
        }
        repository.latest_terminal_by_phone["5511999991000"] = repository.restricted_by_phone[
            "5511999991000"
        ]
        service = ReconnectService(
            repository=repository,
            target_server_by_origem={PhoneLine.Origem.SRVMEMU_01: "rafael"},
        )

        payload = service.get_status_for_line(self.line)

        self.assertEqual(payload["session_id"], "sess-restricted-001")
        self.assertEqual(payload["status"], "FAILED")
        self.assertEqual(payload["error_code"], "whatsapp_account_restricted")
        self.assertEqual(payload["account_state"], "RESTRICTED")
        self.assertEqual(payload["restriction_seconds_remaining"], 720)
        self.assertEqual(payload["restriction_remaining_hms"], "00:12:00")
        self.assertTrue(payload["restriction_until"].endswith("Z"))
        self.assertTrue(payload["is_terminal"])

    def test_get_status_for_line_derives_restriction_seconds_from_hms_payload(self):
        from telecom.services.reconnect_service import ReconnectService

        repository = FakeReconnectRepository()
        repository.restricted_by_phone["5511999991000"] = {
            "_id": "sess-restricted-hms",
            "phone_number": "5511999991000",
            "status": "FAILED",
            "attempt": 1,
            "error_code": "whatsapp_account_restricted",
            "error_message": "Conta restrita temporariamente.",
            "account_state": "RESTRICTED",
            "restriction_remaining_hms": "72:00:00",
            "account_state_detected_at": timezone.now(),
            "device_name": "Rafael Gomes",
            "active_lock": False,
        }
        repository.latest_terminal_by_phone["5511999991000"] = repository.restricted_by_phone[
            "5511999991000"
        ]
        service = ReconnectService(
            repository=repository,
            target_server_by_origem={PhoneLine.Origem.SRVMEMU_01: "rafael"},
        )

        payload = service.get_status_for_line(self.line)

        self.assertEqual(payload["session_id"], "sess-restricted-hms")
        self.assertEqual(payload["restriction_seconds_remaining"], 259200)
        self.assertEqual(payload["restriction_remaining_hms"], "72:00:00")
        self.assertEqual(payload["account_state"], "RESTRICTED")
        self.assertTrue(payload["is_terminal"])

    def test_get_status_for_line_ignores_expired_restricted_terminal_session(self):
        from telecom.services.reconnect_service import ReconnectService

        repository = FakeReconnectRepository()
        repository.restricted_by_phone["5511999991000"] = {
            "_id": "sess-restricted-expired",
            "phone_number": "5511999991000",
            "status": "FAILED",
            "attempt": 1,
            "error_code": "whatsapp_account_restricted",
            "account_state": "RESTRICTED",
            "restriction_seconds_remaining": 120,
            "restriction_until": timezone.now() - timedelta(minutes=1),
            "device_name": "Rafael Gomes",
            "active_lock": False,
        }
        repository.latest_terminal_by_phone["5511999991000"] = repository.restricted_by_phone[
            "5511999991000"
        ]
        service = ReconnectService(
            repository=repository,
            target_server_by_origem={PhoneLine.Origem.SRVMEMU_01: "rafael"},
        )

        payload = service.get_status_for_line(self.line)

        self.assertIsNone(payload)

    def test_get_status_for_line_does_not_return_old_restricted_when_newer_terminal_exists(
        self,
    ):
        from telecom.services.reconnect_service import ReconnectService

        repository = FakeReconnectRepository()
        repository.restricted_by_phone["5511999991000"] = {
            "_id": "sess-restricted-old",
            "phone_number": "5511999991000",
            "status": "FAILED",
            "attempt": 1,
            "error_code": "whatsapp_account_restricted",
            "account_state": "RESTRICTED",
            "restriction_seconds_remaining": 1800,
            "restriction_until": timezone.now() + timedelta(minutes=30),
            "active_lock": False,
        }
        repository.latest_terminal_by_phone["5511999991000"] = {
            "_id": "sess-failed-new",
            "phone_number": "5511999991000",
            "status": "FAILED",
            "attempt": 2,
            "error_code": "pre_reconnect_whatsapp_sync_failed",
            "error_message": "Falha de pré-sincronização.",
            "active_lock": False,
        }
        service = ReconnectService(
            repository=repository,
            target_server_by_origem={PhoneLine.Origem.SRVMEMU_01: "rafael"},
        )

        payload = service.get_status_for_line(self.line)

        self.assertIsNone(payload)

    def test_serialize_session_exposes_progress_fields(self):
        from telecom.services.reconnect_service import ReconnectService

        repository = FakeReconnectRepository()
        service = ReconnectService(
            repository=repository,
            target_server_by_origem={PhoneLine.Origem.SRVMEMU_01: "rafael"},
        )

        payload = service._serialize_session(
            {
                "_id": "sess-qr-001",
                "phone_number": "5511999991000",
                "status": "OPEN_LINKED_DEVICES",
                "attempt": 1,
                "progress_stage": "open_linked_devices",
                "progress_stage_label": "Abrindo dispositivos conectados",
                "progress_stage_updated_at": timezone.now(),
                "progress_history": [
                    {
                        "stage": "claimed",
                        "label": "Sessao capturada pelo worker",
                        "at": timezone.now(),
                    },
                    {
                        "stage": "open_linked_devices",
                        "label": "Abrindo dispositivos conectados",
                        "at": timezone.now(),
                    },
                ],
            }
        )

        self.assertEqual(payload["status"], "OPEN_LINKED_DEVICES")
        self.assertEqual(payload["progress_stage"], "open_linked_devices")
        self.assertEqual(
            payload["progress_stage_label"],
            "Abrindo dispositivos conectados",
        )
        self.assertEqual(len(payload["progress_history"]), 2)
        self.assertFalse(payload["can_submit_code"])

    def test_cancel_for_line_immediately_finishes_queued_session(self):
        from telecom.services.reconnect_service import ReconnectService

        repository = FakeReconnectRepository()
        repository.by_id["sess-queue-001"] = {
            "_id": "sess-queue-001",
            "phone_number": "5511999991000",
            "status": "QUEUED",
            "attempt": 0,
            "active_lock": True,
        }
        repository.active_by_phone["5511999991000"] = repository.by_id["sess-queue-001"]
        service = ReconnectService(
            repository=repository,
            target_server_by_origem={PhoneLine.Origem.SRVMEMU_01: "rafael"},
        )

        result = service.cancel_for_line(
            self.line,
            session_id="sess-queue-001",
        )

        self.assertTrue(result["cancel_requested"])
        self.assertEqual(result["status"], "CANCELLED")
        self.assertTrue(result["is_terminal"])
        self.assertFalse(result["can_cancel"])

    def test_serialize_session_marks_cancel_requested_before_terminal_state(self):
        from telecom.services.reconnect_service import ReconnectService

        repository = FakeReconnectRepository()
        service = ReconnectService(
            repository=repository,
            target_server_by_origem={PhoneLine.Origem.SRVMEMU_01: "rafael"},
        )

        payload = service._serialize_session(
            {
                "_id": "sess-cancel-001",
                "phone_number": "5511999991000",
                "status": "WAITING_FOR_CODE",
                "attempt": 1,
                "cancel_requested_at": timezone.now(),
            }
        )

        self.assertEqual(payload["status"], "CANCEL_REQUESTED")
        self.assertFalse(payload["is_terminal"])
        self.assertFalse(payload["can_cancel"])
        self.assertFalse(payload["can_submit_code"])
        self.assertTrue(payload["cancel_requested"])

    @patch("telecom.services.reconnect_service.logger")
    def test_start_for_line_logs_queued_session_with_context(self, mocked_logger):
        from telecom.services.reconnect_service import ReconnectService

        repository = FakeReconnectRepository()
        service = ReconnectService(
            repository=repository,
            target_server_by_origem={PhoneLine.Origem.SRVMEMU_01: "rafael"},
        )

        session = service.start_for_line(self.line)

        mocked_logger.info.assert_any_call(
            "Reconnect session queued",
            extra=ANY,
        )
        _, kwargs = mocked_logger.info.call_args
        self.assertEqual(kwargs["extra"]["session_id"], session["session_id"])
        self.assertEqual(kwargs["extra"]["phone_line_id"], self.line.pk)
        self.assertEqual(kwargs["extra"]["phone_number"], "5511999991000")

    @patch("telecom.services.reconnect_service.logger")
    def test_submit_code_logs_result_with_context(self, mocked_logger):
        from telecom.services.reconnect_service import ReconnectService

        repository = FakeReconnectRepository()
        repository.by_id["sess-log-submit-1"] = {
            "_id": "sess-log-submit-1",
            "phone_number": "5511999991000",
            "status": "WAITING_FOR_CODE",
            "attempt": 1,
            "device_name": "Rafael Gomes",
        }
        service = ReconnectService(
            repository=repository,
            target_server_by_origem={PhoneLine.Origem.SRVMEMU_01: "rafael"},
        )

        service.submit_code_for_line(
            self.line,
            session_id="sess-log-submit-1",
            pair_code="ab12cd34",
        )

        mocked_logger.info.assert_any_call(
            "Reconnect pair code submitted",
            extra=ANY,
        )
        _, kwargs = mocked_logger.info.call_args
        self.assertEqual(kwargs["extra"]["session_id"], "sess-log-submit-1")
        self.assertEqual(kwargs["extra"]["phone_line_id"], self.line.pk)
        self.assertEqual(kwargs["extra"]["pair_code_length"], 8)
        self.assertTrue(kwargs["extra"]["code_accepted"])

    @patch("telecom.services.reconnect_service.logger")
    def test_cancel_for_line_logs_result_with_context(self, mocked_logger):
        from telecom.services.reconnect_service import ReconnectService

        repository = FakeReconnectRepository()
        repository.by_id["sess-log-cancel-1"] = {
            "_id": "sess-log-cancel-1",
            "phone_number": "5511999991000",
            "status": "QUEUED",
            "attempt": 0,
            "active_lock": True,
            "device_name": "Rafael Gomes",
        }
        repository.active_by_phone["5511999991000"] = repository.by_id["sess-log-cancel-1"]
        service = ReconnectService(
            repository=repository,
            target_server_by_origem={PhoneLine.Origem.SRVMEMU_01: "rafael"},
        )

        service.cancel_for_line(
            self.line,
            session_id="sess-log-cancel-1",
        )

        mocked_logger.info.assert_any_call(
            "Reconnect session cancel requested",
            extra=ANY,
        )
        _, kwargs = mocked_logger.info.call_args
        self.assertEqual(kwargs["extra"]["session_id"], "sess-log-cancel-1")
        self.assertEqual(kwargs["extra"]["phone_line_id"], self.line.pk)
        self.assertTrue(kwargs["extra"]["cancel_requested"])


class FakeReconnectWebService:
    def __init__(self):
        self.start_calls = []
        self.status_calls = []
        self.code_calls = []
        self.cancel_calls = []

    def start_for_line(self, line):
        self.start_calls.append(line.pk)
        return {
            "session_id": "sess-web-1",
            "status": "QUEUED",
            "attempt": 0,
            "can_submit_code": False,
            "can_cancel": True,
            "is_terminal": False,
        }

    def get_status_for_line(self, line, *, session_id=""):
        self.status_calls.append((line.pk, session_id))
        return {
            "session_id": "sess-web-1",
            "status": "WAITING_FOR_CODE",
            "attempt": 1,
            "can_submit_code": True,
            "can_cancel": True,
            "is_terminal": False,
        }

    def submit_code_for_line(self, line, *, session_id, pair_code):
        self.code_calls.append((line.pk, session_id, pair_code))
        return {
            "session_id": session_id,
            "status": "SUBMITTING_CODE",
            "attempt": 1,
            "code_accepted": True,
            "can_submit_code": False,
            "can_cancel": True,
            "is_terminal": False,
        }

    def cancel_for_line(self, line, *, session_id):
        self.cancel_calls.append((line.pk, session_id))
        return {
            "session_id": session_id,
            "status": "CANCELLED",
            "attempt": 1,
            "can_submit_code": False,
            "can_cancel": False,
            "is_terminal": True,
        }


@override_settings(RECONNECT_ENABLED=True)
class PhoneLineReconnectViewsTests(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="admin.reconnect.view@test.com",
            password="123456",
            role=SystemUser.Role.ADMIN,
        )
        self.supervisor = SystemUser.objects.create_user(
            email="super.reconnect.view@test.com",
            password="123456",
            role=SystemUser.Role.SUPER,
        )
        self.backoffice = SystemUser.objects.create_user(
            email="backoffice.reconnect.view@test.com",
            password="123456",
            role=SystemUser.Role.BACKOFFICE,
            supervisor_email="super.reconnect.view@test.com",
        )
        self.other_supervisor = SystemUser.objects.create_user(
            email="other.super.reconnect.view@test.com",
            password="123456",
            role=SystemUser.Role.SUPER,
        )
        self.managed_employee = Employee.objects.create(
            full_name="Usuario Gerenciado",
            corporate_email=self.supervisor.email,
            employee_id="EMP-RECON-V1",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        self.unmanaged_employee = Employee.objects.create(
            full_name="Usuario Nao Gerenciado",
            corporate_email=self.other_supervisor.email,
            employee_id="EMP-RECON-V2",
            teams="Araquari",
            status=Employee.Status.ACTIVE,
        )
        self.managed_sim = SIMcard.objects.create(
            iccid="8900000000000088001",
            carrier="CarrierView",
            status=SIMcard.Status.AVAILABLE,
        )
        self.unmanaged_sim = SIMcard.objects.create(
            iccid="8900000000000088002",
            carrier="CarrierView",
            status=SIMcard.Status.AVAILABLE,
        )
        self.managed_line = PhoneLine.objects.create(
            phone_number="+5511999992001",
            sim_card=self.managed_sim,
            status=PhoneLine.Status.AVAILABLE,
            origem=PhoneLine.Origem.SRVMEMU_01,
        )
        self.unmanaged_line = PhoneLine.objects.create(
            phone_number="+5511999992002",
            sim_card=self.unmanaged_sim,
            status=PhoneLine.Status.AVAILABLE,
            origem=PhoneLine.Origem.SRVMEMU_01,
        )
        self.non_eligible_sim = SIMcard.objects.create(
            iccid="8900000000000088003",
            carrier="CarrierView",
            status=SIMcard.Status.AVAILABLE,
        )
        self.non_eligible_line = PhoneLine.objects.create(
            phone_number="+5511999992003",
            sim_card=self.non_eligible_sim,
            status=PhoneLine.Status.AVAILABLE,
            origem=PhoneLine.Origem.SRVMEMU_02,
        )
        AllocationService.allocate_line(
            employee=self.managed_employee,
            phone_line=self.managed_line,
            allocated_by=self.admin,
        )
        AllocationService.allocate_line(
            employee=self.unmanaged_employee,
            phone_line=self.unmanaged_line,
            allocated_by=self.admin,
        )
        AllocationService.allocate_line(
            employee=self.managed_employee,
            phone_line=self.non_eligible_line,
            allocated_by=self.admin,
        )

    @patch("telecom.views.get_reconnect_service")
    def test_detail_view_shows_reconnect_section_when_feature_enabled(
        self, mocked_service
    ):
        mocked_service.return_value = FakeReconnectWebService()
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("telecom:phoneline_detail", args=[self.managed_line.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reconexao WhatsApp")
        self.assertContains(response, 'data-reconnect-root')
        self.assertContains(response, "Nenhuma reconexao em andamento.")
        self.assertContains(response, "Detalhes tecnicos da sessao")
        self.assertContains(response, "Estado da conta")
        self.assertContains(response, "Acao de TI")
        self.assertContains(response, "Motivo TI")
        self.assertContains(response, "Etapa atual")
        self.assertContains(response, "Tempo restante")
        self.assertContains(response, "data-reconnect-restriction-countdown")
        self.assertContains(response, "window.setInterval(updateRestrictionCountdown, 1000);")
        self.assertContains(response, 'data-reconnect-code-form data-no-loading="true"')
        self.assertContains(response, 'class="modal-content reconnect-history-modal-content"')
        self.assertContains(
            response,
            "if (payload && payload.session_id && !payload.is_terminal) {",
        )

    @patch("telecom.views.get_reconnect_service")
    def test_detail_view_hides_reconnect_section_for_non_srvmemu_01(
        self, mocked_service
    ):
        mocked_service.return_value = FakeReconnectWebService()
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("telecom:phoneline_detail", args=[self.non_eligible_line.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Reconexao WhatsApp")
        self.assertNotContains(response, 'data-reconnect-root')

    @patch("telecom.views.get_reconnect_service")
    def test_start_endpoint_returns_session_payload(self, mocked_service):
        service = FakeReconnectWebService()
        mocked_service.return_value = service
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("telecom:phoneline_reconnect_start", args=[self.managed_line.pk])
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "QUEUED")
        self.assertEqual(payload["session_id"], "sess-web-1")
        self.assertEqual(service.start_calls, [self.managed_line.pk])

    @patch("telecom.views.get_reconnect_service")
    def test_start_endpoint_returns_404_for_non_srvmemu_01_line(self, mocked_service):
        service = FakeReconnectWebService()
        mocked_service.return_value = service
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("telecom:phoneline_reconnect_start", args=[self.non_eligible_line.pk])
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(service.start_calls, [])

    @patch("telecom.views.get_reconnect_service")
    def test_status_endpoint_returns_active_session_payload(self, mocked_service):
        service = FakeReconnectWebService()
        mocked_service.return_value = service
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("telecom:phoneline_reconnect_status", args=[self.managed_line.pk])
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "WAITING_FOR_CODE")
        self.assertTrue(payload["can_submit_code"])
        self.assertEqual(service.status_calls, [(self.managed_line.pk, "")])

    @patch("telecom.views.get_reconnect_service")
    def test_status_endpoint_reuses_session_id_to_fetch_terminal_payload(
        self, mocked_service
    ):
        class FakeTerminalReconnectWebService(FakeReconnectWebService):
            def get_status_for_line(self, line, *, session_id=""):
                self.status_calls.append((line.pk, session_id))
                return {
                    "session_id": session_id,
                    "status": "CONNECTED",
                    "attempt": 1,
                    "can_submit_code": False,
                    "can_cancel": False,
                    "is_terminal": True,
                }

        service = FakeTerminalReconnectWebService()
        mocked_service.return_value = service
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("telecom:phoneline_reconnect_status", args=[self.managed_line.pk]),
            data={"session_id": "sess-web-terminal-1"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["session_id"], "sess-web-terminal-1")
        self.assertEqual(payload["status"], "CONNECTED")
        self.assertTrue(payload["is_terminal"])
        self.assertEqual(
            service.status_calls,
            [(self.managed_line.pk, "sess-web-terminal-1")],
        )

    @patch("telecom.views.get_reconnect_service")
    def test_status_endpoint_returns_progress_payload(
        self, mocked_service
    ):
        class FakeProgressReconnectWebService(FakeReconnectWebService):
            def get_status_for_line(self, line, *, session_id=""):
                self.status_calls.append((line.pk, session_id))
                return {
                    "session_id": "sess-web-progress-1",
                    "status": "OPEN_MENU",
                    "attempt": 1,
                    "progress_stage": "open_menu",
                    "progress_stage_label": "Abrindo menu do WhatsApp",
                    "progress_stage_updated_at": timezone.now().isoformat(),
                    "progress_history": [
                        {
                            "stage": "claimed",
                            "label": "Sessao capturada pelo worker",
                            "at": timezone.now().isoformat(),
                        },
                        {
                            "stage": "open_menu",
                            "label": "Abrindo menu do WhatsApp",
                            "at": timezone.now().isoformat(),
                        },
                    ],
                    "can_submit_code": False,
                    "can_cancel": True,
                    "is_terminal": False,
                }

        service = FakeProgressReconnectWebService()
        mocked_service.return_value = service
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("telecom:phoneline_reconnect_status", args=[self.managed_line.pk])
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "OPEN_MENU")
        self.assertEqual(payload["progress_stage"], "open_menu")
        self.assertEqual(payload["progress_stage_label"], "Abrindo menu do WhatsApp")

    @patch("telecom.views.get_reconnect_service")
    def test_submit_code_endpoint_passes_code_to_service(self, mocked_service):
        service = FakeReconnectWebService()
        mocked_service.return_value = service
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("telecom:phoneline_reconnect_submit_code", args=[self.managed_line.pk]),
            data={"session_id": "sess-web-1", "pair_code": "ab12cd34"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "SUBMITTING_CODE")
        self.assertTrue(payload["code_accepted"])
        self.assertEqual(
            service.code_calls,
            [(self.managed_line.pk, "sess-web-1", "ab12cd34")],
        )

    @patch("telecom.views.get_reconnect_service")
    def test_cancel_endpoint_passes_session_to_service(self, mocked_service):
        service = FakeReconnectWebService()
        mocked_service.return_value = service
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("telecom:phoneline_reconnect_cancel", args=[self.managed_line.pk]),
            data={"session_id": "sess-web-1"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "CANCELLED")
        self.assertEqual(
            service.cancel_calls,
            [(self.managed_line.pk, "sess-web-1")],
        )

    def test_start_endpoint_logs_warning_when_business_rule_exception(self):
        class FailingStartReconnectService(FakeReconnectWebService):
            def start_for_line(self, line):
                raise BusinessRuleException("nao pode iniciar")

        self.client.force_login(self.admin)
        with (
            patch("telecom.views.get_reconnect_service") as mocked_service,
            patch("telecom.views.logger") as mocked_logger,
        ):
            mocked_service.return_value = FailingStartReconnectService()
            response = self.client.post(
                reverse("telecom:phoneline_reconnect_start", args=[self.managed_line.pk])
            )

        self.assertEqual(response.status_code, 400)
        mocked_logger.warning.assert_called_once_with(
            "Reconnect start rejected by business rule",
            extra={
                "phone_line_id": self.managed_line.pk,
                "user_id": self.admin.pk,
            },
        )

    def test_status_endpoint_logs_warning_when_business_rule_exception(self):
        class FailingStatusReconnectService(FakeReconnectWebService):
            def get_status_for_line(self, line, *, session_id=""):
                raise BusinessRuleException("status indisponivel")

        self.client.force_login(self.admin)
        with (
            patch("telecom.views.get_reconnect_service") as mocked_service,
            patch("telecom.views.logger") as mocked_logger,
        ):
            mocked_service.return_value = FailingStatusReconnectService()
            response = self.client.get(
                reverse("telecom:phoneline_reconnect_status", args=[self.managed_line.pk]),
                data={"session_id": "sess-1"},
            )

        self.assertEqual(response.status_code, 400)
        mocked_logger.warning.assert_called_once_with(
            "Reconnect status rejected by business rule",
            extra={
                "phone_line_id": self.managed_line.pk,
                "user_id": self.admin.pk,
                "session_id": "sess-1",
            },
        )

    def test_submit_code_endpoint_logs_warning_when_business_rule_exception(self):
        class FailingSubmitReconnectService(FakeReconnectWebService):
            def submit_code_for_line(self, line, *, session_id, pair_code):
                raise BusinessRuleException("codigo invalido")

        self.client.force_login(self.admin)
        with (
            patch("telecom.views.get_reconnect_service") as mocked_service,
            patch("telecom.views.logger") as mocked_logger,
        ):
            mocked_service.return_value = FailingSubmitReconnectService()
            response = self.client.post(
                reverse("telecom:phoneline_reconnect_submit_code", args=[self.managed_line.pk]),
                data={"session_id": "sess-2", "pair_code": "ab12cd34"},
            )

        self.assertEqual(response.status_code, 400)
        mocked_logger.warning.assert_called_once_with(
            "Reconnect pair code submission rejected by business rule",
            extra={
                "phone_line_id": self.managed_line.pk,
                "user_id": self.admin.pk,
                "session_id": "sess-2",
                "pair_code_length": 8,
            },
        )

    def test_cancel_endpoint_logs_warning_when_business_rule_exception(self):
        class FailingCancelReconnectService(FakeReconnectWebService):
            def cancel_for_line(self, line, *, session_id):
                raise BusinessRuleException("nao pode cancelar")

        self.client.force_login(self.admin)
        with (
            patch("telecom.views.get_reconnect_service") as mocked_service,
            patch("telecom.views.logger") as mocked_logger,
        ):
            mocked_service.return_value = FailingCancelReconnectService()
            response = self.client.post(
                reverse("telecom:phoneline_reconnect_cancel", args=[self.managed_line.pk]),
                data={"session_id": "sess-3"},
            )

        self.assertEqual(response.status_code, 400)
        mocked_logger.warning.assert_called_once_with(
            "Reconnect cancel rejected by business rule",
            extra={
                "phone_line_id": self.managed_line.pk,
                "user_id": self.admin.pk,
                "session_id": "sess-3",
            },
        )

    @patch("telecom.views.get_reconnect_service")
    def test_backoffice_cannot_operate_on_unmanaged_line(self, mocked_service):
        mocked_service.return_value = FakeReconnectWebService()
        self.client.force_login(self.backoffice)

        response = self.client.post(
            reverse("telecom:phoneline_reconnect_start", args=[self.unmanaged_line.pk])
        )

        self.assertEqual(response.status_code, 404)


# ---------------------------------------------------------------------------
# WhatsappReconnectHistory — model + service
# ---------------------------------------------------------------------------

class WhatsappReconnectHistoryModelTest(TestCase):
    def setUp(self):
        self.sim = SIMcard.objects.create(
            iccid="8900000000000099001",
            carrier="CarrierHist",
            status=SIMcard.Status.AVAILABLE,
        )
        self.line = PhoneLine.objects.create(
            phone_number="+5511999993001",
            sim_card=self.sim,
            status=PhoneLine.Status.AVAILABLE,
            origem=PhoneLine.Origem.SRVMEMU_01,
        )
        self.admin = SystemUser.objects.create_user(
            email="admin.hist@test.com",
            password="123456",
            role=SystemUser.Role.ADMIN,
        )

    def test_open_creates_entry_in_progress(self):
        from telecom.services.reconnect_history_service import WhatsappReconnectHistoryService
        entry = WhatsappReconnectHistoryService.open(
            phone_line=self.line,
            session_id="sess-hist-1",
            started_by=self.admin,
        )
        self.assertEqual(entry.phone_line, self.line)
        self.assertEqual(entry.session_id, "sess-hist-1")
        self.assertIsNone(entry.outcome)
        self.assertIsNone(entry.finished_at)
        self.assertEqual(entry.started_by, self.admin)

    def test_open_is_idempotent(self):
        from telecom.services.reconnect_history_service import WhatsappReconnectHistoryService
        WhatsappReconnectHistoryService.open(
            phone_line=self.line, session_id="sess-hist-2", started_by=self.admin
        )
        WhatsappReconnectHistoryService.open(
            phone_line=self.line, session_id="sess-hist-2", started_by=self.admin
        )
        self.assertEqual(
            WhatsappReconnectHistory.objects.filter(session_id="sess-hist-2").count(), 1
        )

    def test_close_sets_outcome_and_finished_at(self):
        from telecom.services.reconnect_history_service import WhatsappReconnectHistoryService
        WhatsappReconnectHistoryService.open(
            phone_line=self.line, session_id="sess-hist-3", started_by=self.admin
        )
        WhatsappReconnectHistoryService.close(
            session_id="sess-hist-3",
            outcome=WhatsappReconnectHistory.Outcome.CONNECTED,
            attempt_count=2,
        )
        entry = WhatsappReconnectHistory.objects.get(session_id="sess-hist-3")
        self.assertEqual(entry.outcome, WhatsappReconnectHistory.Outcome.CONNECTED)
        self.assertIsNotNone(entry.finished_at)
        self.assertEqual(entry.attempt_count, 2)

    def test_close_sets_error_fields_on_failure(self):
        from telecom.services.reconnect_history_service import WhatsappReconnectHistoryService
        WhatsappReconnectHistoryService.open(
            phone_line=self.line, session_id="sess-hist-4", started_by=self.admin
        )
        WhatsappReconnectHistoryService.close(
            session_id="sess-hist-4",
            outcome=WhatsappReconnectHistory.Outcome.FAILED,
            error_code="TIMEOUT",
            error_message="Tempo limite excedido",
            attempt_count=3,
        )
        entry = WhatsappReconnectHistory.objects.get(session_id="sess-hist-4")
        self.assertEqual(entry.outcome, WhatsappReconnectHistory.Outcome.FAILED)
        self.assertEqual(entry.error_code, "TIMEOUT")
        self.assertEqual(entry.error_message, "Tempo limite excedido")

    def test_close_is_noop_when_already_closed(self):
        from telecom.services.reconnect_history_service import WhatsappReconnectHistoryService
        WhatsappReconnectHistoryService.open(
            phone_line=self.line, session_id="sess-hist-5", started_by=self.admin
        )
        WhatsappReconnectHistoryService.close(
            session_id="sess-hist-5",
            outcome=WhatsappReconnectHistory.Outcome.CONNECTED,
        )
        # Segunda chamada não deve sobrescrever
        WhatsappReconnectHistoryService.close(
            session_id="sess-hist-5",
            outcome=WhatsappReconnectHistory.Outcome.FAILED,
            error_code="LATE_ERROR",
        )
        entry = WhatsappReconnectHistory.objects.get(session_id="sess-hist-5")
        self.assertEqual(entry.outcome, WhatsappReconnectHistory.Outcome.CONNECTED)
        self.assertEqual(entry.error_code, "")

    def test_str_representation(self):
        entry = WhatsappReconnectHistory.objects.create(
            phone_line=self.line,
            session_id="sess-hist-str",
            outcome=WhatsappReconnectHistory.Outcome.CONNECTED,
            started_by=self.admin,
        )
        self.assertIn(self.line.phone_number, str(entry))
        self.assertIn("Conectado", str(entry))


@override_settings(RECONNECT_ENABLED=True)
class WhatsappReconnectHistoryViewsTest(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="admin.histview@test.com",
            password="123456",
            role=SystemUser.Role.ADMIN,
        )
        self.sim = SIMcard.objects.create(
            iccid="8900000000000099002",
            carrier="CarrierHistV",
            status=SIMcard.Status.AVAILABLE,
        )
        self.line = PhoneLine.objects.create(
            phone_number="+5511999993002",
            sim_card=self.sim,
            status=PhoneLine.Status.AVAILABLE,
            origem=PhoneLine.Origem.SRVMEMU_01,
        )

    @patch("telecom.views.get_reconnect_service")
    def test_start_creates_history_entry(self, mocked_service):
        mocked_service.return_value = FakeReconnectWebService()
        self.client.force_login(self.admin)

        self.client.post(
            reverse("telecom:phoneline_reconnect_start", args=[self.line.pk])
        )

        self.assertEqual(
            WhatsappReconnectHistory.objects.filter(
                phone_line=self.line, session_id="sess-web-1"
            ).count(),
            1,
        )

    @patch("telecom.views.get_reconnect_service")
    def test_status_closes_history_on_terminal(self, mocked_service):
        class FakeTerminalService(FakeReconnectWebService):
            def get_status_for_line(self, line, *, session_id=""):
                return {
                    "session_id": "sess-web-terminal",
                    "status": "CONNECTED",
                    "attempt": 2,
                    "is_terminal": True,
                    "error_code": None,
                    "error_message": None,
                    "can_submit_code": False,
                    "can_cancel": False,
                }

        WhatsappReconnectHistory.objects.create(
            phone_line=self.line,
            session_id="sess-web-terminal",
            started_by=self.admin,
        )
        mocked_service.return_value = FakeTerminalService()
        self.client.force_login(self.admin)

        self.client.get(
            reverse("telecom:phoneline_reconnect_status", args=[self.line.pk]),
            {"session_id": "sess-web-terminal"},
        )

        entry = WhatsappReconnectHistory.objects.get(session_id="sess-web-terminal")
        self.assertEqual(entry.outcome, WhatsappReconnectHistory.Outcome.CONNECTED)
        self.assertIsNotNone(entry.finished_at)

    @patch("telecom.views.get_reconnect_service")
    def test_status_closes_history_when_service_returns_success_alias(self, mocked_service):
        class FakeSuccessAliasService(FakeReconnectWebService):
            def get_status_for_line(self, line, *, session_id=""):
                return {
                    "session_id": "sess-web-terminal-success",
                    "status": "CONNECTED",
                    "raw_status": "SUCCESS",
                    "attempt": 1,
                    "is_terminal": True,
                    "error_code": None,
                    "error_message": None,
                    "can_submit_code": False,
                    "can_cancel": False,
                }

        WhatsappReconnectHistory.objects.create(
            phone_line=self.line,
            session_id="sess-web-terminal-success",
            started_by=self.admin,
        )
        mocked_service.return_value = FakeSuccessAliasService()
        self.client.force_login(self.admin)

        self.client.get(
            reverse("telecom:phoneline_reconnect_status", args=[self.line.pk]),
            {"session_id": "sess-web-terminal-success"},
        )

        entry = WhatsappReconnectHistory.objects.get(
            session_id="sess-web-terminal-success"
        )
        self.assertEqual(entry.outcome, WhatsappReconnectHistory.Outcome.CONNECTED)
        self.assertIsNotNone(entry.finished_at)

    def test_history_endpoint_returns_entries(self):
        WhatsappReconnectHistory.objects.create(
            phone_line=self.line,
            session_id="sess-hist-view-1",
            outcome=WhatsappReconnectHistory.Outcome.CONNECTED,
            attempt_count=1,
            started_by=self.admin,
        )
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("telecom:phoneline_reconnect_history", args=[self.line.pk])
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["entries"]), 1)
        self.assertEqual(data["entries"][0]["session_id"], "sess-hist-view-1")
        self.assertEqual(data["entries"][0]["outcome"], "CONNECTED")

    def test_history_endpoint_returns_empty_when_no_entries(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("telecom:phoneline_reconnect_history", args=[self.line.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["entries"], [])

    @override_settings(RECONNECT_ENABLED=False)
    def test_history_endpoint_returns_404_when_disabled(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("telecom:phoneline_reconnect_history", args=[self.line.pk])
        )

        self.assertEqual(response.status_code, 404)
