import hashlib
import unicodedata
from collections import defaultdict
from datetime import datetime, time, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Q
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from allocations.models import LineAllocation
from core.mixins import AuthenticadView
from core.services.daily_indicator_service import DailyIndicatorService
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard

from .forms import (
    B2B_PORTFOLIOS,
    B2B_SUPERVISORS,
    B2C_PORTFOLIOS,
    B2C_SUPERVISORS,
    DailyIndicatorFilterForm,
    DailyIndicatorForm,
    DailyUserActionForm,
)
from .models import DailyIndicator, DailyUserAction

PERCENT_CRITICAL_THRESHOLD = 20
PERCENT_WARNING_THRESHOLD = 10
COUNT_CRITICAL_THRESHOLD = 10
COUNT_WARNING_THRESHOLD = 5
DEFAULT_TREND_PERIOD = 7
ALLOWED_TREND_PERIODS = (7, 15, 30)


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
    employees = Employee.objects.filter(is_deleted=False)
    role = (getattr(user, "role", "") or "").lower()
    if role == "super":
        employees = employees.filter(corporate_email__iexact=user.email)
    elif supervisor_filter:
        employees = employees.filter(corporate_email__icontains=supervisor_filter)
    return employees.order_by("full_name")


def build_number_details_for_day(day, base_lines, allocated_line_ids):
    available_numbers = list(
        base_lines.exclude(id__in=allocated_line_ids)
        .order_by("phone_number")
        .values_list("phone_number", flat=True)
    )

    delivered_allocations = list(
        LineAllocation.objects.filter(allocated_at__date=day)
        .select_related("employee", "phone_line")
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
    ]

    reconnected_allocations = list(
        LineAllocation.objects.filter(allocated_at__date=day)
        .filter(phone_line__allocations__released_at__lt=F("allocated_at"))
        .select_related("employee", "phone_line")
        .distinct()
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
    ]

    new_numbers = list(
        PhoneLine.objects.filter(created_at__date=day, is_deleted=False)
        .order_by("phone_number")
        .values_list("phone_number", flat=True)
    )
    return available_numbers, delivered_numbers, reconnected_numbers, new_numbers


def build_user_details_for_day(employees, active_allocations):
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


def build_indicator_for_day(day, include_users=False):
    end_of_day = timezone.make_aware(datetime.combine(day, time.max))
    employees = Employee.objects.filter(is_deleted=False, created_at__date__lte=day)
    active_employees = employees.filter(status=Employee.Status.ACTIVE)

    active_allocations = LineAllocation.objects.filter(allocated_at__lte=end_of_day)
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

    base_lines = PhoneLine.objects.filter(is_deleted=False, created_at__date__lte=day)
    allocated_line_ids = active_allocations.values_list(
        "phone_line_id", flat=True
    ).distinct()
    numeros_disponiveis = base_lines.exclude(id__in=allocated_line_ids).count()

    numeros_entregues = LineAllocation.objects.filter(allocated_at__date=day).count()
    reconectados = (
        LineAllocation.objects.filter(allocated_at__date=day)
        .filter(phone_line__allocations__released_at__lt=F("allocated_at"))
        .distinct()
        .count()
    )
    novos = PhoneLine.objects.filter(created_at__date=day, is_deleted=False).count()
    sem_whats_portfolios = employees_without_whats.values_list("employee_id", flat=True)
    b2b_sem_whats = 0
    b2c_sem_whats = 0
    for portfolio_name in sem_whats_portfolios:
        normalized = normalize_portfolio_name(portfolio_name)
        if normalized in B2B_PORTFOLIO_NAMES:
            b2b_sem_whats += 1
        elif normalized in B2C_PORTFOLIO_NAMES:
            b2c_sem_whats += 1

    available_numbers, delivered_numbers, reconnected_numbers, new_numbers = (
        build_number_details_for_day(day, base_lines, allocated_line_ids)
    )

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
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", str(value))
    without_diacritics = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return " ".join(without_diacritics.strip().lower().split())


B2B_PORTFOLIO_NAMES = {
    normalize_portfolio_name(portfolio) for portfolio, _ in B2B_PORTFOLIOS
}
B2C_PORTFOLIO_NAMES = {
    normalize_portfolio_name(portfolio) for portfolio, _ in B2C_PORTFOLIOS
}


