from __future__ import annotations

from typing import Any

from whatsapp.choices import WhatsAppActionStatus
from whatsapp.models import WhatsAppActionAudit, WhatsAppSession


class WhatsAppAuditService:
    @staticmethod
    def record(  # noqa: PLR0913
        *,
        session: WhatsAppSession,
        action: str,
        status: str,
        request_payload: dict[str, Any] | None = None,
        response_payload: dict[str, Any] | None = None,
        created_by: None = None,
    ) -> WhatsAppActionAudit:
        """Records a WhatsApp action audit entry."""
        return WhatsAppActionAudit.objects.create(
            session=session,
            action=action,
            status=status,
            request_payload=request_payload,
            response_payload=response_payload,
            created_by=created_by,
        )

    @staticmethod
    def success(
        *,
        session: WhatsAppSession,
        action: str,
        request_payload: dict[str, Any] | None = None,
        response_payload: dict[str, Any] | None = None,
        created_by: None = None,
    ) -> WhatsAppActionAudit:
        """Records a successful WhatsApp action audit entry."""
        return WhatsAppAuditService.record(
            session=session,
            action=action,
            status=WhatsAppActionStatus.SUCCESS,
            request_payload=request_payload,
            response_payload=response_payload,
            created_by=created_by,
        )

    @staticmethod
    def failure(
        *,
        session: WhatsAppSession,
        action: str,
        request_payload: dict[str, Any] | None = None,
        response_payload: dict[str, Any] | None = None,
        created_by: None = None,
    ) -> WhatsAppActionAudit:
        """Records a failed WhatsApp action audit entry."""
        return WhatsAppAuditService.record(
            session=session,
            action=action,
            status=WhatsAppActionStatus.FAILURE,
            request_payload=request_payload,
            response_payload=response_payload,
            created_by=created_by,
        )
