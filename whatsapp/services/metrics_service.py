from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.db.models import Avg, Count, Max, Q, QuerySet
from django.utils import timezone

from whatsapp.choices import WhatsAppActionStatus, WhatsAppActionType
from whatsapp.models import MeowInstance


@dataclass
class MeowMetricsSummary:
    instance: MeowInstance
    qr_requests: int
    reconnect_attempts: int
    failures: int
    average_latency_ms: float | None
    last_audit_at: datetime | None


class WhatsAppMetricsService:
    DEFAULT_WINDOW_HOURS = 24

    def summarize_instances(
        self,
        *,
        queryset: QuerySet | None = None,
        include_inactive: bool = False,
        window_hours: int | None = None,
    ) -> list[MeowMetricsSummary]:
        queryset = queryset if queryset is not None else MeowInstance.objects.all()
        if not include_inactive:
            queryset = queryset.filter(is_active=True)

        window_hours = window_hours or getattr(
            settings,
            "WHATSAPP_METRICS_WINDOW_HOURS",
            self.DEFAULT_WINDOW_HOURS,
        )
        since = timezone.now() - timedelta(hours=window_hours)

        queryset = queryset.annotate(
            qr_requests_count=Count(
                "whatsapp_sessions__action_audits",
                filter=Q(
                    whatsapp_sessions__action_audits__created_at__gte=since,
                    whatsapp_sessions__action_audits__action=WhatsAppActionType.GET_QR,
                ),
            ),
            reconnect_attempts_count=Count(
                "whatsapp_sessions__action_audits",
                filter=Q(
                    whatsapp_sessions__action_audits__created_at__gte=since,
                    whatsapp_sessions__action_audits__action=(
                        WhatsAppActionType.CONNECT_SESSION
                    ),
                ),
            ),
            failures_count=Count(
                "whatsapp_sessions__action_audits",
                filter=Q(
                    whatsapp_sessions__action_audits__created_at__gte=since,
                    whatsapp_sessions__action_audits__status=(
                        WhatsAppActionStatus.FAILURE
                    ),
                ),
            ),
            average_latency_ms_value=Avg(
                "whatsapp_sessions__action_audits__duration_ms",
                filter=Q(
                    whatsapp_sessions__action_audits__created_at__gte=since,
                    whatsapp_sessions__action_audits__duration_ms__isnull=False,
                ),
            ),
            last_audit_at_value=Max(
                "whatsapp_sessions__action_audits__created_at",
                filter=Q(whatsapp_sessions__action_audits__created_at__gte=since),
            ),
        ).order_by("name")

        return [
            MeowMetricsSummary(
                instance=instance,
                qr_requests=instance.qr_requests_count,
                reconnect_attempts=instance.reconnect_attempts_count,
                failures=instance.failures_count,
                average_latency_ms=instance.average_latency_ms_value,
                last_audit_at=instance.last_audit_at_value,
            )
            for instance in queryset
        ]
