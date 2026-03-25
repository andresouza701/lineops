from django.urls import reverse

from dashboard.models import DailyUserAction
from whatsapp.choices import MeowInstanceHealthStatus, WhatsAppSessionStatus
from whatsapp.models import MeowInstance, WhatsAppSession


class DashboardWhatsAppService:
    PENDING_ACTION_TYPES = {
        DailyUserAction.ActionType.NEW_NUMBER,
        DailyUserAction.ActionType.RECONNECT_WHATSAPP,
    }
    PENDING_SESSION_STATUSES = [
        WhatsAppSessionStatus.PENDING_NEW_NUMBER,
        WhatsAppSessionStatus.PENDING_RECONNECT,
        WhatsAppSessionStatus.CONNECTING,
        WhatsAppSessionStatus.QR_PENDING,
    ]
    DEGRADED_SESSION_STATUSES = [
        WhatsAppSessionStatus.ERROR,
        WhatsAppSessionStatus.DISCONNECTED,
    ]

    @classmethod
    def count_pending_actions(cls, rows) -> dict[str, int]:
        counts = {
            "new_number": 0,
            "reconnect_whatsapp": 0,
        }
        for row in rows:
            action = row.get("action")
            if not action or action.action_type not in cls.PENDING_ACTION_TYPES:
                continue

            if action.action_type == DailyUserAction.ActionType.NEW_NUMBER:
                counts["new_number"] += 1
            elif action.action_type == DailyUserAction.ActionType.RECONNECT_WHATSAPP:
                counts["reconnect_whatsapp"] += 1

        return counts

    @classmethod
    def build_pending_summary(
        cls,
        rows,
        *,
        limit: int = 8,
        action_board_url: str | None = None,
        allocation_visibility_resolver=None,
    ) -> dict:
        if allocation_visibility_resolver is None:
            allocation_visibility_resolver = lambda allocation: bool(allocation)

        items = []
        for row in rows:
            action = row.get("action")
            if not action or action.action_type not in cls.PENDING_ACTION_TYPES:
                continue

            allocation = row.get("allocation")
            phone_line = None
            if allocation and allocation_visibility_resolver(allocation):
                phone_line = allocation.phone_line

            items.append(
                {
                    "day": action.day,
                    "employee_name": row["employee"].full_name,
                    "portfolio": row["employee"].employee_id or "-",
                    "action_label": action.get_action_type_display(),
                    "phone_number": phone_line.phone_number if phone_line else "-",
                    "note": action.note or "-",
                    "line_detail_url": (
                        reverse("telecom:phoneline_detail", args=[phone_line.pk])
                        if phone_line
                        else None
                    ),
                }
            )

        items.sort(
            key=lambda item: (item["day"], item["employee_name"].lower()),
            reverse=True,
        )

        summary = {
            "total": len(items),
            "items": items[:limit],
            **cls.count_pending_actions(rows),
        }
        if action_board_url is not None:
            summary["action_board_url"] = action_board_url
        return summary

    @classmethod
    def build_meow_operational_summary(cls) -> dict[str, int]:
        instances = MeowInstance.objects.all()
        active_sessions = WhatsAppSession.objects.filter(is_active=True)

        return {
            "total_instances": instances.count(),
            "healthy_instances": instances.filter(
                health_status=MeowInstanceHealthStatus.HEALTHY
            ).count(),
            "degraded_instances": instances.filter(
                health_status=MeowInstanceHealthStatus.DEGRADED
            ).count(),
            "unavailable_instances": instances.filter(
                health_status=MeowInstanceHealthStatus.UNAVAILABLE
            ).count(),
            "active_sessions": active_sessions.count(),
            "connected_sessions": active_sessions.filter(
                status=WhatsAppSessionStatus.CONNECTED
            ).count(),
            "pending_sessions": active_sessions.filter(
                status__in=cls.PENDING_SESSION_STATUSES
            ).count(),
            "degraded_sessions": active_sessions.filter(
                status__in=cls.DEGRADED_SESSION_STATUSES
            ).count(),
        }
