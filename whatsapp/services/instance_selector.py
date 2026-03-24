from django.db.models import Case, Count, F, IntegerField, Q, Value, When

from whatsapp.choices import MeowInstanceHealthStatus
from whatsapp.models import MeowInstance


class NoAvailableMeowInstanceError(Exception):
    """Nenhuma instancia elegivel do Meow foi encontrada."""


class InstanceSelectorService:
    @staticmethod
    def select_available_instance(*, allow_above_warning: bool = False):
        queryset = (
            MeowInstance.objects.filter(is_active=True)
            .exclude(health_status=MeowInstanceHealthStatus.UNAVAILABLE)
            .annotate(
                active_sessions=Count(
                    "whatsapp_sessions",
                    filter=Q(whatsapp_sessions__is_active=True),
                ),
                health_priority=Case(
                    When(
                        health_status=MeowInstanceHealthStatus.HEALTHY,
                        then=Value(0),
                    ),
                    When(
                        health_status=MeowInstanceHealthStatus.UNKNOWN,
                        then=Value(1),
                    ),
                    When(
                        health_status=MeowInstanceHealthStatus.DEGRADED,
                        then=Value(2),
                    ),
                    default=Value(3),
                    output_field=IntegerField(),
                ),
            )
        )

        normal_capacity_queryset = queryset.filter(
            active_sessions__lt=F("warning_sessions")
        )
        selected = normal_capacity_queryset.order_by(
            "health_priority",
            "active_sessions",
            "name",
        ).first()
        if selected:
            return selected

        if allow_above_warning:
            selected = (
                queryset.filter(active_sessions__lt=F("max_sessions"))
                .order_by(
                    "health_priority",
                    "active_sessions",
                    "name",
                )
                .first()
            )
            if selected:
                return selected

        raise NoAvailableMeowInstanceError(
            "Nenhuma instancia Meow ativa e com capacidade disponivel."
        )
