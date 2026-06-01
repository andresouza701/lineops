from dashboard.services.action_board_metrics_service import (
    ACTION_VALUES,
    LINE_STATUS_VALUES,
    summarize_action_board_responsibles,
)
from employees.models import Employee
from pendencies.models import AllocationPendency


def _display_name(user):
    if not user:
        return "Sem responsavel"
    full_name = user.get_full_name().strip()
    return full_name or user.email or str(user.pk)


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
        "resolved_total": 0,
        "oldest_submitted_at": None,
    }


def _resolve_line_status(pendency):
    if pendency.allocation_id and pendency.allocation:
        return pendency.allocation.line_status
    return pendency.employee.line_status


def _apply_resolved_filters(queryset, filters):
    filters = filters or {}

    action = filters.get("action") or ""
    if action in ACTION_VALUES:
        queryset = queryset.filter(last_submitted_action=action)

    technical_responsible = filters.get("technical_responsible") or ""
    if technical_responsible:
        queryset = queryset.filter(updated_by_id=technical_responsible)

    supervisor = filters.get("supervisor") or ""
    if supervisor:
        queryset = queryset.filter(employee__corporate_email__icontains=supervisor)

    return queryset


def build_pendency_metrics(user, filters=None):
    filters = filters or {}
    scoped_employee_ids = user.scope_employee_queryset(
        Employee.objects.filter(is_deleted=False)
    ).values_list("id", flat=True)

    current_metrics = summarize_action_board_responsibles(user, filters)
    line_status_filter = current_metrics["line_status_filter"]
    action_filter = current_metrics["action_filter"]
    summary = current_metrics["summary"]
    unassigned = current_metrics["unassigned_breakdown"]
    rankings_by_responsible = {}

    for responsible_id, responsible_summary in current_metrics[
        "responsibles"
    ].items():
        row = rankings_by_responsible.setdefault(
            responsible_id,
            _new_ranking_row(responsible_summary["responsible"]),
        )
        for key in (
            "total",
            "restricted",
            "permanently_banned",
            "under_analysis",
            "waiting_operator",
            "new_number",
            "reconnect_whatsapp",
            "pending",
        ):
            row[key] = responsible_summary[key]
        row["oldest_submitted_at"] = responsible_summary["oldest_submitted_at"]

    resolved_pendencies = (
        AllocationPendency.objects.filter(
            employee_id__in=scoped_employee_ids,
            resolved_at__isnull=False,
            updated_by_id__isnull=False,
        )
        .select_related("employee", "allocation", "updated_by")
        .order_by("updated_by_id", "resolved_at", "id")
    )
    resolved_pendencies = _apply_resolved_filters(resolved_pendencies, filters)

    for pendency in resolved_pendencies:
        line_status = _resolve_line_status(pendency)
        if line_status_filter and line_status != line_status_filter:
            continue

        responsible = pendency.updated_by
        row = rankings_by_responsible.setdefault(
            responsible.id,
            _new_ranking_row(responsible),
        )
        row["resolved_total"] += 1

    responsible_rankings = sorted(
        rankings_by_responsible.values(),
        key=lambda item: (
            -item["total"],
            -item["resolved_total"],
            item["responsible_name"].lower(),
        ),
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
            "action": action_filter,
            "technical_responsible": filters.get("technical_responsible", "") or "",
            "supervisor": filters.get("supervisor", "") or "",
        },
        "summary": summary,
        "responsible_rankings": responsible_rankings,
        "unassigned_breakdown": unassigned,
        "technical_responsible_choices": technical_responsible_choices,
    }
