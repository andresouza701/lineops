import hashlib
import unicodedata
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from allocations.models import LineAllocation
from core.constants import (
    B2B_PORTFOLIO_NAMES,
    B2B_PORTFOLIOS,
    B2C_PORTFOLIO_NAMES,
    B2C_PORTFOLIOS,
)
from core.mixins import AuthenticadView, RoleRequiredMixin, roles_required
from core.services.daily_indicator_service import DailyIndicatorService
from employees.models import Employee
from telecom.models import PhoneLine, PhoneLineHistory, SIMcard
from users.models import SystemUser

from .forms import (
    B2B_SUPERVISORS,
    B2C_SUPERVISORS,
    DailyIndicatorFilterForm,
    DailyIndicatorForm,
    DailyUserActionForm,
)
from .models import DashboardDailySnapshot, DailyIndicator, DailyUserAction

PERCENT_CRITICAL_THRESHOLD = 20
PERCENT_WARNING_THRESHOLD = 10
COUNT_CRITICAL_THRESHOLD = 10
COUNT_WARNING_THRESHOLD = 5
DEFAULT_TREND_PERIOD = 7
ALLOWED_TREND_PERIODS = (7, 15, 30)
DASHBOARD_ALLOWED_ROLES = (
    SystemUser.Role.ADMIN,
    SystemUser.Role.SUPER,
    SystemUser.Role.GERENTE,
)


def resolve_trend_period(raw_period):
    try:
        period = int(raw_period)
    except (TypeError, ValueError):
        return DEFAULT_TREND_PERIOD

    if period in ALLOWED_TREND_PERIODS:
        return period
    return DEFAULT_TREND_PERIOD


def resolve_day(value):
    if not value:
        return timezone.localdate()
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return timezone.localdate()


def get_supervised_employees_queryset(user, supervisor_filter=None):
    employees = user.scope_employee_queryset(Employee.objects.filter(is_deleted=False))
    if user.role == SystemUser.Role.ADMIN and supervisor_filter:
        employees = employees.filter(corporate_email__icontains=supervisor_filter)
    return employees.order_by("full_name")


def get_daily_indicators_queryset(user):
    indicators = DailyIndicator.objects.all()
    if user.role == SystemUser.Role.SUPER:
        indicators = indicators.filter(
            Q(supervisor__iexact=user.email) | Q(created_by=user) | Q(updated_by=user)
        )
    elif user.role == SystemUser.Role.GERENTE:
        supervisor_emails = user.get_managed_supervisor_emails()
        indicators = indicators.filter(
            Q(supervisor__in=supervisor_emails)
            | Q(created_by=user)
            | Q(updated_by=user)
        )
    return indicators


def get_latest_unresolved_actions_queryset(user):
    employees_qs = get_supervised_employees_queryset(user).filter(
        status=Employee.Status.ACTIVE,
        is_deleted=False,
    )
    employee_ids = employees_qs.values_list("id", flat=True)
    actions = (
        DailyUserAction.objects.filter(
            employee_id__in=employee_ids,
            is_resolved=False,
        )
        .select_related("employee", "allocation__phone_line__sim_card")
        .order_by("employee_id", "-day", "-id", "allocation_id")
    )

    latest_by_key = {}
    for action in actions:
        allocation_id = (
            action.allocation_id
            if action.allocation and allocation_is_currently_visible(action.allocation)
            else None
        )
        key = (action.employee_id, allocation_id)
        if key not in latest_by_key:
            latest_by_key[key] = action

    return list(latest_by_key.values())


def get_unresolved_action_maps(employee_ids):
    all_actions = (
        DailyUserAction.objects.filter(
            employee_id__in=employee_ids,
            is_resolved=False,
        )
        .select_related("employee", "allocation__phone_line__sim_card")
        .order_by("employee_id", "-day", "-id", "allocation_id")
    )

    actions_by_allocation = {}
    latest_action_by_employee = {}
    for action in all_actions:
        allocation_id = (
            action.allocation_id
            if action.allocation and allocation_is_currently_visible(action.allocation)
            else None
        )
        key = (action.employee_id, allocation_id)
        if key not in actions_by_allocation:
            actions_by_allocation[key] = action
        if action.employee_id not in latest_action_by_employee:
            latest_action_by_employee[action.employee_id] = action

    return actions_by_allocation, latest_action_by_employee


def phone_line_is_visible_now(phone_line):
    return bool(
        phone_line
        and not phone_line.is_deleted
        and not phone_line.sim_card.is_deleted
    )


def is_historical_day(day):
    return day < timezone.localdate()


def allocation_is_currently_visible(allocation):
    return bool(
        allocation and allocation.phone_line and phone_line_is_visible_now(allocation.phone_line)
    )


def phone_line_was_visible_at(phone_line, reference_time):
    return bool(
        phone_line
        and (not phone_line.is_deleted or phone_line.updated_at > reference_time)
        and (
            not phone_line.sim_card.is_deleted
            or phone_line.sim_card.updated_at > reference_time
        )
    )


def phone_line_is_visible_for_day(phone_line, day, reference_time):
    if is_historical_day(day):
        return phone_line_was_visible_at(phone_line, reference_time)
    return phone_line_is_visible_now(phone_line)


def get_active_allocations_by_employee(employee_ids):
    active_allocations = (
        LineAllocation.objects.filter(
            is_active=True,
            employee_id__in=employee_ids,
            phone_line__is_deleted=False,
            phone_line__sim_card__is_deleted=False,
        )
        .select_related("phone_line")
        .order_by("employee_id", "-allocated_at")
    )

    allocations_by_employee = defaultdict(list)
    for allocation in active_allocations:
        if allocation.phone_line:
            allocations_by_employee[allocation.employee_id].append(allocation)
    return allocations_by_employee


def should_hide_row_for_admin(row):
    action = row.get("action")
    allocation = row.get("allocation")
    if allocation:
        return (
            allocation.line_status == LineAllocation.LineStatus.ACTIVE
            and (not action or not action.action_type)
        )

    return (
        row["employee"].line_status == Employee.LineStatus.ACTIVE
        and (not action or not action.action_type)
    )


