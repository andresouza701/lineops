from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from telecom.models import PhoneLine
from whatsapp.choices import (
    WhatsAppActionType,
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
        session = self._get_existing_session(line)
        if session:
            return session

        meow_instance = InstanceSelectorService.select_available_instance()
        return WhatsAppSession.objects.create(
            line=line,
            meow_instance=meow_instance,
            session_id=self.build_session_id(line),
            status=WhatsAppSessionStatus.PENDING_NEW_NUMBER,
            is_active=True,
        )

    def connect(self, line: PhoneLine) -> WhatsAppSessionResult:
        session = self.get_or_create_session(line)
        client = self._get_client(session)
        request_payload = {"session_id": session.session_id}
        audit_action = WhatsAppActionType.CREATE_SESSION

        self._mark_connecting(session)

        try:
            try:
                remote_payload = client.create_session(session.session_id)
            except MeowClientConflictError:
                audit_action = WhatsAppActionType.CONNECT_SESSION
                remote_payload = client.connect_session(session.session_id)
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
                )
            return result
        except MeowClientNotFoundError as exc:
            self._mark_error(session, str(exc))
            WhatsAppAuditService.failure(
                session=session,
                action=audit_action,
                request_payload=request_payload,
                response_payload={"error": str(exc)},
            )
            raise WhatsAppSessionServiceError(str(exc)) from exc
        except MeowClientError as exc:
            self._mark_error(session, str(exc))
            WhatsAppAuditService.failure(
                session=session,
                action=audit_action,
                request_payload=request_payload,
                response_payload={"error": str(exc)},
            )
            raise WhatsAppSessionServiceError(str(exc)) from exc

    def get_status(self, line: PhoneLine) -> WhatsAppSessionResult:
        session = self._require_session(line)
        client = self._get_client(session)

        try:
            request_payload = {"session_id": session.session_id}
            remote_payload = client.get_session(session.session_id)
            with transaction.atomic():
                result = self._sync_from_remote(
                    session, remote_payload=remote_payload
                )
                WhatsAppAuditService.success(
                    session=session,
                    action=WhatsAppActionType.GET_SESSION,
                    request_payload=request_payload,
                    response_payload=remote_payload,
                )
            return result
        except MeowClientNotFoundError as exc:
            session.status = WhatsAppSessionStatus.DISCONNECTED
            WhatsAppAuditService.failure(
                session=session,
                action=WhatsAppActionType.GET_SESSION,
                request_payload={"session_id": session.session_id},
                response_payload={"error": "Sessao nao encontrada no Meow."},
            )

            session.last_error = "Sessao nao encontrada no Meow."
            session.last_sync_at = timezone.now()
            session.save(
                update_fields=[
                    "status",
                    "last_error",
                    "last_sync_at",
                    "updated_at",
                ]
            )
            raise WhatsAppSessionServiceError(str(exc)) from exc
        except MeowClientError as exc:
            self._mark_error(session, str(exc))
            WhatsAppAuditService.failure(
                session=session,
                action=WhatsAppActionType.GET_SESSION,
                request_payload={"session_id": session.session_id},
                response_payload={"error": str(exc)},
            )
            raise WhatsAppSessionServiceError(str(exc)) from exc

    def get_qr(self, line: PhoneLine) -> WhatsAppSessionResult:
        session = self._require_session(line)
        client = self._get_client(session)

        try:
            qr_payload = client.get_qr(session.session_id)
            now = timezone.now()
            has_qr = bool(qr_payload.get("qr_code"))
            connected = bool(qr_payload.get("connected"))
            qr_code = qr_payload.get("qr_code")

            if connected:
                session.status = WhatsAppSessionStatus.CONNECTED
                session.connected_at = session.connected_at or now
            elif has_qr:
                session.status = WhatsAppSessionStatus.QR_PENDING
                session.qr_last_generated_at = now
            else:
                session.status = WhatsAppSessionStatus.CONNECTING

            session.last_error = ""
            session.last_sync_at = now
            with transaction.atomic():
                session.save(
                    update_fields=[
                        "status",
                        "connected_at",
                        "qr_last_generated_at",
                        "last_error",
                        "last_sync_at",
                        "updated_at",
                    ]
                )
                result = WhatsAppSessionResult(
                    session=session,
                    status=session.status,
                    remote_payload=qr_payload.get("raw", {}),
                    qr_code=qr_code,
                    has_qr=has_qr,
                    connected=connected,
                )
                WhatsAppAuditService.success(
                    session=session,
                    action=WhatsAppActionType.GET_QR,
                    request_payload={"session_id": session.session_id},
                    response_payload=qr_payload,
                )
            return result
        except MeowClientNotFoundError as exc:
            self._mark_error(session, str(exc))
            WhatsAppAuditService.failure(
                session=session,
                action=WhatsAppActionType.GET_QR,
                request_payload={"session_id": session.session_id},
                response_payload={"error": str(exc)},
            )

            raise WhatsAppSessionServiceError(str(exc)) from exc
        except MeowClientError as exc:
            self._mark_error(session, str(exc))
            WhatsAppAuditService.failure(
                session=session,
                action=WhatsAppActionType.GET_QR,
                request_payload={"session_id": session.session_id},
                response_payload={"error": str(exc)},
            )
            raise WhatsAppSessionServiceError(str(exc)) from exc

    def disconnect(self, line: PhoneLine) -> WhatsAppSessionResult:
        session = self._require_session(line)
        client = self._get_client(session)

        try:
            remote_payload = client.delete_session(session.session_id)
            session.status = WhatsAppSessionStatus.DISCONNECTED
            session.last_error = ""
            session.last_sync_at = timezone.now()
            with transaction.atomic():
                session.save(
                    update_fields=[
                        "status",
                        "last_error",
                        "last_sync_at",
                        "updated_at",
                    ]
                )
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
                )
            return result
        except MeowClientNotFoundError as exc:
            self._mark_error(session, str(exc))
            WhatsAppAuditService.failure(
                session=session,
                action=WhatsAppActionType.DELETE_SESSION,
                request_payload={"session_id": session.session_id},
                response_payload={"error": str(exc)},
            )
            raise WhatsAppSessionServiceError(str(exc)) from exc
        except MeowClientError as exc:
            self._mark_error(session, str(exc))
            WhatsAppAuditService.failure(
                session=session,
                action=WhatsAppActionType.DELETE_SESSION,
                request_payload={"session_id": session.session_id},
                response_payload={"error": str(exc)},
            )
            raise WhatsAppSessionServiceError(str(exc)) from exc

    def _require_session(self, line: PhoneLine) -> WhatsAppSession:
        session = self._get_existing_session(line)
        if session:
            return session

        raise WhatsAppSessionNotConfiguredError(
            f"Linha {line.phone_number} ainda nao possui sessao WhatsApp."
        )

    def _get_client(self, session: WhatsAppSession) -> MeowClient:
        if not session.meow_instance:
            raise WhatsAppSessionServiceError(
                f"Sessao {session.session_id} nao possui instancia Meow."
            )
        return MeowClient(session.meow_instance.base_url)

    def _mark_connecting(self, session: WhatsAppSession) -> None:
        session.status = WhatsAppSessionStatus.CONNECTING
        session.last_error = ""
        session.last_sync_at = timezone.now()
        session.save(
            update_fields=[
                "status",
                "last_error",
                "updated_at",
                "last_sync_at",
            ]
        )

    def _mark_error(
        self, session: WhatsAppSession, error_message: str
    ) -> None:  # noqa: E501
        session.status = WhatsAppSessionStatus.ERROR
        session.last_error = error_message
        session.last_sync_at = timezone.now()
        session.save(
            update_fields=[
                "status",
                "last_error",
                "last_sync_at",
                "updated_at",
            ]  # noqa: E501
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

        if connected:
            session.status = WhatsAppSessionStatus.CONNECTED
            session.connected_at = session.connected_at or now
        elif has_qr:
            session.status = WhatsAppSessionStatus.QR_PENDING
            session.qr_last_generated_at = now
        else:
            session.status = (
                default_status or WhatsAppSessionStatus.DISCONNECTED
            )  # noqa: E501

        session.last_error = ""
        session.last_sync_at = now
        session.save(
            update_fields=[
                "status",
                "connected_at",
                "qr_last_generated_at",
                "last_error",
                "last_sync_at",
                "updated_at",
            ]  # noqa: E501
        )
        return WhatsAppSessionResult(
            session=session,
            status=session.status,
            remote_payload=remote_payload,
            qr_code=qr_code,
            has_qr=has_qr,
            connected=connected,
        )
