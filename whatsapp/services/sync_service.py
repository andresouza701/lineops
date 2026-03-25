from __future__ import annotations

from dataclasses import dataclass

from django.db.models import QuerySet

from whatsapp.models import WhatsAppSession
from whatsapp.services.session_service import (
    WhatsAppSessionService,
    WhatsAppSessionServiceError,
)


@dataclass
class WhatsAppSessionSyncResult:
    session: WhatsAppSession
    success: bool
    status: str
    detail: str


class WhatsAppSessionSyncService:
    def __init__(self, session_service: WhatsAppSessionService | None = None):
        self.session_service = session_service or WhatsAppSessionService()

    def sync_sessions(
        self,
        *,
        queryset: QuerySet | None = None,
        include_inactive: bool = False,
    ) -> list[WhatsAppSessionSyncResult]:
        queryset = queryset if queryset is not None else WhatsAppSession.objects.all()
        if not include_inactive:
            queryset = queryset.filter(is_active=True)

        results = []
        for session in queryset.select_related("line", "meow_instance").order_by(
            "session_id"
        ):
            try:
                result = self.session_service.get_status(session.line)
                results.append(
                    WhatsAppSessionSyncResult(
                        session=result.session,
                        success=True,
                        status=result.status,
                        detail="Sessao sincronizada com sucesso.",
                    )
                )
            except WhatsAppSessionServiceError as exc:
                session.refresh_from_db()
                results.append(
                    WhatsAppSessionSyncResult(
                        session=session,
                        success=False,
                        status=session.status,
                        detail=str(exc),
                    )
                )
        return results
