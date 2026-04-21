from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from django.utils import timezone

from core.exceptions.domain_exceptions import BusinessRuleException
from telecom.exceptions import ActiveReconnectSessionConflict
from telecom.models import PhoneLine

logger = logging.getLogger(__name__)

TERMINAL_RECONNECT_STATUSES = {"CONNECTED", "FAILED", "CANCELLED"}
WAITING_FOR_CODE_STATUS = "WAITING_FOR_CODE"
CANCEL_REQUESTED_STATUS = "CANCEL_REQUESTED"
STATUS_ALIASES = {
    "SUCCESS": "CONNECTED",
    "SUCESS": "CONNECTED",
}
ELIGIBLE_RECONNECT_ORIGENS = {
    PhoneLine.Origem.SRVMEMU_01,
    PhoneLine.Origem.SRVMEMU_02,
    PhoneLine.Origem.SRVMEMU_03,
    PhoneLine.Origem.SRVMEMU_04,
    PhoneLine.Origem.SRVMEMU_05,
    PhoneLine.Origem.SRVMEMU_06,
}

def _format_datetime(value: Any) -> Any:
    if isinstance(value, datetime):
        rendered = value.astimezone(UTC).isoformat()
        return rendered.replace("+00:00", "Z")
    return value


def _format_progress_history(progress_history: Any) -> list[dict[str, Any]]:
    if not isinstance(progress_history, list):
        return []

    normalized_history: list[dict[str, Any]] = []
    for item in progress_history:
        if not isinstance(item, dict):
            continue
        normalized_history.append(
            {
                "stage": item.get("stage"),
                "label": item.get("label"),
                "at": _format_datetime(item.get("at")),
            }
        )
    return normalized_history


def _normalize_status(value: Any) -> str:
    if value is None:
        return ""
    normalized = str(value).strip().upper()
    return STATUS_ALIASES.get(normalized, normalized)


def _parse_restriction_hms(value: Any) -> int | None:
    if value is None:
        return None

    parts = str(value).strip().split(":")
    if len(parts) != 3:
        return None

    try:
        hours, minutes, seconds = (int(part) for part in parts)
    except ValueError:
        return None

    if hours < 0 or minutes < 0 or seconds < 0:
        return None
    if minutes >= 60 or seconds >= 60:
        return None

    return (hours * 3600) + (minutes * 60) + seconds


def _format_restriction_hms(value: Any) -> str | None:
    try:
        total_seconds = int(value)
    except (TypeError, ValueError):
        return None

    if total_seconds < 0:
        return None

    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


