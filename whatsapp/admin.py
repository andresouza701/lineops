from django.contrib import admin
from django.db.models import Count, Q

from whatsapp.models import (
    MeowInstance,
    WhatsAppActionAudit,
    WhatsAppIntegrationJob,
    WhatsAppScheduledJob,
    WhatsAppSession,
    WhatsAppWorkerState,
)
from whatsapp.services.health_service import MeowHealthCheckService
from whatsapp.services.reconcile_service import WhatsAppSessionReconcileService
from whatsapp.services.sync_service import WhatsAppSessionSyncService


@admin.register(MeowInstance)
class MeowInstanceAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "base_url",
        "health_status",
        "is_active",
        "active_sessions_count",
        "connected_sessions_count",
        "degraded_sessions_count",
        "target_sessions",
        "warning_sessions",
        "max_sessions",
        "last_health_check_at",
    )
    list_filter = ("health_status", "is_active")
    search_fields = ("name", "base_url")
    actions = ("run_health_check",)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(
            active_sessions_count_value=Count(
                "whatsapp_sessions",
                filter=Q(whatsapp_sessions__is_active=True),
            ),
            connected_sessions_count_value=Count(
                "whatsapp_sessions",
                filter=Q(
                    whatsapp_sessions__is_active=True,
                    whatsapp_sessions__status="CONNECTED",
                ),
            ),
            degraded_sessions_count_value=Count(
                "whatsapp_sessions",
                filter=Q(
                    whatsapp_sessions__is_active=True,
                    whatsapp_sessions__status__in=["ERROR", "DISCONNECTED"],
                ),
            ),
        )

    @admin.display(description="Sessoes ativas", ordering="active_sessions_count_value")
    def active_sessions_count(self, obj):
        return obj.active_sessions_count_value

    @admin.display(
        description="Sessoes conectadas",
        ordering="connected_sessions_count_value",
    )
    def connected_sessions_count(self, obj):
        return obj.connected_sessions_count_value

    @admin.display(
        description="Sessoes degradadas",
        ordering="degraded_sessions_count_value",
    )
    def degraded_sessions_count(self, obj):
        return obj.degraded_sessions_count_value

    @admin.action(description="Executar health check nas instancias selecionadas")
    def run_health_check(self, request, queryset):
        service = MeowHealthCheckService()
        results = service.check_instances(queryset=queryset, include_inactive=True)
        self.message_user(
            request,
            (
                f"Health check executado em {len(results)} instancia(s)."
            ),
        )


@admin.register(WhatsAppSession)
class WhatsAppSessionAdmin(admin.ModelAdmin):
    list_display = (
        "line_phone_number",
        "session_id",
        "meow_instance",
        "status",
        "is_active",
        "connected_at",
        "last_sync_at",
    )
    list_filter = ("status", "is_active", "meow_instance")
    search_fields = ("line__phone_number", "session_id", "meow_instance__name")
    autocomplete_fields = ("meow_instance",)
    actions = ("sync_selected_sessions", "reconcile_selected_sessions")

    @admin.display(description="Linha")
    def line_phone_number(self, obj):
        return obj.line.phone_number

    @admin.action(description="Sincronizar sessoes selecionadas")
    def sync_selected_sessions(self, request, queryset):
        service = WhatsAppSessionSyncService()
        results = service.sync_sessions(queryset=queryset, include_inactive=True)
        success_count = sum(result.success for result in results)
        failure_count = len(results) - success_count
        self.message_user(
            request,
            (
                "Sincronizacao executada em "
                f"{len(results)} sessao(oes): "
                f"{success_count} sucesso, {failure_count} falha."
            ),
        )

    @admin.action(description="Reconciliar sessoes selecionadas")
    def reconcile_selected_sessions(self, request, queryset):
        service = WhatsAppSessionReconcileService()
        results = service.reconcile_sessions(queryset=queryset, include_inactive=True)
        inconsistent_count = sum(not result.is_consistent for result in results)
        self.message_user(
            request,
            (
                "Reconciliação executada em "
                f"{len(results)} sessao(oes): "
                f"{len(results) - inconsistent_count} consistente(s), "
                f"{inconsistent_count} com inconsistencia."
            ),
        )


@admin.register(WhatsAppActionAudit)
class WhatsAppActionAuditAdmin(admin.ModelAdmin):
    list_display = (
        "target_reference",
        "action",
        "status",
        "duration_ms",
        "created_by",
        "created_at",
    )
    list_filter = ("action", "status")
    search_fields = (
        "session__session_id",
        "session__line__phone_number",
        "meow_instance__name",
    )
    autocomplete_fields = ("session", "meow_instance", "created_by")
    readonly_fields = (
        "session",
        "meow_instance",
        "action",
        "status",
        "request_payload",
        "response_payload",
        "duration_ms",
        "created_by",
        "created_at",
    )

    @admin.display(description="Contexto")
    def target_reference(self, obj):
        if obj.session_id:
            return obj.session
        return obj.meow_instance


@admin.register(WhatsAppScheduledJob)
class WhatsAppScheduledJobAdmin(admin.ModelAdmin):
    list_display = (
        "job_code",
        "interval_seconds",
        "last_status",
        "is_running",
        "last_started_at",
        "last_finished_at",
        "next_run_at",
    )
    list_filter = ("job_code", "last_status", "is_running")
    readonly_fields = (
        "job_code",
        "interval_seconds",
        "last_status",
        "last_detail",
        "is_running",
        "last_started_at",
        "last_finished_at",
        "next_run_at",
        "created_at",
        "updated_at",
    )


@admin.register(WhatsAppIntegrationJob)
class WhatsAppIntegrationJobAdmin(admin.ModelAdmin):
    list_display = (
        "session",
        "job_type",
        "status",
        "attempt_count",
        "available_at",
        "claimed_by",
        "finished_at",
    )
    list_filter = ("job_type", "status")
    search_fields = ("session__session_id", "session__line__phone_number")
    autocomplete_fields = ("session", "created_by")
    readonly_fields = (
        "session",
        "job_type",
        "status",
        "dedupe_key",
        "request_payload",
        "response_payload",
        "attempt_count",
        "max_attempts",
        "available_at",
        "claimed_at",
        "claimed_by",
        "finished_at",
        "last_error",
        "created_by",
        "created_at",
        "updated_at",
    )


@admin.register(WhatsAppWorkerState)
class WhatsAppWorkerStateAdmin(admin.ModelAdmin):
    list_display = (
        "worker_code",
        "is_running",
        "last_heartbeat_at",
        "last_processed_job_at",
        "updated_at",
    )
    search_fields = ("worker_code",)
    readonly_fields = (
        "worker_code",
        "is_running",
        "last_heartbeat_at",
        "last_processed_job_at",
        "last_error",
        "created_at",
        "updated_at",
    )
