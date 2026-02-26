from collections import defaultdict

from django.db.models import Count
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
        # Dados para tabela negociador
        # Supervisor: campo teams
        # Negociador sem Whats: sem linha alocada ativa
        # Carteira, Unidade, PA: campos fictícios (adapte se existirem)
        # Status: Employee.status
        employees = Employee.objects.filter(is_deleted=False)
        negociador_data = []
        for emp in employees:
            # Verifica se tem linha alocada ativa
            has_whats = LineAllocation.objects.filter(
                employee=emp, is_active=True
            ).exists()
            negociador_data.append(
                {
                    "supervisor": emp.teams,
                    "negociador": emp.full_name,
                    "sem_whats": not has_whats,
                    "carteira": getattr(emp, "carteira", "-"),
                    "unidade": getattr(emp, "unidade", "-"),
                    "pa": getattr(emp, "pa", "-"),
                    "status": emp.get_status_display(),
                }
            )
        context["negociador_data"] = negociador_data

        # Indicadores diários
        from datetime import date

        dia = date.today()
        # Pessoas logadas: ativos
        pessoas_logadas = Employee.objects.filter(status=Employee.Status.ACTIVE).count()
        # Negociadores sem Whats
        total_negociadores = Employee.objects.filter(is_deleted=False).count()
        sem_whats = (
            Employee.objects.filter(is_deleted=False)
            .exclude(allocations__is_active=True)
            .count()
        )
        perc_sem_whats = (
            (sem_whats / total_negociadores * 100) if total_negociadores else 0
        )
        # B2B/B2C sem Whats: campos fictícios
        b2b_sem_whats = 0
        b2c_sem_whats = 0
        # Números disponíveis
        numeros_disponiveis = PhoneLine.objects.filter(
            status=PhoneLine.Status.AVAILABLE, is_deleted=False
        ).count()
        # Números entregues: linhas alocadas hoje
        numeros_entregues = LineAllocation.objects.filter(
            allocated_at__date=dia, is_active=True
        ).count()
        # Reconectados: linhas liberadas e alocadas novamente hoje
        reconectados = LineAllocation.objects.filter(
            allocated_at__date=dia, released_at__isnull=False
        ).count()
        # Novos: linhas criadas hoje
        novos = PhoneLine.objects.filter(created_at__date=dia, is_deleted=False).count()
        # Total descoberto DIA: negociadores sem Whats hoje
        total_descoberto_dia = sem_whats
        indicadores_diarios = [
            {
                "data": dia.strftime("%d/%m/%Y"),
                "pessoas_logadas": pessoas_logadas,
                "perc_sem_whats": perc_sem_whats,
                "b2b_sem_whats": b2b_sem_whats,
                "b2c_sem_whats": b2c_sem_whats,
                "numeros_disponiveis": numeros_disponiveis,
                "numeros_entregues": numeros_entregues,
                "reconectados": reconectados,
                "novos": novos,
                "total_descoberto_dia": total_descoberto_dia,
            }
        ]
        context["indicadores_diarios"] = indicadores_diarios
        return context

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
