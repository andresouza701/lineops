from collections import defaultdict
from datetime import datetime, time, timedelta

from django.db.models import Count, F, Q
from django.utils import timezone
from django.views.generic import TemplateView

from allocations.models import LineAllocation
from core.mixins import AuthenticadView
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard


class DashboardView(AuthenticadView, TemplateView):
    template_name = "dashboard/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
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
        context["indicadores_diarios"] = self._build_daily_indicators(days=7)

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
        return context

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
                {"label": label, "count": sim_counts.get(value, 0)}
                for value, label in SIMcard.Status.choices
            ],
            "line_status_counts": [
                {"label": label, "count": line_counts.get(value, 0)}
                for value, label in PhoneLine.Status.choices
            ],
        }
