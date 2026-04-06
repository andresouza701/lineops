from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from whatsapp.choices import (
    MeowInstanceHealthStatus,
    WhatsAppActionStatus,
    WhatsAppActionType,
    WhatsAppIntegrationJobStatus,
    WhatsAppIntegrationJobType,
    WhatsAppSchedulerJobCode,
    WhatsAppSchedulerJobStatus,
    WhatsAppSessionStatus,
)


class MeowInstance(models.Model):
    name = models.CharField(max_length=100, unique=True)
    base_url = models.URLField(unique=True)
    is_active = models.BooleanField(default=True, db_index=True)
    health_status = models.CharField(
        max_length=20,
        choices=MeowInstanceHealthStatus.choices,
        default=MeowInstanceHealthStatus.UNKNOWN,
        db_index=True,
    )
    target_sessions = models.PositiveSmallIntegerField(default=35)
    warning_sessions = models.PositiveSmallIntegerField(default=40)
    max_sessions = models.PositiveSmallIntegerField(default=45)
    last_health_check_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["health_status", "is_active"]),
        ]

    def clean(self):
        if self.target_sessions > self.warning_sessions:
            raise ValidationError(
                {"target_sessions": "target_sessions deve ser <= warning_sessions."}
            )
        if self.warning_sessions > self.max_sessions:
            raise ValidationError(
                {"warning_sessions": "warning_sessions deve ser <= max_sessions."}
            )

    def save(self, *args, **kwargs):
        if self.base_url:
            self.base_url = self.base_url.rstrip("/")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class WhatsAppSession(models.Model):
    line = models.OneToOneField(
        "telecom.PhoneLine",
        on_delete=models.CASCADE,
        related_name="whatsapp_session",
    )
    meow_instance = models.ForeignKey(
        "whatsapp.MeowInstance",
        on_delete=models.PROTECT,
        related_name="whatsapp_sessions",
    )
    session_id = models.CharField(max_length=100, unique=True, db_index=True)
    status = models.CharField(
        max_length=32,
        choices=WhatsAppSessionStatus.choices,
        default=WhatsAppSessionStatus.PENDING_NEW_NUMBER,
        db_index=True,
    )
    version = models.PositiveIntegerField(default=1)
    connected_at = models.DateTimeField(null=True, blank=True)
    qr_code = models.TextField(blank=True, default="")
    qr_last_generated_at = models.DateTimeField(null=True, blank=True)
    qr_expires_at = models.DateTimeField(null=True, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["session_id"]
        indexes = [
            models.Index(fields=["status", "is_active"]),
            models.Index(fields=["meow_instance", "status"]),
        ]

    def __str__(self):
        return f"{self.line.phone_number} - {self.status}"


class WhatsAppIntegrationJob(models.Model):
    session = models.ForeignKey(
        "whatsapp.WhatsAppSession",
        on_delete=models.CASCADE,
        related_name="integration_jobs",
    )
    job_type = models.CharField(
        max_length=32,
        choices=WhatsAppIntegrationJobType.choices,
        db_index=True,
    )
    status = models.CharField(
        max_length=16,
        choices=WhatsAppIntegrationJobStatus.choices,
        default=WhatsAppIntegrationJobStatus.PENDING,
        db_index=True,
    )
    dedupe_key = models.CharField(
        max_length=128,
        unique=True,
        null=True,
        blank=True,
    )
    request_payload = models.JSONField(null=True, blank=True)
    response_payload = models.JSONField(null=True, blank=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    available_at = models.DateTimeField(db_index=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    claimed_by = models.CharField(max_length=64, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["available_at", "id"]
        indexes = [
            models.Index(fields=["status", "available_at"]),
            models.Index(fields=["session", "job_type", "status"]),
        ]

    def __str__(self):
        return f"{self.session.session_id} - {self.job_type} - {self.status}"


class WhatsAppActionAudit(models.Model):
    session = models.ForeignKey(
        "whatsapp.WhatsAppSession",
        on_delete=models.CASCADE,
        related_name="action_audits",
        null=True,
        blank=True,
    )
    meow_instance = models.ForeignKey(
        "whatsapp.MeowInstance",
        on_delete=models.PROTECT,
        related_name="action_audits",
        null=True,
        blank=True,
    )
    action = models.CharField(max_length=32, choices=WhatsAppActionType.choices)
    status = models.CharField(max_length=16, choices=WhatsAppActionStatus.choices)
    request_payload = models.JSONField(null=True, blank=True)
    response_payload = models.JSONField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["session", "-created_at"]),
            models.Index(fields=["action", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(session__isnull=False)
                    | models.Q(meow_instance__isnull=False)
                ),
                name="whatsapp_audit_has_target",
            ),
        ]

    def __str__(self):
        target = (
            self.session.session_id
            if self.session_id
            else self.meow_instance.name
            if self.meow_instance_id
            else "sem-contexto"
        )
        return f"{target} - {self.action} - {self.status}"


class WhatsAppScheduledJob(models.Model):
    job_code = models.CharField(
        max_length=32,
        choices=WhatsAppSchedulerJobCode.choices,
        unique=True,
        db_index=True,
    )
    interval_seconds = models.PositiveIntegerField()
    is_running = models.BooleanField(default=False, db_index=True)
    last_status = models.CharField(
        max_length=16,
        choices=WhatsAppSchedulerJobStatus.choices,
        default=WhatsAppSchedulerJobStatus.IDLE,
    )
    last_detail = models.TextField(blank=True)
    last_started_at = models.DateTimeField(null=True, blank=True)
    last_finished_at = models.DateTimeField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["job_code"]
        indexes = [
            models.Index(fields=["is_running", "next_run_at"]),
        ]

    def __str__(self):
        return self.get_job_code_display()


class WhatsAppWorkerState(models.Model):
    worker_code = models.CharField(max_length=64, unique=True)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_processed_job_at = models.DateTimeField(null=True, blank=True)
    is_running = models.BooleanField(default=False, db_index=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["worker_code"]

    def __str__(self):
        return self.worker_code
