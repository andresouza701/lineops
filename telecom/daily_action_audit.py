"""
Servico central de auditoria de acoes diarias de linha.

Constroi snapshots completos (before_state/after_state) para os dois source
de LineDailyActionAuditEvent (AllocationPendency e DailyUserAction) e cria a
linha de auditoria propriamente dita. Nao decide event_type, nao muta linhas
de negocio e nao abre sua propria transacao — quem chama e responsavel por
isso.
"""

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
    """Snapshot completo do estado de um DailyUserAction (fonte legada)."""
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
