from allocations.models import LineAllocation
from pendencies.models import AllocationPendency


ACTION_VALUES = {
    AllocationPendency.ActionType.NEW_NUMBER,
    AllocationPendency.ActionType.RECONNECT_WHATSAPP,
    AllocationPendency.ActionType.PENDING,
}

LINE_STATUS_VALUES = {
    LineAllocation.LineStatus.ACTIVE,
    LineAllocation.LineStatus.UNDER_ANALYSIS,
    LineAllocation.LineStatus.RESTRICTED,
    LineAllocation.LineStatus.PERMANENTLY_BANNED,
    LineAllocation.LineStatus.WAITING_OPERATOR,
}


def _row_line_status(row):
    allocation = row.get("allocation")
    if allocation:
        return allocation.line_status
    return row["employee"].line_status


def _row_action(row):
    pendency = row.get("pendency")
    if not pendency:
        return AllocationPendency.ActionType.NO_ACTION
    return pendency.action


def summarize_action_board_responsibles(user, filters=None):
    """
    Resume responsaveis tecnicos usando a mesma base visivel de Acoes do Dia.
    Import local evita ciclo: dashboard.views importa metrics_service.
    """
    from dashboard.views import (
        build_daily_user_action_rows,
        get_supervised_employees_queryset,
    )

    filters = filters or {}
    action_filter = filters.get("action") or ""
    if action_filter not in ACTION_VALUES:
        action_filter = ""

    line_status_filter = filters.get("line_status") or ""
    if line_status_filter not in LINE_STATUS_VALUES:
        line_status_filter = ""

    technical_responsible_filter = filters.get("technical_responsible") or ""
    supervisor_filter = filters.get("supervisor") or ""

    employees_qs = get_supervised_employees_queryset(user, supervisor_filter)
    rows = build_daily_user_action_rows(employees_qs, user, include_forms=False)

    summary = {
        "open_total": 0,
        "assigned_total": 0,
        "unassigned_total": 0,
        "restricted_assigned_total": 0,
        "banned_assigned_total": 0,
    }
    unassigned = {
        "total": 0,
        "restricted": 0,
        "permanently_banned": 0,
    }
    responsibles = {}

    for row in rows:
        pendency = row.get("pendency")
        action = _row_action(row)
        line_status = _row_line_status(row)

        if action_filter and action != action_filter:
            continue
        if line_status_filter and line_status != line_status_filter:
            continue

        responsible = getattr(pendency, "technical_responsible", None)
        responsible_id = getattr(pendency, "technical_responsible_id", None)
        if (
            technical_responsible_filter
            and str(responsible_id) != str(technical_responsible_filter)
        ):
            continue

        is_open = action in ACTION_VALUES
        if is_open:
            summary["open_total"] += 1

        if responsible_id:
            summary["assigned_total"] += 1
            if line_status == LineAllocation.LineStatus.RESTRICTED:
                summary["restricted_assigned_total"] += 1
            elif line_status == LineAllocation.LineStatus.PERMANENTLY_BANNED:
                summary["banned_assigned_total"] += 1

            responsible_summary = responsibles.setdefault(
                responsible_id,
                {
                    "responsible": responsible,
                    "total": 0,
                    "restricted": 0,
                    "permanently_banned": 0,
                    "under_analysis": 0,
                    "waiting_operator": 0,
                    "new_number": 0,
                    "reconnect_whatsapp": 0,
                    "pending": 0,
                    "oldest_submitted_at": None,
                },
            )
            responsible_summary["total"] += 1
            if line_status == LineAllocation.LineStatus.RESTRICTED:
                responsible_summary["restricted"] += 1
            elif line_status == LineAllocation.LineStatus.PERMANENTLY_BANNED:
                responsible_summary["permanently_banned"] += 1
            elif line_status == LineAllocation.LineStatus.UNDER_ANALYSIS:
                responsible_summary["under_analysis"] += 1
            elif line_status == LineAllocation.LineStatus.WAITING_OPERATOR:
                responsible_summary["waiting_operator"] += 1

            if action == AllocationPendency.ActionType.NEW_NUMBER:
                responsible_summary["new_number"] += 1
            elif action == AllocationPendency.ActionType.RECONNECT_WHATSAPP:
                responsible_summary["reconnect_whatsapp"] += 1
            elif action == AllocationPendency.ActionType.PENDING:
                responsible_summary["pending"] += 1

            submitted_at = getattr(pendency, "pendency_submitted_at", None)
            if submitted_at and (
                responsible_summary["oldest_submitted_at"] is None
                or submitted_at < responsible_summary["oldest_submitted_at"]
            ):
                responsible_summary["oldest_submitted_at"] = submitted_at
        elif is_open:
            summary["unassigned_total"] += 1
            unassigned["total"] += 1
            if line_status == LineAllocation.LineStatus.RESTRICTED:
                unassigned["restricted"] += 1
            elif line_status == LineAllocation.LineStatus.PERMANENTLY_BANNED:
                unassigned["permanently_banned"] += 1

    return {
        "summary": summary,
        "unassigned_breakdown": unassigned,
        "responsibles": responsibles,
        "line_status_filter": line_status_filter,
        "action_filter": action_filter,
    }
