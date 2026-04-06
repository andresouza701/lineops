from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from whatsapp.choices import (
    WhatsAppIntegrationJobStatus,
    WhatsAppIntegrationJobType,
)
from whatsapp.models import WhatsAppIntegrationJob, WhatsAppSession


class WhatsAppIntegrationJobService:
    active_statuses = (
        WhatsAppIntegrationJobStatus.PENDING,
        WhatsAppIntegrationJobStatus.RUNNING,
        WhatsAppIntegrationJobStatus.RETRY,
    )
    claimable_statuses = (
        WhatsAppIntegrationJobStatus.PENDING,
        WhatsAppIntegrationJobStatus.RETRY,
    )

    def get_default_max_attempts(self) -> int:
        return int(
            getattr(
                settings,
                "WHATSAPP_INTEGRATION_JOB_MAX_ATTEMPTS",
                5,
            )
        )

    def get_base_backoff_seconds(self) -> int:
        return int(
            getattr(
                settings,
                "WHATSAPP_INTEGRATION_JOB_BACKOFF_SECONDS",
                15,
            )
        )

    def get_max_backoff_seconds(self) -> int:
        return int(
            getattr(
                settings,
                "WHATSAPP_INTEGRATION_JOB_MAX_BACKOFF_SECONDS",
                300,
            )
        )

    def get_status_poll_seconds(self) -> int:
        return int(
            getattr(
                settings,
                "WHATSAPP_INTEGRATION_STATUS_POLL_SECONDS",
                30,
            )
        )

    def build_dedupe_key(self, session: WhatsAppSession, job_type: str) -> str:
        return f"{session.pk}:{job_type}"

    @transaction.atomic
    def enqueue(
        self,
        *,
        session: WhatsAppSession,
        job_type: str,
        created_by=None,
        correlation_id: str = "",
        request_payload: dict | None = None,
        available_at=None,
        max_attempts: int | None = None,
    ) -> tuple[WhatsAppIntegrationJob, bool]:
        available_at = available_at or timezone.now()
        max_attempts = max_attempts or self.get_default_max_attempts()
        dedupe_key = self.build_dedupe_key(session, job_type)

        existing = (
            WhatsAppIntegrationJob.objects.select_for_update()
            .filter(
                dedupe_key=dedupe_key,
                status__in=self.active_statuses,
            )
            .first()
        )
        if existing:
            update_fields = []
            if correlation_id and not existing.correlation_id:
                existing.correlation_id = correlation_id
                update_fields.append("correlation_id")
            if request_payload is not None and existing.request_payload != request_payload:
                existing.request_payload = request_payload
                update_fields.append("request_payload")
            if available_at < existing.available_at:
                existing.available_at = available_at
                update_fields.append("available_at")
            if update_fields:
                existing.save(update_fields=[*update_fields, "updated_at"])
            return existing, False

        defaults = {
            "status": WhatsAppIntegrationJobStatus.PENDING,
            "correlation_id": correlation_id,
            "request_payload": request_payload,
            "available_at": available_at,
            "max_attempts": max_attempts,
            "created_by": created_by,
        }
        try:
            return (
                WhatsAppIntegrationJob.objects.create(
                    session=session,
                    job_type=job_type,
                    dedupe_key=dedupe_key,
                    **defaults,
                ),
                True,
            )
        except IntegrityError:
            existing = (
                WhatsAppIntegrationJob.objects.select_for_update()
                .filter(dedupe_key=dedupe_key)
                .first()
            )
            if existing is None:
                raise
            if correlation_id and not existing.correlation_id:
                existing.correlation_id = correlation_id
                existing.save(update_fields=["correlation_id", "updated_at"])
            return existing, False

    def claim_due_jobs(
        self,
        *,
        worker_code: str,
        limit: int = 10,
        now=None,
    ) -> list[WhatsAppIntegrationJob]:
        now = now or timezone.now()
        with transaction.atomic():
            queryset = WhatsAppIntegrationJob.objects.select_related(
                "session",
                "session__line",
                "session__meow_instance",
            )
            if connection.features.has_select_for_update:
                lock_kwargs = {}
                if connection.features.has_select_for_update_skip_locked:
                    lock_kwargs["skip_locked"] = True
                queryset = queryset.select_for_update(**lock_kwargs)

            jobs = list(
                queryset.filter(
                    status__in=self.claimable_statuses,
                    available_at__lte=now,
                )
                .order_by("available_at", "id")[:limit]
            )
            if not jobs:
                return []

            job_ids = [job.pk for job in jobs]
            WhatsAppIntegrationJob.objects.filter(pk__in=job_ids).update(
                status=WhatsAppIntegrationJobStatus.RUNNING,
                claimed_at=now,
                claimed_by=worker_code,
                last_error="",
                finished_at=None,
            )

            for job in jobs:
                job.status = WhatsAppIntegrationJobStatus.RUNNING
                job.claimed_at = now
                job.claimed_by = worker_code
                job.last_error = ""
                job.finished_at = None

            return jobs

    def mark_success(
        self,
        job: WhatsAppIntegrationJob,
        *,
        response_payload: dict | None = None,
        finished_at=None,
    ) -> None:
        finished_at = finished_at or timezone.now()
        WhatsAppIntegrationJob.objects.filter(pk=job.pk).update(
            status=WhatsAppIntegrationJobStatus.SUCCESS,
            response_payload=response_payload,
            finished_at=finished_at,
            claimed_at=None,
            claimed_by="",
            last_error="",
            dedupe_key=None,
        )
        job.status = WhatsAppIntegrationJobStatus.SUCCESS
        job.response_payload = response_payload
        job.finished_at = finished_at
        job.claimed_at = None
        job.claimed_by = ""
        job.last_error = ""
        job.dedupe_key = None

    def mark_retry(
        self,
        job: WhatsAppIntegrationJob,
        *,
        error_message: str,
        response_payload: dict | None = None,
        finished_at=None,
    ) -> None:
        finished_at = finished_at or timezone.now()
        attempt_count = job.attempt_count + 1
        is_terminal = attempt_count >= job.max_attempts
        next_status = (
            WhatsAppIntegrationJobStatus.FAILURE
            if is_terminal
            else WhatsAppIntegrationJobStatus.RETRY
        )
        available_at = (
            finished_at
            if is_terminal
            else finished_at
            + timedelta(seconds=self._build_backoff_seconds(attempt_count))
        )
        dedupe_key = None if is_terminal else job.dedupe_key

        WhatsAppIntegrationJob.objects.filter(pk=job.pk).update(
            status=next_status,
            response_payload=response_payload,
            attempt_count=attempt_count,
            available_at=available_at,
            finished_at=finished_at if is_terminal else None,
            claimed_at=None,
            claimed_by="",
            last_error=error_message,
            dedupe_key=dedupe_key,
        )
        job.status = next_status
        job.response_payload = response_payload
        job.attempt_count = attempt_count
        job.available_at = available_at
        job.finished_at = finished_at if is_terminal else None
        job.claimed_at = None
        job.claimed_by = ""
        job.last_error = error_message
        job.dedupe_key = dedupe_key

    def enqueue_status_poll(
        self,
        *,
        session: WhatsAppSession,
        available_at=None,
        created_by=None,
        correlation_id: str = "",
    ) -> tuple[WhatsAppIntegrationJob, bool]:
        if available_at is None:
            available_at = timezone.now() + timedelta(
                seconds=self.get_status_poll_seconds()
            )
        return self.enqueue(
            session=session,
            job_type=WhatsAppIntegrationJobType.SYNC_STATUS,
            created_by=created_by,
            correlation_id=correlation_id,
            request_payload={"session_id": session.session_id},
            available_at=available_at,
        )

    def _build_backoff_seconds(self, attempt_count: int) -> int:
        return min(
            self.get_base_backoff_seconds() * (2 ** max(0, attempt_count - 1)),
            self.get_max_backoff_seconds(),
        )
