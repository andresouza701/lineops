from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import LogoutView
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import FormView, TemplateView

from config.forms import UploadForm
from core.mixins import RoleRequiredMixin
from core.services.upload_service import process_upload_file
from users.models import SystemUser


class DashboardView(TemplateView):
    template_name = "dashboard.html"


class ProfileView(TemplateView):
    template_name = "profile.html"


class OperationsView(TemplateView):
    template_name = "operations.html"


class DocumentationView(TemplateView):
    template_name = "documentation.html"


class UploadView(RoleRequiredMixin, FormView):
    allowed_roles = [SystemUser.Role.ADMIN]
    template_name = "upload/upload.html"
    form_class = UploadForm
    success_url = reverse_lazy("upload")

    def form_valid(self, form):
        uploaded_file = form.cleaned_data["file"]
        saved_path = self._persist_file(uploaded_file)
        summary = process_upload_file(saved_path)

        self._notify(summary, saved_path.name)
        context = self.get_context_data(
            form=self.form_class(), summary=summary, last_uploaded=saved_path.name
        )
        return self.render_to_response(context)

    def form_invalid(self, form):
        messages.error(self.request, "Não foi possível processar o arquivo enviado.")
        return self.render_to_response(self.get_context_data(form=form))

    def _persist_file(self, uploaded_file) -> Path:
        upload_dir = Path(settings.MEDIA_ROOT) / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)

        timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
        original_name = Path(uploaded_file.name).name
        destination = upload_dir / f"{timestamp}_{original_name}"

        with destination.open("wb") as dest:
            for chunk in uploaded_file.chunks():
                dest.write(chunk)
        return destination

    def _notify(self, summary, filename: str) -> None:
        messages.success(
            self.request,
            (
                f"Arquivo {filename} recebido. "
                f"Linhas processadas: {summary.rows_processed}. "
                f"Colaboradores criados/atualizados: "
                f"{summary.employees_created}/{summary.employees_updated}. "
                f"SIM cards criados/atualizados: "
                f"{summary.simcards_created}/{summary.simcards_updated}."
            ),
        )

        if summary.has_errors:
            messages.error(
                self.request,
                f"Encontramos {len(summary.errors)} erro(s). Confira a lista abaixo.",
            )


class LogoutGetView(LogoutView):
    http_method_names = ["get", "post", "options"]

    def get(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)


class HealthCheckView(TemplateView):
    # Usa TemplateView apenas para evitar boilerplate; sobrepõe get
    def get(self, request, *args, **kwargs):
        return JsonResponse({"status": "ok"})


def custom_permission_denied_view(request, exception=None):
    return render(request, "403.html", status=403)


def custom_page_not_found_view(request, exception=None):
    return render(request, "404.html", status=404)
