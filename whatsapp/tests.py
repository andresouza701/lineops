import io
import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from allocations.models import LineAllocation
from dashboard.models import DailyUserAction
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser
from whatsapp.admin import MeowInstanceAdmin, WhatsAppSessionAdmin
from whatsapp.choices import (
    MeowInstanceHealthStatus,
    WhatsAppSchedulerJobCode,
    WhatsAppSchedulerJobStatus,
    WhatsAppSessionStatus,
)
from whatsapp.clients.exceptions import (
    MeowClientConflictError,
    MeowClientTimeoutError,
    MeowClientUnavailableError,
)
from whatsapp.clients.meow_client import MeowClient
from whatsapp.models import (
    MeowInstance,
    WhatsAppActionAudit,
    WhatsAppScheduledJob,
    WhatsAppSession,
)
from whatsapp.services.capacity_service import MeowCapacityService
from whatsapp.services.health_service import MeowHealthCheckService
from whatsapp.services.instance_selector import (
    InstanceSelectorService,
    NoAvailableMeowInstanceError,
)
from whatsapp.services.metrics_service import WhatsAppMetricsService
from whatsapp.services.provisioning_service import WhatsAppProvisioningService
from whatsapp.services.reconcile_service import WhatsAppSessionReconcileService
from whatsapp.services.rollout_service import MeowRolloutService
from whatsapp.services.scheduler_service import WhatsAppOpsSchedulerService
from whatsapp.services.session_service import (
    WhatsAppSessionNotConfiguredError,
    WhatsAppSessionResult,
    WhatsAppSessionService,
    WhatsAppSessionServiceError,
)
from whatsapp.services.sync_service import WhatsAppSessionSyncService


class WhatsAppModelTests(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="whatsapp-admin@test.com",
            password="123456",
            role=SystemUser.Role.ADMIN,
        )
        self.meow = MeowInstance.objects.create(
            name="Meow A",
            base_url="http://meow-a.local/",
        )
        self.sim = SIMcard.objects.create(
            iccid="89000000000000999901",
            carrier="Carrier A",
            status=SIMcard.Status.AVAILABLE,
        )
        self.line = PhoneLine.objects.create(
            phone_number="+5511999990001",
            sim_card=self.sim,
            status=PhoneLine.Status.AVAILABLE,
        )

    def test_meow_instance_normalizes_trailing_slash(self):
        self.meow.refresh_from_db()
        self.assertEqual(self.meow.base_url, "http://meow-a.local")

    def test_meow_instance_validates_capacity_thresholds(self):
        invalid_instance = MeowInstance(
            name="Meow B",
            base_url="http://meow-b.local",
            target_sessions=41,
            warning_sessions=40,
            max_sessions=45,
        )

        with self.assertRaises(ValidationError):
            invalid_instance.full_clean()

    def test_scheduled_job_defaults_to_idle(self):
        job = WhatsAppScheduledJob.objects.create(
            job_code=WhatsAppSchedulerJobCode.HEALTH_CHECK,
            interval_seconds=300,
        )

        self.assertEqual(job.last_status, WhatsAppSchedulerJobStatus.IDLE)
        self.assertFalse(job.is_running)

    def test_whatsapp_session_defaults_to_pending_new_number(self):
        session = WhatsAppSession.objects.create(
            line=self.line,
            meow_instance=self.meow,
            session_id="session_5511999990001",
        )

        self.assertEqual(session.status, WhatsAppSessionStatus.PENDING_NEW_NUMBER)
        self.assertTrue(session.is_active)

    def test_action_audit_keeps_created_by(self):
        session = WhatsAppSession.objects.create(
            line=self.line,
            meow_instance=self.meow,
            session_id="session_5511999990001",
        )

        audit = WhatsAppActionAudit.objects.create(
            session=session,
            action="CREATE_SESSION",
            status="SUCCESS",
            created_by=self.admin,
            response_payload={"ok": True},
        )

        self.assertEqual(audit.created_by, self.admin)

    def test_action_audit_can_store_duration_ms(self):
        session = WhatsAppSession.objects.create(
            line=self.line,
            meow_instance=self.meow,
            session_id="session_5511999990002",
        )

        audit = WhatsAppActionAudit.objects.create(
            session=session,
            action="GET_QR",
            status="SUCCESS",
            duration_ms=187,
        )

        self.assertEqual(audit.duration_ms, 187)


class InstanceSelectorServiceTests(TestCase):
    def setUp(self):
        self.meow_healthy = MeowInstance.objects.create(
            name="Healthy",
            base_url="http://healthy.local",
            health_status=MeowInstanceHealthStatus.HEALTHY,
        )
        self.meow_unknown = MeowInstance.objects.create(
            name="Unknown",
            base_url="http://unknown.local",
            health_status=MeowInstanceHealthStatus.UNKNOWN,
        )

    def _create_line(self, suffix):
        sim = SIMcard.objects.create(
            iccid=f"8900000000000099{suffix:04d}",
            carrier="Carrier A",
            status=SIMcard.Status.AVAILABLE,
        )
        return PhoneLine.objects.create(
            phone_number=f"+55119998{suffix:04d}",
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
        )

    def test_selector_prefers_healthier_instance_with_lower_load(self):
        line = self._create_line(1)
        WhatsAppSession.objects.create(
            line=line,
            meow_instance=self.meow_unknown,
            session_id="session_1",
        )

        selected = InstanceSelectorService.select_available_instance()

        self.assertEqual(selected, self.meow_healthy)

    def test_selector_raises_when_all_instances_exceed_limit(self):
        self.meow_healthy.warning_sessions = 1
        self.meow_healthy.max_sessions = 1
        self.meow_healthy.save(update_fields=["warning_sessions", "max_sessions"])
        line = self._create_line(2)
        WhatsAppSession.objects.create(
            line=line,
            meow_instance=self.meow_healthy,
            session_id="session_2",
        )

        self.meow_unknown.health_status = MeowInstanceHealthStatus.UNAVAILABLE
        self.meow_unknown.save(update_fields=["health_status"])

        with self.assertRaises(NoAvailableMeowInstanceError):
            InstanceSelectorService.select_available_instance()

    def test_selector_can_fallback_above_warning_up_to_max(self):
        self.meow_healthy.warning_sessions = 1
        self.meow_healthy.max_sessions = 2
        self.meow_healthy.save(update_fields=["warning_sessions", "max_sessions"])
        line = self._create_line(3)
        WhatsAppSession.objects.create(
            line=line,
            meow_instance=self.meow_healthy,
            session_id="session_3",
        )
        self.meow_unknown.health_status = MeowInstanceHealthStatus.UNAVAILABLE
        self.meow_unknown.save(update_fields=["health_status"])

        selected = InstanceSelectorService.select_available_instance(
            allow_above_warning=True
        )

        self.assertEqual(selected, self.meow_healthy)


