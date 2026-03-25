from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from core.exceptions.domain_exceptions import BusinessRuleException
from core.services.allocation_service import AllocationService
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser
from whatsapp.models import MeowInstance, WhatsAppSession
from whatsapp.services.instance_selector import NoAvailableMeowInstanceError


class AllocationRulesTestCase(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="admin@test.com",
            password="123456",
            role="ADMIN",
        )

        self.employee = Employee.objects.create(
            full_name="John Doe",
            corporate_email="john@corp.com",
            employee_id="EMP001",
            teams="IT",
        )

        self.lines = []
        for i in range(5):
            sim = SIMcard.objects.create(
                iccid=f"890000000000000000{i}", carrier="CarrierX"
            )

            line = PhoneLine.objects.create(
                phone_number=f"+55119999999{i}", sim_card=sim
            )

            self.lines.append(line)

    def test_employee_cannot_have_more_than_four_active_lines(self):
        for line in self.lines[:4]:
            AllocationService.allocate_line(
                employee=self.employee,
                phone_line=line,
                allocated_by=self.admin,
            )

        with self.assertRaises(BusinessRuleException):
            AllocationService.allocate_line(
                employee=self.employee,
                phone_line=self.lines[4],
                allocated_by=self.admin,
            )

    def test_phone_line_cannot_be_allocated_to_two_employees(self):
        employee_2 = Employee.objects.create(
            full_name="Jane Smith",
            corporate_email="jane@corp.com",
            employee_id="EMP002",
            teams="HR",
        )

        line = self.lines[0]

        AllocationService.allocate_line(
            employee=self.employee, phone_line=line, allocated_by=self.admin
        )

        with self.assertRaises(BusinessRuleException):
            AllocationService.allocate_line(
                employee=employee_2, phone_line=line, allocated_by=self.admin
            )

    @patch(
        "core.services.allocation_service.InstanceSelectorService.select_available_instance",
        side_effect=NoAvailableMeowInstanceError("sem capacidade"),
    )
    def test_allocate_line_blocks_when_new_whatsapp_session_has_no_capacity(
        self,
        _select_available_instance,
    ):
        MeowInstance.objects.create(
            name="QA Meow Saturado",
            base_url="http://qa-meow-saturado.local",
        )
        line = self.lines[0]

        with self.assertRaises(BusinessRuleException) as exc:
            AllocationService.allocate_line(
                employee=self.employee,
                phone_line=line,
                allocated_by=self.admin,
            )

        line.refresh_from_db()
        self.assertIn("capacidade disponivel", str(exc.exception))
        self.assertFalse(
            PhoneLine.objects.filter(
                pk=line.pk,
                status=PhoneLine.Status.ALLOCATED,
            ).exists()
        )
        self.assertEqual(line.status, PhoneLine.Status.AVAILABLE)
        self.assertFalse(WhatsAppSession.objects.filter(line=line).exists())

    @patch(
        "core.services.allocation_service.InstanceSelectorService.select_available_instance",
        side_effect=AssertionError("selector nao deveria ser chamado"),
    )
    def test_allocate_line_reuses_existing_whatsapp_session_without_capacity_check(
        self,
        _select_available_instance,
    ):
        meow = MeowInstance.objects.create(
            name="QA Meow Reuso",
            base_url="http://qa-meow-reuso.local",
        )
        line = self.lines[0]
        WhatsAppSession.objects.create(
            line=line,
            meow_instance=meow,
            session_id=f"session_{line.phone_number}",
        )

        allocation = AllocationService.allocate_line(
            employee=self.employee,
            phone_line=line,
            allocated_by=self.admin,
        )

        allocation.refresh_from_db()
        line.refresh_from_db()
        self.assertTrue(allocation.is_active)
        self.assertEqual(line.status, PhoneLine.Status.ALLOCATED)

    def test_full_allocation_flow(self):
        line = self.lines[0]

        with self.captureOnCommitCallbacks(execute=True):
            allocation = AllocationService.allocate_line(
                employee=self.employee, phone_line=line, allocated_by=self.admin
            )

        self.assertTrue(allocation.is_active)
        self.assertIsNone(allocation.released_at)

        line.refresh_from_db()
        self.assertEqual(line.status, PhoneLine.Status.ALLOCATED)

        with self.captureOnCommitCallbacks(execute=True):
            AllocationService.release_line(
                allocation=allocation,
                released_by=self.admin,
            )

        allocation.refresh_from_db()
        self.assertFalse(allocation.is_active)
        self.assertIsNotNone(allocation.released_at)
        self.assertEqual(allocation.released_by, self.admin)

        line.refresh_from_db()
        self.assertEqual(line.status, PhoneLine.Status.AVAILABLE)

        total_allocations = (
            type(allocation).objects.filter(employee=allocation.employee).count()
        )
        self.assertEqual(total_allocations, 1)

        total_releases = (
            type(allocation)
            .objects.filter(employee=allocation.employee, released_at__isnull=False)
            .count()
        )
        self.assertEqual(total_releases, 1)

    def test_line_allocation_cannot_be_deleted(self):
        allocation = AllocationService.allocate_line(
            employee=self.employee, phone_line=self.lines[0], allocated_by=self.admin
        )

        with self.assertRaises(BusinessRuleException):
            allocation.delete()

    @patch(
        "core.services.allocation_service.WhatsAppProvisioningService.mark_allocation_pending"
    )
    def test_allocate_line_triggers_whatsapp_pending_on_commit(self, mark_pending):
        line = self.lines[0]

        with self.captureOnCommitCallbacks(execute=True):
            allocation = AllocationService.allocate_line(
                employee=self.employee,
                phone_line=line,
                allocated_by=self.admin,
            )

        mark_pending.assert_called_once()
        called_kwargs = mark_pending.call_args.kwargs
        self.assertEqual(called_kwargs["allocation"].pk, allocation.pk)
        self.assertEqual(called_kwargs["actor"], self.admin)

    @patch(
        "core.services.allocation_service.WhatsAppProvisioningService.mark_allocation_pending",
        side_effect=RuntimeError("boom"),
    )
    def test_allocate_line_does_not_fail_when_whatsapp_pending_callback_raises(
        self,
        _mark_pending,
    ):
        line = self.lines[1]

        with (
            self.assertLogs("core.services.allocation_service", level="ERROR") as logs,
            self.captureOnCommitCallbacks(execute=True),
        ):
                allocation = AllocationService.allocate_line(
                    employee=self.employee,
                    phone_line=line,
                    allocated_by=self.admin,
                )

        allocation.refresh_from_db()
        line.refresh_from_db()
        self.assertTrue(allocation.is_active)
        self.assertEqual(line.status, PhoneLine.Status.ALLOCATED)
        self.assertTrue(
            any(
                "WhatsApp provisioning callback failed" in entry
                for entry in logs.output
            )
        )

    @patch(
        "core.services.allocation_service.WhatsAppProvisioningService.resolve_allocation_pending"
    )
    def test_release_line_resolves_whatsapp_pending_on_commit(self, resolve_pending):
        with self.captureOnCommitCallbacks(execute=True):
            allocation = AllocationService.allocate_line(
                employee=self.employee,
                phone_line=self.lines[2],
                allocated_by=self.admin,
            )

        resolve_pending.reset_mock()

        with self.captureOnCommitCallbacks(execute=True):
            AllocationService.release_line(
                allocation=allocation,
                released_by=self.admin,
            )

        resolve_pending.assert_called_once()
        called_kwargs = resolve_pending.call_args.kwargs
        self.assertEqual(called_kwargs["allocation"].pk, allocation.pk)
        self.assertEqual(called_kwargs["actor"], self.admin)


class AllocationReleaseViewTestCase(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="admin@test.com",
            password="123456",
            role="ADMIN",
        )

        self.employee = Employee.objects.create(
            full_name="John Doe",
            corporate_email="john@corp.com",
            employee_id="EMP001",
            teams="IT",
        )

        sim = SIMcard.objects.create(iccid="8900000000000000000", carrier="CarrierX")
        self.phone_line = PhoneLine.objects.create(
            phone_number="+551199999990",
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
        )

        self.allocation = AllocationService.allocate_line(
            employee=self.employee, phone_line=self.phone_line, allocated_by=self.admin
        )

        self.client.force_login(self.admin)

    def test_release_view_deactivates_allocation(self):
        url = reverse("allocations:allocation_release", args=[self.allocation.pk])
        response = self.client.post(url, follow=True)

        self.assertRedirects(response, reverse("allocations:allocation_list"))

        self.allocation.refresh_from_db()
        self.assertFalse(self.allocation.is_active)
        self.assertIsNotNone(self.allocation.released_at)

        self.phone_line.refresh_from_db()
        self.assertEqual(self.phone_line.status, PhoneLine.Status.AVAILABLE)
