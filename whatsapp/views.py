from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from core.mixins import RoleRequiredMixin
from telecom.models import PhoneLine
from users.models import SystemUser
from whatsapp.models import MeowInstance, WhatsAppSession
from whatsapp.services.capacity_service import MeowCapacityService
from whatsapp.services.health_service import MeowHealthCheckService
from whatsapp.services.reconcile_service import WhatsAppSessionReconcileService
from whatsapp.services.session_service import (
    WhatsAppSessionNotConfiguredError,
    WhatsAppSessionService,
    WhatsAppSessionServiceError,
)
from whatsapp.services.sync_service import WhatsAppSessionSyncService


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
        selected_instance = self._get_selected_instance(self.request.GET)
        selected_issue_code = self._get_selected_issue_code(self.request.GET)
        inconsistent_results = self._get_inconsistent_session_results(
            selected_instance_id=getattr(selected_instance, "id", None)
        )
        context["instance_summaries"] = MeowCapacityService().summarize_instances(
            include_inactive=True
        )
        context["issue_summary_counts"] = self._build_issue_summary_counts(
            inconsistent_results
        )
        context["problem_session_results"] = self._filter_problem_session_results(
            inconsistent_results,
            selected_issue_code=selected_issue_code,
        )
        context["selected_instance"] = selected_instance
        context["selected_issue_code"] = selected_issue_code
        context["issue_filter_options"] = [
            {"code": code, "label": label}
            for code, label in WhatsAppSessionReconcileService.ISSUE_MESSAGES.items()
        ]
        context["stale_minutes"] = getattr(
            settings,
            "WHATSAPP_SESSION_STALE_MINUTES",
            30,
        )
        return context

    def post(self, request, *args, **kwargs):
        selected_instance = self._get_selected_instance(request.POST)
        selected_issue_code = self._get_selected_issue_code(request.POST)
        selected_session = self._get_selected_session(request.POST)
        action = (request.POST.get("action") or "").strip()

        if action == "check_health":
            self._run_health_check(selected_instance)
        elif action == "sync_sessions":
            self._run_session_sync(selected_instance)
        elif action == "sync_session":
            self._run_single_session_sync(selected_session)
        elif action == "reconcile_sessions":
            self._run_session_reconcile(selected_instance)
        else:
            messages.error(request, "Acao operacional invalida.")

        return redirect(
            self._build_operations_url(selected_instance, selected_issue_code)
        )

    def _get_selected_instance(self, source):
        raw_instance_id = source.get("instance_id")
        if not raw_instance_id:
            return None

        try:
            instance_id = int(raw_instance_id)
        except (TypeError, ValueError):
            return None

        return MeowInstance.objects.filter(pk=instance_id).first()

    def _get_selected_issue_code(self, source) -> str | None:
        issue_code = (source.get("issue_code") or "").strip().upper()
        if issue_code in WhatsAppSessionReconcileService.ISSUE_MESSAGES:
            return issue_code
        return None

    def _get_selected_session(self, source) -> WhatsAppSession | None:
        raw_session_pk = source.get("session_pk")
        if not raw_session_pk:
            return None

        try:
            session_pk = int(raw_session_pk)
        except (TypeError, ValueError):
            return None

        return (
            WhatsAppSession.objects.select_related("line", "meow_instance")
            .filter(pk=session_pk)
            .first()
        )

    def _build_operations_url(
        self,
        selected_instance: MeowInstance | None,
        selected_issue_code: str | None = None,
    ) -> str:
        base_url = reverse("whatsapp_operations")
        query_params = []
        if selected_instance is not None:
            query_params.append(f"instance_id={selected_instance.id}")
        if selected_issue_code:
            query_params.append(f"issue_code={selected_issue_code}")
        if not query_params:
            return base_url
        return f"{base_url}?{'&'.join(query_params)}"

    def _run_health_check(self, selected_instance: MeowInstance | None) -> None:
        queryset = MeowInstance.objects.all()
        if selected_instance is not None:
            queryset = queryset.filter(pk=selected_instance.pk)

        results = MeowHealthCheckService().check_instances(
            queryset=queryset,
            include_inactive=True,
        )
        messages.success(
            self.request,
            f"Health check executado em {len(results)} instancia(s).",
        )

    def _run_session_sync(self, selected_instance: MeowInstance | None) -> None:
        queryset = WhatsAppSession.objects.all()
        if selected_instance is not None:
            queryset = queryset.filter(meow_instance=selected_instance)

        results = WhatsAppSessionSyncService().sync_sessions(
            queryset=queryset,
            include_inactive=True,
        )
        success_count = sum(result.success for result in results)
        failure_count = len(results) - success_count
        messages.success(
            self.request,
            (
                "Sincronizacao executada em "
                f"{len(results)} sessao(oes): "
                f"{success_count} sucesso, {failure_count} falha."
            ),
        )

    def _run_single_session_sync(
        self,
        selected_session: WhatsAppSession | None,
    ) -> None:
        if selected_session is None:
            messages.error(self.request, "Sessao operacional invalida.")
            return

        results = WhatsAppSessionSyncService().sync_sessions(
            queryset=WhatsAppSession.objects.filter(pk=selected_session.pk),
            include_inactive=True,
        )
        success_count = sum(result.success for result in results)
        failure_count = len(results) - success_count
        messages.success(
            self.request,
            (
                f"Sessao {selected_session.session_id} sincronizada: "
                f"{success_count} sucesso, {failure_count} falha."
            ),
        )

    def _run_session_reconcile(self, selected_instance: MeowInstance | None) -> None:
        queryset = WhatsAppSession.objects.all()
        if selected_instance is not None:
            queryset = queryset.filter(meow_instance=selected_instance)

        results = WhatsAppSessionReconcileService().reconcile_sessions(
            queryset=queryset,
            include_inactive=True,
        )
        inconsistent_count = sum(not result.is_consistent for result in results)
        messages.success(
            self.request,
            (
                "Reconciliação executada em "
                f"{len(results)} sessao(oes): "
                f"{len(results) - inconsistent_count} consistente(s), "
                f"{inconsistent_count} com inconsistencia."
            ),
        )

    def _get_inconsistent_session_results(
        self,
        *,
        selected_instance_id: int | None = None,
    ):
        queryset = WhatsAppSession.objects.all()
        if selected_instance_id is not None:
            queryset = queryset.filter(meow_instance_id=selected_instance_id)

        results = WhatsAppSessionReconcileService().reconcile_sessions(
            queryset=queryset,
            include_inactive=True,
        )
        inconsistent_results = [
            result for result in results if not result.is_consistent
        ]
        return sorted(
            inconsistent_results,
            key=lambda result: result.session.last_sync_at or result.session.updated_at,
            reverse=True,
        )

    def _filter_problem_session_results(
        self,
        results,
        *,
        selected_issue_code: str | None = None,
    ):
        if selected_issue_code:
            results = [
                result
                for result in results
                if selected_issue_code in result.issue_codes
            ]
        return results[:25]

    def _build_issue_summary_counts(self, results):
        counts = []
        for code, label in WhatsAppSessionReconcileService.ISSUE_MESSAGES.items():
            total = sum(code in result.issue_codes for result in results)
            if total:
                counts.append(
                    {
                        "code": code,
                        "label": label,
                        "count": total,
                    }
                )
        return sorted(counts, key=lambda item: (-item["count"], item["code"]))
