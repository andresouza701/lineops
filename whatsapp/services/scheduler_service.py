from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError
from django.db.models import Q
from django.utils import timezone

from whatsapp.choices import WhatsAppSchedulerJobCode, WhatsAppSchedulerJobStatus
from whatsapp.models import MeowInstance, WhatsAppScheduledJob, WhatsAppSession
from whatsapp.services.health_service import MeowHealthCheckService
from whatsapp.services.reconcile_service import WhatsAppSessionReconcileService
from whatsapp.services.sync_service import WhatsAppSessionSyncService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WhatsAppSchedulerJobDefinition:
    job_code: str
    label: str
    interval_seconds: int


@dataclass
class WhatsAppSchedulerJobSummary:
    job_code: str
    label: str
    interval_seconds: int
    is_running: bool
    last_status: str
    last_detail: str
    last_started_at: object
    last_finished_at: object
    next_run_at: object


@dataclass
class WhatsAppSchedulerRunResult:
    job_code: str
    label: str
    ran: bool
    status: str
    detail: str
    next_run_at: object


class WhatsAppOpsSchedulerService:
    def get_job_definitions(self) -> list[WhatsAppSchedulerJobDefinition]:
        return [
            WhatsAppSchedulerJobDefinition(
                job_code=WhatsAppSchedulerJobCode.HEALTH_CHECK,
                label="Health check",
                interval_seconds=int(
                    getattr(settings, "WHATSAPP_OPS_HEALTH_INTERVAL_SECONDS", 300)
                ),
            ),
            WhatsAppSchedulerJobDefinition(
                job_code=WhatsAppSchedulerJobCode.SESSION_SYNC,
                label="Sync de sessoes",
                interval_seconds=int(
                    getattr(settings, "WHATSAPP_OPS_SYNC_INTERVAL_SECONDS", 600)
                ),
            ),
            WhatsAppSchedulerJobDefinition(
                job_code=WhatsAppSchedulerJobCode.SESSION_RECONCILE,
                label="Reconciliacao",
                interval_seconds=int(
                    getattr(settings, "WHATSAPP_OPS_RECONCILE_INTERVAL_SECONDS", 3600)
                ),
            ),
        ]

    def get_tick_seconds(self) -> int:
        return int(getattr(settings, "WHATSAPP_OPS_SCHEDULER_TICK_SECONDS", 30))

    def build_job_summaries(self) -> list[WhatsAppSchedulerJobSummary]:
        definitions = self.get_job_definitions()
        states = {
            state.job_code: state
            for state in WhatsAppScheduledJob.objects.filter(
                job_code__in=[definition.job_code for definition in definitions]
            )
        }
        return [
            self._build_summary(definition, states.get(definition.job_code))
            for definition in definitions
        ]

    def run_due_jobs(self, *, now=None) -> list[WhatsAppSchedulerRunResult]:
        now = now or timezone.now()
        results = []

        for definition in self.get_job_definitions():
            job_state = self._ensure_job_state(definition)
            if not self._claim_due_job(job_state, now=now):
                job_state.refresh_from_db()
                results.append(
                    WhatsAppSchedulerRunResult(
                        job_code=definition.job_code,
                        label=definition.label,
                        ran=False,
                        status=job_state.last_status,
                        detail=job_state.last_detail,
                        next_run_at=job_state.next_run_at,
                    )
                )
                continue

            try:
                detail = self._run_job(definition.job_code)
                status = WhatsAppSchedulerJobStatus.SUCCESS
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "Falha ao executar job do scheduler WhatsApp",
                    extra={"job_code": definition.job_code},
                )
                detail = str(exc)
                status = WhatsAppSchedulerJobStatus.FAILURE

            finished_at = timezone.now()
            next_run_at = finished_at + timedelta(seconds=definition.interval_seconds)
            self._finish_job(
                job_state=job_state,
                status=status,
                detail=detail,
                finished_at=finished_at,
                next_run_at=next_run_at,
            )
            results.append(
                WhatsAppSchedulerRunResult(
                    job_code=definition.job_code,
                    label=definition.label,
                    ran=True,
                    status=status,
                    detail=detail,
                    next_run_at=next_run_at,
                )
            )

        return results

    def _build_summary(
        self,
        definition: WhatsAppSchedulerJobDefinition,
        job_state: WhatsAppScheduledJob | None,
    ) -> WhatsAppSchedulerJobSummary:
        return WhatsAppSchedulerJobSummary(
            job_code=definition.job_code,
            label=definition.label,
            interval_seconds=definition.interval_seconds,
            is_running=job_state.is_running if job_state else False,
            last_status=(
                job_state.last_status if job_state else WhatsAppSchedulerJobStatus.IDLE
            ),
            last_detail=job_state.last_detail if job_state else "",
            last_started_at=job_state.last_started_at if job_state else None,
            last_finished_at=job_state.last_finished_at if job_state else None,
            next_run_at=job_state.next_run_at if job_state else None,
        )

    def _ensure_job_state(
        self,
        definition: WhatsAppSchedulerJobDefinition,
    ) -> WhatsAppScheduledJob:
        defaults = {
            "interval_seconds": definition.interval_seconds,
            "last_status": WhatsAppSchedulerJobStatus.IDLE,
        }
        try:
            job_state, created = WhatsAppScheduledJob.objects.get_or_create(
                job_code=definition.job_code,
                defaults=defaults,
            )
        except IntegrityError:
            job_state = WhatsAppScheduledJob.objects.get(job_code=definition.job_code)
            created = False

        if not created and job_state.interval_seconds != definition.interval_seconds:
            job_state.interval_seconds = definition.interval_seconds
            job_state.save(update_fields=["interval_seconds", "updated_at"])

        return job_state

    def _claim_due_job(self, job_state: WhatsAppScheduledJob, *, now) -> bool:
        due_filter = Q(next_run_at__isnull=True) | Q(next_run_at__lte=now)
        return bool(
            WhatsAppScheduledJob.objects.filter(pk=job_state.pk, is_running=False)
            .filter(due_filter)
            .update(
                is_running=True,
                last_status=WhatsAppSchedulerJobStatus.RUNNING,
                last_started_at=now,
                last_detail="",
            )
        )

    def _finish_job(
        self,
        *,
        job_state: WhatsAppScheduledJob,
        status: str,
        detail: str,
        finished_at,
        next_run_at,
    ) -> None:
        WhatsAppScheduledJob.objects.filter(pk=job_state.pk).update(
            is_running=False,
            last_status=status,
            last_detail=detail,
            last_finished_at=finished_at,
            next_run_at=next_run_at,
        )

    def _run_job(self, job_code: str) -> str:
        include_inactive = bool(
            getattr(settings, "WHATSAPP_OPS_INCLUDE_INACTIVE", False)
        )

        if job_code == WhatsAppSchedulerJobCode.HEALTH_CHECK:
            results = MeowHealthCheckService().check_instances(
                queryset=MeowInstance.objects.all(),
                include_inactive=include_inactive,
            )
            healthy = sum(result.health_status == "HEALTHY" for result in results)
            degraded = sum(result.health_status == "DEGRADED" for result in results)
            unavailable = sum(
                result.health_status == "UNAVAILABLE" for result in results
            )
            return (
                f"{len(results)} instancia(s) verificadas: "
                f"{healthy} healthy, {degraded} degraded, {unavailable} unavailable."
            )

        if job_code == WhatsAppSchedulerJobCode.SESSION_SYNC:
            results = WhatsAppSessionSyncService().sync_sessions(
                queryset=WhatsAppSession.objects.all(),
                include_inactive=include_inactive,
            )
            success_count = sum(result.success for result in results)
            failure_count = len(results) - success_count
            return (
                f"{len(results)} sessao(oes) sincronizadas: "
                f"{success_count} sucesso, {failure_count} falha."
            )

        if job_code == WhatsAppSchedulerJobCode.SESSION_RECONCILE:
            results = WhatsAppSessionReconcileService().reconcile_sessions(
                queryset=WhatsAppSession.objects.all(),
                include_inactive=include_inactive,
            )
            inconsistent_count = sum(not result.is_consistent for result in results)
            return (
                f"{len(results)} sessao(oes) reconciliadas: "
                f"{len(results) - inconsistent_count} consistente(s), "
                f"{inconsistent_count} com inconsistencias."
            )

        raise ValueError(f"Job do scheduler WhatsApp desconhecido: {job_code}")