def apply_action_board_visibility_rules(rows, user):
    if user.role != SystemUser.Role.ADMIN:
        return rows
    return [row for row in rows if not should_hide_row_for_admin(row)]


def build_daily_user_action_rows(
    employees_qs, user, include_forms=False, form_day=None
):
    employees = list(employees_qs)
    employee_ids = [employee.id for employee in employees]
    actions_by_allocation, latest_action_by_employee = get_unresolved_action_maps(
        employee_ids
    )
    allocations_by_employee = get_active_allocations_by_employee(employee_ids)
    form_day = form_day or timezone.localdate()

    rows = []
    for employee in employees:
        allocations = allocations_by_employee.get(employee.id, [])
        employee_level_action = actions_by_allocation.get((employee.id, None))
        if allocations:
            for allocation in allocations:
                action = actions_by_allocation.get((employee.id, allocation.id))
                if (
                    not action
                    and len(allocations) == 1
                    and employee_level_action
                    and employee_level_action.action_type
                    == DailyUserAction.ActionType.RECONNECT_WHATSAPP
                ):
                    action = employee_level_action
                row = {
                    "employee": employee,
                    "allocation": allocation,
                    "has_line": True,
                    "action": action,
                }
                if include_forms:
                    row["line_number"] = allocation.phone_line.phone_number
                    row["form"] = DailyUserActionForm(
                        initial={
                            "day": form_day,
                            "employee_id": employee.id,
                            "allocation_id": allocation.id,
                            "action_type": action.action_type if action else "",
                            "note": action.note if action else "",
                            "line_status": allocation.line_status,
                        }
                    )
                rows.append(row)
            continue

        action = employee_level_action
        if not action:
            action = latest_action_by_employee.get(employee.id)

        row = {
            "employee": employee,
            "allocation": None,
            "has_line": False,
            "action": action,
        }
        if include_forms:
            row["line_number"] = None
            row["form"] = DailyUserActionForm(
                initial={
                    "day": form_day,
                    "employee_id": employee.id,
                    "allocation_id": None,
                    "action_type": action.action_type if action else "",
                    "note": action.note if action else "",
                    "line_status": employee.line_status,
                }
            )
        rows.append(row)

    return apply_action_board_visibility_rules(rows, user)


def count_visible_pending_actions(rows):
    return {
        "new_number": sum(
            1
            for row in rows
            if row.get("action")
            and row["action"].action_type == DailyUserAction.ActionType.NEW_NUMBER
        ),
        "reconnect_whatsapp": sum(
            1
            for row in rows
            if row.get("action")
            and row["action"].action_type
            == DailyUserAction.ActionType.RECONNECT_WHATSAPP
        ),
    }


def count_admin_resolved_reconnect_actions(user):
    employees_qs = get_supervised_employees_queryset(user).filter(
        status=Employee.Status.ACTIVE,
        is_deleted=False,
    )
    employee_ids = employees_qs.values_list("id", flat=True)
    return get_admin_resolved_reconnect_actions_queryset(
        timezone.localdate(), employee_ids
    ).count()


def get_admin_resolved_reconnect_actions_queryset(day, employee_ids=None):
    queryset = DailyUserAction.objects.filter(
        day=day,
        action_type=DailyUserAction.ActionType.RECONNECT_WHATSAPP,
        is_resolved=True,
        updated_by__role=SystemUser.Role.ADMIN,
        updated_at__date=day,
    ).select_related("employee", "allocation__phone_line__sim_card")

    if employee_ids is not None:
        queryset = queryset.filter(employee_id__in=employee_ids)

    return queryset.order_by("-updated_at", "-id")


def build_admin_resolved_reconnect_numbers_for_day(day):
    actions = list(get_admin_resolved_reconnect_actions_queryset(day))
    details = []

    for action in actions:
        action_reference_time = action.updated_at or timezone.make_aware(
            datetime.combine(day, time.min)
        )
        allocation = action.allocation
        if not allocation:
            active_allocations = list(
                LineAllocation.objects.filter(
                    employee=action.employee,
                    allocated_at__lte=action_reference_time,
                )
                .filter(
                    Q(released_at__isnull=True) | Q(released_at__gt=action_reference_time)
                )
                .select_related("phone_line__sim_card")
                .order_by("-allocated_at")[:2]
            )
            active_allocations = [
                item
                for item in active_allocations
                if phone_line_is_visible_for_day(
                    item.phone_line, day, action_reference_time
                )
            ]
            if len(active_allocations) == 1:
                allocation = active_allocations[0]

        if (
            not allocation
            or not allocation.phone_line
            or not phone_line_is_visible_for_day(
                allocation.phone_line, day, action_reference_time
            )
        ):
            continue

        details.append(
            {
                "numero": allocation.phone_line.phone_number,
                "usuario": action.employee.full_name,
                "carteira": action.employee.employee_id,
            }
        )

    return details


def build_reconnected_numbers_for_day(day):
    start_of_day = timezone.make_aware(datetime.combine(day, time.min))
    reconnected_allocations = list(
        DailyIndicatorService.get_reconnected_allocations_queryset(day)
        .select_related("employee", "phone_line__sim_card")
        .order_by("allocated_at")
    )
    reconnected_numbers = [
        {
            "numero": allocation.phone_line.phone_number,
            "usuario": allocation.employee.full_name,
            "carteira": allocation.employee.employee_id,
        }
        for allocation in reconnected_allocations
        if allocation.phone_line
        and phone_line_is_visible_for_day(
            allocation.phone_line,
            day,
            allocation.allocated_at or start_of_day,
        )
    ]
    reconnected_numbers.extend(build_admin_resolved_reconnect_numbers_for_day(day))
    return reconnected_numbers


