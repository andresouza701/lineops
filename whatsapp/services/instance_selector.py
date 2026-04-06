from django.db.models import Case, Count, F, IntegerField, Q, Value, When

from whatsapp.choices import MeowInstanceHealthStatus
from whatsapp.models import MeowInstance, WhatsAppSession


class NoAvailableMeowInstanceError(Exception):
    """Nenhuma instancia elegivel do Meow foi encontrada."""


class InstanceSelectorService:
    @staticmethod
    def select_available_instance(
        *,
        allow_above_warning: bool = False,
        lock_instances: bool = False,
    ):
        if lock_instances:
            return InstanceSelectorService._select_available_instance_with_locks(
                allow_above_warning=allow_above_warning
            )

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

    @staticmethod
    def _select_available_instance_with_locks(*, allow_above_warning: bool):
        instances = list(
            MeowInstance.objects.select_for_update()
            .filter(is_active=True)
            .exclude(health_status=MeowInstanceHealthStatus.UNAVAILABLE)
            .order_by("name")
        )
        scored_instances: list[tuple[int, int, str, MeowInstance]] = []
        for instance in instances:
            active_sessions = WhatsAppSession.objects.filter(
                meow_instance=instance,
                is_active=True,
            ).count()
            scored_instances.append(
                (
                    InstanceSelectorService._health_priority(instance.health_status),
                    active_sessions,
                    instance.name,
                    instance,
                )
            )

        normal_capacity_candidates = [
            item
            for item in scored_instances
            if item[1] < item[3].warning_sessions
        ]
        if normal_capacity_candidates:
            return min(normal_capacity_candidates)[3]

        if allow_above_warning:
            overflow_candidates = [
                item
                for item in scored_instances
                if item[1] < item[3].max_sessions
            ]
            if overflow_candidates:
                return min(overflow_candidates)[3]

        raise NoAvailableMeowInstanceError(
            "Nenhuma instancia Meow ativa e com capacidade disponivel."
        )

    @staticmethod
    def _health_priority(health_status: str) -> int:
        priorities = {
            MeowInstanceHealthStatus.HEALTHY: 0,
            MeowInstanceHealthStatus.UNKNOWN: 1,
            MeowInstanceHealthStatus.DEGRADED: 2,
        }
        return priorities.get(health_status, 3)
