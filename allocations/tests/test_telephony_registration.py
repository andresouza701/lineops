from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from allocations.forms import TelephonyAssignmentForm
from allocations.models import LineAllocation
from dashboard.models import DailyUserAction
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser
from whatsapp.models import MeowInstance, WhatsAppSession
from whatsapp.services.instance_selector import NoAvailableMeowInstanceError


class TelephonyRegistrationFlowTests(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="admin.telephony@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.supervisor = SystemUser.objects.create_user(
            email="supervisor@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.manager = SystemUser.objects.create_user(
            email="gerente@test.com",
            password="StrongPass123",
            role=SystemUser.Role.GERENTE,
        )
        self.client.force_login(self.admin)

        self.employee = Employee.objects.create(
            full_name="Telephony User",
            corporate_email="supervisor@test.com",
            employee_id="EMP-TEL-1",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )

        self.sim = SIMcard.objects.create(
            iccid="8900000000000000707",
            carrier="CarrierG",
            status=SIMcard.Status.AVAILABLE,
        )
        self.line = PhoneLine.objects.create(
            phone_number="+5511999990707",
            sim_card=self.sim,
            status=PhoneLine.Status.AVAILABLE,
        )

    def test_existing_line_links_employee_and_updates_line_status(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("allocations:allocation_list"),
                {
                    "action": "telephony",
                    "line_action": "existing",
                    "employee": self.employee.pk,
                    "phone_line": self.line.pk,
                },
                follow=False,
            )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            LineAllocation.objects.filter(
                employee=self.employee,
                phone_line=self.line,
                is_active=True,
            ).exists()
        )
        self.line.refresh_from_db()
        self.assertEqual(self.line.status, PhoneLine.Status.ALLOCATED)

    def test_existing_line_allocation_creates_pending_daily_action_without_meow(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("allocations:allocation_list"),
                {
                    "action": "telephony",
                    "line_action": "existing",
                    "employee": self.employee.pk,
                    "phone_line": self.line.pk,
                },
                follow=False,
            )

        self.assertEqual(response.status_code, 302)
        allocation = LineAllocation.objects.get(
            employee=self.employee,
            phone_line=self.line,
            is_active=True,
        )
        action = DailyUserAction.objects.get(
            employee=self.employee,
            allocation=allocation,
            is_resolved=False,
        )
        self.assertEqual(action.action_type, DailyUserAction.ActionType.NEW_NUMBER)
        self.assertEqual(action.created_by, self.admin)
        self.assertEqual(WhatsAppSession.objects.filter(line=self.line).count(), 0)

    @patch(
        "core.services.allocation_service.InstanceSelectorService.select_available_instance",
        side_effect=NoAvailableMeowInstanceError("sem capacidade"),
    )
    def test_existing_line_allocation_is_blocked_when_meow_is_configured_without_capacity(
        self,
        _select_available_instance,
    ):
        MeowInstance.objects.create(
            name="QA Meow Saturado",
            base_url="http://qa-meow-saturado.local",
        )

        response = self.client.post(
            reverse("allocations:allocation_list"),
            {
                "action": "telephony",
                "line_action": "existing",
                "employee": self.employee.pk,
                "phone_line": self.line.pk,
            },
            follow=False,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "capacidade disponivel")
        self.assertFalse(
            LineAllocation.objects.filter(
                employee=self.employee,
                phone_line=self.line,
                is_active=True,
            ).exists()
        )
        self.line.refresh_from_db()
        self.assertEqual(self.line.status, PhoneLine.Status.AVAILABLE)

    def test_telephony_registration_form_includes_blip_origin_choice(self):
        form = TelephonyAssignmentForm()

        self.assertIn(
            (PhoneLine.Origem.BLIP, "Blip"),
            list(form.fields["origem"].choices),
        )

    def test_new_line_creation_flow_creates_sim_and_line_without_allocation(self):
        response = self.client.post(
            reverse("allocations:allocation_list"),
            {
                "action": "telephony",
                "line_action": "new",
                "phone_number": "+5511999990999",
                "iccid": "8900000000000000999",
                "carrier": "CarrierNew",
                "origem": PhoneLine.Origem.APARELHO,
            },
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        line = PhoneLine.objects.get(phone_number="+5511999990999")
        self.assertEqual(line.status, PhoneLine.Status.AVAILABLE)
        self.assertEqual(line.sim_card.iccid, "8900000000000000999")
        self.assertFalse(LineAllocation.objects.filter(phone_line=line).exists())

    def test_new_line_creation_with_allocation_creates_pending_new_number_action(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("allocations:allocation_list"),
                {
                    "action": "telephony",
                    "line_action": "new",
                    "employee": self.employee.pk,
                    "phone_number": "+5511999990777",
                    "iccid": "8900000000000000777",
                    "carrier": "CarrierNew",
                    "origem": PhoneLine.Origem.APARELHO,
                },
                follow=False,
            )

        self.assertEqual(response.status_code, 302)
        line = PhoneLine.objects.get(phone_number="+5511999990777")
        allocation = LineAllocation.objects.get(phone_line=line, is_active=True)
        action = DailyUserAction.objects.get(
            employee=self.employee,
            allocation=allocation,
            is_resolved=False,
        )
        self.assertEqual(action.action_type, DailyUserAction.ActionType.NEW_NUMBER)
        self.assertEqual(line.status, PhoneLine.Status.ALLOCATED)

    def test_release_view_resolves_pending_daily_action(self):
        with self.captureOnCommitCallbacks(execute=True):
            allocation = LineAllocation.objects.create(
                employee=self.employee,
                phone_line=self.line,
                allocated_by=self.admin,
                is_active=True,
            )
            self.line.status = PhoneLine.Status.ALLOCATED
            self.line.save(update_fields=["status"])
            DailyUserAction.objects.create(
                day=allocation.allocated_at.date(),
                employee=self.employee,
                allocation=allocation,
                action_type=DailyUserAction.ActionType.NEW_NUMBER,
                supervisor=self.supervisor,
                created_by=self.admin,
                updated_by=self.admin,
                is_resolved=False,
            )

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("allocations:allocation_release", args=[allocation.pk]),
                follow=False,
            )

        self.assertEqual(response.status_code, 302)
        allocation.refresh_from_db()
        self.assertFalse(allocation.is_active)
        action = DailyUserAction.objects.get(allocation=allocation)
        self.assertTrue(action.is_resolved)
        self.assertEqual(action.updated_by, self.admin)

    def test_reallocating_released_line_creates_reconnect_action(self):
        second_employee = Employee.objects.create(
            full_name="Telephony User 2",
            corporate_email="supervisor@test.com",
            employee_id="EMP-TEL-2",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )

        with self.captureOnCommitCallbacks(execute=True):
            first_allocation = LineAllocation.objects.create(
                employee=self.employee,
                phone_line=self.line,
                allocated_by=self.admin,
                is_active=True,
            )
            self.line.status = PhoneLine.Status.ALLOCATED
            self.line.save(update_fields=["status"])
            DailyUserAction.objects.create(
                day=first_allocation.allocated_at.date(),
                employee=self.employee,
                allocation=first_allocation,
                action_type=DailyUserAction.ActionType.NEW_NUMBER,
                supervisor=self.supervisor,
                created_by=self.admin,
                updated_by=self.admin,
                is_resolved=False,
            )

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                reverse("allocations:allocation_release", args=[first_allocation.pk]),
                follow=False,
            )

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("allocations:allocation_list"),
                {
                    "action": "telephony",
                    "line_action": "existing",
                    "employee": second_employee.pk,
                    "phone_line": self.line.pk,
                },
                follow=False,
            )

        self.assertEqual(response.status_code, 302)
        second_allocation = LineAllocation.objects.get(
            employee=second_employee,
            phone_line=self.line,
            is_active=True,
        )
        reconnect_action = DailyUserAction.objects.get(
            employee=second_employee,
            allocation=second_allocation,
            is_resolved=False,
        )
        self.assertEqual(
            reconnect_action.action_type,
            DailyUserAction.ActionType.RECONNECT_WHATSAPP,
        )

    def test_new_line_creation_reuses_soft_deleted_phone_number(self):
        recycled_sim = SIMcard.objects.create(
            iccid="8900000000000000888",
            carrier="CarrierOld",
            status=SIMcard.Status.AVAILABLE,
        )
        deleted_line = PhoneLine.objects.create(
            phone_number="+5511999990888",
            sim_card=recycled_sim,
            status=PhoneLine.Status.AVAILABLE,
            origem=PhoneLine.Origem.APARELHO,
        )
        deleted_line.delete()

        response = self.client.post(
            reverse("allocations:allocation_list"),
            {
                "action": "telephony",
                "line_action": "new",
                "phone_number": deleted_line.phone_number,
                "iccid": "ICCID-REUSE-01",
                "carrier": "CarrierRecovered",
                "origem": PhoneLine.Origem.SRVMEMU_01,
            },
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        reused_line = PhoneLine.all_objects.get(pk=deleted_line.pk)
        self.assertFalse(reused_line.is_deleted)
        self.assertEqual(reused_line.sim_card.iccid, "ICCID-REUSE-01")
        self.assertEqual(reused_line.origem, PhoneLine.Origem.SRVMEMU_01)
        self.assertEqual(
            PhoneLine.all_objects.filter(phone_number=deleted_line.phone_number).count(),
            1,
        )

    def test_allocation_template_has_default_line_action_new(self):
        response = self.client.get(reverse("allocations:allocation_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, '<input type="hidden" name="line_action" value="new">', html=True
        )

    def test_change_status_updates_line_when_no_active_allocation(self):
        response = self.client.post(
            reverse("allocations:allocation_list"),
            {
                "action": "telephony",
                "line_action": "change_status",
                "phone_line_status": self.line.pk,
                "status_line": PhoneLine.Status.SUSPENDED,
            },
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        self.line.refresh_from_db()
        self.assertEqual(self.line.status, PhoneLine.Status.SUSPENDED)

    def test_change_status_does_not_break_active_allocation_consistency(self):
        LineAllocation.objects.create(
            employee=self.employee,
            phone_line=self.line,
            allocated_by=self.admin,
            is_active=True,
        )
        self.line.status = PhoneLine.Status.ALLOCATED
        self.line.save(update_fields=["status"])

        response = self.client.post(
            reverse("allocations:allocation_list"),
            {
                "action": "telephony",
                "line_action": "change_status",
                "phone_line_status": self.line.pk,
                "status_line": PhoneLine.Status.AVAILABLE,
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.line.refresh_from_db()
        self.assertEqual(self.line.status, PhoneLine.Status.ALLOCATED)

    def test_new_line_rejects_invalid_phone_number_format(self):
        response = self.client.post(
            reverse("allocations:allocation_list"),
            {
                "action": "telephony",
                "line_action": "new",
                "phone_number": "invalid-phone",
                "iccid": "ICCID-TEXTO-01",
                "carrier": "CarrierNew",
                "origem": PhoneLine.Origem.APARELHO,
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Corrija os erros de telefonia.")
        self.assertFalse(
            PhoneLine.objects.filter(phone_number="invalid-phone").exists()
        )

    def test_new_line_accepts_textual_iccid(self):
        response = self.client.post(
            reverse("allocations:allocation_list"),
            {
                "action": "telephony",
                "line_action": "new",
                "phone_number": "+5511999990888",
                "iccid": "ICCID-TEXTO-01",
                "carrier": "CarrierText",
                "origem": PhoneLine.Origem.APARELHO,
            },
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        line = PhoneLine.objects.get(phone_number="+5511999990888")
        self.assertEqual(line.sim_card.iccid, "ICCID-TEXTO-01")

    def test_new_line_with_virtual_iccid_payload_succeeds(self):
        response = self.client.post(
            reverse("allocations:allocation_list"),
            {
                "action": "telephony",
                "line_action": "new",
                "phone_number": "111111111111",
                "iccid": "VIRTUAL",
                "carrier": "CCCC",
                "origem": PhoneLine.Origem.SRVMEMU_01,
            },
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        line = PhoneLine.objects.get(phone_number="111111111111")
        self.assertEqual(line.sim_card.iccid, "VIRTUAL")
        self.assertEqual(line.origem, PhoneLine.Origem.SRVMEMU_01)

    def test_new_line_handles_duplicate_phone_integrity_error_without_500(self):
        with patch(
            "allocations.views.TelephonyUseCase.create_new_line_with_allocation",
            side_effect=IntegrityError(
                "duplicate key value violates unique constraint "
                "telecom_phoneline_phone_number_key"
            ),
        ):
            response = self.client.post(
                reverse("allocations:allocation_list"),
                {
                    "action": "telephony",
                    "line_action": "new",
                    "phone_number": "111111111111",
                    "iccid": "VIRTUAL",
                    "carrier": "CCCC",
                    "origem": PhoneLine.Origem.SRVMEMU_01,
                },
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Corrija os erros de telefonia.")
        self.assertIn("phone_number", response.context["telephony_form"].errors)

    def test_employee_registration_rejects_duplicate_full_name(self):
        response = self.client.post(
            reverse("allocations:allocation_list"),
            {
                "action": "employee",
                "full_name": " telephony user ",
                "corporate_email": "supervisor@test.com",
                "manager_email": "gerente@test.com",
                "employee_id": "Ambiental",
                "teams": Employee.UnitChoices.JOINVILLE,
                "status": Employee.Status.ACTIVE,
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Corrija os erros do usuário.")
        self.assertContains(response, "Ja existe um usuario cadastrado com este nome.")
        self.assertEqual(
            Employee.objects.filter(full_name__iexact="telephony user").count(),
            1,
        )

    def test_employee_registration_handles_duplicate_integrity_error_constraint(self):
        with patch(
            "allocations.views.Employee.objects.create",
            side_effect=IntegrityError(
                "duplicate key value violates unique constraint "
                "employees_employee_unique_active_full_name_ci"
            ),
        ):
            response = self.client.post(
                reverse("allocations:allocation_list"),
                {
                    "action": "employee",
                    "full_name": "Novo Usuario",
                    "corporate_email": "supervisor@test.com",
                    "manager_email": "gerente@test.com",
                    "employee_id": "Ambiental",
                    "teams": Employee.UnitChoices.JOINVILLE,
                    "status": Employee.Status.ACTIVE,
                },
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Corrija os erros do usuário.")
        self.assertContains(response, "Ja existe um usuario cadastrado com este nome.")

    def test_employee_registration_re_raises_non_duplicate_integrity_error(self):
        with (
            patch(
                "allocations.views.Employee.objects.create",
                side_effect=IntegrityError("some other integrity error"),
            ),
            self.assertRaises(IntegrityError),
        ):
            self.client.post(
                reverse("allocations:allocation_list"),
                {
                    "action": "employee",
                    "full_name": "Novo Usuario",
                    "corporate_email": "supervisor@test.com",
                    "manager_email": "gerente@test.com",
                    "employee_id": "Ambiental",
                    "teams": Employee.UnitChoices.JOINVILLE,
                    "status": Employee.Status.ACTIVE,
                },
                follow=True,
            )

    def test_employee_registration_saves_manager_email(self):
        response = self.client.post(
            reverse("allocations:allocation_list"),
            {
                "action": "employee",
                "full_name": "Novo Usuario Manager",
                "corporate_email": self.supervisor.email,
                "manager_email": self.manager.email,
                "employee_id": "Ambiental",
                "teams": Employee.UnitChoices.JOINVILLE,
                "status": Employee.Status.ACTIVE,
            },
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        employee = Employee.objects.get(full_name="Novo Usuario Manager")
        self.assertEqual(employee.manager_email, self.manager.email)