def get_visible_phone_lines_for_day(day):
    queryset = PhoneLine.all_objects.filter(created_at__date__lte=day)
    if is_historical_day(day):
        end_of_day = timezone.make_aware(datetime.combine(day, time.max))
        return queryset.filter(
            DailyIndicatorService.build_visible_phone_line_q(end_of_day)
        )
    return queryset.filter(is_deleted=False, sim_card__is_deleted=False)


def get_visible_employees_for_day(day):
    queryset = Employee.all_objects.filter(created_at__date__lte=day)
    if is_historical_day(day):
        end_of_day = timezone.make_aware(datetime.combine(day, time.max))
        return queryset.filter(Q(is_deleted=False) | Q(updated_at__gt=end_of_day))
    return queryset.filter(is_deleted=False)


def get_open_action_for_resolution(employee, allocation_id=None):
    unresolved_actions = DailyUserAction.objects.filter(
        employee=employee,
        is_resolved=False,
    ).order_by("-day", "-id")

    if allocation_id:
        action = unresolved_actions.filter(allocation_id=allocation_id).first()
        if action:
            return action

        allocation = LineAllocation.objects.filter(
            pk=allocation_id,
            employee=employee,
            is_active=True,
            phone_line__is_deleted=False,
            phone_line__sim_card__is_deleted=False,
        ).first()
        if allocation:
            active_allocations_count = LineAllocation.objects.filter(
                employee=employee,
                is_active=True,
                phone_line__is_deleted=False,
                phone_line__sim_card__is_deleted=False,
            ).count()
            if active_allocations_count == 1:
                return unresolved_actions.filter(
                    allocation__isnull=True,
                    action_type=DailyUserAction.ActionType.RECONNECT_WHATSAPP,
                ).first()

        return None

    return unresolved_actions.filter(allocation__isnull=True).first()


def build_number_details_for_day(
    day: date, base_lines, allocated_line_ids
) -> tuple[list[str], list[dict], list[dict], list[str]]:
    """Build detailed number allocations for a specific day."""
    start_of_day = timezone.make_aware(datetime.combine(day, time.min))
    available_numbers = list(
        base_lines.exclude(id__in=allocated_line_ids)
        .order_by("phone_number")
        .values_list("phone_number", flat=True)
    )

    delivered_allocations = list(
        LineAllocation.objects.filter(allocated_at__date=day)
        .select_related("employee", "phone_line__sim_card")
        .order_by("allocated_at")
    )
    delivered_numbers = [
        {
            "numero": allocation.phone_line.phone_number,
            "usuario": allocation.employee.full_name,
            "carteira": allocation.employee.employee_id,
        }
        for allocation in delivered_allocations
        if allocation.phone_line
        and phone_line_is_visible_for_day(
            allocation.phone_line,
            day,
            allocation.allocated_at or start_of_day,
        )
    ]

    reconnected_numbers = build_reconnected_numbers_for_day(day)

    new_lines = list(
        PhoneLine.all_objects.filter(created_at__date=day)
        .select_related("sim_card")
        .order_by("phone_number")
    )
    new_numbers = [
        line.phone_number
        for line in new_lines
        if phone_line_is_visible_for_day(line, day, line.created_at or start_of_day)
    ]
    return available_numbers, delivered_numbers, reconnected_numbers, new_numbers


def build_user_details_for_day(
    employees, active_allocations
) -> tuple[list[dict], list[str], list[dict], list[dict]]:
    """Build user details and allocation status for a specific day."""
    allocations_by_employee = {}
    allocations_for_day = active_allocations.select_related(
        "employee", "phone_line"
    ).order_by("employee_id", "-allocated_at")
    for allocation in allocations_for_day:
        if allocation.employee_id not in allocations_by_employee:
            allocations_by_employee[allocation.employee_id] = allocation

    users = []
    for employee in employees.order_by("full_name"):
        allocation = allocations_by_employee.get(employee.id)
        line = "-"
        if allocation and allocation.phone_line:
            line = allocation.phone_line.phone_number

        portfolio_name = normalize_portfolio_name(employee.employee_id)
        if portfolio_name in B2B_PORTFOLIO_NAMES:
            segment = "B2B"
        elif portfolio_name in B2C_PORTFOLIO_NAMES:
            segment = "B2C"
        else:
            segment = "Nao classificado"

        users.append(
            {
                "nome": employee.full_name,
                "equipe": employee.teams,
                "carteira": employee.employee_id,
                "linha": line,
                "segmento": segment,
                "sem_whats": allocation is None,
            }
        )

    logged_users = [
        employee.full_name
        for employee in employees.filter(status=Employee.Status.ACTIVE).order_by(
            "full_name"
        )
    ]
    users_with_line = [user for user in users if not user["sem_whats"]]
    users_without_line = [user for user in users if user["sem_whats"]]
    return users, logged_users, users_with_line, users_without_line