class WhatsAppSessionServiceTests(TestCase):
    def setUp(self):
        self.meow = MeowInstance.objects.create(
            name="Session Meow",
            base_url="http://session-meow.local",
        )
        self.sim = SIMcard.objects.create(
            iccid="89000000000000999991",
            carrier="Carrier A",
            status=SIMcard.Status.AVAILABLE,
        )
        self.line = PhoneLine.objects.create(
            phone_number="+5511999990091",
            sim_card=self.sim,
            status=PhoneLine.Status.AVAILABLE,
        )
        self.service = WhatsAppSessionService()

    @patch(
        "whatsapp.services.session_service.InstanceSelectorService.select_available_instance"
    )
    def test_get_or_create_session_handles_line_without_reverse_relation(
        self,
        select_available_instance,
    ):
        select_available_instance.return_value = self.meow

        session = self.service.get_or_create_session(self.line)

        self.assertEqual(session.line, self.line)
        self.assertEqual(session.meow_instance, self.meow)
        self.assertEqual(session.session_id, "session_+5511999990091")

    def test_get_status_raises_clean_error_when_line_has_no_session(self):
        with self.assertRaises(WhatsAppSessionNotConfiguredError):
            self.service.get_status(self.line)

    def test_connect_audits_success_after_local_sync(self):
        session = WhatsAppSession.objects.create(
            line=self.line,
            meow_instance=self.meow,
            session_id="session_+5511999990091",
        )
        events = []
        mock_client = MagicMock()
        mock_client.create_session.return_value = {"details": {"connected": True}}

        def sync_side_effect(*args, **kwargs):
            events.append("sync")
            return WhatsAppSessionResult(
                session=session,
                status=WhatsAppSessionStatus.CONNECTED,
                remote_payload=kwargs["remote_payload"],
                connected=True,
            )

        with (
            patch.object(self.service, "_get_client", return_value=mock_client),
            patch.object(
                self.service,
                "_sync_from_remote",
                side_effect=sync_side_effect,
            ),
            patch(
                "whatsapp.services.session_service.WhatsAppAuditService.success",
                side_effect=lambda **kwargs: events.append("audit"),
            ),
        ):
            result = self.service.connect(self.line)

        self.assertEqual(result.status, WhatsAppSessionStatus.CONNECTED)
        self.assertEqual(events, ["sync", "audit"])

    def test_connect_audit_includes_duration_ms(self):
        session = WhatsAppSession.objects.create(
            line=self.line,
            meow_instance=self.meow,
            session_id="session_+5511999990091",
        )
        mock_client = MagicMock()
        mock_client.create_session.return_value = {"details": {"connected": True}}

        with (
            patch.object(self.service, "_get_client", return_value=mock_client),
            patch.object(
                self.service,
                "_sync_from_remote",
                return_value=WhatsAppSessionResult(
                    session=session,
                    status=WhatsAppSessionStatus.CONNECTED,
                    remote_payload={"details": {"connected": True}},
                    connected=True,
                ),
            ),
            patch(
                "whatsapp.services.session_service.WhatsAppAuditService.success"
            ) as audit_success,
            patch(
                "whatsapp.services.session_service.time.monotonic",
                side_effect=[10.0, 10.123],
            ),
        ):
            self.service.connect(self.line)

        self.assertEqual(audit_success.call_args.kwargs["duration_ms"], 123)

    def test_get_status_audits_success_after_local_sync(self):
        session = WhatsAppSession.objects.create(
            line=self.line,
            meow_instance=self.meow,
            session_id="session_+5511999990091",
        )
        events = []
        mock_client = MagicMock()
        mock_client.get_session.return_value = {"details": {"connected": True}}

        def sync_side_effect(*args, **kwargs):
            events.append("sync")
            return WhatsAppSessionResult(
                session=session,
                status=WhatsAppSessionStatus.CONNECTED,
                remote_payload=kwargs["remote_payload"],
                connected=True,
            )

        with (
            patch.object(self.service, "_get_client", return_value=mock_client),
            patch.object(
                self.service,
                "_sync_from_remote",
                side_effect=sync_side_effect,
            ),
            patch(
                "whatsapp.services.session_service.WhatsAppAuditService.success",
                side_effect=lambda **kwargs: events.append("audit"),
            ),
        ):
            result = self.service.get_status(self.line)

        self.assertEqual(result.status, WhatsAppSessionStatus.CONNECTED)
        self.assertEqual(events, ["sync", "audit"])

    def test_get_qr_audits_success_after_local_save(self):
        session = WhatsAppSession.objects.create(
            line=self.line,
            meow_instance=self.meow,
            session_id="session_+5511999990091",
        )
        events = []
        mock_client = MagicMock()
        mock_client.get_qr.return_value = {
            "has_qr": True,
            "qr_code": "qr-base64",
            "connected": False,
            "raw": {"details": {"hasQR": True, "connected": False}},
        }
        original_save = WhatsAppSession.save

        def save_side_effect(instance, *args, **kwargs):
            if instance.pk == session.pk:
                events.append("save")
            return original_save(instance, *args, **kwargs)

        with (
            patch.object(self.service, "_get_client", return_value=mock_client),
            patch.object(
                WhatsAppSession,
                "save",
                autospec=True,
                side_effect=save_side_effect,
            ),
            patch(
                "whatsapp.services.session_service.WhatsAppAuditService.success",
                side_effect=lambda **kwargs: events.append("audit"),
            ),
        ):
            result = self.service.get_qr(self.line)

        self.assertEqual(result.qr_code, "qr-base64")
        self.assertEqual(events, ["save", "audit"])

    def test_disconnect_audits_success_after_local_save(self):
        session = WhatsAppSession.objects.create(
            line=self.line,
            meow_instance=self.meow,
            session_id="session_+5511999990091",
            status=WhatsAppSessionStatus.CONNECTED,
        )
        events = []
        mock_client = MagicMock()
        mock_client.delete_session.return_value = {"success": True}
        original_save = WhatsAppSession.save

        def save_side_effect(instance, *args, **kwargs):
            if instance.pk == session.pk:
                events.append("save")
            return original_save(instance, *args, **kwargs)

        with (
            patch.object(self.service, "_get_client", return_value=mock_client),
            patch.object(
                WhatsAppSession,
                "save",
                autospec=True,
                side_effect=save_side_effect,
            ),
            patch(
                "whatsapp.services.session_service.WhatsAppAuditService.success",
                side_effect=lambda **kwargs: events.append("audit"),
            ),
        ):
            result = self.service.disconnect(self.line)

        self.assertEqual(result.status, WhatsAppSessionStatus.DISCONNECTED)
        self.assertEqual(events, ["save", "audit"])


class WhatsAppProvisioningServiceTests(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="admin-whatsapp-provision@test.com",
            password="123456",
            role=SystemUser.Role.ADMIN,
        )
        self.supervisor = SystemUser.objects.create_user(
            email="supervisor-whatsapp-provision@test.com",
            password="123456",
            role=SystemUser.Role.SUPER,
        )
        self.employee = Employee.objects.create(
            full_name="Operador Provisioning",
            corporate_email=self.supervisor.email,
            employee_id="CART-001",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )
        self.meow = MeowInstance.objects.create(
            name="Provision Meow",
            base_url="http://provision-meow.local",
        )
        self.sim = SIMcard.objects.create(
            iccid="89000000000000777771",
            carrier="Carrier A",
            status=SIMcard.Status.ACTIVE,
        )
        self.line = PhoneLine.objects.create(
            phone_number="+5511999990071",
            sim_card=self.sim,
            status=PhoneLine.Status.ALLOCATED,
        )

    def test_mark_allocation_pending_creates_action_without_session_when_no_meow_is_available(  # noqa: E501
        self,
    ):
        mock_session_service = MagicMock()
        mock_session_service.get_or_create_session.side_effect = (
            NoAvailableMeowInstanceError("sem capacidade")
        )
        service = WhatsAppProvisioningService(session_service=mock_session_service)
        allocation = LineAllocation.objects.create(
            employee=self.employee,
            phone_line=self.line,
            allocated_by=self.admin,
            is_active=True,
        )

        session, action = service.mark_allocation_pending(
            allocation=allocation,
            actor=self.admin,
        )

        self.assertIsNone(session)
        self.assertEqual(action.action_type, DailyUserAction.ActionType.NEW_NUMBER)
        self.assertEqual(action.supervisor, self.supervisor)
        self.assertFalse(action.is_resolved)
        self.assertIn("Infraestrutura Meow sem capacidade disponivel.", action.note)
        self.assertEqual(WhatsAppSession.objects.count(), 0)

    def test_mark_allocation_pending_keeps_new_number_on_first_allocation_with_existing_session(  # noqa: E501
        self,
    ):
        session = WhatsAppSession.objects.create(
            line=self.line,
            meow_instance=self.meow,
            session_id="session_+5511999990071",
            status=WhatsAppSessionStatus.DISCONNECTED,
        )
        allocation = LineAllocation.objects.create(
            employee=self.employee,
            phone_line=self.line,
            allocated_by=self.admin,
            is_active=True,
        )
        service = WhatsAppProvisioningService()

        returned_session, action = service.mark_allocation_pending(
            allocation=allocation,
            actor=self.admin,
        )

        session.refresh_from_db()
        self.assertEqual(returned_session, session)
        self.assertEqual(session.status, WhatsAppSessionStatus.PENDING_NEW_NUMBER)
        self.assertEqual(action.action_type, DailyUserAction.ActionType.NEW_NUMBER)

    def test_mark_allocation_pending_marks_reconnect_for_reallocated_line(self):
        previous_employee = Employee.objects.create(
            full_name="Operador Anterior",
            corporate_email=self.supervisor.email,
            employee_id="CART-002",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )
        session = WhatsAppSession.objects.create(
            line=self.line,
            meow_instance=self.meow,
            session_id="session_+5511999990071",
            status=WhatsAppSessionStatus.CONNECTED,
        )
        previous_allocation = LineAllocation.objects.create(
            employee=previous_employee,
            phone_line=self.line,
            allocated_by=self.admin,
        )
        previous_allocation.is_active = False
        previous_allocation.released_by = self.admin
        previous_allocation.released_at = timezone.now()
        previous_allocation.save(
            update_fields=["is_active", "released_by", "released_at"]
        )
        current_allocation = LineAllocation.objects.create(
            employee=self.employee,
            phone_line=self.line,
            allocated_by=self.admin,
            is_active=True,
        )
        service = WhatsAppProvisioningService()

        returned_session, action = service.mark_allocation_pending(
            allocation=current_allocation,
            actor=self.admin,
        )

        session.refresh_from_db()
        self.assertEqual(returned_session, session)
        self.assertEqual(session.status, WhatsAppSessionStatus.PENDING_RECONNECT)
        self.assertEqual(
            action.action_type, DailyUserAction.ActionType.RECONNECT_WHATSAPP
        )

    def test_resolve_allocation_pending_marks_matching_action_as_resolved(self):
        allocation = LineAllocation.objects.create(
            employee=self.employee,
            phone_line=self.line,
            allocated_by=self.admin,
            is_active=True,
        )
        action = DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=self.employee,
            allocation=allocation,
            supervisor=self.supervisor,
            action_type=DailyUserAction.ActionType.NEW_NUMBER,
            note="Pendente",
            created_by=self.admin,
            updated_by=self.admin,
            is_resolved=False,
        )
        service = WhatsAppProvisioningService()

        resolved = service.resolve_allocation_pending(
            allocation=allocation,
            actor=self.admin,
            note="Resolvido pelo admin",
        )

        action.refresh_from_db()
        self.assertEqual(resolved, 1)
        self.assertTrue(action.is_resolved)
        self.assertEqual(action.note, "Resolvido pelo admin")
        self.assertEqual(action.updated_by, self.admin)