class DashboardView(AuthenticadView, TemplateView):
    template_name = "dashboard/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        trend_period = self._resolve_trend_period()
        context["total_employees"] = Employee.objects.filter(
            status=Employee.Status.ACTIVE
        ).count()
        context["total_lines"] = PhoneLine.objects.filter(is_deleted=False).count()
        context["allocated_lines"] = LineAllocation.objects.filter(
            is_active=True
        ).count()
        context["available_lines"] = context["total_lines"] - context["allocated_lines"]
        context["total_simcards"] = SIMcard.objects.filter(is_deleted=False).count()

        context.update(self._build_status_counts())
        context["indicadores_diarios"] = self._build_daily_indicators(days=trend_period)
        context["trend_period"] = trend_period
        context["trend_period_options"] = ALLOWED_TREND_PERIODS
        context.update(self._build_dashboard_insights(context))
        return context

    def _resolve_trend_period(self):
        raw_period = self.request.GET.get("period", str(DEFAULT_TREND_PERIOD))
        return resolve_trend_period(raw_period)

    def _build_dashboard_insights(self, context):
        daily = context.get("indicadores_diarios", [])
        latest = daily[-1] if daily else {}
        today = timezone.localdate()
        pending_actions = DailyUserAction.objects.filter(day=today)
        pending_new_number_count = pending_actions.filter(
            action_type=DailyUserAction.ActionType.NEW_NUMBER
        ).count()
        pending_reconnect_whatsapp_count = pending_actions.filter(
            action_type=DailyUserAction.ActionType.RECONNECT_WHATSAPP
        ).count()
        action_board_url = (
            f"{reverse('daily_user_action_board')}"
            f"?{urlencode({'day': today.isoformat()})}"
        )

        latest_sem_whats = float(latest.get("perc_sem_whats", 0) or 0)
        latest_descoberto = int(latest.get("total_descoberto_dia", 0) or 0)
        latest_reconectados = int(latest.get("reconectados", 0) or 0)

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
                "action_label": "Ver usuarios",
                "action_url": "/employees/",
            },
            {
                "title": "Linhas bloqueadas",
                "value": blocked_lines,
                "description": "Linhas suspensas ou canceladas no inventario.",
                "level": level_for_count(blocked_lines),
                "action_label": "Ver telecom",
                "action_url": "/telecom/",
            },
            {
                "title": "Pendêcia - Número Novo",
                "value": pending_new_number_count,
                "description": "Pendencias marcadas como precisa numero novo.",
                "level": level_for_count(pending_new_number_count),
                "action_label": "Ver pendencias",
                "action_url": action_board_url,
            },
            {
                "title": "Pendêcia - Reconexão Whats",
                "value": pending_reconnect_whatsapp_count,
                "description": "Pendencias marcadas como precisa reconectar Whats.",
                "level": level_for_count(pending_reconnect_whatsapp_count),
                "action_label": "Ver pendencias",
                "action_url": action_board_url,
            },
            {
                "title": "Descobertos hoje",
                "value": latest_descoberto,
                "description": "Usuarios sem linha no fechamento do dia.",
                "level": level_for_count(latest_descoberto),
                "action_label": "Ir para cadastro",
                "action_url": "/allocations/",
            },
            {
                "title": "Reconectados hoje",
                "value": latest_reconectados,
                "description": "Recuperacoes efetivas no dia atual.",
                "level": "ok" if latest_reconectados > 0 else "warning",
                "action_label": "Detalhar telecom",
                "action_url": "/telecom/",
            },
        ]

        trend_defs = [
            ("pessoas_logadas", "Pessoas logadas", ""),
            ("perc_sem_whats", "% sem Whats", "%"),
            ("numeros_entregues", "Numeros entregues", ""),
            ("reconectados", "Reconectados", ""),
        ]
        trend_series = []
        trend_points = {}
        for key, label, suffix in trend_defs:
            values = [float(item.get(key, 0) or 0) for item in daily]
            trend_points[key] = values
            first_value = values[0] if values else 0
            latest_value = values[-1] if values else 0
            delta = latest_value - first_value
            trend_series.append(
                {
                    "key": key,
                    "label": label,
                    "suffix": suffix,
                    "latest": latest_value,
                    "delta": delta,
                }
            )

        trend_points["labels"] = [
            item["data"].strftime("%d/%m") for item in daily if item.get("data")
        ]

        return {
            "exception_cards": exception_cards,
            "trend_series": trend_series,
            "trend_points": trend_points,
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
        return build_indicator_for_day(day)

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


@login_required
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
def daily_indicator_management(request):
    """
    View para visualizar e gerenciar todos os indicadores diários.
    Permite filtrar por supervisor, carteira, segmento e período.
    """
    filter_form = DailyIndicatorFilterForm(request.GET or None)
    indicators = DailyIndicator.objects.all()

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
def daily_indicator_detail(request, pk):
    """
    View para visualizar detalhes de um indicador específico.
    """
    indicator = DailyIndicator.objects.get(pk=pk)

    context = {
        "indicator": indicator,
        "title": f"Indicador - {indicator.supervisor}",
    }
    return render(request, "dashboard/daily_indicator_detail.html", context)


@login_required
def daily_indicator_edit(request, pk):
    """
    View para editar um indicador existente.
    Apenas o campo "Pessoas Logadas" pode ser editado manualmente.
    """
    indicator = DailyIndicator.objects.get(pk=pk)

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
def daily_user_action_board(request):
    day = resolve_day(request.GET.get("day") or request.POST.get("day"))
    supervisor_filter = (request.GET.get("supervisor") or "").strip()
    employees_qs = get_supervised_employees_queryset(request.user, supervisor_filter)

    if request.method == "POST":
        form = DailyUserActionForm(request.POST)
        if form.is_valid():
            employee_id = form.cleaned_data["employee_id"]
            action_type = form.cleaned_data.get("action_type") or ""
            note = (form.cleaned_data.get("note") or "").strip()
            employee = employees_qs.filter(pk=employee_id).first()

            if not employee:
                messages.error(
                    request,
                    "Usuario nao encontrado para este supervisor.",
                )
            elif action_type and action_type not in dict(
                DailyUserAction.ActionType.choices
            ):
                messages.error(request, "Tipo de acao invalido.")
            elif not action_type:
                deleted, _ = DailyUserAction.objects.filter(
                    day=day, employee=employee
                ).delete()
                if deleted:
                    messages.success(
                        request,
                        f"Acao removida para {employee.full_name}.",
                    )
            else:
                action, created = DailyUserAction.objects.update_or_create(
                    day=day,
                    employee=employee,
                    defaults={
                        "supervisor": request.user,
                        "action_type": action_type,
                        "note": note,
                        "updated_by": request.user,
                        "created_by": request.user,
                    },
                )
                verb = "criada" if created else "atualizada"
                messages.success(
                    request,
                    f"Acao {verb} para {action.employee.full_name}.",
                )
        else:
            messages.error(request, "Nao foi possivel salvar a acao.")

        query = {"day": day.isoformat()}
        if supervisor_filter:
            query["supervisor"] = supervisor_filter
        return redirect(f"{reverse('daily_user_action_board')}?{urlencode(query)}")

    actions_qs = DailyUserAction.objects.filter(
        day=day, employee_id__in=employees_qs.values_list("id", flat=True)
    ).select_related("employee")
    actions_by_employee = {action.employee_id: action for action in actions_qs}

    active_allocations = (
        LineAllocation.objects.filter(
            is_active=True, employee_id__in=employees_qs.values_list("id", flat=True)
        )
        .select_related("phone_line")
        .order_by("employee_id", "-allocated_at")
    )
    line_by_employee = {}
    for allocation in active_allocations:
        if allocation.employee_id not in line_by_employee and allocation.phone_line:
            line_by_employee[allocation.employee_id] = (
                allocation.phone_line.phone_number
            )

    rows = []
    for employee in employees_qs:
        action = actions_by_employee.get(employee.id)
        action_form = DailyUserActionForm(
            initial={
                "day": day,
                "employee_id": employee.id,
                "action_type": action.action_type if action else "",
                "note": action.note if action else "",
            }
        )
        rows.append(
            {
                "employee": employee,
                "line_number": line_by_employee.get(employee.id),
                "has_line": employee.id in line_by_employee,
                "action": action,
                "form": action_form,
            }
        )

    action_counts = {
        "new_number": actions_qs.filter(
            action_type=DailyUserAction.ActionType.NEW_NUMBER
        ).count(),
        "reconnect_whatsapp": actions_qs.filter(
            action_type=DailyUserAction.ActionType.RECONNECT_WHATSAPP
        ).count(),
    }

    context = {
        "title": "Acoes do Dia",
        "day": day,
        "rows": rows,
        "action_counts": action_counts,
        "supervisor_filter": supervisor_filter,
        "is_supervisor_role": (request.user.role or "").lower() == "super",
    }
    return render(request, "dashboard/daily_user_action_board.html", context)


@login_required
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