def build_indicator_for_day(day: date, include_users: bool = False) -> dict:
    """Calculate all indicators for a specific day from database state."""
    end_of_day = timezone.make_aware(datetime.combine(day, time.max))
    employees = get_visible_employees_for_day(day)
    active_employees = employees.filter(status=Employee.Status.ACTIVE)

    active_allocations = LineAllocation.objects.filter(allocated_at__lte=end_of_day)
    if is_historical_day(day):
        active_allocations = active_allocations.filter(
            DailyIndicatorService.build_visible_phone_line_q(
                end_of_day, prefix="phone_line__"
            )
        )
    else:
        active_allocations = active_allocations.filter(
            phone_line__is_deleted=False,
            phone_line__sim_card__is_deleted=False,
        )
    active_allocations = active_allocations.filter(
        Q(released_at__isnull=True) | Q(released_at__gt=end_of_day)
    )

    allocated_employee_ids = active_allocations.values_list(
        "employee_id", flat=True
    ).distinct()
    employees_without_whats = active_employees.exclude(id__in=allocated_employee_ids)

    total_negociadores = active_employees.count()
    sem_whats = employees_without_whats.count()
    perc_sem_whats = (sem_whats / total_negociadores * 100) if total_negociadores else 0

    base_lines = get_visible_phone_lines_for_day(day).filter(
        status=PhoneLine.Status.AVAILABLE,
    )
    allocated_line_ids = active_allocations.values_list(
        "phone_line_id", flat=True
    ).distinct()
    reconnected_numbers = build_reconnected_numbers_for_day(day)
    sem_whats_portfolios = employees_without_whats.values_list("employee_id", flat=True)
    b2b_sem_whats = 0
    b2c_sem_whats = 0
    for portfolio_name in sem_whats_portfolios:
        normalized = normalize_portfolio_name(portfolio_name)
        if normalized in B2B_PORTFOLIO_NAMES:
            b2b_sem_whats += 1
        elif normalized in B2C_PORTFOLIO_NAMES:
            b2c_sem_whats += 1

    available_numbers, delivered_numbers, _, new_numbers = build_number_details_for_day(
        day, base_lines, allocated_line_ids
    )
    numeros_disponiveis = len(available_numbers)
    numeros_entregues = len(delivered_numbers)
    reconectados = len(reconnected_numbers)
    novos = len(new_numbers)

    indicator = {
        "data": day,
        "pessoas_logadas": employees.filter(status=Employee.Status.ACTIVE).count(),
        "perc_sem_whats": perc_sem_whats,
        "b2b_sem_whats": b2b_sem_whats,
        "b2c_sem_whats": b2c_sem_whats,
        "numeros_disponiveis": numeros_disponiveis,
        "numeros_entregues": numeros_entregues,
        "reconectados": reconectados,
        "novos": novos,
        "total_descoberto_dia": sem_whats,
        "available_numbers": available_numbers,
        "delivered_numbers": delivered_numbers,
        "reconnected_numbers": reconnected_numbers,
        "new_numbers": new_numbers,
    }

    if not include_users:
        return indicator

    users, logged_users, users_with_line, users_without_line = (
        build_user_details_for_day(active_employees, active_allocations)
    )

    indicator["users"] = users
    indicator["logged_users"] = logged_users
    indicator["users_with_line"] = users_with_line
    indicator["users_without_line"] = users_without_line
    return indicator


def _serialize_snapshot_indicator(snapshot: DashboardDailySnapshot) -> dict:
    return {
        "data": snapshot.date,
        "pessoas_logadas": snapshot.people_logged_in,
        "perc_sem_whats": snapshot.percentage_without_whatsapp,
        "b2b_sem_whats": snapshot.b2b_without_whatsapp,
        "b2c_sem_whats": snapshot.b2c_without_whatsapp,
        "numeros_disponiveis": snapshot.numbers_available,
        "numeros_entregues": snapshot.numbers_delivered,
        "reconectados": snapshot.numbers_reconnected,
        "novos": snapshot.numbers_new,
        "total_descoberto_dia": snapshot.total_uncovered_day,
        "available_numbers": [],
        "delivered_numbers": [],
        "reconnected_numbers": [],
        "new_numbers": [],
    }


def persist_dashboard_snapshot_for_day(day: date) -> dict:
    indicator = build_indicator_for_day(day)
    snapshot_defaults = {
        "people_logged_in": int(indicator["pessoas_logadas"]),
        "percentage_without_whatsapp": float(indicator["perc_sem_whats"]),
        "b2b_without_whatsapp": int(indicator["b2b_sem_whats"]),
        "b2c_without_whatsapp": int(indicator["b2c_sem_whats"]),
        "numbers_available": int(indicator["numeros_disponiveis"]),
        "numbers_delivered": int(indicator["numeros_entregues"]),
        "numbers_reconnected": int(indicator["reconectados"]),
        "numbers_new": int(indicator["novos"]),
        "total_uncovered_day": int(indicator["total_descoberto_dia"]),
    }
    DashboardDailySnapshot.objects.update_or_create(
        date=day,
        defaults=snapshot_defaults,
    )
    return indicator


def get_or_create_dashboard_snapshot_for_day(day: date) -> DashboardDailySnapshot:
    if is_historical_day(day):
        snapshot = DashboardDailySnapshot.objects.filter(date=day).first()
        if snapshot is not None:
            return snapshot

    persist_dashboard_snapshot_for_day(day)
    return DashboardDailySnapshot.objects.get(date=day)


def get_dashboard_indicator_for_day(day: date) -> dict:
    if is_historical_day(day):
        snapshot = get_or_create_dashboard_snapshot_for_day(day)
        return _serialize_snapshot_indicator(snapshot)

    persist_dashboard_snapshot_for_day(day)
    snapshot = DashboardDailySnapshot.objects.get(date=day)
    return _serialize_snapshot_indicator(snapshot)


def serialize_daily_indicator(item):
    date_iso = item["data"].strftime("%Y-%m-%d")
    return {
        "data": item["data"].strftime("%d/%m/%Y"),
        "date_iso": date_iso,
        "pessoas_logadas": int(item.get("pessoas_logadas", 0) or 0),
        "perc_sem_whats": float(item.get("perc_sem_whats", 0) or 0),
        "b2b_sem_whats": int(item.get("b2b_sem_whats", 0) or 0),
        "b2c_sem_whats": int(item.get("b2c_sem_whats", 0) or 0),
        "numeros_disponiveis": int(item.get("numeros_disponiveis", 0) or 0),
        "numeros_entregues": int(item.get("numeros_entregues", 0) or 0),
        "reconectados": int(item.get("reconectados", 0) or 0),
        "novos": int(item.get("novos", 0) or 0),
        "total_descoberto_dia": int(item.get("total_descoberto_dia", 0) or 0),
        "detail_url": reverse(
            "daily_indicator_day_breakdown", kwargs={"day": date_iso}
        ),
    }


def get_daily_indicators_payload(days):
    daily = DashboardView()._build_daily_indicators(days=days)
    rows = [serialize_daily_indicator(item) for item in daily]
    base = "|".join(
        [",".join(str(row[key]) for key in sorted(row.keys())) for row in rows]
    )
    fingerprint = hashlib.md5(base.encode("utf-8")).hexdigest()
    return rows, fingerprint


