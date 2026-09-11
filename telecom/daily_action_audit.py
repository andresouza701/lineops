"""
Servico central de auditoria de acoes diarias de linha.

Constroi snapshots completos (before_state/after_state) para os dois source
de LineDailyActionAuditEvent (AllocationPendency e DailyUserAction) e cria a
linha de auditoria propriamente dita. Nao decide event_type, nao muta linhas
de negocio e nao abre sua propria transacao — quem chama e responsavel por
isso.
"""

import uuid

from django.db import transaction
from django.utils import timezone

from telecom.models import LineDailyActionAuditEvent


def _choice_state(code, label):
    return {"code": code, "label": label}


def _user_state(user):
    if user is None:
        return None
    return {
        "id": user.pk,
        "name": user.get_full_name().strip() or user.email,
        "email": user.email,
    }


def _allocation_line_status_state(allocation):
    if allocation is None:
        return {"code": None, "label": None}
    return {
        "code": allocation.line_status,
        "label": allocation.get_line_status_display(),
    }


def _pendency_resolution_state(pendency):
    return {
        "is_resolved": pendency.resolved_at is not None,
        "resolved_at": pendency.resolved_at.isoformat() if pendency.resolved_at else None,
    }


def _pendency_source_state(pendency):
    last_submitted_action = None
    if pendency.last_submitted_action:
        from pendencies.models import AllocationPendency

        last_submitted_action = _choice_state(
            pendency.last_submitted_action,
            dict(AllocationPendency.ActionType.choices).get(
                pendency.last_submitted_action
            ),
        )

    return {
        "day": None,
        "pendency_submitted_at": (
            pendency.pendency_submitted_at.isoformat()
            if pendency.pendency_submitted_at
            else None
        ),
        "last_submitted_action": last_submitted_action,
        "is_resolved": None,
    }


def build_pendency_state(pendency, allocation) -> dict:
    """Snapshot completo do estado de uma AllocationPendency."""
    return {
        "action": _choice_state(pendency.action, pendency.get_action_display()),
        "note": pendency.observation,
        "technical_responsible": _user_state(pendency.technical_responsible),
        "line_status": _allocation_line_status_state(allocation),
        "resolution": _pendency_resolution_state(pendency),
        "source_state": _pendency_source_state(pendency),
    }


def build_daily_user_action_state(action, allocation) -> dict:
    """Snapshot completo do estado de um DailyUserAction (fonte legada).

    ``action=None`` representa o estado "nada existia antes", usado como
    before_state de um evento OPENED quando não havia linha prévia.
    """
    if action is None:
        return {
            "action": {"code": "", "label": "Sem acao"},
            "note": "",
            "technical_responsible": None,
            "line_status": _allocation_line_status_state(allocation),
            "resolution": {"is_resolved": False, "resolved_at": None},
            "source_state": {
                "day": None,
                "pendency_submitted_at": None,
                "last_submitted_action": None,
                "is_resolved": False,
            },
        }
    return {
        "action": _choice_state(action.action_type, action.get_action_type_display()),
        "note": action.note,
        "technical_responsible": None,
        "line_status": _allocation_line_status_state(allocation),
        "resolution": {"is_resolved": action.is_resolved, "resolved_at": None},
        "source_state": {
            "day": action.day.isoformat(),
            "pendency_submitted_at": None,
            "last_submitted_action": None,
            "is_resolved": action.is_resolved,
        },
    }


def record_line_daily_action_event(
    *,
    event_type,
    source,
    source_object_id,
    phone_line,
    allocation,
    employee,
    performed_by,
    before_state,
    after_state,
    occurred_at,
    operation_id,
) -> LineDailyActionAuditEvent:
    """Cria uma unica linha de auditoria append-only. Nao muta nada mais."""
    return LineDailyActionAuditEvent.objects.create(
        event_type=event_type,
        source=source,
        source_object_id=source_object_id,
        phone_line=phone_line,
        allocation=allocation,
        employee=employee,
        performed_by=performed_by,
        phone_number_snapshot=phone_line.phone_number if phone_line else "",
        allocation_id_snapshot=allocation.pk if allocation else None,
        employee_name_snapshot=employee.full_name if employee else "",
        performed_by_name_snapshot=(
            (performed_by.get_full_name().strip() or performed_by.email)
            if performed_by
            else ""
        ),
        performed_by_email_snapshot=performed_by.email if performed_by else "",
        before_state=before_state,
        after_state=after_state,
        occurred_at=occurred_at,
        operation_id=operation_id,
    )


def resolve_old_daily_user_actions() -> int:
    """Resolve cada DailyUserAction em aberto, uma linha por vez, com lock,
    snapshot completo e evento RESOLVED — nunca bulk update.

    Usada por scripts/resolve_old_actions.py (`manage.py shell < script`),
    que nao tem usuario autenticado (performed_by=None). Um unico
    operation_id e compartilhado por todas as resolucoes desta execucao.
    Sem backfill: so gera evento para o que esta execucao realmente resolve.
    """
    from dashboard.models import DailyUserAction

    operation_id = uuid.uuid4()
    resolved_count = 0

    old_action_ids = list(
        DailyUserAction.objects.filter(is_resolved=False).values_list("pk", flat=True)
    )

    for action_id in old_action_ids:
        with transaction.atomic():
            action = (
                DailyUserAction.objects.select_for_update()
                .filter(pk=action_id, is_resolved=False)
                .first()
            )
            if action is None:
                # Ja resolvida por outro processo entre a leitura e o lock.
                continue

            allocation = action.allocation
            before_state = build_daily_user_action_state(action, allocation)

            action.is_resolved = True
            action.updated_at = timezone.now()
            action.save(update_fields=["is_resolved", "updated_at"])

            after_state = build_daily_user_action_state(action, allocation)

            record_line_daily_action_event(
                event_type=LineDailyActionAuditEvent.EventType.RESOLVED,
                source=LineDailyActionAuditEvent.Source.DAILY_USER_ACTION,
                source_object_id=action.pk,
                phone_line=allocation.phone_line if allocation else None,
                allocation=allocation,
                employee=action.employee,
                performed_by=None,
                before_state=before_state,
                after_state=after_state,
                occurred_at=timezone.now(),
                operation_id=operation_id,
            )
            resolved_count += 1

    return resolved_count
