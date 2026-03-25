from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from core.mixins import RoleRequiredMixin
from telecom.models import PhoneLine
from users.models import SystemUser
from whatsapp.choices import MeowInstanceHealthStatus, WhatsAppSessionStatus
from whatsapp.models import MeowInstance, WhatsAppSession
from whatsapp.services.capacity_service import MeowCapacityService
from whatsapp.services.session_service import (
    WhatsAppSessionNotConfiguredError,
    WhatsAppSessionService,
    WhatsAppSessionServiceError,
)


class WhatsAppPhoneLineMixin(RoleRequiredMixin):
    allowed_roles = [SystemUser.Role.ADMIN]
    session_service = WhatsAppSessionService()

    def get_phone_line(self) -> PhoneLine:
        queryset = (
            PhoneLine.objects.filter(
                is_deleted=False,
                sim_card__is_deleted=False,
            )
            .select_related("sim_card")
            .order_by("id")
        )

        queryset = PhoneLine.visible_to_user(self.request.user, queryset)
        return get_object_or_404(queryset, pk=self.kwargs["line_pk"])

    def get_local_session(self, line: PhoneLine) -> WhatsAppSession | None:
        return (
            WhatsAppSession.objects.select_related("meow_instance")
            .filter(line=line)
            .first()
        )

    def is_ajax(self) -> bool:
        return self.request.headers.get("X-Requested-With") == "XMLHttpRequest"

    def redirect_to_line_detail(self, line: PhoneLine):
        return redirect("telecom:phoneline_detail", pk=line.pk)

    def serialize_session(
        self,
        line: PhoneLine,
        session: WhatsAppSession | None,
        *,
        qr_code: str | None = None,
        has_qr: bool = False,
        connected: bool | None = None,
    ) -> dict:
        return {
            "line_id": line.pk,
            "phone_number": line.phone_number,
            "configured": session is not None,
            "session_id": session.session_id if session else None,
            "status": session.status if session else None,
            "status_display": (
                session.get_status_display() if session else "Nao Configurado"
            ),
            "meow_instance": (
                session.meow_instance.name
                if session and session.meow_instance_id
                else None
            ),
            "last_error": session.last_error if session else "",
            "last_sync_at": (
                session.last_sync_at.isoformat()
                if session and session.last_sync_at
                else None
            ),
            "connected_at": (
                session.connected_at.isoformat()
                if session and session.connected_at
                else None
            ),
            "has_qr": has_qr,
            "qr_code": qr_code,
            "connected": bool(connected) if connected is not None else False,
        }


class WhatsAppSessionStatusView(WhatsAppPhoneLineMixin, View):
    def get(self, request, *args, **kwargs):
        line = self.get_phone_line()

        try:
            result = self.session_service.get_status(line)
            payload = self.serialize_session(
                line,
                result.session,
                connected=result.connected,
            )
            return JsonResponse(payload)
        except WhatsAppSessionNotConfiguredError:
            payload = self.serialize_session(line, None)
            return JsonResponse(payload)
        except WhatsAppSessionServiceError as exc:
            session = self.get_local_session(line)
            payload = self.serialize_session(line, session)
            payload["error"] = str(exc)
            return JsonResponse(payload, status=502)


class WhatsAppSessionQRCodeView(WhatsAppPhoneLineMixin, View):
    def get(self, request, *args, **kwargs):
        line = self.get_phone_line()

        try:
            result = self.session_service.get_qr(line)
            payload = self.serialize_session(
                line,
                result.session,
                qr_code=result.qr_code,
                has_qr=result.has_qr,
                connected=result.connected,
            )
            return JsonResponse(payload)
        except WhatsAppSessionNotConfiguredError as exc:
            payload = self.serialize_session(line, None)
            payload["error"] = str(exc)
            return JsonResponse(payload, status=404)
        except WhatsAppSessionServiceError as exc:
            session = self.get_local_session(line)
            payload = self.serialize_session(line, session)
            payload["error"] = str(exc)
            return JsonResponse(payload, status=502)


