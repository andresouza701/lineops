from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from whatsapp.choices import WhatsAppActionType
from whatsapp.models import WhatsAppSession
from whatsapp.services.audit_service import WhatsAppAuditService
from whatsapp.services.state_machine_service import WhatsAppSessionStateMachineService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MeowWebhookProcessResult:
    status_code: int
    body: dict[str, Any]


class MeowWebhookService:
    STATEFUL_EVENTS = {
        "connection_success",
        "connection_closed",
        "qr_code",
        "reconnection_attempt",
        "connection_permanently_failed",
        "manual_intervention_required",
        "temporary_ban_detected",
        "ban_cooldown_ended",
    }
    ACCEPTED_NO_STATE_CHANGE_EVENTS = {
        "message",
        "message_status_update",
        "user-event",
    }
    SUPPORTED_EVENTS = STATEFUL_EVENTS | ACCEPTED_NO_STATE_CHANGE_EVENTS

    def __init__(self):
        self.state_machine = WhatsAppSessionStateMachineService()

    def process_event(
        self,
        payload: dict[str, Any],
        *,
        event_type_header: str | None = None,
    ) -> MeowWebhookProcessResult:
        event_type = self._resolve_event_type(
            payload=payload,
            event_type_header=event_type_header,
        )
        if not event_type:
            return MeowWebhookProcessResult(
                status_code=400,
                body={"detail": "Campo type ausente no payload."},
            )

        event_payload = self._unwrap_payload(payload)
        session_identifier = self._extract_session_identifier(
            payload=payload,
            event_payload=event_payload,
        )
        if event_type not in self.SUPPORTED_EVENTS:
            logger.info(
                "Evento do Meow aceito sem processamento por tipo desconhecido.",
                extra={"event_type": event_type},
            )
            return self._accepted_without_processing(
                event_type=event_type,
                session_identifier=session_identifier,
                reason="unsupported_event_type",
            )

        if not session_identifier:
            logger.warning(
                "Evento do Meow recebido sem sessionId utilizavel.",
                extra={"event_type": event_type},
            )
            return self._accepted_without_processing(
                event_type=event_type,
                session_identifier=None,
                reason="missing_session_identifier",
            )

        session = self._find_session(session_identifier)
        if session is None:
            logger.warning(
                "Sessao local nao encontrada para o evento do Meow.",
                extra={
                    "event_type": event_type,
                    "session_identifier": session_identifier,
                },
            )
            return self._accepted_without_processing(
                event_type=event_type,
                session_identifier=session_identifier,
                reason="session_not_found",
            )

        if event_type in self.ACCEPTED_NO_STATE_CHANGE_EVENTS:
            with transaction.atomic():
                self._audit_event(
                    session=session,
                    payload=payload,
                    event_type=event_type,
                    processed=False,
                    detail="accepted_without_state_change",
                )
            return MeowWebhookProcessResult(
                status_code=202,
                body={
                    "accepted": True,
                    "processed": False,
                    "event_type": event_type,
                    "session_id": session.session_id,
                    "line_id": session.line_id,
                    "reason": "accepted_without_state_change",
                },
            )

        with transaction.atomic():
            self._apply_stateful_event(
                session=session,
                payload=payload,
                event_type=event_type,
                event_payload=event_payload,
            )
            self._audit_event(
                session=session,
                payload=payload,
                event_type=event_type,
                processed=True,
                detail="session_updated",
            )
        return MeowWebhookProcessResult(
            status_code=200,
            body={
                "accepted": True,
                "processed": True,
                "event_type": event_type,
                "session_id": session.session_id,
                "line_id": session.line_id,
                "status": session.status,
            },
        )

    def _resolve_event_type(
        self,
        *,
        payload: dict[str, Any],
        event_type_header: str | None,
    ) -> str:
        payload_type = str(payload.get("type") or "").strip()
        header_type = str(event_type_header or "").strip()
        if payload_type and header_type and payload_type != header_type:
            logger.warning(
                "Payload do Meow com divergencia entre type e X-Event-Type.",
                extra={
                    "payload_type": payload_type,
                    "header_type": header_type,
                },
            )
        return payload_type or header_type

    def _unwrap_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        wrapped_payload = payload.get("payload")
        if isinstance(wrapped_payload, dict):
            return wrapped_payload
        return payload

    def _extract_session_identifier(
        self,
        *,
        payload: dict[str, Any],
        event_payload: dict[str, Any],
    ) -> str | None:
        raw_identifier = event_payload.get("sessionId") or payload.get("sessionId")
        if raw_identifier is None:
            return None
        normalized = str(raw_identifier).strip()
        return normalized or None

    def _find_session(self, session_identifier: str) -> WhatsAppSession | None:
        session_candidates, phone_candidates = self._build_lookup_candidates(
            session_identifier
        )
        queryset = WhatsAppSession.objects.select_related("line", "meow_instance")
        filters = Q(session_id__in=session_candidates)
        if phone_candidates:
            filters |= Q(line__phone_number__in=phone_candidates)
        return queryset.filter(filters).order_by("pk").first()

    def _build_lookup_candidates(
        self, session_identifier: str
    ) -> tuple[set[str], set[str]]:
        raw_identifier = str(session_identifier).strip()
        session_candidates = {raw_identifier}
        phone_candidates: set[str] = set()

        without_prefix = (
            raw_identifier.removeprefix("session_")
            if raw_identifier.startswith("session_")
            else raw_identifier
        )
        if without_prefix:
            phone_candidates.add(without_prefix)
            session_candidates.add(f"session_{without_prefix}")

        digits_only = "".join(ch for ch in without_prefix if ch.isdigit())
        if digits_only:
            phone_candidates.add(digits_only)
            phone_candidates.add(f"+{digits_only}")
            session_candidates.add(f"session_{digits_only}")
            session_candidates.add(f"session_+{digits_only}")

        phone_candidates = {
            candidate
            for candidate in phone_candidates
            if candidate and not candidate.startswith("session_")
        }
        return session_candidates, phone_candidates

    def _apply_stateful_event(
        self,
        *,
        session: WhatsAppSession,
        payload: dict[str, Any],
        event_type: str,
        event_payload: dict[str, Any],
    ) -> None:
        received_at = timezone.now()
        event_time = self._coerce_event_time(
            event_payload.get("timestamp") or payload.get("timestamp")
        )
        qr_code = (
            event_payload.get("qr_code")
            or event_payload.get("qrCode")
            or payload.get("qr_code")
            or payload.get("qrCode")
        )

        if event_type == "connection_success":
            self.state_machine.mark_connected(session, occurred_at=event_time)
        elif event_type == "qr_code":
            self.state_machine.mark_qr_available(
                session,
                qr_code=str(qr_code or ""),
                occurred_at=event_time,
            )
        elif event_type == "reconnection_attempt":
            self.state_machine.mark_session_requested(
                session,
                occurred_at=received_at,
            )
        elif event_type in {"connection_closed", "ban_cooldown_ended"}:
            self.state_machine.mark_disconnected(
                session,
                detail=self._build_error_detail(
                    event_type=event_type,
                    event_payload=event_payload,
                ),
                occurred_at=received_at,
            )
        else:
            self.state_machine.mark_failed(
                session,
                error_message=self._build_error_detail(
                    event_type=event_type,
                    event_payload=event_payload,
                ),
                occurred_at=received_at,
            )

    def _build_error_detail(
        self, *, event_type: str, event_payload: dict[str, Any]
    ) -> str:
        disconnection_reason = event_payload.get("disconnectionReason")
        if isinstance(disconnection_reason, dict):
            message = str(disconnection_reason.get("message") or "").strip()
            code = disconnection_reason.get("code")
            if message and code is not None:
                return f"{event_type}: {message} (code={code})"
            if message:
                return f"{event_type}: {message}"
            if code is not None:
                return f"{event_type}: code={code}"

        detail_fields = [
            event_payload.get("message"),
            event_payload.get("detail"),
            event_payload.get("reason"),
        ]
        for detail in detail_fields:
            normalized = str(detail or "").strip()
            if normalized:
                return f"{event_type}: {normalized}"
        return event_type

    def _coerce_event_time(self, raw_timestamp: Any):
        if raw_timestamp in (None, ""):
            return timezone.now()
        try:
            timestamp_value = int(raw_timestamp)
        except (TypeError, ValueError):
            return timezone.now()

        if timestamp_value > 10_000_000_000:
            timestamp_value = timestamp_value / 1000
        return datetime.fromtimestamp(
            timestamp_value,
            tz=timezone.get_current_timezone(),
        )

    def _audit_event(
        self,
        *,
        session: WhatsAppSession,
        payload: dict[str, Any],
        event_type: str,
        processed: bool,
        detail: str,
    ) -> None:
        WhatsAppAuditService.success(
            session=session,
            action=WhatsAppActionType.WEBHOOK_EVENT,
            request_payload=payload,
            response_payload={
                "event_type": event_type,
                "processed": processed,
                "detail": detail,
            },
        )

    def _accepted_without_processing(
        self,
        *,
        event_type: str,
        session_identifier: str | None,
        reason: str,
    ) -> MeowWebhookProcessResult:
        return MeowWebhookProcessResult(
            status_code=202,
            body={
                "accepted": True,
                "processed": False,
                "event_type": event_type,
                "session_identifier": session_identifier,
                "reason": reason,
            },
        )