class MeowHealthCheckServiceTests(TestCase):
    def setUp(self):
        self.healthy_instance = MeowInstance.objects.create(
            name="Healthy Meow",
            base_url="http://healthy-meow.local",
        )
        self.degraded_instance = MeowInstance.objects.create(
            name="Degraded Meow",
            base_url="http://degraded-meow.local",
        )
        self.inactive_instance = MeowInstance.objects.create(
            name="Inactive Meow",
            base_url="http://inactive-meow.local",
            is_active=False,
        )
        self.service = MeowHealthCheckService()

    @patch("whatsapp.services.health_service.MeowClient.health_check")
    def test_check_instance_marks_healthy_on_successful_payload(self, health_check):
        health_check.return_value = {"success": True, "message": "ok"}

        result = self.service.check_instance(self.healthy_instance)

        self.healthy_instance.refresh_from_db()
        self.assertEqual(
            self.healthy_instance.health_status,
            MeowInstanceHealthStatus.HEALTHY,
        )
        self.assertEqual(result.health_status, MeowInstanceHealthStatus.HEALTHY)
        self.assertEqual(result.detail, "ok")
        self.assertIsNotNone(self.healthy_instance.last_health_check_at)

    @patch("whatsapp.services.health_service.MeowClient.health_check")
    def test_check_instance_marks_degraded_on_unsuccessful_payload(self, health_check):
        health_check.return_value = {"success": False, "message": "downstream issue"}

        result = self.service.check_instance(self.degraded_instance)

        self.degraded_instance.refresh_from_db()
        self.assertEqual(
            self.degraded_instance.health_status,
            MeowInstanceHealthStatus.DEGRADED,
        )
        self.assertEqual(result.detail, "downstream issue")

    @patch("whatsapp.services.health_service.MeowClient.health_check")
    def test_check_instance_marks_unavailable_on_client_unavailable_error(
        self,
        health_check,
    ):
        health_check.side_effect = MeowClientUnavailableError("sem resposta")

        result = self.service.check_instance(self.healthy_instance)

        self.healthy_instance.refresh_from_db()
        self.assertEqual(
            self.healthy_instance.health_status,
            MeowInstanceHealthStatus.UNAVAILABLE,
        )
        self.assertEqual(result.detail, "sem resposta")

    @patch("whatsapp.services.health_service.MeowClient.health_check")
    def test_check_instances_skips_inactive_by_default(self, health_check):
        health_check.return_value = {"success": True}

        results = self.service.check_instances()

        self.assertEqual(len(results), 2)
        self.inactive_instance.refresh_from_db()
        self.assertEqual(
            self.inactive_instance.health_status,
            MeowInstanceHealthStatus.UNKNOWN,
        )

    @patch("whatsapp.management.commands.check_meow_health.MeowHealthCheckService")
    def test_command_checks_selected_instance_only(self, service_class):
        service = service_class.return_value
        service.check_instances.return_value = []
        stdout = io.StringIO()

        call_command(
            "check_meow_health",
            instance_id=self.healthy_instance.pk,
            stdout=stdout,
        )

        queryset = service.check_instances.call_args.kwargs["queryset"]
        self.assertEqual(
            list(queryset.values_list("pk", flat=True)),
            [self.healthy_instance.pk],
        )


class MeowCapacityServiceTests(TestCase):
    def setUp(self):
        self.service = MeowCapacityService()
        self.warning_instance = MeowInstance.objects.create(
            name="Warning Meow",
            base_url="http://warning-meow.local",
            target_sessions=1,
            warning_sessions=2,
            max_sessions=3,
        )
        self.other_instance = MeowInstance.objects.create(
            name="Other Capacity Meow",
            base_url="http://other-capacity-meow.local",
            is_active=False,
        )

        self._create_session(
            "+5511999990051",
            self.warning_instance,
            WhatsAppSessionStatus.CONNECTED,
        )
        self._create_session(
            "+5511999990052",
            self.warning_instance,
            WhatsAppSessionStatus.PENDING_RECONNECT,
        )
        self._create_session(
            "+5511999990053",
            self.warning_instance,
            WhatsAppSessionStatus.ERROR,
        )

    def _create_session(self, phone_number, meow_instance, status):
        sim = SIMcard.objects.create(
            iccid=f"8900000000000{phone_number[-6:]}",
            carrier="Carrier A",
            status=SIMcard.Status.AVAILABLE,
        )
        line = PhoneLine.objects.create(
            phone_number=phone_number,
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
        )
        return WhatsAppSession.objects.create(
            line=line,
            meow_instance=meow_instance,
            session_id=f"session_{phone_number}",
            status=status,
        )

    def test_summarize_instances_returns_capacity_breakdown(self):
        summaries = self.service.summarize_instances()

        self.assertEqual(len(summaries), 1)
        summary = summaries[0]
        self.assertEqual(summary.instance, self.warning_instance)
        self.assertEqual(summary.active_sessions, 3)
        self.assertEqual(summary.connected_sessions, 1)
        self.assertEqual(summary.pending_sessions, 1)
        self.assertEqual(summary.degraded_sessions, 1)
        self.assertEqual(summary.capacity_level, "CRITICAL")

    @patch("whatsapp.management.commands.check_meow_capacity.MeowCapacityService")
    def test_command_filters_selected_instance(self, service_class):
        service = service_class.return_value
        service.summarize_instances.return_value = []
        stdout = io.StringIO()

        call_command(
            "check_meow_capacity",
            instance_id=self.warning_instance.pk,
            stdout=stdout,
        )

        queryset = service.summarize_instances.call_args.kwargs["queryset"]
        self.assertEqual(
            list(queryset.values_list("pk", flat=True)),
            [self.warning_instance.pk],
        )


class WhatsAppSessionSyncServiceTests(TestCase):
    def setUp(self):
        self.meow = MeowInstance.objects.create(
            name="Sync Meow",
            base_url="http://sync-meow.local",
        )
        self.service = WhatsAppSessionSyncService()
        self.session_ok = self._create_session(
            "+5511999990041",
            WhatsAppSessionStatus.CONNECTING,
        )
        self.session_fail = self._create_session(
            "+5511999990042",
            WhatsAppSessionStatus.ERROR,
        )

    def _create_session(self, phone_number, status):
        sim = SIMcard.objects.create(
            iccid=f"8900000000000{phone_number[-6:]}",
            carrier="Carrier A",
            status=SIMcard.Status.AVAILABLE,
        )
        line = PhoneLine.objects.create(
            phone_number=phone_number,
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
        )
        return WhatsAppSession.objects.create(
            line=line,
            meow_instance=self.meow,
            session_id=f"session_{phone_number}",
            status=status,
        )

    def test_sync_sessions_returns_success_and_failure_results(self):
        def get_status_side_effect(line):
            if line.pk == self.session_ok.line_id:
                return WhatsAppSessionResult(
                    session=self.session_ok,
                    status=WhatsAppSessionStatus.CONNECTED,
                    remote_payload={"details": {"connected": True}},
                    connected=True,
                )
            raise WhatsAppSessionServiceError("falha no meow")

        with patch.object(
            self.service.session_service,
            "get_status",
            side_effect=get_status_side_effect,
        ):
            results = self.service.sync_sessions()

        self.assertEqual(len(results), 2)
        self.assertTrue(results[0].success)
        self.assertEqual(results[0].status, WhatsAppSessionStatus.CONNECTED)
        self.assertFalse(results[1].success)
        self.assertEqual(results[1].status, WhatsAppSessionStatus.ERROR)
        self.assertEqual(results[1].detail, "falha no meow")

    @patch("whatsapp.management.commands.sync_whatsapp_sessions.WhatsAppSessionSyncService")
    def test_command_filters_sessions_by_instance(self, service_class):
        service = service_class.return_value
        service.sync_sessions.return_value = []
        stdout = io.StringIO()

        call_command(
            "sync_whatsapp_sessions",
            instance_id=self.meow.pk,
            stdout=stdout,
        )

        queryset = service.sync_sessions.call_args.kwargs["queryset"]
        self.assertEqual(
            list(queryset.values_list("pk", flat=True).order_by("pk")),
            [self.session_ok.pk, self.session_fail.pk],
        )


