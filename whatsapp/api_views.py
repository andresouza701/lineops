from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions.roles import IsAdmin
from telecom.models import PhoneLine
from whatsapp.models import WhatsAppSession
from whatsapp.services.observability_service import (
    emit_integration_log,
    ensure_correlation_id,
)
from whatsapp.services.session_service import (
    WhatsAppSessionResult,
    WhatsAppSessionService,
)


class WhatsAppIntegrationCreateSerializer(serializers.Serializer):
    line_id = serializers.IntegerField(min_value=1)


class WhatsAppIntegrationApiMixin:
    permission_classes = [IsAdmin]
    session_service = WhatsAppSessionService()

    def get_correlation_id(self) -> str:
        return ensure_correlation_id(self.request.headers.get("X-Correlation-ID"))

    def build_response(
        self,
        payload: dict,
        *,
        correlation_id: str,
        status_code: int,
    ) -> Response:
        response = Response(payload, status=status_code)
        response["X-Correlation-ID"] = correlation_id
        return response

    def get_phone_line(self, line_id: int) -> PhoneLine:
        queryset = (
            PhoneLine.objects.filter(
                is_deleted=False,
                sim_card__is_deleted=False,
            )
            .select_related("sim_card")
            .order_by("id")
        )
        queryset = PhoneLine.visible_to_user(self.request.user, queryset)
        return get_object_or_404(queryset, pk=line_id)

    def get_session_queryset(self):
        line_queryset = PhoneLine.visible_to_user(
            self.request.user,
            PhoneLine.objects.filter(
                is_deleted=False,
                sim_card__is_deleted=False,
            ),
        )
        return (
            WhatsAppSession.objects.select_related("line", "meow_instance")
            .filter(line__in=line_queryset)
            .order_by("id")
        )

    def get_session(self) -> WhatsAppSession:
        return get_object_or_404(self.get_session_queryset(), pk=self.kwargs["session_pk"])

    def _has_valid_qr(self, session: WhatsAppSession) -> bool:
        if not session.qr_code:
            return False
        if session.qr_expires_at and session.qr_expires_at <= timezone.now():
            return False
        return True

    def serialize_session(
        self,
        session: WhatsAppSession,
        *,
        detail: str | None = None,
        correlation_id: str = "",
        include_qr: bool = False,
        result: WhatsAppSessionResult | None = None,
    ) -> dict:
        qr_code = (
            result.qr_code
            if include_qr and result is not None
            else session.qr_code
            if include_qr and self._has_valid_qr(session)
            else None
        )
        has_qr = (
            result.has_qr
            if result is not None
            else self._has_valid_qr(session)
        )
        connected = (
            result.connected
            if result is not None
            else session.status == "CONNECTED"
        )
        payload = {
            "id": session.pk,
            "line_id": session.line_id,
            "phone_number": session.line.phone_number,
            "session_id": session.session_id,
            "status": session.status,
            "status_display": session.get_status_display(),
            "version": session.version,
            "meow_instance": session.meow_instance.name if session.meow_instance_id else None,
            "connected": connected,
            "has_qr": has_qr,
            "qr_expires_at": (
                session.qr_expires_at.isoformat() if session.qr_expires_at else None
            ),
            "connected_at": (
                session.connected_at.isoformat() if session.connected_at else None
            ),
            "last_sync_at": (
                session.last_sync_at.isoformat() if session.last_sync_at else None
            ),
            "last_error": session.last_error,
            "is_active": session.is_active,
            "correlation_id": correlation_id,
        }
        if detail:
            payload["detail"] = detail
        if qr_code:
            payload["qr_code"] = qr_code
        if result and result.job_id is not None:
            payload["job"] = {
                "id": result.job_id,
                "type": (
                    session.integration_jobs.filter(pk=result.job_id)
                    .values_list("job_type", flat=True)
                    .first()
                ),
                "status": result.job_status,
                "available_at": (
                    result.job_available_at.isoformat()
                    if result.job_available_at
                    else None
                ),
                "created": result.job_created,
            }
        return payload


