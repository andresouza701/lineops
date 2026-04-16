from __future__ import annotations

from django.utils import timezone


class WhatsappReconnectHistoryService:
    """Cria e fecha entradas de histórico de reconexão WhatsApp."""

    @staticmethod
    def open(*, phone_line, session_id: str, started_by) -> "WhatsappReconnectHistory":
        """Registra o início de uma sessão. Idempotente: get_or_create por session_id."""
        from telecom.models import WhatsappReconnectHistory

        entry, _ = WhatsappReconnectHistory.objects.get_or_create(
            session_id=session_id,
            defaults={
                "phone_line": phone_line,
                "started_by": started_by,
            },
        )
        return entry

    @staticmethod
    def close(
        *,
        session_id: str,
        outcome: str,
        error_code: str = "",
        error_message: str = "",
        attempt_count: int = 0,
    ) -> None:
        """
        Fecha a entrada de histórico com o resultado terminal.

        Filtra por outcome__isnull=True para garantir idempotência:
        chamadas repetidas não sobrescrevem um resultado já registrado.
        """
        from telecom.models import WhatsappReconnectHistory

        WhatsappReconnectHistory.objects.filter(
            session_id=session_id,
            outcome__isnull=True,
        ).update(
            outcome=outcome,
            error_code=error_code or "",
            error_message=error_message or "",
            attempt_count=attempt_count,
            finished_at=timezone.now(),
        )
