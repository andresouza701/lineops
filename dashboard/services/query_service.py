from collections import defaultdict

from django.db.models import Count

from allocations.models import LineAllocation
from employees.models import Employee
from pendencies.models import AllocationPendency
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser


def uses_scoped_dashboard_metrics(user):
    return bool(
        user
        and getattr(user, "role", None)
        in {
            SystemUser.Role.SUPER,
            SystemUser.Role.BACKOFFICE,
            SystemUser.Role.GERENTE,
        }
    )


def get_supervised_employees_queryset(user, supervisor_filter=None):
    employees = user.scope_employee_queryset(Employee.objects.filter(is_deleted=False))
    if user.role == SystemUser.Role.ADMIN and supervisor_filter:
        employees = employees.filter(corporate_email__icontains=supervisor_filter)
    return employees.order_by("full_name")


def get_scoped_phone_lines_queryset_for_dashboard(user):
    lines = PhoneLine.objects.filter(
        is_deleted=False,
        sim_card__is_deleted=False,
    )
    if not uses_scoped_dashboard_metrics(user):
        return lines

    scoped_employee_ids = get_supervised_employees_queryset(user).values_list(
        "id", flat=True
    )
    scoped_line_ids = (
        LineAllocation.objects.filter(
            employee_id__in=scoped_employee_ids,
            phone_line__is_deleted=False,
            phone_line__sim_card__is_deleted=False,
        )
        .values_list("phone_line_id", flat=True)
        .distinct()
    )
    return lines.filter(id__in=scoped_line_ids)


def build_dashboard_overview_counts(user):
    scoped_active_employees = get_supervised_employees_queryset(user).filter(
        status=Employee.Status.ACTIVE,
        is_deleted=False,
    )
    scoped_employee_ids = scoped_active_employees.values_list("id", flat=True)
    return {
        "total_employees": scoped_active_employees.count(),
        "total_lines": PhoneLine.objects.filter(is_deleted=False).count(),
        "allocated_lines": LineAllocation.objects.filter(
            is_active=True,
            employee_id__in=scoped_employee_ids,
        ).count(),
        "available_lines": PhoneLine.objects.filter(
            is_deleted=False,
            status=PhoneLine.Status.AVAILABLE,
        ).count(),
        "total_simcards": SIMcard.objects.filter(is_deleted=False).count(),
    }


def build_dashboard_status_counts(user):
    sim_counts = defaultdict(int)
    line_counts = defaultdict(int)

    for row in (
        SIMcard.objects.filter(is_deleted=False)
        .values("status")
        .annotate(count=Count("id"))
    ):
        sim_counts[row["status"]] = row["count"]

    scoped_lines = get_scoped_phone_lines_queryset_for_dashboard(user)
    for row in scoped_lines.values("status").annotate(count=Count("id")):
        line_counts[row["status"]] = row["count"]

    return {
        "sim_status_counts": [
            {"value": value, "label": label, "count": sim_counts.get(value, 0)}
            for value, label in SIMcard.Status.choices
        ],
        "line_status_counts": [
            {"value": value, "label": label, "count": line_counts.get(value, 0)}
            for value, label in PhoneLine.Status.choices
        ],
    }


def get_pending_action_counts_for_user(user):
    scoped_employee_ids = (
        get_supervised_employees_queryset(user)
        .filter(
            status=Employee.Status.ACTIVE,
            is_deleted=False,
        )
        .values_list("id", flat=True)
    )
    pendencies = AllocationPendency.objects.filter(employee_id__in=scoped_employee_ids)
    return {
        "new_number": pendencies.filter(
            action=AllocationPendency.ActionType.NEW_NUMBER
        ).count(),
        "reconnect_whatsapp": pendencies.filter(
            action=AllocationPendency.ActionType.RECONNECT_WHATSAPP
        ).count(),
        "pending": pendencies.filter(action=AllocationPendency.ActionType.PENDING).count(),
    }