def normalize_portfolio_name(value):
    """Normalize portfolio name by removing diacritics and converting to lowercase."""
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", str(value))
    without_diacritics = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return " ".join(without_diacritics.strip().lower().split())


class DashboardView(AuthenticadView, TemplateView):
    template_name = "dashboard/dashboard.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.role == SystemUser.Role.DEV:
            return redirect("telecom:blip_configuration_list")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        trend_period = self._resolve_trend_period()
        context["snapshot_report_date"] = self.request.GET.get(
            "snapshot_report_date", timezone.localdate().isoformat()
        )
        context["total_employees"] = Employee.objects.filter(
            status=Employee.Status.ACTIVE
        ).count()
        context["total_lines"] = PhoneLine.objects.filter(is_deleted=False).count()
        context["allocated_lines"] = LineAllocation.objects.filter(
            is_active=True
        ).count()
        context["available_lines"] = PhoneLine.objects.filter(
            is_deleted=False,
            status=PhoneLine.Status.AVAILABLE,
        ).count()
        context["total_simcards"] = SIMcard.objects.filter(is_deleted=False).count()

        context.update(self._build_status_counts())
        context["indicadores_diarios"] = self._build_daily_indicators(days=trend_period)
        context["trend_period"] = trend_period
        context.update(self._build_dashboard_insights(context))
        return context

    def _resolve_trend_period(self):
        raw_period = self.request.GET.get("period", str(DEFAULT_TREND_PERIOD))
        return resolve_trend_period(raw_period)

    def _build_dashboard_insights(self, context):  # noqa: PLR0912, PLR0915
        daily = context.get("indicadores_diarios", [])
        latest = daily[-1] if daily else {}
        employees_qs = get_supervised_employees_queryset(self.request.user).filter(
            status=Employee.Status.ACTIVE, is_deleted=False
        )
        rows = build_daily_user_action_rows(employees_qs, self.request.user)
        action_counts = count_visible_pending_actions(rows)
        pending_new_number_count = action_counts["new_number"]
        pending_reconnect_whatsapp_count = action_counts["reconnect_whatsapp"]
        action_board_url = reverse("daily_user_action_board")

        latest_sem_whats = float(latest.get("perc_sem_whats", 0) or 0)
        latest_descoberto = int(latest.get("total_descoberto_dia", 0) or 0)
        latest_reconectados = int(latest.get("reconectados", 0) or 0)
        reconectados_exception_value = latest_reconectados

        line_status_map = {
            entry["value"]: int(entry.get("count", 0))
            for entry in context.get("line_status_counts", [])
        }
        blocked_lines = line_status_map.get("suspended", 0) + line_status_map.get(
            "cancelled", 0
        )

        def level_for_percentage(value):
            if value >= PERCENT_CRITICAL_THRESHOLD:
                return "critical"
            if value >= PERCENT_WARNING_THRESHOLD:
                return "warning"
            return "ok"

        def level_for_count(value):
            if value >= COUNT_CRITICAL_THRESHOLD:
                return "critical"
            if value >= COUNT_WARNING_THRESHOLD:
                return "warning"
            return "ok"

        exception_cards = [
            {
                "title": "Cobertura Whats",
                "value": f"{latest_sem_whats:.1f}%",
                "description": "Percentual da equipe sem linha ativa.",
                "level": level_for_percentage(latest_sem_whats),
                "action_label": "Ver usuários",
                "action_url": "/employees/",
            },
            {
                "title": "Linhas bloqueadas",
                "value": blocked_lines,
                "description": "Linhas suspensas ou canceladas no inventário.",
                "level": level_for_count(blocked_lines),
                "action_label": "Ver telecom",
                "action_url": "/telecom/",
            },
            {
                "title": "Pendêcia - Número Novo",
                "value": pending_new_number_count,
                "description": "Pendências marcadas como precisa número novo.",
                "level": level_for_count(pending_new_number_count),
                "action_label": "Ver pendências",
                "action_url": action_board_url,
            },
            {
                "title": "Pendêcia - Reconexão Whats",
                "value": pending_reconnect_whatsapp_count,
                "description": "Pendências marcadas como precisa reconectar WhatsApp.",
                "level": level_for_count(pending_reconnect_whatsapp_count),
                "action_label": "Ver pendências",
                "action_url": action_board_url,
            },
            {
                "title": "Descobertos hoje",
                "value": latest_descoberto,
                "description": "Usuários sem linha no fechamento do dia.",
                "level": level_for_count(latest_descoberto),
                "action_label": "Ir para cadastro",
                "action_url": "/allocations/",
            },
            {
                "title": "Reconectados hoje",
                "value": reconectados_exception_value,
                "description": "Recuperações efetivas no dia atual.",
                "level": "ok" if reconectados_exception_value > 0 else "warning",
                "action_label": "Detalhar telecom",
                "action_url": "/telecom/",
            },
        ]

        return {
            "exception_cards": exception_cards,
        }

    def _build_negociador_data(self):
        employees = Employee.objects.filter(is_deleted=False)
        active_allocated_employee_ids = set(
            LineAllocation.objects.filter(is_active=True).values_list(
                "employee_id", flat=True
            )
        )

        return [
            {
                "supervisor": emp.teams,
                "negociador": emp.full_name,
                "sem_whats": emp.id not in active_allocated_employee_ids,
                "carteira": getattr(emp, "carteira", "-"),
                "unidade": getattr(emp, "unidade", "-"),
                "pa": getattr(emp, "pa", "-"),
                "status": emp.get_status_display(),
            }
            for emp in employees
        ]

    def _build_daily_indicators(self, days: int):
        today = timezone.localdate()
        indicators = []

        for offset in range(days - 1, -1, -1):
            day = today - timedelta(days=offset)
            indicators.append(self._build_indicator_for_day(day))

        return indicators

    def _build_indicator_for_day(self, day):
        return get_dashboard_indicator_for_day(day)

    def _build_status_counts(self):
        sim_counts = defaultdict(int)
        line_counts = defaultdict(int)

        for row in (
            SIMcard.objects.filter(is_deleted=False)
            .values("status")
            .annotate(count=Count("id"))
        ):
            sim_counts[row["status"]] = row["count"]

        for row in (
            PhoneLine.objects.filter(is_deleted=False)
            .values("status")
            .annotate(count=Count("id"))
        ):
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


