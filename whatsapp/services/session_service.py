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
from whatsapp.services.observability_service import emit_integration_log
from whatsapp.services.instance_selector import (
    InstanceSelectorService,
    NoAvailableMeowInstanceError,
)
from whatsapp.services.state_machine_service import (
    InvalidWhatsAppSessionTransition,
    WhatsAppSessionStateMachineService,
)


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
    correlation_id: str = ""
    job_id: int | None = None
    job_status: str | None = None
    job_created: bool | None = None
    job_available_at: datetime | None = None
    session_created: bool | None = None


class WhatsAppSessionService:
    def __init__(self):
        self.job_service = WhatsAppIntegrationJobService()
        self.state_machine = WhatsAppSessionStateMachineService()

    @staticmethod
    def _elapsed_ms(started_at: float) -> int:
        return max(0, int(round((time.monotonic() - started_at) * 1000)))

    @staticmethod
    def _raise_local_request_error(exc: Exception) -> None:
        if isinstance(exc, NoAvailableMeowInstanceError):
            raise WhatsAppSessionServiceError(
                "Nao ha instancia Meow ativa com capacidade disponivel."
            ) from exc
        if isinstance(exc, InvalidWhatsAppSessionTransition):
            raise WhatsAppSessionServiceError(
                "A sessao WhatsApp esta em um estado invalido para esta operacao."
            ) from exc
        raise exc

    def build_session_id(self, line: PhoneLine) -> str:
        return f"session_{line.phone_number}"

    def _get_existing_session(self, line: PhoneLine) -> WhatsAppSession | None:
        return (
            WhatsAppSession.objects.select_related("meow_instance")
            .filter(line=line)
            .first()
        )

    @transaction.atomic
    def get_or_create_session_with_created(
        self,
        line: PhoneLine,
    ) -> tuple[WhatsAppSession, bool]:
        locked_line = PhoneLine.objects.select_for_update().get(pk=line.pk)
        session = self._get_existing_session(locked_line)
        if session:
            return session, False

        meow_instance = InstanceSelectorService.select_available_instance(
            allow_above_warning=True,
            lock_instances=True,
        )
        try:
            with transaction.atomic():
                return (
                    WhatsAppSession.objects.create(
                        line=locked_line,
                        meow_instance=meow_instance,
                        session_id=self.build_session_id(locked_line),
                        status=WhatsAppSessionStatus.NEW,
                        is_active=True,
                    ),
                    True,
                )
        except IntegrityError:
            return (
                WhatsAppSession.objects.select_related("meow_instance")
                .get(line=locked_line),
                False,
            )

    def get_or_create_session(self, line: PhoneLine) -> WhatsAppSession:
        session, _ = self.get_or_create_session_with_created(line)
        return session

    def request_connect(
        self,
        line: PhoneLine,
        *,
        created_by=None,
        correlation_id: str = "",
    ) -> WhatsAppSessionResult:
        try:
            session, session_created = self.get_or_create_session_with_created(line)
            detail = (
                "Conexao local criada e solicitacao registrada."
                if session_created
                else "Sessao local reutilizada."
            )
            job = None
            job_created = None
            if session.status != WhatsAppSessionStatus.CONNECTED:
                self.state_machine.mark_session_requested(session)
                job, job_created = self.job_service.enqueue(
                    session=session,
                    job_type=WhatsAppIntegrationJobType.CREATE_SESSION,
                    created_by=created_by,
                    correlation_id=correlation_id,
                    request_payload={"session_id": session.session_id},
                )
                detail = (
                    "Solicitacao de conexao registrada."
                    if job_created
                    else "Solicitacao de conexao ja pendente."
                )
            effective_correlation_id = job.correlation_id if job else correlation_id
            self._record_local_action(
                session=session,
                action=WhatsAppActionType.CREATE_SESSION,
                detail=detail,
                created_by=created_by,
                correlation_id=effective_correlation_id,
                job=job,
                job_created=job_created,
            )
            return self._build_local_result(
                session,
                detail=detail,
                correlation_id=effective_correlation_id,
                job=job,
                job_created=job_created,
                session_created=session_created,
            )
        except (NoAvailableMeowInstanceError, InvalidWhatsAppSessionTransition) as exc:
            self._raise_local_request_error(exc)

    def get_local_status(self, line: PhoneLine) -> WhatsAppSessionResult:
        session = self._require_session(line)
        return self._build_local_result(session)

    def request_qr(
        self,
        line: PhoneLine,
        *,
        created_by=None,
        correlation_id: str = "",
    ) -> WhatsAppSessionResult:
        try:
            session = self._require_session(line)
            local_result = self._build_local_result(session)
            if local_result.has_qr:
                local_result.detail = "QR local reutilizado."
                local_result.correlation_id = correlation_id
                self._record_local_action(
                    session=session,
                    action=WhatsAppActionType.GET_QR,
                    detail=local_result.detail,
                    created_by=created_by,
                    correlation_id=correlation_id,
                    response_payload={
                        "source": "local_cache",
                        "has_qr": local_result.has_qr,
                        "connected": local_result.connected,
                    },
                )
                return local_result

            if local_result.connected:
                local_result.detail = "Sessao ja conectada; QR nao e necessario."
                local_result.correlation_id = correlation_id
                self._record_local_action(
                    session=session,
                    action=WhatsAppActionType.GET_QR,
                    detail=local_result.detail,
                    created_by=created_by,
                    correlation_id=correlation_id,
                    response_payload={
                        "source": "connected_session",
                        "has_qr": local_result.has_qr,
                        "connected": local_result.connected,
                    },
                )
                return local_result

            self.state_machine.mark_session_requested(session)
            job, job_created = self.job_service.enqueue(
                session=session,
                job_type=WhatsAppIntegrationJobType.GENERATE_QR,
                created_by=created_by,
                correlation_id=correlation_id,
                request_payload={"session_id": session.session_id},
            )
            detail = (
                "Solicitacao de QR registrada."
                if job_created
                else "Solicitacao de QR ja pendente."
            )
            effective_correlation_id = job.correlation_id or correlation_id
            self._record_local_action(
                session=session,
                action=WhatsAppActionType.GET_QR,
                detail=detail,
                created_by=created_by,
                correlation_id=effective_correlation_id,
                job=job,
                job_created=job_created,
            )
            return self._build_local_result(
                session,
                detail=detail,
                correlation_id=effective_correlation_id,
                job=job,
                job_created=job_created,
            )
        except InvalidWhatsAppSessionTransition as exc:
            self._raise_local_request_error(exc)

    def get_local_qr(self, line: PhoneLine) -> WhatsAppSessionResult:
        session = self._require_session(line)
        return self._build_local_result(session)

    def request_disconnect(
        self,
        line: PhoneLine,
        *,
        created_by=None,
        correlation_id: str = "",
    ) -> WhatsAppSessionResult:
        try:
            session = self._require_session(line)
            self.state_machine.mark_disconnected(session)
            job, job_created = self.job_service.enqueue(
                session=session,
                job_type=WhatsAppIntegrationJobType.DELETE_SESSION,
                created_by=created_by,
                correlation_id=correlation_id,
                request_payload={"session_id": session.session_id},
            )
            detail = (
                "Solicitacao de desconexao registrada."
                if job_created
                else "Solicitacao de desconexao ja pendente."
            )
            effective_correlation_id = job.correlation_id or correlation_id
            self._record_local_action(
                session=session,
                action=WhatsAppActionType.DELETE_SESSION,
                detail=detail,
                created_by=created_by,
                correlation_id=effective_correlation_id,
                job=job,
                job_created=job_created,
            )
            return self._build_local_result(
                session,
                detail=detail,
                correlation_id=effective_correlation_id,
                job=job,
                job_created=job_created,
            )
        except InvalidWhatsAppSessionTransition as exc:
            self._raise_local_request_error(exc)

    def connect(self, line: PhoneLine, *, correlation_id: str = "") -> WhatsAppSessionResult:
        session = self.get_or_create_session(line)
        client = self._get_client(session)
        request_payload = {"session_id": session.session_id}
        audit_action = WhatsAppActionType.CREATE_SESSION

        self.state_machine.mark_session_requested(session)

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
                    default_status=WhatsAppSessionStatus.SESSION_REQUESTED,
                )
                WhatsAppAuditService.success(
                    session=session,
                    action=audit_action,
                    correlation_id=correlation_id,
                    request_payload=request_payload,
                    response_payload=remote_payload,
                    duration_ms=duration_ms,
                )
            result.correlation_id = correlation_id
            emit_integration_log(
                "whatsapp.remote.connect.success",
                correlation_id=correlation_id,
                session_id=session.session_id,
                session_pk=session.pk,
                status=result.status,
            )
            return result
        except MeowClientNotFoundError as exc:
            duration_ms = self._elapsed_ms(started_at)
            self.state_machine.mark_failed(session, error_message=str(exc))
            WhatsAppAuditService.failure(
                session=session,
                action=audit_action,
                correlation_id=correlation_id,
                request_payload=request_payload,
                response_payload={"error": str(exc)},
                duration_ms=duration_ms,
            )
            emit_integration_log(
                "whatsapp.remote.connect.failure",
                correlation_id=correlation_id,
                session_id=session.session_id,
                session_pk=session.pk,
                error=str(exc),
            )
            raise WhatsAppSessionServiceError(str(exc)) from exc
        except MeowClientError as exc:
            duration_ms = self._elapsed_ms(started_at)
            self.state_machine.mark_failed(session, error_message=str(exc))
            WhatsAppAuditService.failure(
                session=session,
                action=audit_action,
                correlation_id=correlation_id,
                request_payload=request_payload,
                response_payload={"error": str(exc)},
                duration_ms=duration_ms,
            )
            emit_integration_log(
                "whatsapp.remote.connect.failure",
                correlation_id=correlation_id,
                session_id=session.session_id,
                session_pk=session.pk,
                error=str(exc),
            )
            raise WhatsAppSessionServiceError(str(exc)) from exc

    def get_status(self, line: PhoneLine, *, correlation_id: str = "") -> WhatsAppSessionResult:
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
                    correlation_id=correlation_id,
                    request_payload=request_payload,
                    response_payload=remote_payload,
                    duration_ms=duration_ms,
                )
            result.correlation_id = correlation_id
            return result
        except MeowClientNotFoundError as exc:
            duration_ms = self._elapsed_ms(started_at)
            with transaction.atomic():
                self.state_machine.mark_disconnected(session)
                result = self._build_local_result(
                    session,
                    detail="Sessao ausente no Meow; estado local convergiu para desconectado.",
                )
                WhatsAppAuditService.success(
                    session=session,
                    action=WhatsAppActionType.GET_SESSION,
                    correlation_id=correlation_id,
                    request_payload={"session_id": session.session_id},
                    response_payload={
                        "detail": "Sessao nao encontrada no Meow.",
                        "converged": True,
                    },
                    duration_ms=duration_ms,
                )
            result.correlation_id = correlation_id
            return result
        except MeowClientError as exc:
            duration_ms = self._elapsed_ms(started_at)
            self.state_machine.mark_failed(session, error_message=str(exc))
            WhatsAppAuditService.failure(
                session=session,
                action=WhatsAppActionType.GET_SESSION,
                correlation_id=correlation_id,
                request_payload={"session_id": session.session_id},
                response_payload={"error": str(exc)},
                duration_ms=duration_ms,
            )
            raise WhatsAppSessionServiceError(str(exc)) from exc

    def get_qr(self, line: PhoneLine, *, correlation_id: str = "") -> WhatsAppSessionResult:
        session = self._require_session(line)
        client = self._get_client(session)
        started_at = time.monotonic()

        try:
            qr_payload = client.get_qr(session.session_id)
            duration_ms = self._elapsed_ms(started_at)
            now = timezone.now()
            has_qr = bool(qr_payload.get("has_qr") and qr_payload.get("qr_code"))
            connected = bool(qr_payload.get("connected"))
            qr_code = qr_payload.get("qr_code")
            qr_expires_at = self._resolve_qr_expires_at(
                qr_payload.get("qr_expires"),
                now=now,
            )
            with transaction.atomic():
                self.state_machine.apply_remote_snapshot(
                    session,
                    connected=connected,
                    has_qr=has_qr,
                    qr_code=qr_code,
                    qr_expires_at=qr_expires_at,
                    occurred_at=now,
                    requested_status=WhatsAppSessionStatus.SESSION_REQUESTED,
                )
                result = self._build_result_from_remote_payload(
                    session,
                    remote_payload=qr_payload.get("raw", {}),
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
                        correlation_id=correlation_id,
                        request_payload={"session_id": session.session_id},
                        response_payload=qr_payload,
                        duration_ms=duration_ms,
                    )
            result.correlation_id = correlation_id
            return result
        except MeowClientNotFoundError as exc:
            duration_ms = self._elapsed_ms(started_at)
            with transaction.atomic():
                self.state_machine.mark_disconnected(session)
                result = self._build_local_result(
                    session,
                    detail="Sessao ausente no Meow; QR local invalidado.",
                )
                WhatsAppAuditService.success(
                    session=session,
                    action=WhatsAppActionType.GET_QR,
                    correlation_id=correlation_id,
                    request_payload={"session_id": session.session_id},
                    response_payload={
                        "detail": "Sessao nao encontrada no Meow.",
                        "converged": True,
                    },
                    duration_ms=duration_ms,
                )
            result.correlation_id = correlation_id
            return result
        except MeowClientError as exc:
            duration_ms = self._elapsed_ms(started_at)
            self.state_machine.mark_failed(session, error_message=str(exc))
            WhatsAppAuditService.failure(
                session=session,
                action=WhatsAppActionType.GET_QR,
                correlation_id=correlation_id,
                request_payload={"session_id": session.session_id},
                response_payload={"error": str(exc)},
                duration_ms=duration_ms,
            )
            raise WhatsAppSessionServiceError(str(exc)) from exc

    def disconnect(
        self,
        line: PhoneLine,
        *,
        correlation_id: str = "",
    ) -> WhatsAppSessionResult:
        session = self._require_session(line)
        client = self._get_client(session)
        started_at = time.monotonic()

        try:
            remote_payload = client.disconnect_session(session.session_id)
            duration_ms = self._elapsed_ms(started_at)
            with transaction.atomic():
                self.state_machine.mark_disconnected(session)
                result = WhatsAppSessionResult(
                    session=session,
                    status=session.status,
                    remote_payload=remote_payload,
                    connected=False,
                )
                WhatsAppAuditService.success(
                    session=session,
                    action=WhatsAppActionType.DELETE_SESSION,
                    correlation_id=correlation_id,
                    request_payload={"session_id": session.session_id},
                    response_payload=remote_payload,
                    duration_ms=duration_ms,
                )
            result.correlation_id = correlation_id
            return result
        except MeowClientNotFoundError as exc:
            duration_ms = self._elapsed_ms(started_at)
            with transaction.atomic():
                self.state_machine.mark_disconnected(session)
                result = self._build_local_result(
                    session,
                    detail="Sessao ausente no Meow; desconexao convergiu localmente.",
                )
                WhatsAppAuditService.success(
                    session=session,
                    action=WhatsAppActionType.DELETE_SESSION,
                    correlation_id=correlation_id,
                    request_payload={"session_id": session.session_id},
                    response_payload={
                        "detail": "Sessao nao encontrada no Meow.",
                        "converged": True,
                    },
                    duration_ms=duration_ms,
                )
            result.correlation_id = correlation_id
            return result
        except MeowClientError as exc:
            duration_ms = self._elapsed_ms(started_at)
            self.state_machine.mark_failed(session, error_message=str(exc))
            WhatsAppAuditService.failure(
                session=session,
                action=WhatsAppActionType.DELETE_SESSION,
                correlation_id=correlation_id,
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

    def _record_local_action(
        self,
        *,
        session: WhatsAppSession,
        action: str,
        detail: str,
        created_by=None,
        correlation_id: str = "",
        job=None,
        job_created: bool | None = None,
        response_payload: dict | None = None,
    ) -> None:
        payload = response_payload or {
            "source": "local_request",
            "detail": detail,
        }
        if job is not None:
            payload = {
                **payload,
                "job_id": job.pk,
                "job_type": job.job_type,
                "job_status": job.status,
                "job_created": job_created,
            }
        WhatsAppAuditService.success(
            session=session,
            action=action,
            correlation_id=correlation_id,
            request_payload={"session_id": session.session_id},
            response_payload=payload,
            created_by=created_by,
        )
        if correlation_id:
            emit_integration_log(
                "whatsapp.local.request.accepted",
                correlation_id=correlation_id,
                session_id=session.session_id,
                session_pk=session.pk,
                action=action,
                detail=detail,
                job_id=job.pk if job is not None else None,
                job_created=job_created,
            )

    def _build_local_result(
        self,
        session: WhatsAppSession,
        *,
        detail: str | None = None,
        correlation_id: str = "",
        job=None,
        job_created: bool | None = None,
        session_created: bool | None = None,
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
            correlation_id=correlation_id,
            job_id=job.pk if job is not None else None,
            job_status=job.status if job is not None else None,
            job_created=job_created,
            job_available_at=job.available_at if job is not None else None,
            session_created=session_created,
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
        self.state_machine.apply_remote_snapshot(
            session,
            connected=connected,
            has_qr=has_qr,
            qr_code=qr_code,
            qr_expires_at=qr_expires_at,
            occurred_at=now,
            requested_status=default_status,
        )
        return self._build_result_from_remote_payload(
            session,
            remote_payload=remote_payload,
        )

    def _build_result_from_remote_payload(
        self,
        session: WhatsAppSession,
        *,
        remote_payload: dict,
    ) -> WhatsAppSessionResult:
        qr_code = self._get_valid_qr_code(session)
        return WhatsAppSessionResult(
            session=session,
            status=session.status,
            remote_payload=remote_payload,
            qr_code=qr_code,
            has_qr=bool(qr_code),
            connected=session.status == WhatsAppSessionStatus.CONNECTED,
        )
