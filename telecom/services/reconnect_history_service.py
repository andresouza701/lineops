from __future__ import annotations

from django.utils import timezone

_TERMINAL_STATUSES = frozenset({"CONNECTED", "FAILED", "CANCELLED"})
_STATUS_ALIASES = {"SUCCESS": "CONNECTED", "SUCESS": "CONNECTED"}


def _normalize_mongo_status(raw) -> str:
    normalized = str(raw or "").strip().upper()
    return _STATUS_ALIASES.get(normalized, normalized)


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

    @staticmethod
    def reconcile_open_entries_for_line(*, phone_line, repository) -> None:
        """
        Reconcilia entradas abertas (outcome IS NULL) contra o repositório Mongo.

        Para cada entrada aberta:
        - Sessão Mongo terminal (CONNECTED/FAILED/CANCELLED) → fecha com o outcome correto.
        - Sessão Mongo não encontrada → fecha como CANCELLED com error_code='stale_session'.
        - Sessão Mongo ativa (não-terminal) → mantém como Em andamento.

        Qualquer exceção de get_session é tratada como "não encontrada".
        """
        from telecom.models import WhatsappReconnectHistory

        open_entries = list(
            WhatsappReconnectHistory.objects.filter(
                phone_line=phone_line,
                outcome__isnull=True,
            )
        )
        if not open_entries:
            return

        outcome_map = {
            "CONNECTED": WhatsappReconnectHistory.Outcome.CONNECTED,
            "FAILED": WhatsappReconnectHistory.Outcome.FAILED,
            "CANCELLED": WhatsappReconnectHistory.Outcome.CANCELLED,
        }

        for entry in open_entries:
            try:
                document = repository.get_session(entry.session_id)
            except Exception:
                document = None

            if document is None:
                WhatsappReconnectHistoryService.close(
                    session_id=entry.session_id,
                    outcome=WhatsappReconnectHistory.Outcome.CANCELLED,
                    error_code="stale_session",
                    error_message="Sessao nao encontrada no Mongo ao consultar historico.",
                    attempt_count=entry.attempt_count,
                )
                continue

            raw_status = _normalize_mongo_status(document.get("status"))
            if raw_status not in _TERMINAL_STATUSES:
                continue

            outcome = outcome_map.get(raw_status)
            if outcome:
                WhatsappReconnectHistoryService.close(
                    session_id=entry.session_id,
                    outcome=outcome,
                    error_code=document.get("error_code") or "",
                    error_message=document.get("error_message") or "",
                    attempt_count=document.get("attempt") or 0,
                )