class WhatsAppSessionReconcileServiceTests(TestCase):
    def setUp(self):
        self.service = WhatsAppSessionReconcileService()
        self.meow_ok = MeowInstance.objects.create(
            name="Reconcile OK Meow",
            base_url="http://reconcile-ok-meow.local",
            health_status=MeowInstanceHealthStatus.HEALTHY,
        )
        self.meow_bad = MeowInstance.objects.create(
            name="Reconcile Bad Meow",
            base_url="http://reconcile-bad-meow.local",
            health_status=MeowInstanceHealthStatus.UNAVAILABLE,
            is_active=False,
        )

    def _create_session(
        self,
        phone_number,
        *,
        meow_instance,
        line_deleted=False,
        sim_deleted=False,
        minutes_since_sync=5,
    ):
        sim = SIMcard.all_objects.create(
            iccid=f"8900000000000{phone_number[-6:]}",
            carrier="Carrier A",
            status=SIMcard.Status.AVAILABLE,
            is_deleted=sim_deleted,
        )
        line = PhoneLine.all_objects.create(
            phone_number=phone_number,
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
            is_deleted=line_deleted,
        )
        return WhatsAppSession.objects.create(
            line=line,
            meow_instance=meow_instance,
            session_id=f"session_{phone_number}",
            status=WhatsAppSessionStatus.CONNECTED,
            last_sync_at=timezone.now() - timedelta(minutes=minutes_since_sync),
        )

    @override_settings(WHATSAPP_SESSION_STALE_MINUTES=30)
    def test_reconcile_detects_structural_and_stale_issues(self):
        healthy_session = self._create_session(
            "+5511999990031",
            meow_instance=self.meow_ok,
            minutes_since_sync=5,
        )
        inconsistent_session = self._create_session(
            "+5511999990032",
            meow_instance=self.meow_bad,
            line_deleted=True,
            minutes_since_sync=90,
        )

        results = self.service.reconcile_sessions(include_inactive=True)
        result_map = {result.session.session_id: result for result in results}

        self.assertTrue(result_map[healthy_session.session_id].is_consistent)
        self.assertFalse(result_map[inconsistent_session.session_id].is_consistent)
        self.assertEqual(
            result_map[inconsistent_session.session_id].issue_codes,
            [
                "LINE_HIDDEN",
                "INSTANCE_INACTIVE",
                "INSTANCE_UNAVAILABLE",
                "SYNC_STALE",
            ],
        )

    @patch(
        "whatsapp.management.commands.reconcile_whatsapp_sessions.WhatsAppSessionReconcileService"
    )
    def test_command_filters_sessions_by_instance(self, service_class):
        session = self._create_session(
            "+5511999990033",
            meow_instance=self.meow_ok,
            minutes_since_sync=5,
        )
        service = service_class.return_value
        service.reconcile_sessions.return_value = []
        stdout = io.StringIO()

        call_command(
            "reconcile_whatsapp_sessions",
            instance_id=self.meow_ok.pk,
            stdout=stdout,
        )

        queryset = service.reconcile_sessions.call_args.kwargs["queryset"]
        self.assertEqual(list(queryset.values_list("pk", flat=True)), [session.pk])


class WhatsAppMetricsServiceTests(TestCase):
    def setUp(self):
        self.meow_a = MeowInstance.objects.create(
            name="Metrics A",
            base_url="http://metrics-a.local",
        )
        self.meow_b = MeowInstance.objects.create(
            name="Metrics B",
            base_url="http://metrics-b.local",
            is_active=False,
        )
        self.line_a = self._create_line("+5511999990201", "89000000000000992001")
        self.line_b = self._create_line("+5511999990202", "89000000000000992002")
        self.session_a = WhatsAppSession.objects.create(
            line=self.line_a,
            meow_instance=self.meow_a,
            session_id="session_metrics_a",
        )
        self.session_b = WhatsAppSession.objects.create(
            line=self.line_b,
            meow_instance=self.meow_b,
            session_id="session_metrics_b",
        )

    def _create_line(self, phone_number, iccid):
        sim = SIMcard.objects.create(
            iccid=iccid,
            carrier="Carrier A",
            status=SIMcard.Status.AVAILABLE,
        )
        return PhoneLine.objects.create(
            phone_number=phone_number,
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
        )

    def test_metrics_service_summarizes_recent_metrics_per_instance(self):
        recent_qr = WhatsAppActionAudit.objects.create(
            session=self.session_a,
            action="GET_QR",
            status="SUCCESS",
            duration_ms=120,
        )
        recent_reconnect = WhatsAppActionAudit.objects.create(
            session=self.session_a,
            action="CONNECT_SESSION",
            status="FAILURE",
            duration_ms=240,
        )
        WhatsAppActionAudit.objects.create(
            session=self.session_b,
            action="GET_QR",
            status="SUCCESS",
            duration_ms=80,
        )
        old_audit = WhatsAppActionAudit.objects.create(
            session=self.session_a,
            action="GET_QR",
            status="SUCCESS",
            duration_ms=999,
        )
        old_time = timezone.now() - timedelta(hours=48)
        WhatsAppActionAudit.objects.filter(pk=old_audit.pk).update(created_at=old_time)
        recent_time = timezone.now() - timedelta(hours=1)
        WhatsAppActionAudit.objects.filter(
            pk__in=[recent_qr.pk, recent_reconnect.pk]
        ).update(created_at=recent_time)

        summaries = WhatsAppMetricsService().summarize_instances(
            include_inactive=True,
            window_hours=24,
        )

        summary_by_name = {summary.instance.name: summary for summary in summaries}
        meow_a_summary = summary_by_name["Metrics A"]
        meow_b_summary = summary_by_name["Metrics B"]

        self.assertEqual(meow_a_summary.qr_requests, 1)
        self.assertEqual(meow_a_summary.reconnect_attempts, 1)
        self.assertEqual(meow_a_summary.failures, 1)
        self.assertEqual(meow_a_summary.average_latency_ms, 180)
        self.assertIsNotNone(meow_a_summary.last_audit_at)

        self.assertEqual(meow_b_summary.qr_requests, 1)
        self.assertEqual(meow_b_summary.reconnect_attempts, 0)
        self.assertEqual(meow_b_summary.failures, 0)
        self.assertEqual(meow_b_summary.average_latency_ms, 80)


@override_settings(
    WHATSAPP_MEOW_ROLLOUT_STAGES=[25, 30, 35, 40],
    WHATSAPP_MEOW_ROLLOUT_BUFFER=5,
    WHATSAPP_MEOW_OPERATIONAL_CEILING=45,
    WHATSAPP_MEOW_EXPECTED_ACTIVE_INSTANCES=2,
)
class MeowRolloutServiceTests(TestCase):
    def _create_line(self, phone_number, iccid):
        sim = SIMcard.objects.create(
            iccid=iccid,
            carrier="Carrier A",
            status=SIMcard.Status.AVAILABLE,
        )
        return PhoneLine.objects.create(
            phone_number=phone_number,
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
        )

    def _create_session(self, meow_instance, phone_number, iccid):
        line = self._create_line(phone_number, iccid)
        return WhatsAppSession.objects.create(
            line=line,
            meow_instance=meow_instance,
            session_id=f"session_{phone_number}",
        )

    def test_rollout_service_summarizes_uniform_stage_and_next_step(self):
        meow_a = MeowInstance.objects.create(
            name="Rollout A",
            base_url="http://rollout-a.local",
            target_sessions=25,
            warning_sessions=30,
            max_sessions=35,
        )
        meow_b = MeowInstance.objects.create(
            name="Rollout B",
            base_url="http://rollout-b.local",
            target_sessions=25,
            warning_sessions=30,
            max_sessions=35,
        )
        self._create_session(meow_a, "+5511999990301", "89000000000000993001")
        self._create_session(meow_b, "+5511999990302", "89000000000000993002")

        summary = MeowRolloutService().build_summary()

        self.assertTrue(summary.is_uniform)
        self.assertIsNotNone(summary.current_stage)
        self.assertEqual(summary.current_stage.stage_sessions, 30)
        self.assertIsNotNone(summary.next_stage)
        self.assertEqual(summary.next_stage.stage_sessions, 35)
        self.assertEqual(summary.total_active_sessions, 2)
        self.assertEqual(summary.current_capacity_sessions, 60)
        self.assertIn("Proxima etapa: 35", summary.recommendation)

    def test_rollout_service_flags_mixed_capacity_configuration(self):
        MeowInstance.objects.create(
            name="Mixed A",
            base_url="http://mixed-a.local",
            target_sessions=25,
            warning_sessions=30,
            max_sessions=35,
        )
        MeowInstance.objects.create(
            name="Mixed B",
            base_url="http://mixed-b.local",
            target_sessions=30,
            warning_sessions=35,
            max_sessions=40,
        )

        summary = MeowRolloutService().build_summary()

        self.assertFalse(summary.is_uniform)
        self.assertIsNone(summary.current_stage)
        self.assertIn("Padronize", summary.recommendation)

    def test_rollout_service_recommends_opening_sixth_meow_at_trigger(self):
        meow_a = MeowInstance.objects.create(
            name="Final A",
            base_url="http://final-a.local",
            target_sessions=35,
            warning_sessions=40,
            max_sessions=45,
        )
        meow_b = MeowInstance.objects.create(
            name="Final B",
            base_url="http://final-b.local",
            target_sessions=35,
            warning_sessions=40,
            max_sessions=45,
        )

        for index in range(40):
            self._create_session(
                meow_a,
                f"+55119999904{index:02d}",
                f"89000000000000994{index:03d}",
            )
            self._create_session(
                meow_b,
                f"+55119999905{index:02d}",
                f"89000000000000995{index:03d}",
            )

        summary = MeowRolloutService().build_summary()

        self.assertTrue(summary.should_open_sixth_meow)
        self.assertEqual(summary.sixth_meow_trigger_sessions, 80)
        self.assertIn("Abrir o 6o Meow", summary.recommendation)


