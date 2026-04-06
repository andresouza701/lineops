from __future__ import annotations

import time
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from whatsapp.choices import MeowInstanceHealthStatus, WhatsAppActionType
from whatsapp.clients.exceptions import MeowClientError, MeowClientUnavailableError
from whatsapp.clients.meow_client import MeowClient
from whatsapp.models import MeowInstance
from whatsapp.services.audit_service import WhatsAppAuditService


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
        started_at = time.monotonic()
        request_payload = {"base_url": instance.base_url}

        try:
            payload = client.health_check()
            health_status, detail = self._resolve_status_from_payload(payload)
            audit_method = WhatsAppAuditService.success
            response_payload = payload
        except MeowClientUnavailableError as exc:
            health_status = MeowInstanceHealthStatus.UNAVAILABLE
            detail = str(exc)
            audit_method = WhatsAppAuditService.failure
            response_payload = {"error": detail}
        except MeowClientError as exc:
            health_status = MeowInstanceHealthStatus.DEGRADED
            detail = str(exc)
            audit_method = WhatsAppAuditService.failure
            response_payload = {"error": detail}

        instance.health_status = health_status
        instance.last_health_check_at = now
        duration_ms = max(0, int(round((time.monotonic() - started_at) * 1000)))
        with transaction.atomic():
            instance.save(
                update_fields=[
                    "health_status",
                    "last_health_check_at",
                    "updated_at",
                ]
            )
            audit_method(
                meow_instance=instance,
                action=WhatsAppActionType.HEALTH_CHECK,
                request_payload=request_payload,
                response_payload=response_payload,
                duration_ms=duration_ms,
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
