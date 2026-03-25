from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from allocations.models import LineAllocation
from dashboard.models import DailyUserAction
from users.models import SystemUser
from whatsapp.choices import WhatsAppSessionStatus
from whatsapp.models import WhatsAppSession
from whatsapp.services.instance_selector import NoAvailableMeowInstanceError
from whatsapp.services.session_service import WhatsAppSessionService

logger = logging.getLogger(__name__)


class WhatsAppProvisioningService:
    def __init__(self, session_service: WhatsAppSessionService | None = None):
        self.session_service = session_service or WhatsAppSessionService()

    @transaction.atomic
    def mark_allocation_pending(
        self,
        *,
        allocation: LineAllocation,
        actor,
    ):
        target_status, action_type, note = self._resolve_pending_context(allocation)
        session = self._get_existing_session(allocation.phone_line)
        if session is None:
            session, note = self._try_create_session(allocation.phone_line, note=note)

        if session is not None:
            self._set_session_pending(session, target_status)

        action = self._upsert_daily_action(
            employee=allocation.employee,
            allocation=allocation,
            action_type=action_type,
            note=note,
            actor=actor,
        )
        return session, action

    @transaction.atomic
    def resolve_allocation_pending(
        self,
        *,
        allocation: LineAllocation,
        actor,
        note="",
    ):
        actions = DailyUserAction.objects.filter(
            employee=allocation.employee,
            allocation=allocation,
            is_resolved=False,
        ).order_by("day", "-id")

        resolved = 0
        now = timezone.now()
        for action in actions:
            action.is_resolved = True
            if note:
                action.note = note
            action.updated_by = actor
            action.updated_at = now
            update_fields = ["is_resolved", "updated_by", "updated_at"]
            if note:
                update_fields.append("note")
            action.save(update_fields=update_fields)
            resolved += 1
        return resolved

    def _resolve_pending_context(self, allocation: LineAllocation):
        if self._is_first_allocation_for_line(allocation):
            return (
                WhatsAppSessionStatus.PENDING_NEW_NUMBER,
                DailyUserAction.ActionType.NEW_NUMBER,
                "Linha alocada; pendente de conexao inicial do WhatsApp.",
            )

        return (
            WhatsAppSessionStatus.PENDING_RECONNECT,
            DailyUserAction.ActionType.RECONNECT_WHATSAPP,
            "Linha realocada; validar ou reconectar sessao do WhatsApp.",
        )

    def _get_existing_session(self, phone_line):
        return (
            WhatsAppSession.objects.select_related("meow_instance")
            .filter(line=phone_line)
            .first()
        )

    def _try_create_session(
        self,
        phone_line,
        *,
        note: str,
    ) -> tuple[WhatsAppSession | None, str]:
        try:
            return self.session_service.get_or_create_session(phone_line), note
        except NoAvailableMeowInstanceError as exc:
            logger.warning(
                "WhatsApp session could not be provisioned due to Meow capacity",
                extra={
                    "phone_line_id": phone_line.id,
                    "phone_number": phone_line.phone_number,
                },
            )
            return None, f"{note} Infraestrutura Meow sem capacidade disponivel."

    def _is_first_allocation_for_line(self, allocation: LineAllocation) -> bool:
        return not (
            LineAllocation.objects.filter(phone_line=allocation.phone_line)
            .exclude(pk=allocation.pk)
            .exists()
        )

    def _set_session_pending(self, session: WhatsAppSession, status: str) -> None:
        session.status = status
        session.last_error = ""
        session.last_sync_at = timezone.now()
        session.save(
            update_fields=[
                "status",
                "last_error",
                "last_sync_at",
                "updated_at",
            ]
        )

    def _upsert_daily_action(
        self,
        *,
        employee,
        allocation,
        action_type: str,
        note: str,
        actor,
    ):
        supervisor = self._resolve_supervisor(employee.corporate_email)
        action, created = DailyUserAction.objects.get_or_create(
            day=timezone.localdate(),
            employee=employee,
            allocation=allocation,
            defaults={"created_by": actor},
        )

        action.supervisor = supervisor
        action.action_type = action_type
        action.note = note
        action.updated_by = actor
        action.is_resolved = False
        if created and action.created_by_id is None:
            action.created_by = actor

        update_fields = [
            "supervisor",
            "action_type",
            "note",
            "is_resolved",
            "updated_by",
            "updated_at",
        ]
        if created:
            update_fields.append("created_by")
        action.save(update_fields=update_fields)
        return action

    def _resolve_supervisor(self, email: str) -> SystemUser | None:
        if not email:
            return None
        return SystemUser.objects.filter(email__iexact=email).first()