class WhatsAppIntegrationListCreateApiView(WhatsAppIntegrationApiMixin, APIView):
    def get(self, request, *args, **kwargs):
        correlation_id = self.get_correlation_id()
        sessions = list(self.get_session_queryset())
        emit_integration_log(
            "whatsapp.api.list",
            correlation_id=correlation_id,
            count=len(sessions),
            user_id=request.user.pk,
        )
        payload = {
            "count": len(sessions),
            "results": [
                self.serialize_session(session, correlation_id=correlation_id)
                for session in sessions
            ],
        }
        return self.build_response(
            payload,
            correlation_id=correlation_id,
            status_code=status.HTTP_200_OK,
        )

    def post(self, request, *args, **kwargs):
        correlation_id = self.get_correlation_id()
        serializer = WhatsAppIntegrationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        line = self.get_phone_line(serializer.validated_data["line_id"])
        result = self.session_service.request_connect(
            line,
            created_by=request.user,
            correlation_id=correlation_id,
        )
        effective_correlation_id = result.correlation_id or correlation_id
        emit_integration_log(
            "whatsapp.api.create_or_reuse",
            correlation_id=effective_correlation_id,
            line_id=line.pk,
            session_pk=result.session.pk,
            created=bool(result.session_created),
            status=result.status,
            user_id=request.user.pk,
        )
        return self.build_response(
            self.serialize_session(
                result.session,
                detail=result.detail,
                correlation_id=effective_correlation_id,
                result=result,
            ),
            correlation_id=effective_correlation_id,
            status_code=(
                status.HTTP_201_CREATED
                if result.session_created
                else status.HTTP_200_OK
            ),
        )


class WhatsAppIntegrationDetailApiView(WhatsAppIntegrationApiMixin, APIView):
    def get(self, request, *args, **kwargs):
        correlation_id = self.get_correlation_id()
        session = self.get_session()
        emit_integration_log(
            "whatsapp.api.retrieve",
            correlation_id=correlation_id,
            session_pk=session.pk,
            session_id=session.session_id,
            user_id=request.user.pk,
        )
        return self.build_response(
            self.serialize_session(session, correlation_id=correlation_id),
            correlation_id=correlation_id,
            status_code=status.HTTP_200_OK,
        )


class WhatsAppIntegrationStatusApiView(WhatsAppIntegrationApiMixin, APIView):
    def get(self, request, *args, **kwargs):
        correlation_id = self.get_correlation_id()
        session = self.get_session()
        result = self.session_service.get_local_status(session.line)
        result.correlation_id = correlation_id
        emit_integration_log(
            "whatsapp.api.status",
            correlation_id=correlation_id,
            session_pk=session.pk,
            session_id=session.session_id,
            status=result.status,
            user_id=request.user.pk,
        )
        return self.build_response(
            self.serialize_session(
                result.session,
                detail=result.detail,
                correlation_id=correlation_id,
                result=result,
            ),
            correlation_id=correlation_id,
            status_code=status.HTTP_200_OK,
        )


class WhatsAppIntegrationGenerateQrApiView(WhatsAppIntegrationApiMixin, APIView):
    def post(self, request, *args, **kwargs):
        correlation_id = self.get_correlation_id()
        session = self.get_session()
        result = self.session_service.request_qr(
            session.line,
            created_by=request.user,
            correlation_id=correlation_id,
        )
        effective_correlation_id = result.correlation_id or correlation_id
        has_local_qr = bool(result.has_qr and result.qr_code)
        queued = result.job_id is not None
        emit_integration_log(
            "whatsapp.api.generate_qr",
            correlation_id=effective_correlation_id,
            session_pk=session.pk,
            session_id=session.session_id,
            has_local_qr=has_local_qr,
            queued=queued,
            user_id=request.user.pk,
        )
        return self.build_response(
            self.serialize_session(
                result.session,
                detail=result.detail,
                correlation_id=effective_correlation_id,
                include_qr=has_local_qr,
                result=result,
            ),
            correlation_id=effective_correlation_id,
            status_code=status.HTTP_202_ACCEPTED if queued else status.HTTP_200_OK,
        )


class WhatsAppIntegrationDeleteSessionApiView(WhatsAppIntegrationApiMixin, APIView):
    def delete(self, request, *args, **kwargs):
        correlation_id = self.get_correlation_id()
        session = self.get_session()
        result = self.session_service.request_disconnect(
            session.line,
            created_by=request.user,
            correlation_id=correlation_id,
        )
        effective_correlation_id = result.correlation_id or correlation_id
        emit_integration_log(
            "whatsapp.api.delete_session",
            correlation_id=effective_correlation_id,
            session_pk=session.pk,
            session_id=session.session_id,
            status=result.status,
            user_id=request.user.pk,
        )
        return self.build_response(
            self.serialize_session(
                result.session,
                detail=result.detail,
                correlation_id=effective_correlation_id,
                result=result,
            ),
            correlation_id=effective_correlation_id,
            status_code=status.HTTP_202_ACCEPTED,
        )
