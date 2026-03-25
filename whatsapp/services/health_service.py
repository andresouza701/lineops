from __future__ import annotations

from dataclasses import dataclass

from django.utils import timezone

from whatsapp.choices import MeowInstanceHealthStatus
from whatsapp.clients.exceptions import MeowClientError, MeowClientUnavailableError
from whatsapp.clients.meow_client import MeowClient
from whatsapp.models import MeowInstance


@dataclass
class MeowHealthCheckResult:
    instance: MeowInstance
    health_status: str
    detail: str


class MeowHealthCheckService:
    def check_instances(
        self,
        *,
        queryset=None,
        include_inactive: bool = False,
    ) -> list[MeowHealthCheckResult]:
        queryset = queryset if queryset is not None else MeowInstance.objects.all()
        if not include_inactive:
            queryset = queryset.filter(is_active=True)

        results = []
        for instance in queryset.order_by("name"):
            results.append(self.check_instance(instance))
        return results

    def check_instance(self, instance: MeowInstance) -> MeowHealthCheckResult:
        client = MeowClient(instance.base_url)
        now = timezone.now()

        try:
            payload = client.health_check()
            health_status, detail = self._resolve_status_from_payload(payload)
        except MeowClientUnavailableError as exc:
            health_status = MeowInstanceHealthStatus.UNAVAILABLE
            detail = str(exc)
        except MeowClientError as exc:
            health_status = MeowInstanceHealthStatus.DEGRADED
            detail = str(exc)

        instance.health_status = health_status
        instance.last_health_check_at = now
        instance.save(
            update_fields=[
                "health_status",
                "last_health_check_at",
                "updated_at",
            ]
        )

        return MeowHealthCheckResult(
            instance=instance,
            health_status=health_status,
            detail=detail,
        )

    def _resolve_status_from_payload(self, payload: dict) -> tuple[str, str]:
        success = payload.get("success")
        if success is False:
            detail = (
                payload.get("detail")
                or payload.get("message")
                or "Health check retornou falha."
            )
            return MeowInstanceHealthStatus.DEGRADED, str(detail)

        detail = (
            payload.get("detail")
            or payload.get("message")
            or "Instancia Meow saudavel."
        )
        return MeowInstanceHealthStatus.HEALTHY, str(detail)
