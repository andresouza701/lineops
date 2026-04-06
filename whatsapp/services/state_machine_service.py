from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from whatsapp.choices import WhatsAppSessionStatus
from whatsapp.models import WhatsAppSession


class InvalidWhatsAppSessionTransition(ValueError):
    """Raised when a WhatsApp session transition is not allowed."""


class WhatsAppSessionStateMachineService:
    _UNSET = object()
    ALLOWED_TRANSITIONS = {
        WhatsAppSessionStatus.NEW: {
            WhatsAppSessionStatus.NEW,
            WhatsAppSessionStatus.SESSION_REQUESTED,
            WhatsAppSessionStatus.QR_AVAILABLE,
            WhatsAppSessionStatus.WAITING_SCAN,
            WhatsAppSessionStatus.CONNECTED,
            WhatsAppSessionStatus.DISCONNECTED,
            WhatsAppSessionStatus.FAILED,
        },
        WhatsAppSessionStatus.SESSION_REQUESTED: {
            WhatsAppSessionStatus.SESSION_REQUESTED,
            WhatsAppSessionStatus.QR_AVAILABLE,
            WhatsAppSessionStatus.WAITING_SCAN,
            WhatsAppSessionStatus.CONNECTED,
            WhatsAppSessionStatus.DISCONNECTED,
            WhatsAppSessionStatus.FAILED,
        },
        WhatsAppSessionStatus.QR_AVAILABLE: {
            WhatsAppSessionStatus.QR_AVAILABLE,
            WhatsAppSessionStatus.WAITING_SCAN,
            WhatsAppSessionStatus.CONNECTED,
            WhatsAppSessionStatus.EXPIRED,
            WhatsAppSessionStatus.DISCONNECTED,
            WhatsAppSessionStatus.FAILED,
        },
        WhatsAppSessionStatus.WAITING_SCAN: {
            WhatsAppSessionStatus.WAITING_SCAN,
            WhatsAppSessionStatus.QR_AVAILABLE,
            WhatsAppSessionStatus.CONNECTED,
            WhatsAppSessionStatus.EXPIRED,
            WhatsAppSessionStatus.DISCONNECTED,
            WhatsAppSessionStatus.FAILED,
        },
        WhatsAppSessionStatus.CONNECTED: {
            WhatsAppSessionStatus.CONNECTED,
            WhatsAppSessionStatus.DISCONNECTED,
            WhatsAppSessionStatus.FAILED,
        },
        WhatsAppSessionStatus.FAILED: {
            WhatsAppSessionStatus.FAILED,
            WhatsAppSessionStatus.NEW,
            WhatsAppSessionStatus.SESSION_REQUESTED,
            WhatsAppSessionStatus.QR_AVAILABLE,
            WhatsAppSessionStatus.WAITING_SCAN,
            WhatsAppSessionStatus.CONNECTED,
            WhatsAppSessionStatus.DISCONNECTED,
        },
        WhatsAppSessionStatus.EXPIRED: {
            WhatsAppSessionStatus.EXPIRED,
            WhatsAppSessionStatus.NEW,
            WhatsAppSessionStatus.SESSION_REQUESTED,
            WhatsAppSessionStatus.QR_AVAILABLE,
            WhatsAppSessionStatus.WAITING_SCAN,
            WhatsAppSessionStatus.CONNECTED,
            WhatsAppSessionStatus.DISCONNECTED,
            WhatsAppSessionStatus.FAILED,
        },
        WhatsAppSessionStatus.DISCONNECTED: {
            WhatsAppSessionStatus.DISCONNECTED,
            WhatsAppSessionStatus.NEW,
            WhatsAppSessionStatus.SESSION_REQUESTED,
            WhatsAppSessionStatus.QR_AVAILABLE,
            WhatsAppSessionStatus.WAITING_SCAN,
            WhatsAppSessionStatus.CONNECTED,
            WhatsAppSessionStatus.FAILED,
        },
    }

    def mark_new(self, session: WhatsAppSession, *, occurred_at=None) -> WhatsAppSession:
        return self.transition(
            session,
            WhatsAppSessionStatus.NEW,
            occurred_at=occurred_at,
            last_error="",
            clear_qr=True,
        )

    def mark_session_requested(
        self,
        session: WhatsAppSession,
        *,
        occurred_at=None,
    ) -> WhatsAppSession:
        return self.transition(
            session,
            WhatsAppSessionStatus.SESSION_REQUESTED,
            occurred_at=occurred_at,
            last_error="",
            clear_qr=True,
        )

    def mark_qr_available(
        self,
        session: WhatsAppSession,
        *,
        qr_code: str,
        qr_expires_at=None,
        occurred_at=None,
    ) -> WhatsAppSession:
        normalized_qr_code = str(qr_code or "").strip()
        if not normalized_qr_code:
            raise ValueError("QR code nao pode ser vazio para QR_AVAILABLE.")
        occurred_at = occurred_at or timezone.now()
        qr_expires_at = qr_expires_at or self._build_fallback_qr_expiration(
            occurred_at
        )
        return self.transition(
            session,
            WhatsAppSessionStatus.QR_AVAILABLE,
            occurred_at=occurred_at,
            qr_code=normalized_qr_code,
            qr_generated_at=occurred_at,
            qr_expires_at=qr_expires_at,
            last_error="",
        )

    def mark_waiting_scan(
        self,
        session: WhatsAppSession,
        *,
        qr_code: str | None = None,
        qr_expires_at=None,
        occurred_at=None,
    ) -> WhatsAppSession:
        occurred_at = occurred_at or timezone.now()
        next_qr_code = qr_code if qr_code is not None else session.qr_code
        next_qr_expires_at = (
            qr_expires_at
            if qr_expires_at is not None
            else session.qr_expires_at or self._build_fallback_qr_expiration(occurred_at)
        )
        return self.transition(
            session,
            WhatsAppSessionStatus.WAITING_SCAN,
            occurred_at=occurred_at,
            qr_code=next_qr_code or "",
            qr_expires_at=next_qr_expires_at,
            last_error="",
        )

    def mark_connected(
        self,
        session: WhatsAppSession,
        *,
        occurred_at=None,
    ) -> WhatsAppSession:
        occurred_at = occurred_at or timezone.now()
        return self.transition(
            session,
            WhatsAppSessionStatus.CONNECTED,
            occurred_at=occurred_at,
            connected_at=session.connected_at or occurred_at,
            last_error="",
            clear_qr=True,
        )

    def mark_failed(
        self,
        session: WhatsAppSession,
        *,
        error_message: str,
        occurred_at=None,
    ) -> WhatsAppSession:
        return self.transition(
            session,
            WhatsAppSessionStatus.FAILED,
            occurred_at=occurred_at,
            last_error=error_message,
            clear_qr=True,
        )

    def mark_expired(
        self,
        session: WhatsAppSession,
        *,
        detail: str = "QR expirado.",
        occurred_at=None,
    ) -> WhatsAppSession:
        return self.transition(
            session,
            WhatsAppSessionStatus.EXPIRED,
            occurred_at=occurred_at,
            last_error=detail,
            clear_qr=True,
            qr_expires_at=occurred_at or timezone.now(),
        )

    def mark_disconnected(
        self,
        session: WhatsAppSession,
        *,
        detail: str = "",
        occurred_at=None,
    ) -> WhatsAppSession:
        return self.transition(
            session,
            WhatsAppSessionStatus.DISCONNECTED,
            occurred_at=occurred_at,
            last_error=detail,
            clear_qr=True,
        )

    def touch(
        self,
        session: WhatsAppSession,
        *,
        occurred_at=None,
    ) -> WhatsAppSession:
        return self.transition(
            session,
            session.status,
            occurred_at=occurred_at,
            last_error=session.last_error,
        )

    def apply_remote_snapshot(
        self,
        session: WhatsAppSession,
        *,
        connected: bool,
        has_qr: bool,
        qr_code: str | None,
        qr_expires_at=None,
        occurred_at=None,
        requested_status: str | None = None,
    ) -> WhatsAppSession:
        occurred_at = occurred_at or timezone.now()
        if connected:
            return self.mark_connected(session, occurred_at=occurred_at)

        if has_qr and qr_code:
            if (
                session.status
                in {
                    WhatsAppSessionStatus.QR_AVAILABLE,
                    WhatsAppSessionStatus.WAITING_SCAN,
                }
                and session.qr_code == qr_code
                and self._is_qr_valid(session, now=occurred_at)
            ):
                return self.mark_waiting_scan(
                    session,
                    qr_code=qr_code,
                    qr_expires_at=qr_expires_at,
                    occurred_at=occurred_at,
                )

            return self.mark_qr_available(
                session,
                qr_code=qr_code,
                qr_expires_at=qr_expires_at,
                occurred_at=occurred_at,
            )

        if session.status in {
            WhatsAppSessionStatus.QR_AVAILABLE,
            WhatsAppSessionStatus.WAITING_SCAN,
        }:
            return self.mark_expired(session, occurred_at=occurred_at)

        if session.status == WhatsAppSessionStatus.CONNECTED:
            return self.mark_disconnected(session, occurred_at=occurred_at)

        if requested_status:
            return self.transition(
                session,
                requested_status,
                occurred_at=occurred_at,
                last_error="",
                clear_qr=requested_status == WhatsAppSessionStatus.SESSION_REQUESTED,
            )

        return self.touch(session, occurred_at=occurred_at)

    def transition(
        self,
        session: WhatsAppSession,
        target_status: str,
        *,
        occurred_at=None,
        connected_at=None,
        qr_code=_UNSET,
        qr_generated_at=_UNSET,
        qr_expires_at=_UNSET,
        last_error=_UNSET,
        clear_qr: bool = False,
    ) -> WhatsAppSession:
        occurred_at = occurred_at or timezone.now()
        current_status = session.status or WhatsAppSessionStatus.NEW
        allowed_targets = self.ALLOWED_TRANSITIONS.get(current_status, set())
        if target_status not in allowed_targets:
            raise InvalidWhatsAppSessionTransition(
                f"Transicao invalida de {current_status} para {target_status}."
            )

        update_fields = ["status", "last_sync_at", "version", "updated_at"]
        session.status = target_status
        session.last_sync_at = occurred_at

        if connected_at is not None:
            session.connected_at = connected_at
            update_fields.append("connected_at")

        if clear_qr:
            session.qr_code = ""
            session.qr_expires_at = None
            update_fields.extend(["qr_code", "qr_expires_at"])

        if qr_code is not self._UNSET:
            session.qr_code = qr_code or ""
            update_fields.append("qr_code")
        if qr_generated_at is not self._UNSET:
            session.qr_last_generated_at = qr_generated_at
            update_fields.append("qr_last_generated_at")
        if qr_expires_at is not self._UNSET:
            session.qr_expires_at = qr_expires_at
            update_fields.append("qr_expires_at")
        if last_error is not self._UNSET:
            session.last_error = last_error
            update_fields.append("last_error")

        session.version += 1
        session.save(update_fields=list(dict.fromkeys(update_fields)))
        return session

    def _is_qr_valid(self, session: WhatsAppSession, *, now) -> bool:
        return not session.qr_expires_at or session.qr_expires_at > now

    def _build_fallback_qr_expiration(self, base_time):
        return base_time + timedelta(
            seconds=int(getattr(settings, "WHATSAPP_LOCAL_QR_TTL_SECONDS", 60))
        )
