from __future__ import annotations

from typing import Any

from whatsapp.choices import WhatsAppActionStatus
from whatsapp.models import MeowInstance, WhatsAppActionAudit, WhatsAppSession


class WhatsAppAuditService:
    @staticmethod
    def record(  # noqa: PLR0913
        *,
        session: WhatsAppSession | None = None,
        meow_instance: MeowInstance | None = None,
        action: str,
        status: str,
        request_payload: dict[str, Any] | None = None,
        response_payload: dict[str, Any] | None = None,
        duration_ms: int | None = None,
        created_by: None = None,
    ) -> WhatsAppActionAudit:
        """Records a WhatsApp action audit entry."""
        if session is None and meow_instance is None:
            raise ValueError(
                "WhatsApp audit requires a session or Meow instance context."
            )
        if session is not None and meow_instance is None:
            meow_instance = session.meow_instance
        if (
            session is not None
            and meow_instance is not None
            and session.meow_instance_id != meow_instance.pk
        ):
            raise ValueError(
                "WhatsApp audit session and Meow instance must match."
            )
        return WhatsAppActionAudit.objects.create(
            session=session,
            meow_instance=meow_instance,
            action=action,
            status=status,
            request_payload=request_payload,
            response_payload=response_payload,
            duration_ms=duration_ms,
            created_by=created_by,
        )

    @staticmethod
    def success(
        *,
        session: WhatsAppSession | None = None,
        meow_instance: MeowInstance | None = None,
        action: str,
        request_payload: dict[str, Any] | None = None,
        response_payload: dict[str, Any] | None = None,
        duration_ms: int | None = None,
        created_by: None = None,
    ) -> WhatsAppActionAudit:
        """Records a successful WhatsApp action audit entry."""
        return WhatsAppAuditService.record(
            session=session,
            meow_instance=meow_instance,
            action=action,
            status=WhatsAppActionStatus.SUCCESS,
            request_payload=request_payload,
            response_payload=response_payload,
            duration_ms=duration_ms,
            created_by=created_by,
        )

    @staticmethod
    def failure(
        *,
        session: WhatsAppSession | None = None,
        meow_instance: MeowInstance | None = None,
        action: str,
        request_payload: dict[str, Any] | None = None,
        response_payload: dict[str, Any] | None = None,
        duration_ms: int | None = None,
        created_by: None = None,
    ) -> WhatsAppActionAudit:
        """Records a failed WhatsApp action audit entry."""
        return WhatsAppAuditService.record(
            session=session,
            meow_instance=meow_instance,
            action=action,
            status=WhatsAppActionStatus.FAILURE,
            request_payload=request_payload,
            response_payload=response_payload,
            duration_ms=duration_ms,
            created_by=created_by,
        )