@override_settings(
    WHATSAPP_OPS_INCLUDE_INACTIVE=False,
    WHATSAPP_OPS_HEALTH_INTERVAL_SECONDS=300,
    WHATSAPP_OPS_SYNC_INTERVAL_SECONDS=600,
    WHATSAPP_OPS_RECONCILE_INTERVAL_SECONDS=3600,
)
class WhatsAppOpsSchedulerServiceTests(TestCase):
    @patch("whatsapp.services.scheduler_service.MeowHealthCheckService")
    @patch("whatsapp.services.scheduler_service.WhatsAppSessionSyncService")
    @patch("whatsapp.services.scheduler_service.WhatsAppSessionReconcileService")
    def test_scheduler_runs_due_jobs_and_persists_state(
        self,
        reconcile_service_class,
        sync_service_class,
        health_service_class,
    ):
        health_service_class.return_value.check_instances.return_value = [
            MagicMock(health_status="HEALTHY"),
            MagicMock(health_status="DEGRADED"),
        ]
        sync_service_class.return_value.sync_sessions.return_value = [
            MagicMock(success=True),
            MagicMock(success=False),
        ]
        reconcile_service_class.return_value.reconcile_sessions.return_value = [
            MagicMock(is_consistent=True),
            MagicMock(is_consistent=False),
        ]

        now = timezone.now()
        results = WhatsAppOpsSchedulerService().run_due_jobs(now=now)

        self.assertEqual(len(results), 3)
        self.assertTrue(all(result.ran for result in results))
        self.assertEqual(WhatsAppScheduledJob.objects.count(), 3)

        health_job = WhatsAppScheduledJob.objects.get(
            job_code=WhatsAppSchedulerJobCode.HEALTH_CHECK
        )
        sync_job = WhatsAppScheduledJob.objects.get(
            job_code=WhatsAppSchedulerJobCode.SESSION_SYNC
        )
        reconcile_job = WhatsAppScheduledJob.objects.get(
            job_code=WhatsAppSchedulerJobCode.SESSION_RECONCILE
        )

        self.assertEqual(health_job.last_status, WhatsAppSchedulerJobStatus.SUCCESS)
        self.assertIn("2 instancia(s) verificadas", health_job.last_detail)
        self.assertEqual(sync_job.last_status, WhatsAppSchedulerJobStatus.SUCCESS)
        self.assertIn("1 sucesso, 1 falha", sync_job.last_detail)
        self.assertEqual(
            reconcile_job.last_status,
            WhatsAppSchedulerJobStatus.SUCCESS,
        )
        self.assertIn(
            "1 consistente(s), 1 com inconsistencias",
            reconcile_job.last_detail,
        )
        self.assertFalse(health_job.is_running)
        self.assertIsNotNone(health_job.next_run_at)

    @patch("whatsapp.services.scheduler_service.MeowHealthCheckService")
    @patch("whatsapp.services.scheduler_service.WhatsAppSessionSyncService")
    @patch("whatsapp.services.scheduler_service.WhatsAppSessionReconcileService")
    def test_scheduler_skips_jobs_that_are_not_due(
        self,
        reconcile_service_class,
        sync_service_class,
        health_service_class,
    ):
        now = timezone.now()
        future = now + timedelta(minutes=30)
        for job_code, interval_seconds in (
            (WhatsAppSchedulerJobCode.HEALTH_CHECK, 300),
            (WhatsAppSchedulerJobCode.SESSION_SYNC, 600),
            (WhatsAppSchedulerJobCode.SESSION_RECONCILE, 3600),
        ):
            WhatsAppScheduledJob.objects.create(
                job_code=job_code,
                interval_seconds=interval_seconds,
                last_status=WhatsAppSchedulerJobStatus.SUCCESS,
                next_run_at=future,
            )

        results = WhatsAppOpsSchedulerService().run_due_jobs(now=now)

        self.assertEqual(len(results), 3)
        self.assertTrue(all(not result.ran for result in results))
        health_service_class.return_value.check_instances.assert_not_called()
        sync_service_class.return_value.sync_sessions.assert_not_called()
        reconcile_service_class.return_value.reconcile_sessions.assert_not_called()

    @patch("whatsapp.services.scheduler_service.MeowHealthCheckService")
    @patch("whatsapp.services.scheduler_service.WhatsAppSessionSyncService")
    @patch("whatsapp.services.scheduler_service.WhatsAppSessionReconcileService")
    def test_scheduler_marks_failure_and_releases_job_lock(
        self,
        reconcile_service_class,
        sync_service_class,
        health_service_class,
    ):
        health_service_class.return_value.check_instances.side_effect = RuntimeError(
            "meow offline"
        )
        sync_service_class.return_value.sync_sessions.return_value = []
        reconcile_service_class.return_value.reconcile_sessions.return_value = []

        WhatsAppOpsSchedulerService().run_due_jobs(now=timezone.now())

        health_job = WhatsAppScheduledJob.objects.get(
            job_code=WhatsAppSchedulerJobCode.HEALTH_CHECK
        )
        self.assertEqual(health_job.last_status, WhatsAppSchedulerJobStatus.FAILURE)
        self.assertEqual(health_job.last_detail, "meow offline")
        self.assertFalse(health_job.is_running)
        self.assertIsNotNone(health_job.next_run_at)


class MeowInstanceAdminTests(TestCase):
    def setUp(self):
        self.superuser = SystemUser.objects.create_superuser(
            email="admin-whatsapp-admin@test.com",
            password="123456",
            role=SystemUser.Role.ADMIN,
        )
        self.factory = RequestFactory()
        self.admin_instance = MeowInstanceAdmin(MeowInstance, admin.site)
        self.meow = MeowInstance.objects.create(
            name="Admin Meow",
            base_url="http://admin-meow.local",
        )
        self.other_meow = MeowInstance.objects.create(
            name="Other Meow",
            base_url="http://other-meow.local",
        )

        sim_connected = SIMcard.objects.create(
            iccid="89000000000000666661",
            carrier="Carrier A",
            status=SIMcard.Status.AVAILABLE,
        )
        line_connected = PhoneLine.objects.create(
            phone_number="+5511999990061",
            sim_card=sim_connected,
            status=PhoneLine.Status.AVAILABLE,
        )
        WhatsAppSession.objects.create(
            line=line_connected,
            meow_instance=self.meow,
            session_id="session_+5511999990061",
            status=WhatsAppSessionStatus.CONNECTED,
        )

        sim_error = SIMcard.objects.create(
            iccid="89000000000000666662",
            carrier="Carrier A",
            status=SIMcard.Status.AVAILABLE,
        )
        line_error = PhoneLine.objects.create(
            phone_number="+5511999990062",
            sim_card=sim_error,
            status=PhoneLine.Status.AVAILABLE,
        )
        WhatsAppSession.objects.create(
            line=line_error,
            meow_instance=self.meow,
            session_id="session_+5511999990062",
            status=WhatsAppSessionStatus.ERROR,
        )

        sim_disconnected = SIMcard.objects.create(
            iccid="89000000000000666663",
            carrier="Carrier A",
            status=SIMcard.Status.AVAILABLE,
        )
        line_disconnected = PhoneLine.objects.create(
            phone_number="+5511999990063",
            sim_card=sim_disconnected,
            status=PhoneLine.Status.AVAILABLE,
        )
        WhatsAppSession.objects.create(
            line=line_disconnected,
            meow_instance=self.meow,
            session_id="session_+5511999990063",
            status=WhatsAppSessionStatus.DISCONNECTED,
        )

        sim_other = SIMcard.objects.create(
            iccid="89000000000000666664",
            carrier="Carrier A",
            status=SIMcard.Status.AVAILABLE,
        )
        line_other = PhoneLine.objects.create(
            phone_number="+5511999990064",
            sim_card=sim_other,
            status=PhoneLine.Status.AVAILABLE,
        )
        WhatsAppSession.objects.create(
            line=line_other,
            meow_instance=self.other_meow,
            session_id="session_+5511999990064",
            status=WhatsAppSessionStatus.CONNECTED,
        )

    def test_admin_queryset_annotates_session_counts(self):
        request = self.factory.get("/admin/whatsapp/meowinstance/")
        request.user = self.superuser

        obj = self.admin_instance.get_queryset(request).get(pk=self.meow.pk)

        self.assertEqual(obj.active_sessions_count_value, 3)
        self.assertEqual(obj.connected_sessions_count_value, 1)
        self.assertEqual(obj.degraded_sessions_count_value, 2)

    @patch("whatsapp.admin.MeowHealthCheckService")
    def test_admin_action_runs_health_check_for_selected_instances(
        self,
        service_class,
    ):
        service = service_class.return_value
        service.check_instances.return_value = [MagicMock(), MagicMock()]
        request = self.factory.post("/admin/whatsapp/meowinstance/")
        request.user = self.superuser
        queryset = MeowInstance.objects.filter(
            pk__in=[self.meow.pk, self.other_meow.pk]
        )

        with patch.object(self.admin_instance, "message_user") as message_user:
            self.admin_instance.run_health_check(request, queryset)

        service.check_instances.assert_called_once_with(
            queryset=queryset,
            include_inactive=True,
        )
        message_user.assert_called_once()