class ReconnectService:
    def __init__(self, *, repository, target_server_by_origem: dict[str, str]):
        self.repository = repository
        self.target_server_by_origem = target_server_by_origem

    def start_for_line(self, phone_line: PhoneLine) -> dict[str, Any]:
        self._ensure_line_is_eligible_for_reconnect(phone_line)
        normalized_phone = self._normalize_phone_number(phone_line.phone_number)
        line_log_context = self._line_log_context(phone_line)
        active_session = self.repository.find_active_session_by_phone(normalized_phone)
        if active_session:
            serialized = self._serialize_session(active_session)
            logger.info(
                "Reconnect session reused",
                extra={
                    **line_log_context,
                    "session_id": serialized.get("session_id"),
                    "status": serialized.get("status"),
                    "attempt": serialized.get("attempt"),
                },
            )
            return serialized
        self._ensure_active_session_unique_index()

        now = timezone.now()
        document = {
            "_id": f"manual_reconnect_{uuid4().hex}",
            "phone_number": normalized_phone,
            "vm_name": self._resolve_vm_name(phone_line),
            "target_server": self._resolve_target_server(phone_line),
            "assigned_server": None,
            "status": "QUEUED",
            "attempt": 0,
            "active_lock": True,
            "device_name": self._resolve_device_name(phone_line),
            "created_at": now,
            "updated_at": now,
        }

        try:
            created = self.repository.create_session(document)
        except ActiveReconnectSessionConflict:
            active_session = self.repository.find_active_session_by_phone(normalized_phone)
            if active_session:
                serialized = self._serialize_session(active_session)
                logger.warning(
                    "Reconnect session conflict resolved by reusing active session",
                    extra={
                        **line_log_context,
                        "session_id": serialized.get("session_id"),
                        "status": serialized.get("status"),
                        "attempt": serialized.get("attempt"),
                    },
                )
                return serialized
            raise BusinessRuleException(
                "Ja existe uma sessao de reconexao ativa para este numero. Tente novamente."
            )
        serialized = self._serialize_session(created)
        logger.info(
            "Reconnect session queued",
            extra={
                **line_log_context,
                "session_id": serialized.get("session_id"),
                "status": serialized.get("status"),
                "attempt": serialized.get("attempt"),
            },
        )
        return serialized

    def get_active_for_line(self, phone_line: PhoneLine) -> dict[str, Any] | None:
        return self.get_status_for_line(phone_line)

    def get_status_for_line(
        self,
        phone_line: PhoneLine,
        *,
        session_id: str = "",
    ) -> dict[str, Any] | None:
        normalized_phone = self._normalize_phone_number(phone_line.phone_number)
        normalized_session_id = (session_id or "").strip()
        if normalized_session_id:
            session = self.repository.get_session(normalized_session_id)
            if not session:
                raise BusinessRuleException("Sessao de reconexao nao encontrada.")
            if session.get("phone_number") != normalized_phone:
                raise BusinessRuleException(
                    "Sessao de reconexao nao pertence a esta linha."
                )
            return self._serialize_session(session)

        active_session = self.repository.find_active_session_by_phone(normalized_phone)
        if active_session:
            return self._serialize_session(active_session)

        restricted_session = None
        if hasattr(self.repository, "find_recent_restricted_session_by_phone"):
            restricted_session = self.repository.find_recent_restricted_session_by_phone(
                normalized_phone
            )
        if (
            self._is_restriction_window_active(restricted_session)
            and self._is_latest_terminal_session_for_phone(
                phone_number=normalized_phone,
                session_id=str(restricted_session.get("_id") or ""),
            )
        ):
            return self._serialize_session(restricted_session)

        return None

    def submit_code_for_line(
        self,
        phone_line: PhoneLine,
        *,
        session_id: str,
        pair_code: str,
    ) -> dict[str, Any]:
        session = self._require_session_for_line(phone_line, session_id)
        normalized_code = (pair_code or "").strip().upper()
        if not normalized_code:
            raise BusinessRuleException("Informe um codigo de conexao valido.")

        line_log_context = self._line_log_context(phone_line)
        if session.get("status") != WAITING_FOR_CODE_STATUS:
            result = self._serialize_session(session)
            result["code_accepted"] = False
            logger.warning(
                "Reconnect pair code ignored due to invalid status",
                extra={
                    **line_log_context,
                    "session_id": session_id,
                    "status": result.get("status"),
                    "pair_code_length": len(normalized_code),
                },
            )
            return result

        modified = self.repository.submit_pair_code(
            session_id=session_id,
            attempt=session.get("attempt", 0),
            pair_code=normalized_code,
            submitted_at=timezone.now(),
        )
        latest = self.repository.get_session(session_id) or session
        result = self._serialize_session(latest)
        result["code_accepted"] = bool(modified)
        logger.info(
            "Reconnect pair code submitted",
            extra={
                **line_log_context,
                "session_id": session_id,
                "status": result.get("status"),
                "attempt": result.get("attempt"),
                "pair_code_length": len(normalized_code),
                "code_accepted": bool(modified),
            },
        )
        return result

    def cancel_for_line(self, phone_line: PhoneLine, *, session_id: str) -> dict[str, Any]:
        session = self._require_session_for_line(phone_line, session_id)
        line_log_context = self._line_log_context(phone_line)
        modified = self.repository.cancel_session(
            session_id=session_id,
            requested_at=timezone.now(),
        )
        latest = self.repository.get_session(session_id) or session
        result = self._serialize_session(latest)
        result["cancel_requested"] = bool(modified)
        logger.info(
            "Reconnect session cancel requested",
            extra={
                **line_log_context,
                "session_id": session_id,
                "status": result.get("status"),
                "attempt": result.get("attempt"),
                "cancel_requested": bool(modified),
            },
        )
        return result

    def _line_log_context(self, phone_line: PhoneLine) -> dict[str, Any]:
        return {
            "phone_line_id": phone_line.pk,
            "phone_number": self._normalize_phone_number(phone_line.phone_number),
            "origem": phone_line.origem or "",
        }

    def _require_session_for_line(
        self,
        phone_line: PhoneLine,
        session_id: str,
    ) -> dict[str, Any]:
        if not session_id:
            raise BusinessRuleException("Sessao de reconexao nao informada.")

        session = self.repository.get_session(session_id)
        if not session:
            raise BusinessRuleException("Sessao de reconexao nao encontrada.")

        normalized_phone = self._normalize_phone_number(phone_line.phone_number)
        if session.get("phone_number") != normalized_phone:
            raise BusinessRuleException("Sessao de reconexao nao pertence a esta linha.")
        return session

    def _ensure_line_is_eligible_for_reconnect(self, phone_line: PhoneLine) -> None:
        if phone_line.origem not in ELIGIBLE_RECONNECT_ORIGENS:
            raise BusinessRuleException(
                "A linha precisa ter origem SRVMEMU para iniciar a reconexao."
            )

    def _ensure_active_session_unique_index(self) -> None:
        if not hasattr(self.repository, "has_active_session_unique_index"):
            return
        if not self.repository.has_active_session_unique_index():
            raise BusinessRuleException(
                "A collection de reconexao precisa do indice unico parcial por "
                "phone_number com active_lock=true antes de iniciar novas sessoes."
            )

    def _resolve_target_server(self, phone_line: PhoneLine) -> str:
        origem = phone_line.origem or ""
        target_server = self.target_server_by_origem.get(origem, "").strip()
        if not target_server:
            raise BusinessRuleException(
                "A linha nao possui mapeamento de servidor para reconexao."
            )
        return target_server

    def _resolve_vm_name(self, phone_line: PhoneLine) -> str:
        return self._normalize_phone_number(phone_line.phone_number)

    def _resolve_device_name(self, phone_line: PhoneLine) -> str:
        active_allocation = (
            phone_line.allocations.filter(is_active=True)
            .select_related("employee")
            .first()
        )
        raw_device_name = (
            active_allocation.employee.full_name
            if active_allocation and active_allocation.employee
            else self._normalize_phone_number(phone_line.phone_number)
        )
        if len(raw_device_name) > 50:
            logger.warning(
                "device_name truncado para 50 chars (original: %r) para linha %s",
                raw_device_name,
                phone_line.phone_number,
            )
        return raw_device_name[:50]

    def _normalize_phone_number(self, phone_number: str) -> str:
        return "".join(character for character in (phone_number or "") if character.isdigit())

    def _is_restriction_window_active(self, document: dict[str, Any] | None) -> bool:
        if not document:
            return False

        account_state = _normalize_status(document.get("account_state"))
        error_code = (document.get("error_code") or "").strip()
        if account_state != "RESTRICTED" and error_code != "whatsapp_account_restricted":
            return False

        now = timezone.now()
        restriction_until = self._to_aware_datetime(document.get("restriction_until"))
        if restriction_until is not None:
            return restriction_until > now

        seconds_remaining = self._resolve_restriction_seconds(document)
        if seconds_remaining is None:
            return False
        if seconds_remaining <= 0:
            return False

        detected_at = self._to_aware_datetime(
            document.get("account_state_detected_at")
            or document.get("updated_at")
            or document.get("finished_at")
        )
        if detected_at is None:
            return True

        return (detected_at + timedelta(seconds=seconds_remaining)) > now

    def _resolve_restriction_seconds(self, document: dict[str, Any]) -> int | None:
        raw_seconds_remaining = document.get("restriction_seconds_remaining")
        try:
            return int(raw_seconds_remaining)
        except (TypeError, ValueError):
            return _parse_restriction_hms(document.get("restriction_remaining_hms"))

    def _resolve_restriction_remaining_hms(self, document: dict[str, Any]) -> str | None:
        explicit_value = _format_restriction_hms(document.get("restriction_remaining_hms"))
        if explicit_value is not None:
            return explicit_value

        resolved_seconds = self._resolve_restriction_seconds(document)
        return _format_restriction_hms(resolved_seconds)

    def _is_latest_terminal_session_for_phone(self, *, phone_number: str, session_id: str) -> bool:
        if not session_id:
            return False
        if not hasattr(self.repository, "find_latest_terminal_session_by_phone"):
            return True

        latest_terminal = self.repository.find_latest_terminal_session_by_phone(phone_number)
        if not latest_terminal:
            return False

        return str(latest_terminal.get("_id") or "") == session_id

    @staticmethod
    def _to_aware_datetime(value: Any) -> datetime | None:
        if not isinstance(value, datetime):
            return None
        if timezone.is_naive(value):
            return value.replace(tzinfo=UTC)
        return value

    def _serialize_session(self, document: dict[str, Any]) -> dict[str, Any]:
        raw_status = _normalize_status(document.get("status"))
        cancel_requested = bool(document.get("cancel_requested_at")) and (
            raw_status not in TERMINAL_RECONNECT_STATUSES
        )
        serialized_status = CANCEL_REQUESTED_STATUS if cancel_requested else raw_status
        restriction_seconds_remaining = self._resolve_restriction_seconds(document)
        payload = {
            "session_id": document.get("_id"),
            "status": serialized_status,
            "raw_status": raw_status,
            "attempt": document.get("attempt", 0),
            "assigned_server": document.get("assigned_server"),
            "error_code": document.get("error_code"),
            "error_message": document.get("error_message"),
            "session_deadline_at": _format_datetime(document.get("session_deadline_at")),
            "worker_heartbeat_at": _format_datetime(document.get("worker_heartbeat_at")),
            "progress_stage": document.get("progress_stage"),
            "progress_stage_label": document.get("progress_stage_label"),
            "progress_stage_updated_at": _format_datetime(
                document.get("progress_stage_updated_at")
            ),
            "progress_history": _format_progress_history(document.get("progress_history")),
            "cancel_requested": cancel_requested,
            "cancel_requested_at": _format_datetime(document.get("cancel_requested_at")),
            "account_state": document.get("account_state"),
            "needs_it_action": document.get("needs_it_action"),
            "needs_it_reason": document.get("needs_it_reason"),
            "restriction_seconds_remaining": restriction_seconds_remaining,
            "restriction_remaining_hms": self._resolve_restriction_remaining_hms(document),
            "restriction_until": _format_datetime(document.get("restriction_until")),
            "device_name": document.get("device_name"),
            "last_pair_code": document.get("last_pair_code"),
            "last_pair_code_attempt": document.get("last_pair_code_attempt"),
            "last_pair_code_submitted_at": _format_datetime(
                document.get("last_pair_code_submitted_at")
            ),
            "last_pair_code_consumed_at": _format_datetime(
                document.get("last_pair_code_consumed_at")
            ),
            "phone_number": document.get("phone_number"),
            "vm_name": document.get("vm_name"),
            "target_server": document.get("target_server"),
            "is_terminal": raw_status in TERMINAL_RECONNECT_STATUSES,
            "can_submit_code": raw_status == WAITING_FOR_CODE_STATUS and not cancel_requested,
            "can_cancel": raw_status not in TERMINAL_RECONNECT_STATUSES and not cancel_requested,
        }
        return payload


def build_default_reconnect_service() -> ReconnectService:
    from django.conf import settings

    from telecom.repositories.reconnect_sessions import MongoReconnectSessionRepository

    repository = MongoReconnectSessionRepository.from_settings()
    return ReconnectService(
        repository=repository,
        target_server_by_origem=settings.RECONNECT_TARGET_SERVER_BY_ORIGEM,
    )
