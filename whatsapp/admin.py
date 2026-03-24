from django.contrib import admin

from whatsapp.models import MeowInstance, WhatsAppActionAudit, WhatsAppSession


@admin.register(MeowInstance)
class MeowInstanceAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "base_url",
        "health_status",
        "is_active",
        "target_sessions",
        "warning_sessions",
        "max_sessions",
        "last_health_check_at",
    )
    list_filter = ("health_status", "is_active")
    search_fields = ("name", "base_url")


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

    @admin.display(description="Linha")
    def line_phone_number(self, obj):
        return obj.line.phone_number


@admin.register(WhatsAppActionAudit)
class WhatsAppActionAuditAdmin(admin.ModelAdmin):
    list_display = ("session", "action", "status", "created_by", "created_at")
    list_filter = ("action", "status")
    search_fields = ("session__session_id", "session__line__phone_number")
    autocomplete_fields = ("session", "created_by")
    readonly_fields = (
        "session",
        "action",
        "status",
        "request_payload",
        "response_payload",
        "created_by",
        "created_at",
    )