class WhatsAppSessionAdminTests(TestCase):
    def setUp(self):
        self.superuser = SystemUser.objects.create_superuser(
            email="admin-whatsapp-session-admin@test.com",
            password="123456",
            role=SystemUser.Role.ADMIN,
        )
        self.factory = RequestFactory()
        self.admin_instance = WhatsAppSessionAdmin(WhatsAppSession, admin.site)
        self.meow = MeowInstance.objects.create(
            name="Session Admin Meow",
            base_url="http://session-admin-meow.local",
        )

        sim = SIMcard.objects.create(
            iccid="89000000000000666671",
            carrier="Carrier A",
            status=SIMcard.Status.AVAILABLE,
        )
        line = PhoneLine.objects.create(
            phone_number="+5511999990071",
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
        )
        self.session = WhatsAppSession.objects.create(
            line=line,
            meow_instance=self.meow,
            session_id="session_+5511999990071",
            status=WhatsAppSessionStatus.CONNECTING,
        )

    @patch("whatsapp.admin.WhatsAppSessionSyncService")
    def test_admin_action_syncs_selected_sessions(self, service_class):
        service = service_class.return_value
        service.sync_sessions.return_value = [MagicMock(success=True)]
        request = self.factory.post("/admin/whatsapp/whatsappsession/")
        request.user = self.superuser
        queryset = WhatsAppSession.objects.filter(pk=self.session.pk)

        with patch.object(self.admin_instance, "message_user") as message_user:
            self.admin_instance.sync_selected_sessions(request, queryset)

        service.sync_sessions.assert_called_once_with(
            queryset=queryset,
            include_inactive=True,
        )
        message_user.assert_called_once()

    @patch("whatsapp.admin.WhatsAppSessionReconcileService")
    def test_admin_action_reconciles_selected_sessions(self, service_class):
        service = service_class.return_value
        service.reconcile_sessions.return_value = [MagicMock(is_consistent=False)]
        request = self.factory.post("/admin/whatsapp/whatsappsession/")
        request.user = self.superuser
        queryset = WhatsAppSession.objects.filter(pk=self.session.pk)

        with patch.object(self.admin_instance, "message_user") as message_user:
            self.admin_instance.reconcile_selected_sessions(request, queryset)

        service.reconcile_sessions.assert_called_once_with(
            queryset=queryset,
            include_inactive=True,
        )
        message_user.assert_called_once()


@override_settings(WHATSAPP_MEOW_TIMEOUT_SECONDS=7)
class MeowClientTests(TestCase):
    def _mock_response(self, payload):
        response = MagicMock()
        response.read.return_value = json.dumps(payload).encode("utf-8")
        context_manager = MagicMock()
        context_manager.__enter__.return_value = response
        context_manager.__exit__.return_value = False
        return context_manager

    @patch("whatsapp.clients.meow_client.request.urlopen")
    def test_health_check_uses_expected_endpoint(self, urlopen):
        urlopen.return_value = self._mock_response({"success": True})
        client = MeowClient("http://meow.local/")

        response = client.health_check()

        self.assertEqual(response["success"], True)
        called_request = urlopen.call_args.args[0]
        self.assertEqual(called_request.full_url, "http://meow.local/api/health")
        self.assertEqual(called_request.method, "GET")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 7)

    @patch("whatsapp.clients.meow_client.request.urlopen")
    def test_create_session_posts_json_payload(self, urlopen):
        urlopen.return_value = self._mock_response({"success": True, "sessionId": "s1"})
        client = MeowClient("http://meow.local")

        response = client.create_session("session_5511999990001")

        self.assertEqual(response["sessionId"], "s1")
        called_request = urlopen.call_args.args[0]
        self.assertEqual(called_request.full_url, "http://meow.local/api/sessions")
        self.assertEqual(called_request.method, "POST")
        self.assertEqual(
            json.loads(called_request.data.decode("utf-8")),
            {"session_id": "session_5511999990001"},
        )

    @patch("whatsapp.clients.meow_client.request.urlopen")
    def test_conflict_response_is_mapped(self, urlopen):
        error_body = io.BytesIO(b'{"message":"session already exists"}')
        urlopen.side_effect = HTTPError(
            url="http://meow.local/api/sessions",
            code=409,
            msg="Conflict",
            hdrs=None,
            fp=error_body,
        )
        client = MeowClient("http://meow.local")

        with self.assertRaises(MeowClientConflictError) as exc:
            client.create_session("session_5511999990001")

        self.assertEqual(exc.exception.status_code, 409)
        self.assertIn("session already exists", str(exc.exception.detail))

    @patch("whatsapp.clients.meow_client.request.urlopen")
    def test_timeout_is_mapped(self, urlopen):
        urlopen.side_effect = TimeoutError()
        client = MeowClient("http://meow.local")

        with self.assertRaises(MeowClientTimeoutError):
            client.health_check()


