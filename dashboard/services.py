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
        WhatsAppSessionStatus.NEW,
        WhatsAppSessionStatus.SESSION_REQUESTED,
        WhatsAppSessionStatus.QR_AVAILABLE,
        WhatsAppSessionStatus.WAITING_SCAN,
    ]
    DEGRADED_SESSION_STATUSES = [
        WhatsAppSessionStatus.FAILED,
        WhatsAppSessionStatus.EXPIRED,
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
        include_line_detail_url: bool = False,
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
            session = cls._get_phone_line_session(phone_line)

            items.append(
                {
                    "day": action.day,
                    "employee_name": row["employee"].full_name,
                    "portfolio": row["employee"].employee_id or "-",
                    "action_label": action.get_action_type_display(),
                    "phone_number": phone_line.phone_number if phone_line else "-",
                    "whatsapp_status_summary": cls._build_status_summary(
                        phone_line,
                        session,
                    ),
                    "note": action.note or "-",
                    "line_detail_url": (
                        reverse("telecom:phoneline_detail", args=[phone_line.pk])
                        if phone_line and include_line_detail_url
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

    @staticmethod
    def _get_phone_line_session(phone_line):
        if not phone_line:
            return None

        try:
            return phone_line.whatsapp_session
        except WhatsAppSession.DoesNotExist:
            return None

    @classmethod
    def _build_status_summary(cls, phone_line, session) -> str:
        if not phone_line:
            return "Sem linha visivel"
        if session is None:
            return "Nao configurado"
        return session.get_status_display()

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
