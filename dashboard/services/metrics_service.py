from allocations.models import LineAllocation
from employees.models import Employee
from pendencies.models import AllocationPendency


LINE_STATUS_VALUES = {
    LineAllocation.LineStatus.ACTIVE,
    LineAllocation.LineStatus.UNDER_ANALYSIS,
    LineAllocation.LineStatus.RESTRICTED,
    LineAllocation.LineStatus.PERMANENTLY_BANNED,
    LineAllocation.LineStatus.WAITING_OPERATOR,
}

ACTION_VALUES = {
    AllocationPendency.ActionType.NEW_NUMBER,
    AllocationPendency.ActionType.RECONNECT_WHATSAPP,
    AllocationPendency.ActionType.PENDING,
}


def _display_name(user):
    if not user:
        return "Sem responsavel"
    full_name = user.get_full_name().strip()
    return full_name or user.email or str(user.pk)


def _empty_summary():
    return {
        "open_total": 0,
        "assigned_total": 0,
        "unassigned_total": 0,
        "restricted_assigned_total": 0,
        "banned_assigned_total": 0,
    }


def _empty_breakdown():
    return {
        "total": 0,
        "restricted": 0,
        "permanently_banned": 0,
    }


def _new_ranking_row(responsible):
    return {
        "responsible_id": responsible.id,
        "responsible_name": _display_name(responsible),
        "total": 0,
        "restricted": 0,
        "permanently_banned": 0,
        "under_analysis": 0,
        "waiting_operator": 0,
        "new_number": 0,
        "reconnect_whatsapp": 0,
        "pending": 0,
        "oldest_submitted_at": None,
    }


def _resolve_line_status(pendency):
    if pendency.allocation_id and pendency.allocation:
        return pendency.allocation.line_status
    return pendency.employee.line_status


def _apply_filters(queryset, filters):
    filters = filters or {}

    action = filters.get("action") or ""
    if action in ACTION_VALUES:
        queryset = queryset.filter(action=action)

    technical_responsible = filters.get("technical_responsible") or ""
    if technical_responsible:
        queryset = queryset.filter(technical_responsible_id=technical_responsible)

    supervisor = filters.get("supervisor") or ""
    if supervisor:
        queryset = queryset.filter(employee__corporate_email__icontains=supervisor)

    return queryset


def build_pendency_metrics(user, filters=None):
    filters = filters or {}
    scoped_employee_ids = user.scope_employee_queryset(
        Employee.objects.filter(is_deleted=False)
    ).values_list("id", flat=True)

    pendencies = (
        AllocationPendency.objects.filter(employee_id__in=scoped_employee_ids)
        .exclude(action=AllocationPendency.ActionType.NO_ACTION)
        .select_related("employee", "allocation", "technical_responsible")
        .order_by("technical_responsible_id", "pendency_submitted_at", "id")
    )
    pendencies = _apply_filters(pendencies, filters)

    line_status_filter = filters.get("line_status") or ""
    if line_status_filter not in LINE_STATUS_VALUES:
        line_status_filter = ""

    summary = _empty_summary()
    unassigned = _empty_breakdown()
    rankings_by_responsible = {}

    for pendency in pendencies:
        line_status = _resolve_line_status(pendency)
        if line_status_filter and line_status != line_status_filter:
            continue

        summary["open_total"] += 1
        is_restricted = line_status == LineAllocation.LineStatus.RESTRICTED
        is_banned = line_status == LineAllocation.LineStatus.PERMANENTLY_BANNED

        if pendency.technical_responsible_id:
            summary["assigned_total"] += 1
            if is_restricted:
                summary["restricted_assigned_total"] += 1
            if is_banned:
                summary["banned_assigned_total"] += 1

            responsible = pendency.technical_responsible
            row = rankings_by_responsible.setdefault(
                responsible.id,
                _new_ranking_row(responsible),
            )
            row["total"] += 1
            if line_status == LineAllocation.LineStatus.RESTRICTED:
                row["restricted"] += 1
            elif line_status == LineAllocation.LineStatus.PERMANENTLY_BANNED:
                row["permanently_banned"] += 1
            elif line_status == LineAllocation.LineStatus.UNDER_ANALYSIS:
                row["under_analysis"] += 1
            elif line_status == LineAllocation.LineStatus.WAITING_OPERATOR:
                row["waiting_operator"] += 1

            if pendency.action == AllocationPendency.ActionType.NEW_NUMBER:
                row["new_number"] += 1
            elif pendency.action == AllocationPendency.ActionType.RECONNECT_WHATSAPP:
                row["reconnect_whatsapp"] += 1
            elif pendency.action == AllocationPendency.ActionType.PENDING:
                row["pending"] += 1

            submitted_at = pendency.pendency_submitted_at
            if submitted_at and (
                row["oldest_submitted_at"] is None
                or submitted_at < row["oldest_submitted_at"]
            ):
                row["oldest_submitted_at"] = submitted_at
        else:
            summary["unassigned_total"] += 1
            unassigned["total"] += 1
            if is_restricted:
                unassigned["restricted"] += 1
            if is_banned:
                unassigned["permanently_banned"] += 1

    responsible_rankings = sorted(
        rankings_by_responsible.values(),
        key=lambda item: (-item["total"], item["responsible_name"].lower()),
    )

    technical_responsible_choices = [
        {
            "id": row["responsible_id"],
            "name": row["responsible_name"],
        }
        for row in responsible_rankings
    ]

    return {
        "filters": {
            "line_status": line_status_filter,
            "action": (
                filters.get("action", "")
                if filters.get("action", "") in ACTION_VALUES
                else ""
            ),
            "technical_responsible": filters.get("technical_responsible", "") or "",
            "supervisor": filters.get("supervisor", "") or "",
        },
        "summary": summary,
        "responsible_rankings": responsible_rankings,
        "unassigned_breakdown": unassigned,
        "technical_responsible_choices": technical_responsible_choices,
    }
