from collections import defaultdict
from datetime import datetime, time, timedelta

from django.db.models import Count, F, Q
from django.utils import timezone
from django.views.generic import TemplateView

from allocations.models import LineAllocation
from core.mixins import AuthenticadView
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard

PERCENT_CRITICAL_THRESHOLD = 20
PERCENT_WARNING_THRESHOLD = 10
COUNT_CRITICAL_THRESHOLD = 10
COUNT_WARNING_THRESHOLD = 5
DEFAULT_TREND_PERIOD = 7
ALLOWED_TREND_PERIODS = (7, 15, 30)


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

        # Tabela de reconexão por segmento e unidade
        unidades = ["Joinville", "Araquari"]
        b2b_emps = Employee.objects.filter(teams__icontains="b2b", is_deleted=False)
        reconexao_data = []
        hoje = timezone.localdate()
        fim = timezone.make_aware(datetime.combine(hoje, time.max))
        inicio = timezone.make_aware(datetime.combine(hoje, time.min))
        for unidade in unidades:
            emps_unidade = b2b_emps.filter(teams__icontains=unidade)
            negociadores_logados = emps_unidade.filter(
                status=Employee.Status.ACTIVE
            ).count()
            liberados = (
                LineAllocation.objects.filter(
                    employee__in=emps_unidade, released_at__range=(inicio, fim)
                )
                .values_list("employee_id", flat=True)
                .distinct()
            )
            precisa_numero_novo = emps_unidade.exclude(
                allocations__is_active=True
            ).count()
            reconectar_whats = len(liberados)
            reconexao_data.append(
                {
                    "unidade": unidade,
                    "negociadores_logados": negociadores_logados,
                    "reconectar_whats": reconectar_whats,
                    "precisa_numero_novo": precisa_numero_novo,
                }
            )
        negociadores_logados_total = b2b_emps.filter(
            status=Employee.Status.ACTIVE
        ).count()
        liberados_total = (
            LineAllocation.objects.filter(
                employee__in=b2b_emps, released_at__range=(inicio, fim)
            )
            .values_list("employee_id", flat=True)
            .distinct()
        )
        precisa_numero_novo_total = b2b_emps.exclude(
            allocations__is_active=True
        ).count()
        reconexao_data.append(
            {
                "unidade": "Total B2B",
                "negociadores_logados": negociadores_logados_total,
                "reconectar_whats": len(liberados_total),
                "precisa_numero_novo": precisa_numero_novo_total,
            }
        )
        context["reconexao_data"] = reconexao_data
        context.update(self._build_dashboard_insights(context))
        return context

    def _resolve_trend_period(self):
        raw_period = self.request.GET.get("period", str(DEFAULT_TREND_PERIOD))
        try:
            period = int(raw_period)
        except (TypeError, ValueError):
            return DEFAULT_TREND_PERIOD

        if period in ALLOWED_TREND_PERIODS:
            return period
        return DEFAULT_TREND_PERIOD

    def _build_dashboard_insights(self, context):
        daily = context.get("indicadores_diarios", [])
        latest = daily[-1] if daily else {}

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

        ranking = [
            item
            for item in context.get("reconexao_data", [])
            if item.get("unidade") != "Total B2B"
        ]
        ranking.sort(
            key=lambda item: (
                item.get("precisa_numero_novo", 0),
                item.get("reconectar_whats", 0),
            ),
            reverse=True,
        )

        return {
            "exception_cards": exception_cards,
            "trend_series": trend_series,
            "trend_points": trend_points,
            "unit_ranking": ranking,
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
        end_of_day = timezone.make_aware(datetime.combine(day, time.max))
        employees = Employee.objects.filter(is_deleted=False, created_at__date__lte=day)

        active_allocations = LineAllocation.objects.filter(allocated_at__lte=end_of_day)
        active_allocations = active_allocations.filter(
            Q(released_at__isnull=True) | Q(released_at__gt=end_of_day)
        )

        allocated_employee_ids = active_allocations.values_list(
            "employee_id", flat=True
        ).distinct()
        employees_without_whats = employees.exclude(id__in=allocated_employee_ids)

        total_negociadores = employees.count()
        sem_whats = employees_without_whats.count()
        perc_sem_whats = (
            (sem_whats / total_negociadores * 100) if total_negociadores else 0
        )

        base_lines = PhoneLine.objects.filter(
            is_deleted=False, created_at__date__lte=day
        )
        allocated_line_ids = active_allocations.values_list(
            "phone_line_id", flat=True
        ).distinct()
        numeros_disponiveis = base_lines.exclude(id__in=allocated_line_ids).count()

        numeros_entregues = LineAllocation.objects.filter(
            allocated_at__date=day
        ).count()
        reconectados = (
            LineAllocation.objects.filter(allocated_at__date=day)
            .filter(phone_line__allocations__released_at__lt=F("allocated_at"))
            .distinct()
            .count()
        )
        novos = PhoneLine.objects.filter(created_at__date=day, is_deleted=False).count()

        return {
            "data": day,
            "pessoas_logadas": employees.filter(status=Employee.Status.ACTIVE).count(),
            "perc_sem_whats": perc_sem_whats,
            "b2b_sem_whats": employees_without_whats.filter(
                teams__icontains="b2b"
            ).count(),
            "b2c_sem_whats": employees_without_whats.filter(
                teams__icontains="b2c"
            ).count(),
            "numeros_disponiveis": numeros_disponiveis,
            "numeros_entregues": numeros_entregues,
            "reconectados": reconectados,
            "novos": novos,
            "total_descoberto_dia": sem_whats,
        }

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
