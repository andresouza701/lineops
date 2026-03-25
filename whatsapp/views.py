from __future__ import annotations

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View

from core.mixins import RoleRequiredMixin
from telecom.models import PhoneLine
from users.models import SystemUser
from whatsapp.models import WhatsAppSession
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
