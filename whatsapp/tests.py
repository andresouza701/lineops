import io
import json
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser
from whatsapp.choices import MeowInstanceHealthStatus, WhatsAppSessionStatus
from whatsapp.clients.exceptions import (
    MeowClientConflictError,
    MeowClientTimeoutError,
)
from whatsapp.clients.meow_client import MeowClient
from whatsapp.models import MeowInstance, WhatsAppActionAudit, WhatsAppSession
from whatsapp.services.instance_selector import (
    InstanceSelectorService,
    NoAvailableMeowInstanceError,
)
from whatsapp.services.session_service import (
    WhatsAppSessionNotConfiguredError,
    WhatsAppSessionResult,
    WhatsAppSessionService,
    WhatsAppSessionServiceError,
)


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