class ManagerDashboardView(RoleRequiredMixin, TemplateView):
    allowed_roles = [SystemUser.Role.GERENTE]
    template_name = "dashboard/manager_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        grouped = {
            supervisor_email: {
                "supervisor": supervisor_email,
                "rows": {},
                "total_logged": 0,
                "total_with_line": 0,
                "total_without_line": 0,
                "total_reconnect": 0,
                "total_new_number": 0,
            }
            for supervisor_email in sorted(
                self.request.user.get_managed_supervisor_emails()
            )
        }

        employees = get_supervised_employees_queryset(self.request.user).filter(
            is_deleted=False,
        )
        active_allocated_employee_ids = set(
            LineAllocation.objects.filter(
                is_active=True,
                employee_id__in=employees.values_list("id", flat=True),
            ).values_list("employee_id", flat=True)
        )
        for employee in employees:
            supervisor = employee.corporate_email or "Sem supervisor"
            portfolio = employee.employee_id or "Sem carteira"
            supervisor_group = grouped.setdefault(
                supervisor,
                {
                    "supervisor": supervisor,
                    "rows": {},
                    "total_logged": 0,
                    "total_with_line": 0,
                    "total_without_line": 0,
                    "total_reconnect": 0,
                    "total_new_number": 0,
                },
            )
            row = supervisor_group["rows"].setdefault(
                portfolio,
                {
                    "portfolio": portfolio,
                    "logged_count": 0,
                    "with_line_count": 0,
                    "without_line_count": 0,
                    "reconnect_count": 0,
                    "new_number_count": 0,
                },
            )
            is_active_employee = employee.status == Employee.Status.ACTIVE
            if not is_active_employee:
                continue

            is_logged = True
            has_line = employee.id in active_allocated_employee_ids

            if is_logged:
                row["logged_count"] += 1
                supervisor_group["total_logged"] += 1
            if has_line:
                row["with_line_count"] += 1
                supervisor_group["total_with_line"] += 1
            else:
                row["without_line_count"] += 1
                supervisor_group["total_without_line"] += 1

        for action in get_latest_unresolved_actions_queryset(self.request.user):
            employee = action.employee
            if employee.status != Employee.Status.ACTIVE:
                continue
            supervisor = employee.corporate_email or "Sem supervisor"
            portfolio = employee.employee_id or "Sem carteira"

            supervisor_group = grouped.setdefault(
                supervisor,
                {
                    "supervisor": supervisor,
                    "rows": {},
                    "total_logged": 0,
                    "total_with_line": 0,
                    "total_without_line": 0,
                    "total_reconnect": 0,
                    "total_new_number": 0,
                },
            )
            row = supervisor_group["rows"].setdefault(
                portfolio,
                {
                    "portfolio": portfolio,
                    "logged_count": 0,
                    "with_line_count": 0,
                    "without_line_count": 0,
                    "reconnect_count": 0,
                    "new_number_count": 0,
                },
            )

            if action.action_type == DailyUserAction.ActionType.RECONNECT_WHATSAPP:
                row["reconnect_count"] += 1
                supervisor_group["total_reconnect"] += 1
            elif action.action_type == DailyUserAction.ActionType.NEW_NUMBER:
                row["new_number_count"] += 1
                supervisor_group["total_new_number"] += 1

        supervisor_dashboards = []
        for supervisor_name in sorted(grouped.keys()):
            supervisor_group = grouped[supervisor_name]
            rows = sorted(
                supervisor_group["rows"].values(),
                key=lambda item: item["portfolio"].lower(),
            )
            supervisor_group["rows"] = rows
            supervisor_dashboards.append(supervisor_group)

        context["supervisor_dashboards"] = supervisor_dashboards
        return context


@login_required
@roles_required(*DASHBOARD_ALLOWED_ROLES)
def daily_indicator_entry(request):
    """
    View para supervisores inserirem indicadores diários.
    Apenas o campo "Pessoas Logadas" é preenchido manualmente.
    Os demais indicadores são calculados automaticamente.
    """
    if request.method == "POST":
        form = DailyIndicatorForm(request.POST)
        if form.is_valid():
            indicator = form.save(commit=False)
            indicator.created_by = request.user
            indicator.updated_by = request.user
            indicator.save()

            # Disparar cálculo automático dos outros indicadores
            DailyIndicatorService.populate_daily_indicators(indicator.date)

            msg = f"Indicador para {indicator.supervisor} registrado com sucesso!"
            messages.success(request, msg)
            return redirect("daily_indicator_management")
    else:
        form = DailyIndicatorForm()

    context = {
        "form": form,
        "title": "Registrar Indicador Diário",
        "b2b_supervisors": B2B_SUPERVISORS,
        "b2b_portfolios": B2B_PORTFOLIOS,
        "b2c_supervisors": B2C_SUPERVISORS,
        "b2c_portfolios": B2C_PORTFOLIOS,
    }
    return render(request, "dashboard/daily_indicator_form.html", context)


