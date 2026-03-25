from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Count, Q, QuerySet

from whatsapp.choices import WhatsAppSessionStatus
from whatsapp.models import MeowInstance


@dataclass
class MeowCapacitySummary:
    instance: MeowInstance
    active_sessions: int
    connected_sessions: int
    pending_sessions: int
    degraded_sessions: int
    capacity_level: str


class MeowCapacityService:
    def summarize_instances(
        self,
        *,
        queryset: QuerySet | None = None,
        include_inactive: bool = False,
    ) -> list[MeowCapacitySummary]:
        queryset = queryset if queryset is not None else MeowInstance.objects.all()
        if not include_inactive:
            queryset = queryset.filter(is_active=True)

        annotated_queryset = self._annotate_queryset(queryset).order_by("name")
        return [self._build_summary(instance) for instance in annotated_queryset]

    def _annotate_queryset(self, queryset: QuerySet) -> QuerySet:
        return queryset.annotate(
            active_sessions_count=Count(
                "whatsapp_sessions",
                filter=Q(whatsapp_sessions__is_active=True),
            ),
            connected_sessions_count=Count(
                "whatsapp_sessions",
                filter=Q(
                    whatsapp_sessions__is_active=True,
                    whatsapp_sessions__status=WhatsAppSessionStatus.CONNECTED,
                ),
            ),
            pending_sessions_count=Count(
                "whatsapp_sessions",
                filter=Q(
                    whatsapp_sessions__is_active=True,
                    whatsapp_sessions__status__in=[
                        WhatsAppSessionStatus.PENDING_NEW_NUMBER,
                        WhatsAppSessionStatus.PENDING_RECONNECT,
                        WhatsAppSessionStatus.CONNECTING,
                        WhatsAppSessionStatus.QR_PENDING,
                    ],
                ),
            ),
            degraded_sessions_count=Count(
                "whatsapp_sessions",
                filter=Q(
                    whatsapp_sessions__is_active=True,
                    whatsapp_sessions__status__in=[
                        WhatsAppSessionStatus.ERROR,
                        WhatsAppSessionStatus.DISCONNECTED,
                    ],
                ),
            ),
        )

    def _build_summary(self, instance: MeowInstance) -> MeowCapacitySummary:
        active_sessions = instance.active_sessions_count
        return MeowCapacitySummary(
            instance=instance,
            active_sessions=active_sessions,
            connected_sessions=instance.connected_sessions_count,
            pending_sessions=instance.pending_sessions_count,
            degraded_sessions=instance.degraded_sessions_count,
            capacity_level=self._resolve_capacity_level(instance, active_sessions),
        )

    def _resolve_capacity_level(
        self,
        instance: MeowInstance,
        active_sessions: int,
    ) -> str:
        if active_sessions > instance.max_sessions:
            return "OVER_CAPACITY"
        if active_sessions > instance.warning_sessions:
            return "CRITICAL"
        if active_sessions > instance.target_sessions:
            return "WARNING"
        return "OK"