class WhatsAppSessionConnectView(WhatsAppPhoneLineMixin, View):
    def post(self, request, *args, **kwargs):
        line = self.get_phone_line()

        try:
            result = self.session_service.connect(line)
        except WhatsAppSessionServiceError as exc:
            if self.is_ajax():
                payload = self.serialize_session(line, self.get_local_session(line))
                payload["error"] = str(exc)
                return JsonResponse(payload, status=502)
            messages.error(request, f"Erro ao conectar sessao: {exc}")
            return self.redirect_to_line_detail(line)
        if self.is_ajax():
            payload = self.serialize_session(
                line,
                result.session,
                connected=result.connected,
            )
            return JsonResponse(payload)
        messages.success(request, "Sessao conectada com sucesso.")
        return self.redirect_to_line_detail(line)


class WhatsAppSessionDisconnectView(WhatsAppPhoneLineMixin, View):
    def post(self, request, *args, **kwargs):
        line = self.get_phone_line()

        try:
            result = self.session_service.disconnect(line)
        except WhatsAppSessionNotConfiguredError as exc:
            if self.is_ajax():
                payload = self.serialize_session(line, None)
                payload["error"] = str(exc)
                return JsonResponse(payload, status=400)

            messages.error(request, str(exc))
            return self.redirect_to_line_detail(line)
        except WhatsAppSessionServiceError as exc:
            if self.is_ajax():
                payload = self.serialize_session(line, self.get_local_session(line))
                payload["error"] = str(exc)
                return JsonResponse(payload, status=502)

            messages.error(request, f"Erro ao desconectar sessao: {exc}")
            return self.redirect_to_line_detail(line)

        if self.is_ajax():
            payload = self.serialize_session(
                line,
                result.session,
                connected=result.connected,
            )
            return JsonResponse(payload)

        messages.success(request, "Sessao desconectada com sucesso.")
        return self.redirect_to_line_detail(line)


class WhatsAppOperationsView(RoleRequiredMixin, TemplateView):
    allowed_roles = [SystemUser.Role.ADMIN, SystemUser.Role.DEV]
    template_name = "whatsapp/operations.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_instance = self._get_selected_instance()
        context["instance_summaries"] = MeowCapacityService().summarize_instances(
            include_inactive=True
        )
        context["problem_sessions"] = self._get_problem_sessions(
            selected_instance_id=getattr(selected_instance, "id", None)
        )
        context["selected_instance"] = selected_instance
        context["stale_minutes"] = getattr(
            settings,
            "WHATSAPP_SESSION_STALE_MINUTES",
            30,
        )
        return context

    def _get_selected_instance(self):
        raw_instance_id = self.request.GET.get("instance_id")
        if not raw_instance_id:
            return None

        try:
            instance_id = int(raw_instance_id)
        except (TypeError, ValueError):
            return None

        return MeowInstance.objects.filter(pk=instance_id).first()

    def _get_problem_sessions(self, *, selected_instance_id: int | None = None):
        stale_minutes = getattr(settings, "WHATSAPP_SESSION_STALE_MINUTES", 30)
        stale_threshold = timezone.now() - timedelta(minutes=stale_minutes)

        queryset = WhatsAppSession.objects.select_related(
            "line__sim_card",
            "meow_instance",
        )
        if selected_instance_id is not None:
            queryset = queryset.filter(meow_instance_id=selected_instance_id)

        return (
            queryset.filter(
                Q(last_error__gt="")
                | Q(
                    status__in=[
                        WhatsAppSessionStatus.ERROR,
                        WhatsAppSessionStatus.DISCONNECTED,
                    ]
                )
                | Q(meow_instance__health_status=MeowInstanceHealthStatus.DEGRADED)
                | Q(meow_instance__health_status=MeowInstanceHealthStatus.UNAVAILABLE)
                | Q(meow_instance__is_active=False)
                | Q(line__is_deleted=True)
                | Q(line__sim_card__is_deleted=True)
                | Q(last_sync_at__isnull=True)
                | Q(last_sync_at__lt=stale_threshold)
            )
            .order_by("-last_sync_at", "-updated_at")[:25]
        )
