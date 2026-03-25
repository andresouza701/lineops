from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db.models import QuerySet
from django.utils import timezone

from whatsapp.choices import MeowInstanceHealthStatus
from whatsapp.models import WhatsAppSession


@dataclass
class WhatsAppSessionReconcileResult:
    session: WhatsAppSession
    is_consistent: bool
    issue_codes: list[str]
    detail: str


class WhatsAppSessionReconcileService:
    def reconcile_sessions(
        self,
        *,
        queryset: QuerySet | None = None,
        include_inactive: bool = False,
    ) -> list[WhatsAppSessionReconcileResult]:
        queryset = queryset if queryset is not None else WhatsAppSession.objects.all()
        if not include_inactive:
            queryset = queryset.filter(is_active=True)

        results = []
        queryset = queryset.select_related("line__sim_card", "meow_instance")
        for session in queryset.order_by("session_id"):
            issue_codes, detail = self._collect_issues(session)
            results.append(
                WhatsAppSessionReconcileResult(
                    session=session,
                    is_consistent=not issue_codes,
                    issue_codes=issue_codes,
                    detail=detail,
                )
            )
        return results

    def _collect_issues(self, session: WhatsAppSession) -> tuple[list[str], str]:
        issues: list[str] = []

        if session.line.is_deleted or session.line.sim_card.is_deleted:
            issues.append("LINE_HIDDEN")

        if not session.meow_instance.is_active:
            issues.append("INSTANCE_INACTIVE")

        if session.meow_instance.health_status == MeowInstanceHealthStatus.UNAVAILABLE:
            issues.append("INSTANCE_UNAVAILABLE")
        elif session.meow_instance.health_status == MeowInstanceHealthStatus.DEGRADED:
            issues.append("INSTANCE_DEGRADED")

        if session.is_active and session.last_sync_at is None:
            issues.append("NEVER_SYNCED")
        elif session.is_active and self._is_sync_stale(session):
            issues.append("SYNC_STALE")

        if not issues:
            return [], "Sessao consistente."

        return issues, self._build_detail(issues)

    def _is_sync_stale(self, session: WhatsAppSession) -> bool:
        stale_minutes = getattr(settings, "WHATSAPP_SESSION_STALE_MINUTES", 30)
        if not session.last_sync_at:
            return False

        threshold = timezone.now() - timedelta(minutes=stale_minutes)
        return session.last_sync_at < threshold

    def _build_detail(self, issues: list[str]) -> str:
        issue_messages = {
            "LINE_HIDDEN": "Linha ou SIMcard oculto no inventario.",
            "INSTANCE_INACTIVE": "Instancia Meow inativa.",
            "INSTANCE_UNAVAILABLE": (
                "Instancia Meow indisponivel no ultimo health check."
            ),
            "INSTANCE_DEGRADED": "Instancia Meow degradada no ultimo health check.",
            "NEVER_SYNCED": "Sessao ainda nao foi sincronizada.",
            "SYNC_STALE": "Sessao com sincronizacao desatualizada.",
        }
        return " ".join(issue_messages[issue] for issue in issues)
