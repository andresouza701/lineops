from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from telecom.models import PhoneLine
from whatsapp.choices import (
    WhatsAppActionStatus,
    WhatsAppActionType,
    WhatsAppIntegrationJobType,
    WhatsAppSessionStatus,
)
from whatsapp.clients.exceptions import (
    MeowClientConflictError,
    MeowClientError,
    MeowClientNotFoundError,
)
from whatsapp.clients.meow_client import MeowClient
from whatsapp.models import WhatsAppSession
from whatsapp.services.audit_service import WhatsAppAuditService
from whatsapp.services.integration_job_service import WhatsAppIntegrationJobService
from whatsapp.services.instance_selector import InstanceSelectorService


class WhatsAppSessionServiceError(Exception):
    """Base exception for WhatsAppSessionService errors."""


class WhatsAppSessionNotConfiguredError(WhatsAppSessionServiceError):
    """Raised when a WhatsApp session is not configured for a phone line."""


@dataclass
class WhatsAppSessionResult:
    session: WhatsAppSession
    status: str
    remote_payload: dict
    qr_code: str | None = None
    has_qr: bool = False
    connected: bool = False
    detail: str | None = None


class WhatsAppSessionService:
    def __init__(self):
        self.job_service = WhatsAppIntegrationJobService()

    @staticmethod
    def _elapsed_ms(started_at: float) -> int:
        return max(0, int(round((time.monotonic() - started_at) * 1000)))

    def build_session_id(self, line: PhoneLine) -> str:
        return f"session_{line.phone_number}"

    def _get_existing_session(self, line: PhoneLine) -> WhatsAppSession | None:
        return (
            WhatsAppSession.objects.select_related("meow_instance")
            .filter(line=line)
            .first()
        )

    @transaction.atomic
    def get_or_create_session(self, line: PhoneLine) -> WhatsAppSession:
        locked_line = PhoneLine.objects.select_for_update().get(pk=line.pk)
        session = self._get_existing_session(locked_line)
        if session:
            return session

        meow_instance = InstanceSelectorService.select_available_instance(
            allow_above_warning=True
        )
        try:
            with transaction.atomic():
                return WhatsAppSession.objects.create(
                    line=locked_line,
                    meow_instance=meow_instance,
                    session_id=self.build_session_id(locked_line),
                    status=WhatsAppSessionStatus.PENDING_NEW_NUMBER,
                    is_active=True,
                )
        except IntegrityError:
            return (
                WhatsAppSession.objects.select_related("meow_instance")
                .get(line=locked_line)
            )

    def request_connect(self, line: PhoneLine, *, created_by=None) -> WhatsAppSessionResult:
        session = self.get_or_create_session(line)
        detail = "Sessao local reutilizada."
        if session.status != WhatsAppSessionStatus.CONNECTED:
            self._mark_connecting(session)
            _, created = self.job_service.enqueue(
                session=session,
                job_type=WhatsAppIntegrationJobType.CREATE_SESSION,
                created_by=created_by,
                request_payload={"session_id": session.session_id},
            )
            detail = (
                "Solicitacao de conexao registrada."
                if created
                else "Solicitacao de conexao ja pendente."
            )
        return self._build_local_result(session, detail=detail)

    def get_local_status(self, line: PhoneLine) -> WhatsAppSessionResult:
        session = self._require_session(line)
        return self._build_local_result(session)

    def request_qr(self, line: PhoneLine, *, created_by=None) -> WhatsAppSessionResult:
        session = self._require_session(line)
        local_result = self._build_local_result(session)
        if local_result.has_qr or local_result.connected:
            local_result.detail = "QR local reutilizado."
            return local_result

        session.status = WhatsAppSessionStatus.QR_PENDING
        session.last_error = ""
        session.last_sync_at = timezone.now()
        self._persist_session(
            session,
            [
                "status",
                "last_error",
                "last_sync_at",
            ],
        )
        _, created = self.job_service.enqueue(
            session=session,
            job_type=WhatsAppIntegrationJobType.GENERATE_QR,
            created_by=created_by,
            request_payload={"session_id": session.session_id},
        )
        return self._build_local_result(
            session,
            detail=(
                "Solicitacao de QR registrada."
                if created
                else "Solicitacao de QR ja pendente."
            ),
        )

    def get_local_qr(self, line: PhoneLine) -> WhatsAppSessionResult:
        session = self._require_session(line)
        return self._build_local_result(session)

    def request_disconnect(
        self,
        line: PhoneLine,
        *,
        created_by=None,
    ) -> WhatsAppSessionResult:
        session = self._require_session(line)
        self._mark_disconnected(session)
        _, created = self.job_service.enqueue(
            session=session,
            job_type=WhatsAppIntegrationJobType.DELETE_SESSION,
            created_by=created_by,
            request_payload={"session_id": session.session_id},
        )
        return self._build_local_result(
            session,
            detail=(
                "Solicitacao de desconexao registrada."
                if created
                else "Solicitacao de desconexao ja pendente."
            ),
        )

    def connect(self, line: PhoneLine) -> WhatsAppSessionResult:
        session = self.get_or_create_session(line)
        client = self._get_client(session)
        request_payload = {"session_id": session.session_id}
        audit_action = WhatsAppActionType.CREATE_SESSION

        self._mark_connecting(session)

        started_at = time.monotonic()
        try:
            try:
                remote_payload = client.create_session(session.session_id)
            except MeowClientConflictError:
                audit_action = WhatsAppActionType.CONNECT_SESSION
                remote_payload = client.connect_session(session.session_id)
            duration_ms = self._elapsed_ms(started_at)
            with transaction.atomic():
                result = self._sync_from_remote(
                    session,
                    remote_payload=remote_payload,
                    default_status=WhatsAppSessionStatus.CONNECTING,
                )
                WhatsAppAuditService.success(
                    session=session,
                    action=audit_action,
                    request_payload=request_payload,
                    response_payload=remote_payload,
                    duration_ms=duration_ms,
                )
            return result
        except MeowClientNotFoundError as exc:
            duration_ms = self._elapsed_ms(started_at)
            self._mark_error(session, str(exc))
            WhatsAppAuditService.failure(
                session=session,
                action=audit_action,
                request_payload=request_payload,
                response_payload={"error": str(exc)},
                duration_ms=duration_ms,
            )
            raise WhatsAppSessionServiceError(str(exc)) from exc
        except MeowClientError as exc:
            duration_ms = self._elapsed_ms(started_at)
            self._mark_error(session, str(exc))
            WhatsAppAuditService.failure(
                session=session,
                action=audit_action,
                request_payload=request_payload,
                response_payload={"error": str(exc)},
                duration_ms=duration_ms,
            )
            raise WhatsAppSessionServiceError(str(exc)) from exc

    def get_status(self, line: PhoneLine) -> WhatsAppSessionResult:
        session = self._require_session(line)
        client = self._get_client(session)
        started_at = time.monotonic()

        try:
            request_payload = {"session_id": session.session_id}
            remote_payload = client.get_session(session.session_id)
            duration_ms = self._elapsed_ms(started_at)
            with transaction.atomic():
                result = self._sync_from_remote(
                    session, remote_payload=remote_payload
                )
                WhatsAppAuditService.success(
                    session=session,
                    action=WhatsAppActionType.GET_SESSION,
                    request_payload=request_payload,
                    response_payload=remote_payload,
                    duration_ms=duration_ms,
                )
            return result
        except MeowClientNotFoundError as exc:
            duration_ms = self._elapsed_ms(started_at)
            with transaction.atomic():
                self._mark_disconnected(session)
                result = self._build_local_result(
                    session,
                    detail="Sessao ausente no Meow; estado local convergiu para desconectado.",
                )
                WhatsAppAuditService.success(
                    session=session,
                    action=WhatsAppActionType.GET_SESSION,
                    request_payload={"session_id": session.session_id},
                    response_payload={
                        "detail": "Sessao nao encontrada no Meow.",
                        "converged": True,
                    },
                    duration_ms=duration_ms,
                )
            return result
        except MeowClientError as exc:
            duration_ms = self._elapsed_ms(started_at)
            self._mark_error(session, str(exc))
            WhatsAppAuditService.failure(
                session=session,
                action=WhatsAppActionType.GET_SESSION,
                request_payload={"session_id": session.session_id},
                response_payload={"error": str(exc)},
                duration_ms=duration_ms,
            )
            raise WhatsAppSessionServiceError(str(exc)) from exc

    def get_qr(self, line: PhoneLine) -> WhatsAppSessionResult:
        session = self._require_session(line)
        client = self._get_client(session)
        started_at = time.monotonic()

        try:
            qr_payload = client.get_qr(session.session_id)
            duration_ms = self._elapsed_ms(started_at)
            now = timezone.now()
            has_qr = bool(qr_payload.get("qr_code"))
            connected = bool(qr_payload.get("connected"))
            qr_code = qr_payload.get("qr_code")
            qr_expires_at = self._resolve_qr_expires_at(
                qr_payload.get("qr_expires"),
                now=now,
            )

            if connected:
                session.status = WhatsAppSessionStatus.CONNECTED
                session.connected_at = session.connected_at or now
                session.qr_code = ""
                session.qr_expires_at = None
            elif has_qr:
                session.status = WhatsAppSessionStatus.QR_PENDING
                session.qr_code = qr_code or ""
                session.qr_last_generated_at = now
                session.qr_expires_at = qr_expires_at
            else:
                session.status = WhatsAppSessionStatus.CONNECTING
                session.qr_code = ""
                session.qr_expires_at = None

            session.last_error = ""
            session.last_sync_at = now
            with transaction.atomic():
                self._persist_session(
                    session,
                    [
                        "status",
                        "connected_at",
                        "qr_code",
                        "qr_last_generated_at",
                        "qr_expires_at",
                        "last_error",
                        "last_sync_at",
                    ],
                )
                result = WhatsAppSessionResult(
                    session=session,
                    status=session.status,
                    remote_payload=qr_payload.get("raw", {}),
                    qr_code=qr_code,
                    has_qr=has_qr,
                    connected=connected,
                )
                if self._should_audit_get_qr_success(
                    session=session,
                    qr_payload=qr_payload,
                    has_qr=has_qr,
                    connected=connected,
                ):
                    WhatsAppAuditService.success(
                        session=session,
                        action=WhatsAppActionType.GET_QR,
                        request_payload={"session_id": session.session_id},
                        response_payload=qr_payload,
                        duration_ms=duration_ms,
                    )
            return result
        except MeowClientNotFoundError as exc:
            duration_ms = self._elapsed_ms(started_at)
            with transaction.atomic():
                self._mark_disconnected(session)
                result = self._build_local_result(
                    session,
                    detail="Sessao ausente no Meow; QR local invalidado.",
                )
                WhatsAppAuditService.success(
                    session=session,
                    action=WhatsAppActionType.GET_QR,
                    request_payload={"session_id": session.session_id},
                    response_payload={
                        "detail": "Sessao nao encontrada no Meow.",
                        "converged": True,
                    },
                    duration_ms=duration_ms,
                )
            return result
        except MeowClientError as exc:
            duration_ms = self._elapsed_ms(started_at)
            self._mark_error(session, str(exc))
            WhatsAppAuditService.failure(
                session=session,
                action=WhatsAppActionType.GET_QR,
                request_payload={"session_id": session.session_id},
                response_payload={"error": str(exc)},
                duration_ms=duration_ms,
            )
            raise WhatsAppSessionServiceError(str(exc)) from exc

    def disconnect(self, line: PhoneLine) -> WhatsAppSessionResult:
        session = self._require_session(line)
        client = self._get_client(session)
        started_at = time.monotonic()

        try:
            remote_payload = client.disconnect_session(session.session_id)
            duration_ms = self._elapsed_ms(started_at)
            self._mark_disconnected(session)
            with transaction.atomic():
                result = WhatsAppSessionResult(
                    session=session,
                    status=session.status,
                    remote_payload=remote_payload,
                    connected=False,
                )
                WhatsAppAuditService.success(
                    session=session,
                    action=WhatsAppActionType.DELETE_SESSION,
                    request_payload={"session_id": session.session_id},
                    response_payload=remote_payload,
                    duration_ms=duration_ms,
                )
            return result
        except MeowClientNotFoundError as exc:
            duration_ms = self._elapsed_ms(started_at)
            with transaction.atomic():
                self._mark_disconnected(session)
                result = self._build_local_result(
                    session,
                    detail="Sessao ausente no Meow; desconexao convergiu localmente.",
                )
                WhatsAppAuditService.success(
                    session=session,
                    action=WhatsAppActionType.DELETE_SESSION,
                    request_payload={"session_id": session.session_id},
                    response_payload={
                        "detail": "Sessao nao encontrada no Meow.",
                        "converged": True,
                    },
                    duration_ms=duration_ms,
                )
            return result
        except MeowClientError as exc:
            duration_ms = self._elapsed_ms(started_at)
            self._mark_error(session, str(exc))
            WhatsAppAuditService.failure(
                session=session,
                action=WhatsAppActionType.DELETE_SESSION,
                request_payload={"session_id": session.session_id},
                response_payload={"error": str(exc)},
                duration_ms=duration_ms,
            )
            raise WhatsAppSessionServiceError(str(exc)) from exc

    def _require_session(self, line: PhoneLine) -> WhatsAppSession:
        session = self._get_existing_session(line)
        if session:
            return session

        raise WhatsAppSessionNotConfiguredError(
            f"Linha {line.phone_number} ainda nao possui sessao WhatsApp."
        )

    def _should_audit_get_qr_success(
        self,
        *,
        session: WhatsAppSession,
        qr_payload: dict,
        has_qr: bool,
        connected: bool,
    ) -> bool:
        if connected or not has_qr:
            return True

        dedup_seconds = getattr(
            settings,
            "WHATSAPP_GET_QR_AUDIT_DEDUP_SECONDS",
            30,
        )
        if dedup_seconds <= 0:
            return True

        recent_threshold = timezone.now() - timedelta(seconds=dedup_seconds)
        latest_audit = (
            session.action_audits.filter(
                action=WhatsAppActionType.GET_QR,
                status=WhatsAppActionStatus.SUCCESS,
            )
            .order_by("-created_at")
            .first()
        )
        if latest_audit is None or latest_audit.created_at < recent_threshold:
            return True

        latest_response = latest_audit.response_payload or {}
        return not (
            bool(latest_response.get("has_qr")) == has_qr
            and bool(latest_response.get("connected")) == connected
            and latest_response.get("qr_code") == qr_payload.get("qr_code")
        )

    def _get_client(self, session: WhatsAppSession) -> MeowClient:
        if not session.meow_instance:
            raise WhatsAppSessionServiceError(
                f"Sessao {session.session_id} nao possui instancia Meow."
            )
        return MeowClient(session.meow_instance.base_url)

    def _build_local_result(
        self,
        session: WhatsAppSession,
        *,
        detail: str | None = None,
    ) -> WhatsAppSessionResult:
        qr_code = self._get_valid_qr_code(session)
        return WhatsAppSessionResult(
            session=session,
            status=session.status,
            remote_payload={},
            qr_code=qr_code,
            has_qr=bool(qr_code),
            connected=session.status == WhatsAppSessionStatus.CONNECTED,
            detail=detail,
        )

    def _get_valid_qr_code(self, session: WhatsAppSession) -> str | None:
        if not session.qr_code:
            return None
        if session.qr_expires_at and session.qr_expires_at <= timezone.now():
            return None
        return session.qr_code

    def _resolve_qr_expires_at(self, qr_expires, *, now) -> datetime:
        if isinstance(qr_expires, (int, float)):
            if qr_expires > 1_000_000_000_000:
                qr_expires = qr_expires / 1000
            return datetime.fromtimestamp(qr_expires, tz=dt_timezone.utc)

        if isinstance(qr_expires, str) and qr_expires.strip():
            parsed = datetime.fromisoformat(qr_expires.replace("Z", "+00:00"))
            if timezone.is_naive(parsed):
                return timezone.make_aware(parsed, timezone.get_current_timezone())
            return parsed

        return now + timedelta(
            seconds=int(
                getattr(
                    settings,
                    "WHATSAPP_LOCAL_QR_TTL_SECONDS",
                    60,
                )
            )
        )

    def _persist_session(
        self,
        session: WhatsAppSession,
        update_fields: list[str],
    ) -> None:
        session.version += 1
        session.save(update_fields=[*update_fields, "version", "updated_at"])

    def _mark_connecting(self, session: WhatsAppSession) -> None:
        session.status = WhatsAppSessionStatus.CONNECTING
        session.last_error = ""
        session.last_sync_at = timezone.now()
        self._persist_session(
            session,
            [
                "status",
                "last_error",
                "last_sync_at",
            ],
        )

    def _mark_error(
        self, session: WhatsAppSession, error_message: str
    ) -> None:  # noqa: E501
        session.status = WhatsAppSessionStatus.ERROR
        session.last_error = error_message
        session.last_sync_at = timezone.now()
        self._persist_session(
            session,
            [
                "status",
                "last_error",
                "last_sync_at",
            ],
        )

    def _mark_disconnected(self, session: WhatsAppSession) -> None:
        session.status = WhatsAppSessionStatus.DISCONNECTED
        session.last_error = ""
        session.last_sync_at = timezone.now()
        session.qr_code = ""
        session.qr_expires_at = None
        self._persist_session(
            session,
            [
                "status",
                "last_error",
                "last_sync_at",
                "qr_code",
                "qr_expires_at",
            ],
        )

    def _sync_from_remote(
        self,
        session: WhatsAppSession,
        *,
        remote_payload: dict,
        default_status: str | None = None,
    ) -> WhatsAppSessionResult:
        details = (
            remote_payload.get("details")
            or (remote_payload.get("raw") or {}).get("details")
            or {}
        )
        now = timezone.now()

        connected = bool(details.get("connected"))
        has_qr = bool(details.get("hasQR"))
        qr_code = details.get("qrCode")
        qr_expires_at = self._resolve_qr_expires_at(
            details.get("qrExpires"),
            now=now,
        )

        if connected:
            session.status = WhatsAppSessionStatus.CONNECTED
            session.connected_at = session.connected_at or now
            session.qr_code = ""
            session.qr_expires_at = None
        elif has_qr:
            session.status = WhatsAppSessionStatus.QR_PENDING
            session.qr_code = qr_code or ""
            session.qr_last_generated_at = now
            session.qr_expires_at = qr_expires_at
        else:
            session.status = (
                default_status or WhatsAppSessionStatus.DISCONNECTED
            )  # noqa: E501
            session.qr_code = ""
            session.qr_expires_at = None

        session.last_error = ""
        session.last_sync_at = now
        self._persist_session(
            session,
            [
                "status",
                "connected_at",
                "qr_code",
                "qr_last_generated_at",
                "qr_expires_at",
                "last_error",
                "last_sync_at",
            ],
        )
        return WhatsAppSessionResult(
            session=session,
            status=session.status,
            remote_payload=remote_payload,
            qr_code=qr_code,
            has_qr=has_qr,
            connected=connected,
        )