@login_required
@roles_required(*DASHBOARD_ALLOWED_ROLES)
def daily_indicator_management(request):
    """
    View para visualizar e gerenciar todos os indicadores diários.
    Permite filtrar por supervisor, carteira, segmento e período.
    """
    filter_form = DailyIndicatorFilterForm(request.GET or None)
    indicators = get_daily_indicators_queryset(request.user)

    if filter_form.is_valid():
        segment = filter_form.cleaned_data.get("segment")
        supervisor = filter_form.cleaned_data.get("supervisor")
        portfolio = filter_form.cleaned_data.get("portfolio")
        date_from = filter_form.cleaned_data.get("date_from")
        date_to = filter_form.cleaned_data.get("date_to")

        if segment:
            indicators = indicators.filter(segment=segment)
        if supervisor:
            indicators = indicators.filter(supervisor__icontains=supervisor)
        if portfolio:
            indicators = indicators.filter(portfolio__icontains=portfolio)
        if date_from:
            indicators = indicators.filter(date__gte=date_from)
        if date_to:
            indicators = indicators.filter(date__lte=date_to)

    # Paginação
    from django.core.paginator import Paginator

    paginator = Paginator(indicators.order_by("-date"), 50)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    # Calcular resumo do período
    if filter_form.is_valid():
        date_from = filter_form.cleaned_data.get("date_from")
        date_to = filter_form.cleaned_data.get("date_to")
        segment = filter_form.cleaned_data.get("segment") or None

        if date_from and date_to:
            summary = DailyIndicatorService.get_summary_for_period(
                date_from, date_to, segment
            )
        else:
            summary = {}
    else:
        summary = {}

    context = {
        "filter_form": filter_form,
        "page_obj": page_obj,
        "indicators": page_obj,
        "summary": summary,
        "title": "Gestão de Indicadores Diários",
    }
    return render(request, "dashboard/daily_indicator_management.html", context)


@login_required
@roles_required(*DASHBOARD_ALLOWED_ROLES)
def daily_indicator_legacy_redirect(request, *args, **kwargs):
    return redirect("daily_user_action_board")


@login_required
@roles_required(*DASHBOARD_ALLOWED_ROLES)
def daily_indicator_detail(request, pk):
    """
    View para visualizar detalhes de um indicador específico.
    """
    indicator = get_object_or_404(get_daily_indicators_queryset(request.user), pk=pk)

    context = {
        "indicator": indicator,
        "title": f"Indicador - {indicator.supervisor}",
    }
    return render(request, "dashboard/daily_indicator_detail.html", context)


@login_required
@roles_required(*DASHBOARD_ALLOWED_ROLES)
def daily_indicator_edit(request, pk):
    """
    View para editar um indicador existente.
    Apenas o campo "Pessoas Logadas" pode ser editado manualmente.
    """
    indicator = get_object_or_404(get_daily_indicators_queryset(request.user), pk=pk)

    if request.method == "POST":
        form = DailyIndicatorForm(request.POST, instance=indicator)
        if form.is_valid():
            indicator = form.save(commit=False)
            indicator.updated_by = request.user
            indicator.save()

            # Recalcular indicadores automáticos
            DailyIndicatorService.populate_daily_indicators(indicator.date)

            messages.success(request, "Indicador atualizado com sucesso!")
            return redirect("daily_indicator_management")
    else:
        form = DailyIndicatorForm(instance=indicator)

    context = {
        "form": form,
        "indicator": indicator,
        "title": f"Editar Indicador - {indicator.supervisor}",
        "b2b_supervisors": B2B_SUPERVISORS,
        "b2b_portfolios": B2B_PORTFOLIOS,
        "b2c_supervisors": B2C_SUPERVISORS,
        "b2c_portfolios": B2C_PORTFOLIOS,
    }
    return render(request, "dashboard/daily_indicator_form.html", context)