class WhatsAppSessionViewTests(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="admin-whatsapp-view@test.com",
            password="123456",
            role=SystemUser.Role.ADMIN,
        )
        self.operator = SystemUser.objects.create_user(
            email="operator-whatsapp-view@test.com",
            password="123456",
            role=SystemUser.Role.OPERATOR,
        )
        self.meow = MeowInstance.objects.create(
            name="View Meow",
            base_url="http://view-meow.local",
        )
        self.sim = SIMcard.objects.create(
            iccid="89000000000000888881",
            carrier="Carrier A",
            status=SIMcard.Status.AVAILABLE,
        )
        self.line = PhoneLine.objects.create(
            phone_number="+5511999990081",
            sim_card=self.sim,
            status=PhoneLine.Status.AVAILABLE,
        )
        self.session = WhatsAppSession.objects.create(
            line=self.line,
            meow_instance=self.meow,
            session_id="session_+5511999990081",
            status=WhatsAppSessionStatus.CONNECTING,
        )

    def _build_result(
        self,
        *,
        status=WhatsAppSessionStatus.CONNECTING,
        connected=False,
        qr_code=None,
        has_qr=False,
    ):
        self.session.status = status
        return WhatsAppSessionResult(
            session=self.session,
            status=status,
            remote_payload={"details": {}},
            qr_code=qr_code,
            has_qr=has_qr,
            connected=connected,
        )

    def test_status_view_returns_json_for_admin(self):
        self.client.force_login(self.admin)

        with patch.object(
            WhatsAppSessionService,
            "get_status",
            return_value=self._build_result(
                status=WhatsAppSessionStatus.CONNECTED,
                connected=True,
            ),
        ):
            response = self.client.get(
                reverse("telecom:whatsapp:status", args=[self.line.pk])
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["line_id"], self.line.pk)
        self.assertEqual(payload["session_id"], self.session.session_id)
        self.assertEqual(payload["status"], WhatsAppSessionStatus.CONNECTED)
        self.assertTrue(payload["connected"])

    def test_status_view_returns_configured_false_when_session_is_missing(self):
        self.client.force_login(self.admin)

        with patch.object(
            WhatsAppSessionService,
            "get_status",
            side_effect=WhatsAppSessionNotConfiguredError("nao configurada"),
        ):
            response = self.client.get(
                reverse("telecom:whatsapp:status", args=[self.line.pk])
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["configured"])
        self.assertIsNone(payload["session_id"])

    def test_qr_view_returns_qr_payload(self):
        self.client.force_login(self.admin)

        with patch.object(
            WhatsAppSessionService,
            "get_qr",
            return_value=self._build_result(
                status=WhatsAppSessionStatus.QR_PENDING,
                qr_code="base64-qr",
                has_qr=True,
                connected=False,
            ),
        ):
            response = self.client.get(
                reverse("telecom:whatsapp:qr", args=[self.line.pk])
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["qr_code"], "base64-qr")
        self.assertTrue(payload["has_qr"])

    def test_qr_view_returns_404_when_session_is_missing(self):
        self.client.force_login(self.admin)

        with patch.object(
            WhatsAppSessionService,
            "get_qr",
            side_effect=WhatsAppSessionNotConfiguredError("nao configurada"),
        ):
            response = self.client.get(
                reverse("telecom:whatsapp:qr", args=[self.line.pk])
            )

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertIn("error", payload)

    def test_connect_view_redirects_on_standard_post(self):
        self.client.force_login(self.admin)

        with patch.object(
            WhatsAppSessionService,
            "connect",
            return_value=self._build_result(),
        ):
            response = self.client.post(
                reverse("telecom:whatsapp:connect", args=[self.line.pk])
            )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(
            response,
            reverse("telecom:phoneline_detail", args=[self.line.pk]),
            fetch_redirect_response=False,
        )

    def test_connect_view_returns_json_for_ajax(self):
        self.client.force_login(self.admin)

        with patch.object(
            WhatsAppSessionService,
            "connect",
            return_value=self._build_result(
                status=WhatsAppSessionStatus.CONNECTING,
                connected=False,
            ),
        ):
            response = self.client.post(
                reverse("telecom:whatsapp:connect", args=[self.line.pk]),
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], WhatsAppSessionStatus.CONNECTING)

    def test_disconnect_view_returns_json_for_ajax(self):
        self.client.force_login(self.admin)

        with patch.object(
            WhatsAppSessionService,
            "disconnect",
            return_value=self._build_result(
                status=WhatsAppSessionStatus.DISCONNECTED,
                connected=False,
            ),
        ):
            response = self.client.post(
                reverse("telecom:whatsapp:disconnect", args=[self.line.pk]),
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], WhatsAppSessionStatus.DISCONNECTED)
        self.assertFalse(payload["connected"])

    def test_status_view_returns_502_when_service_fails(self):
        self.client.force_login(self.admin)

        with patch.object(
            WhatsAppSessionService,
            "get_status",
            side_effect=WhatsAppSessionServiceError("falha meow"),
        ):
            response = self.client.get(
                reverse("telecom:whatsapp:status", args=[self.line.pk])
            )

        self.assertEqual(response.status_code, 502)
        payload = response.json()
        self.assertEqual(payload["error"], "falha meow")

    def test_whatsapp_views_require_admin_role(self):
        self.client.force_login(self.operator)

        response = self.client.get(
            reverse("telecom:whatsapp:status", args=[self.line.pk])
        )

        self.assertEqual(response.status_code, 403)

    def test_phoneline_detail_renders_whatsapp_card(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("telecom:phoneline_detail", args=[self.line.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="whatsapp-session-card"', html=False)
        self.assertContains(
            response,
            reverse("telecom:whatsapp:status", args=[self.line.pk]),
        )
        self.assertContains(
            response,
            reverse("telecom:whatsapp:connect", args=[self.line.pk]),
        )
        self.assertContains(response, "Consultar QR")
        self.assertContains(response, "Conectar")
        self.assertContains(response, "Desconectar")


class WhatsAppOperationsViewTests(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="admin-whatsapp-ops@test.com",
            password="123456",
            role=SystemUser.Role.ADMIN,
        )
        self.dev = SystemUser.objects.create_user(
            email="dev-whatsapp-ops@test.com",
            password="123456",
            role=SystemUser.Role.DEV,
        )
        self.operator = SystemUser.objects.create_user(
            email="operator-whatsapp-ops@test.com",
            password="123456",
            role=SystemUser.Role.OPERATOR,
        )
        self.healthy_meow = MeowInstance.objects.create(
            name="Healthy Ops Meow",
            base_url="http://healthy-ops-meow.local",
            health_status=MeowInstanceHealthStatus.HEALTHY,
        )
        self.unavailable_meow = MeowInstance.objects.create(
            name="Unavailable Ops Meow",
            base_url="http://unavailable-ops-meow.local",
            health_status=MeowInstanceHealthStatus.UNAVAILABLE,
            is_active=False,
        )
        self.problem_session = self._create_problem_session()
        self.healthy_problem_session = self._create_problem_session(
            phone_number="+5511999990090",
            meow_instance=self.healthy_meow,
            last_error="stale sync local",
        )

    def _create_problem_session(
        self,
        *,
        phone_number="+5511999990089",
        meow_instance=None,
        last_error="sem conexao com meow",
    ):
        sim = SIMcard.objects.create(
            iccid=f"8900000000000{phone_number[-6:]}",
            carrier="Carrier A",
            status=SIMcard.Status.AVAILABLE,
        )
        line = PhoneLine.objects.create(
            phone_number=phone_number,
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
        )
        return WhatsAppSession.objects.create(
            line=line,
            meow_instance=meow_instance or self.unavailable_meow,
            session_id=f"session_{phone_number}",
            status=WhatsAppSessionStatus.ERROR,
            last_error=last_error,
            last_sync_at=timezone.now() - timedelta(minutes=90),
        )

    def test_operations_view_allows_admin(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("whatsapp_operations"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Instancias Meow")
        self.assertContains(response, "Sessoes com atencao operacional")
        self.assertContains(response, self.healthy_meow.name)
        self.assertContains(response, self.unavailable_meow.name)
        self.assertContains(response, "sem conexao com meow")
        self.assertContains(
            response,
            reverse("telecom:phoneline_detail", args=[self.problem_session.line.pk]),
        )

    def test_operations_view_allows_dev(self):
        self.client.force_login(self.dev)

        response = self.client.get(reverse("whatsapp_operations"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Operacao WhatsApp")

    def test_operations_view_rejects_operator(self):
        self.client.force_login(self.operator)

        response = self.client.get(reverse("whatsapp_operations"))

        self.assertEqual(response.status_code, 403)

    def test_operations_view_can_filter_problem_sessions_by_instance(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("whatsapp_operations"),
            {"instance_id": self.unavailable_meow.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Filtro ativo")
        self.assertContains(response, self.problem_session.session_id)
        self.assertNotContains(response, self.healthy_problem_session.session_id)

    def test_operations_view_can_filter_problem_sessions_by_issue_code(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("whatsapp_operations"),
            {"issue_code": "INSTANCE_UNAVAILABLE"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "INSTANCE_UNAVAILABLE")
        self.assertContains(response, self.problem_session.session_id)
        self.assertNotContains(response, self.healthy_problem_session.session_id)

    def test_operations_view_shows_issue_summary_links(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("whatsapp_operations"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "INSTANCE_UNAVAILABLE (1)")
        self.assertContains(response, "SYNC_STALE (2)")

    def test_operations_view_exposes_recent_metrics_for_selected_instance(self):
        WhatsAppActionAudit.objects.create(
            session=self.healthy_problem_session,
            action="GET_QR",
            status="SUCCESS",
            duration_ms=140,
        )
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("whatsapp_operations"),
            {"instance_id": self.healthy_meow.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Metricas recentes")
        metric_summaries = response.context["instance_metric_summaries"]
        self.assertEqual(len(metric_summaries), 1)
        self.assertEqual(metric_summaries[0].instance, self.healthy_meow)
        self.assertEqual(metric_summaries[0].qr_requests, 1)

    def test_operations_view_exposes_rollout_summary(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("whatsapp_operations"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rollout operacional")
        rollout_summary = response.context["rollout_summary"]
        self.assertIsNotNone(rollout_summary.current_stage)
        self.assertEqual(rollout_summary.current_stage.stage_sessions, 40)
        self.assertFalse(rollout_summary.should_open_sixth_meow)

    def test_operations_view_exposes_scheduler_job_summaries(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("whatsapp_operations"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Agendador operacional")
        scheduler_job_summaries = response.context["scheduler_job_summaries"]
        self.assertEqual(len(scheduler_job_summaries), 3)
        self.assertEqual(scheduler_job_summaries[0].last_status, "IDLE")

    @patch("whatsapp.views.MeowHealthCheckService")
    def test_operations_view_post_runs_health_check_for_selected_instance(
        self,
        service_class,
    ):
        service = service_class.return_value
        service.check_instances.return_value = [MagicMock()]
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("whatsapp_operations"),
            {
                "action": "check_health",
                "instance_id": str(self.unavailable_meow.pk),
                "issue_code": "INSTANCE_UNAVAILABLE",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            f"{reverse('whatsapp_operations')}?instance_id={self.unavailable_meow.pk}&issue_code=INSTANCE_UNAVAILABLE",
        )
        queryset = service.check_instances.call_args.kwargs["queryset"]
        self.assertEqual(
            list(queryset.values_list("pk", flat=True)),
            [self.unavailable_meow.pk],
        )
        self.assertTrue(service.check_instances.call_args.kwargs["include_inactive"])

    @patch("whatsapp.views.WhatsAppSessionSyncService")
    def test_operations_view_post_runs_sync_for_selected_instance(self, service_class):
        service = service_class.return_value
        service.sync_sessions.return_value = [MagicMock(success=True)]
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("whatsapp_operations"),
            {
                "action": "sync_sessions",
                "instance_id": str(self.unavailable_meow.pk),
            },
        )

        self.assertEqual(response.status_code, 302)
        queryset = service.sync_sessions.call_args.kwargs["queryset"]
        self.assertEqual(
            list(queryset.values_list("pk", flat=True)),
            [self.problem_session.pk],
        )
        self.assertTrue(service.sync_sessions.call_args.kwargs["include_inactive"])

    @patch("whatsapp.views.WhatsAppSessionSyncService")
    def test_operations_view_post_runs_sync_for_selected_session(self, service_class):
        service = service_class.return_value
        service.sync_sessions.return_value = [MagicMock(success=True)]
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("whatsapp_operations"),
            {
                "action": "sync_session",
                "session_pk": str(self.problem_session.pk),
                "instance_id": str(self.unavailable_meow.pk),
                "issue_code": "INSTANCE_UNAVAILABLE",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            f"{reverse('whatsapp_operations')}?instance_id={self.unavailable_meow.pk}&issue_code=INSTANCE_UNAVAILABLE",
        )
        queryset = service.sync_sessions.call_args.kwargs["queryset"]
        self.assertEqual(
            list(queryset.values_list("pk", flat=True)),
            [self.problem_session.pk],
        )
        self.assertTrue(service.sync_sessions.call_args.kwargs["include_inactive"])

    @patch("whatsapp.views.WhatsAppSessionReconcileService")
    def test_operations_view_post_runs_reconcile_for_selected_instance(
        self,
        service_class,
    ):
        service = service_class.return_value
        service.reconcile_sessions.return_value = [MagicMock(is_consistent=False)]
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("whatsapp_operations"),
            {
                "action": "reconcile_sessions",
                "instance_id": str(self.unavailable_meow.pk),
            },
        )

        self.assertEqual(response.status_code, 302)
        queryset = service.reconcile_sessions.call_args.kwargs["queryset"]
        self.assertEqual(
            list(queryset.values_list("pk", flat=True)),
            [self.problem_session.pk],
        )
        self.assertTrue(
            service.reconcile_sessions.call_args.kwargs["include_inactive"]
        )


class BootstrapMeowInstancesCommandTests(TestCase):
    def _write_config(self, payload):
        config_path = Path(__file__).resolve().parent / "_test_meow_instances.json"
        config_path.write_text(json.dumps(payload), encoding="utf-8")
        self.addCleanup(lambda: config_path.unlink(missing_ok=True))
        return config_path

    def test_bootstrap_command_creates_instances_from_json(self):
        payload = [
            {
                "name": "QA Meow 01",
                "base_url": "http://qa-meow-01.local/",
                "is_active": True,
                "target_sessions": 35,
                "warning_sessions": 40,
                "max_sessions": 45,
            },
            {
                "name": "QA Meow 02",
                "base_url": "http://qa-meow-02.local",
                "is_active": False,
                "target_sessions": 30,
                "warning_sessions": 35,
                "max_sessions": 40,
            },
        ]
        stdout = io.StringIO()
        config_path = self._write_config(payload)

        call_command(
            "bootstrap_meow_instances",
            config=str(config_path),
            stdout=stdout,
        )

        self.assertEqual(MeowInstance.objects.count(), 2)
        first = MeowInstance.objects.get(name="QA Meow 01")
        second = MeowInstance.objects.get(name="QA Meow 02")
        self.assertEqual(first.base_url, "http://qa-meow-01.local")
        self.assertTrue(first.is_active)
        self.assertFalse(second.is_active)
        self.assertIn(
            "Bootstrap concluido: 2 criada(s), 0 atualizada(s).",
            stdout.getvalue(),
        )

    def test_bootstrap_command_updates_existing_instance(self):
        instance = MeowInstance.objects.create(
            name="QA Meow 01",
            base_url="http://old-meow.local",
            is_active=True,
            target_sessions=35,
            warning_sessions=40,
            max_sessions=45,
        )
        payload = [
            {
                "name": "QA Meow 01",
                "base_url": "http://new-meow.local/",
                "is_active": False,
                "target_sessions": 32,
                "warning_sessions": 38,
                "max_sessions": 44,
            }
        ]
        stdout = io.StringIO()
        config_path = self._write_config(payload)

        call_command(
            "bootstrap_meow_instances",
            config=str(config_path),
            stdout=stdout,
        )

        instance.refresh_from_db()
        self.assertEqual(instance.base_url, "http://new-meow.local")
        self.assertFalse(instance.is_active)
        self.assertEqual(instance.target_sessions, 32)
        self.assertEqual(instance.warning_sessions, 38)
        self.assertEqual(instance.max_sessions, 44)
        self.assertIn(
            "Bootstrap concluido: 0 criada(s), 1 atualizada(s).",
            stdout.getvalue(),
        )

    def test_bootstrap_command_dry_run_does_not_persist(self):
        payload = [
            {
                "name": "QA Meow 01",
                "base_url": "http://qa-meow-01.local",
            }
        ]
        stdout = io.StringIO()
        config_path = self._write_config(payload)

        call_command(
            "bootstrap_meow_instances",
            config=str(config_path),
            dry_run=True,
            stdout=stdout,
        )

        self.assertFalse(MeowInstance.objects.exists())
        self.assertIn(
            "[dry-run] create: QA Meow 01 -> http://qa-meow-01.local",
            stdout.getvalue(),
        )
        self.assertIn(
            "Dry-run concluido: 1 criaria(m), 0 atualizaria(m), sem persistencia.",
            stdout.getvalue(),
        )

    def test_bootstrap_command_rejects_duplicate_names(self):
        payload = [
            {
                "name": "QA Meow 01",
                "base_url": "http://qa-meow-01.local",
            },
            {
                "name": "QA Meow 01",
                "base_url": "http://qa-meow-02.local",
            },
        ]
        config_path = self._write_config(payload)

        with self.assertRaises(CommandError):
            call_command("bootstrap_meow_instances", config=str(config_path))

        self.assertFalse(MeowInstance.objects.exists())


@override_settings(
    WHATSAPP_MEOW_ROLLOUT_STAGES=[25, 30, 35, 40],
    WHATSAPP_MEOW_ROLLOUT_BUFFER=5,
    WHATSAPP_MEOW_OPERATIONAL_CEILING=45,
)
class ApplyMeowRolloutStageCommandTests(TestCase):
    def test_command_updates_active_instances(self):
        active_instance = MeowInstance.objects.create(
            name="Command Meow Active",
            base_url="http://command-meow-active.local",
            target_sessions=35,
            warning_sessions=40,
            max_sessions=45,
        )
        inactive_instance = MeowInstance.objects.create(
            name="Command Meow Inactive",
            base_url="http://command-meow-inactive.local",
            is_active=False,
            target_sessions=35,
            warning_sessions=40,
            max_sessions=45,
        )
        stdout = io.StringIO()

        call_command("apply_meow_rollout_stage", stage=30, stdout=stdout)

        active_instance.refresh_from_db()
        inactive_instance.refresh_from_db()
        self.assertEqual(active_instance.target_sessions, 25)
        self.assertEqual(active_instance.warning_sessions, 30)
        self.assertEqual(active_instance.max_sessions, 35)
        self.assertEqual(inactive_instance.warning_sessions, 40)
        self.assertIn(
            "Rollout aplicado em 1 instancia(s) para a etapa 30.",
            stdout.getvalue(),
        )

    def test_command_dry_run_does_not_persist(self):
        instance = MeowInstance.objects.create(
            name="Dry Run Meow",
            base_url="http://dry-run-meow.local",
            target_sessions=35,
            warning_sessions=40,
            max_sessions=45,
        )
        stdout = io.StringIO()

        call_command(
            "apply_meow_rollout_stage",
            stage=25,
            dry_run=True,
            stdout=stdout,
        )

        instance.refresh_from_db()
        self.assertEqual(instance.target_sessions, 35)
        self.assertEqual(instance.warning_sessions, 40)
        self.assertIn("[dry-run] Dry Run Meow: target=20 warning=25 max=30", stdout.getvalue())
        self.assertIn(
            "Dry-run concluido: 1 instancia(s) seriam ajustadas para a etapa 25.",
            stdout.getvalue(),
        )

    def test_command_rejects_unknown_stage(self):
        MeowInstance.objects.create(
            name="Invalid Stage Meow",
            base_url="http://invalid-stage-meow.local",
        )

        with self.assertRaises(CommandError):
            call_command("apply_meow_rollout_stage", stage=33)


class RunWhatsAppOpsSchedulerCommandTests(TestCase):
    @patch(
        "whatsapp.management.commands.run_whatsapp_ops_scheduler.WhatsAppOpsSchedulerService"
    )
    def test_command_run_once_executes_due_jobs(self, service_class):
        service = service_class.return_value
        service.run_due_jobs.return_value = [
            MagicMock(
                ran=True,
                job_code="HEALTH_CHECK",
                status="SUCCESS",
                detail="1 instancia(s) verificadas",
                next_run_at=timezone.now(),
            )
        ]
        stdout = io.StringIO()

        call_command("run_whatsapp_ops_scheduler", run_once=True, stdout=stdout)

        service.run_due_jobs.assert_called_once()
        self.assertIn("HEALTH_CHECK: SUCCESS", stdout.getvalue())

    @patch(
        "whatsapp.management.commands.run_whatsapp_ops_scheduler.WhatsAppOpsSchedulerService"
    )
    def test_command_run_once_reports_when_nothing_is_due(self, service_class):
        service = service_class.return_value
        service.run_due_jobs.return_value = [
            MagicMock(
                ran=False,
                job_code="HEALTH_CHECK",
                status="SUCCESS",
                detail="",
                next_run_at=timezone.now(),
            )
        ]
        stdout = io.StringIO()

        call_command("run_whatsapp_ops_scheduler", run_once=True, stdout=stdout)

        self.assertIn("Nenhum job elegivel neste ciclo.", stdout.getvalue())
