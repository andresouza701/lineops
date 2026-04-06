from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from whatsapp.choices import WhatsAppIntegrationJobType, WhatsAppSessionStatus
from whatsapp.models import WhatsAppIntegrationJob, WhatsAppWorkerState
from whatsapp.services.integration_job_service import WhatsAppIntegrationJobService
from whatsapp.services.session_service import WhatsAppSessionService


@dataclass
class WhatsAppWorkerRunSummary:
    worker_code: str
    claimed_jobs: int
    processed_jobs: int
    failed_jobs: int


class WhatsAppIntegrationWorkerService:
    def __init__(self):
        self.job_service = WhatsAppIntegrationJobService()
        self.session_service = WhatsAppSessionService()

    def get_heartbeat_ttl_seconds(self) -> int:
        return int(
            getattr(
                settings,
                "WHATSAPP_INTEGRATION_WORKER_HEARTBEAT_TTL_SECONDS",
                120,
            )
        )

    def run_once(
        self,
        *,
        worker_code: str = "default",
        limit: int = 10,
    ) -> WhatsAppWorkerRunSummary:
        now = timezone.now()
        self._touch_worker(worker_code, is_running=True, last_error="")
        claimed_jobs = self.job_service.claim_due_jobs(
            worker_code=worker_code,
            limit=limit,
            now=now,
        )

        processed_jobs = 0
        failed_jobs = 0
        last_error = ""

        for job in claimed_jobs:
            try:
                result = self._run_job(job)
                self.job_service.mark_success(
                    job,
                    response_payload=result.remote_payload,
                )
                if self._should_enqueue_status_poll(job, result.status):
                    self.job_service.enqueue_status_poll(session=job.session)
                processed_jobs += 1
                self._touch_worker(
                    worker_code,
                    is_running=True,
                    last_processed_job_at=timezone.now(),
                    last_error="",
                )
            except Exception as exc:  # noqa: BLE001
                self.job_service.mark_retry(
                    job,
                    error_message=str(exc),
                    response_payload={"error": str(exc)},
                )
                failed_jobs += 1
                last_error = str(exc)
                self._touch_worker(
                    worker_code,
                    is_running=True,
                    last_error=last_error,
                )

        self._touch_worker(
            worker_code,
            is_running=False,
            last_error=last_error,
        )
        return WhatsAppWorkerRunSummary(
            worker_code=worker_code,
            claimed_jobs=len(claimed_jobs),
            processed_jobs=processed_jobs,
            failed_jobs=failed_jobs,
        )

    def build_readiness_payload(self, *, worker_code: str = "default") -> tuple[dict, int]:
        state = WhatsAppWorkerState.objects.filter(worker_code=worker_code).first()
        ttl_seconds = self.get_heartbeat_ttl_seconds()
        deadline = timezone.now() - timedelta(seconds=ttl_seconds)
        is_ready = bool(
            state
            and state.last_heartbeat_at
            and state.last_heartbeat_at >= deadline
        )
        payload = {
            "status": "ok" if is_ready else "unavailable",
            "worker_code": worker_code,
            "last_heartbeat_at": (
                state.last_heartbeat_at.isoformat()
                if state and state.last_heartbeat_at
                else None
            ),
            "last_processed_job_at": (
                state.last_processed_job_at.isoformat()
                if state and state.last_processed_job_at
                else None
            ),
            "last_error": state.last_error if state else "",
        }
        return payload, 200 if is_ready else 503

    def _run_job(self, job: WhatsAppIntegrationJob):
        line = job.session.line
        if job.job_type == WhatsAppIntegrationJobType.CREATE_SESSION:
            return self.session_service.connect(line)
        if job.job_type == WhatsAppIntegrationJobType.GENERATE_QR:
            return self.session_service.get_qr(line)
        if job.job_type == WhatsAppIntegrationJobType.SYNC_STATUS:
            return self.session_service.get_status(line)
        if job.job_type == WhatsAppIntegrationJobType.DELETE_SESSION:
            return self.session_service.disconnect(line)
        raise ValueError(f"Job WhatsApp desconhecido: {job.job_type}")

    def _should_enqueue_status_poll(self, job: WhatsAppIntegrationJob, status: str) -> bool:
        if job.job_type == WhatsAppIntegrationJobType.DELETE_SESSION:
            return False
        return status in {
            WhatsAppSessionStatus.CONNECTING,
            WhatsAppSessionStatus.QR_PENDING,
        }

    def _touch_worker(
        self,
        worker_code: str,
        *,
        is_running: bool,
        last_error: str | None = None,
        last_processed_job_at=None,
    ) -> None:
        defaults = {
            "is_running": is_running,
            "last_heartbeat_at": timezone.now(),
        }
        if last_error is not None:
            defaults["last_error"] = last_error
        if last_processed_job_at is not None:
            defaults["last_processed_job_at"] = last_processed_job_at

        state, _ = WhatsAppWorkerState.objects.get_or_create(
            worker_code=worker_code,
            defaults=defaults,
        )
        for field, value in defaults.items():
            setattr(state, field, value)
        state.save(
            update_fields=[
                *defaults.keys(),
                "updated_at",
            ]
        )