@login_required
@roles_required(*DASHBOARD_ALLOWED_ROLES)
def daily_user_action_board(request):  # noqa: PLR0912, PLR0915
    supervisor_filter = (request.GET.get("supervisor") or "").strip()
    employees_qs = get_supervised_employees_queryset(request.user, supervisor_filter)

    if request.method == "POST":
        form = DailyUserActionForm(request.POST)
        if form.is_valid():
            employee_id = form.cleaned_data["employee_id"]
            allocation_id_str = form.cleaned_data.get("allocation_id", "").strip()
            allocation_id = int(allocation_id_str) if allocation_id_str else None
            action_type = form.cleaned_data.get("action_type") or ""
            note = (form.cleaned_data.get("note") or "").strip()
            employee = employees_qs.filter(pk=employee_id).first()

            if not employee:
                messages.error(
                    request,
                    "Usuario nao encontrado para este supervisor.",
                )
            else:
                if request.user.role == SystemUser.Role.ADMIN:
                    line_status = form.cleaned_data.get("line_status")
                    if line_status and line_status in dict(Employee.LineStatus.choices):
                        if allocation_id:
                            allocation = LineAllocation.objects.filter(
                                pk=allocation_id, employee=employee, is_active=True
                            ).first()
                            if allocation and allocation.line_status != line_status:
                                old_line_status = allocation.get_line_status_display()
                                allocation.line_status = line_status
                                allocation.save(update_fields=["line_status"])
                                new_line_status = allocation.get_line_status_display()
                                PhoneLineHistory.objects.create(
                                    phone_line=allocation.phone_line,
                                    action=PhoneLineHistory.ActionType.STATUS_CHANGED,
                                    old_value=f"Status da linha: {old_line_status}",
                                    new_value=f"Status da linha: {new_line_status}",
                                    changed_by=request.user,
                                    description=(
                                        "Status da linha alterado em Ações do Dia de "
                                        f"{old_line_status} para {new_line_status}"
                                    ),
                                )
                                messages.success(
                                    request,
                                    (
                                        "Status da linha atualizado para "
                                        f"{employee.full_name}."
                                    ),
                                )
                        elif employee.line_status != line_status:
                            employee.line_status = line_status
                            employee.save(update_fields=["line_status"])
                            messages.success(
                                request,
                                (
                                    "Status da linha atualizado para "
                                    f"{employee.full_name}."
                                ),
                            )

                if action_type and action_type not in dict(
                    DailyUserAction.ActionType.choices
                ):
                    messages.error(request, "Tipo de ação inválido.")
                elif not action_type:
                    action = get_open_action_for_resolution(employee, allocation_id)
                    if action:
                        action_label = dict(DailyUserAction.ActionType.choices).get(
                            action.action_type, action.action_type
                        )
                        action.is_resolved = True
                        action.note = note
                        action.updated_by = request.user
                        action.updated_at = timezone.now()
                        action.save(
                            update_fields=[
                                "is_resolved",
                                "note",
                                "updated_by",
                                "updated_at",
                            ]
                        )
                        if action.allocation and action.allocation.phone_line:
                            PhoneLineHistory.objects.create(
                                phone_line=action.allocation.phone_line,
                                action=PhoneLineHistory.ActionType.DAILY_ACTION_CHANGED,
                                old_value=f"Atualizar ação: {action_label}",
                                new_value="Atualizar ação: Sem ação",
                                changed_by=request.user,
                                description=(
                                    "Ação da linha marcada como resolvida em "
                                    "Ações do dia"
                                ),
                            )
                        messages.success(
                            request,
                            f"Ação marcada como resolvida para {employee.full_name}.",
                        )
                    else:
                        messages.info(
                            request,
                            (
                                "Nenhuma ação aberta para resolver para "
                                f"{employee.full_name}."
                            ),
                        )
                else:
                    allocation_obj = None
                    if allocation_id:
                        allocation_obj = LineAllocation.objects.filter(
                            pk=allocation_id, employee=employee, is_active=True
                        ).first()

                    update_or_create_filter = {
                        "day": timezone.localdate(),
                        "employee": employee,
                        "allocation": allocation_obj,
                    }

                    existing_action = DailyUserAction.objects.filter(
                        **update_or_create_filter
                    ).first()
                    previous_action_type = (
                        existing_action.action_type if existing_action else ""
                    )
                    previous_note = (
                        (existing_action.note or "") if existing_action else ""
                    )

                    action, created = DailyUserAction.objects.update_or_create(
                        **update_or_create_filter,
                        defaults={
                            "supervisor": request.user,
                            "action_type": action_type,
                            "note": note,
                            "updated_by": request.user,
                            "created_by": request.user,
                            "is_resolved": False,
                        },
                    )
                    previous_action_label = dict(
                        DailyUserAction.ActionType.choices
                    ).get(previous_action_type, "Sem ação")
                    current_action_label = dict(DailyUserAction.ActionType.choices).get(
                        action_type, action_type
                    )
                    if (
                        allocation_obj
                        and allocation_obj.phone_line
                        and (
                            created
                            or previous_action_type != action_type
                            or previous_note != note
                        )
                    ):
                        PhoneLineHistory.objects.create(
                            phone_line=allocation_obj.phone_line,
                            action=PhoneLineHistory.ActionType.DAILY_ACTION_CHANGED,
                            old_value=f"Atualizar acao: {previous_action_label}",
                            new_value=f"Atualizar acao: {current_action_label}",
                            changed_by=request.user,
                            description=(
                                "Ação da linha criada/atualizada em Ações do dia"
                            ),
                        )
                    verb = "criada" if created else "atualizada"
                    messages.success(
                        request,
                        f"Ação {verb} para {action.employee.full_name}.",
                    )
        else:
            messages.error(request, "Não foi possível salvar a ação.")

        query = {}
        if supervisor_filter:
            query["supervisor"] = supervisor_filter
        return redirect(f"{reverse('daily_user_action_board')}?{urlencode(query)}")

    rows = build_daily_user_action_rows(
        employees_qs,
        request.user,
        include_forms=True,
        form_day=timezone.localdate(),
    )
    action_counts = count_visible_pending_actions(rows)

    context = {
        "title": "Ações do Dia",
        "rows": rows,
        "action_counts": action_counts,
        "supervisor_filter": supervisor_filter,
        "is_supervisor_role": request.user.is_supervisor_role,
        "is_admin_role": (request.user.role or "").lower() == "admin",
    }
    return render(request, "dashboard/daily_user_action_board.html", context)


@login_required
@roles_required(*DASHBOARD_ALLOWED_ROLES)
def daily_indicators_live(request):
    period = resolve_trend_period(request.GET.get("period", DEFAULT_TREND_PERIOD))
    rows, fingerprint = get_daily_indicators_payload(days=period)
    return JsonResponse(
        {
            "period": period,
            "rows": rows,
            "fingerprint": fingerprint,
            "generated_at": timezone.now().isoformat(),
        }
    )


@login_required
@roles_required(*DASHBOARD_ALLOWED_ROLES)
def dashboard_daily_snapshot_report(request):
    selected_day = resolve_day(request.GET.get("date"))
    snapshot = get_or_create_dashboard_snapshot_for_day(selected_day)

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    filename = selected_day.strftime("snapshot_diario_%Y%m%d.csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")

    rows = [
        [
            "Data",
            "Pessoas Logadas",
            "% sem Whats",
            "B2B sem Whats",
            "B2C sem Whats",
            "Números Disponíveis",
            "Números Entregues",
            "Reconectados",
            "Novos",
            "Total Descoberto DIA",
        ],
        [
            selected_day.strftime("%d/%m/%Y"),
            snapshot.people_logged_in,
            f"{snapshot.percentage_without_whatsapp:.2f}",
            snapshot.b2b_without_whatsapp,
            snapshot.b2c_without_whatsapp,
            snapshot.numbers_available,
            snapshot.numbers_delivered,
            snapshot.numbers_reconnected,
            snapshot.numbers_new,
            snapshot.total_uncovered_day,
        ],
    ]

    import csv

    writer = csv.writer(response)
    writer.writerows(rows)
    return response


@login_required
@roles_required(*DASHBOARD_ALLOWED_ROLES)
def daily_indicator_day_breakdown(request, day):
    try:
        selected_day = datetime.strptime(day, "%Y-%m-%d").date()
    except ValueError as exc:
        raise Http404("Data invalida.") from exc

    indicator = build_indicator_for_day(selected_day, include_users=True)
    context = {
        "title": f"Detalhes dos Indicadores - {selected_day.strftime('%d/%m/%Y')}",
        "selected_day": selected_day,
        "indicator": indicator,
        "users": indicator.get("users", []),
    }
    return render(request, "dashboard/daily_indicator_day_breakdown.html", context)

