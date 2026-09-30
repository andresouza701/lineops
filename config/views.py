import logging
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import LogoutView
from django.core.paginator import EmptyPage
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import FormView, TemplateView, View

from config.forms import (
    REPORT_CHOICES,
    AllocationsReportQueryForm,
    DailyIndicatorsReportQueryForm,
    LineHistoryReportQueryForm,
    LineInventoryReportQueryForm,
    PendenciesReportQueryForm,
    UploadForm,
    WhatsAppSealReportQueryForm,
)
from core.mixins import AuthenticadView, RoleRequiredMixin
from core.services.allocations_export_service import build_allocations_export_response
from core.services.allocations_report_service import build_allocations_report
from core.services.daily_indicators_export_service import build_daily_indicators_export_response
from core.services.daily_indicators_report_service import build_daily_indicators_report
from core.services.line_history_export_service import build_line_history_export_response
from core.services.line_history_report_service import build_line_history_report
from core.services.line_inventory_export_service import build_line_inventory_export_response
from core.services.line_inventory_report_service import build_line_inventory_report
from core.services.pendencies_export_service import build_pendencies_export_response
from core.services.pendencies_report_service import build_pendencies_report
from core.services.report_export_service import build_whatsapp_seal_export_response
from core.services.upload_service import process_upload_file
from core.services.whatsapp_seal_report_service import build_whatsapp_seal_report
from users.models import SystemUser

logger = logging.getLogger(__name__)


class DashboardView(AuthenticadView, TemplateView):
    template_name = "dashboard.html"


class ProfileView(AuthenticadView, TemplateView):
    template_name = "profile.html"


class OperationsView(AuthenticadView, TemplateView):
    template_name = "operations.html"


class DocumentationView(AuthenticadView, TemplateView):
    template_name = "documentation.html"


REPORT_COMMON_PARAM_NAMES = {
    "relatorio",
    "data_inicial",
    "data_final",
    "incluir_excluidos",
    "page",
    "linha",
}

# Parametros que so fazem sentido para o relatorio indicado — nao entram no
# whitelist global: cada relatorio so aceita os seus proprios, mesmo que
# outro relatorio ja tenha um nome reservado (REL-09-T identificou o risco
# de ampliar indiscriminadamente um unico set global).
REPORT_SPECIFIC_PARAM_NAMES = {
    "whatsapp_seal": {"selo", "pagamento", "situacao"},
    "line_inventory": {
        "status_linha",
        "operadora",
        "origem",
        "canal",
        "com_selo",
        "com_vinculo",
    },
    "allocations": {"situacao_alocacao", "funcionario"},
    "pendencies": {
        "situacao_pendencia",
        "motivo_pendencia",
        "com_responsavel",
        "funcionario",
    },
    "line_history": {"tipo_evento", "fonte_evento", "ator"},
}

REPORT_FORM_CLASSES = {
    "whatsapp_seal": WhatsAppSealReportQueryForm,
    "line_inventory": LineInventoryReportQueryForm,
    "allocations": AllocationsReportQueryForm,
    "pendencies": PendenciesReportQueryForm,
    "line_history": LineHistoryReportQueryForm,
    "daily_indicators": DailyIndicatorsReportQueryForm,
}

# Relatorios com motor de consulta (Q) implementado, respectivamente com
# motor de exportacao (E) implementado. Os seis relatorios do catalogo
# REL-01 agora tem os dois motores — Indicadores diarios (REL-13-Q) ganhou
# primeiro SOMENTE consulta (unica vez que Q e E divergiram para um
# relatorio do catalogo), e REL-13-E fechou a exportacao, reaproveitando
# integralmente o mesmo calculo (`build_indicator_for_day`) sem redefinir
# nenhuma formula.
REPORT_QUERY_ENGINES = {
    "whatsapp_seal", "line_inventory", "allocations", "pendencies", "line_history",
    "daily_indicators",
}
REPORT_EXPORT_ENGINES = {
    "whatsapp_seal", "line_inventory", "allocations", "pendencies", "line_history",
    "daily_indicators",
}

# Uniao de todos os nomes possiveis, usada so para montar o dicionario `raw`
# (eco dos valores submetidos nos campos do formulario) — nao e o whitelist
# de validacao, que e por relatorio (ver _validate_report_query_params).
ALL_REPORT_PARAM_NAMES = REPORT_COMMON_PARAM_NAMES.union(
    *REPORT_SPECIFIC_PARAM_NAMES.values()
)


def _validate_report_query_params(get_params, *, available_relatorios):
    """Validacao estrita comum (REL-07) dos parametros de consulta/exportacao
    do relatorio: parametro repetido, parametro desconhecido, forma/valores
    (via form especifico do relatorio) e relatorio ainda nao implementado
    (`available_relatorios` distingue motor de consulta de motor de
    exportacao — cada view chama com o conjunto que lhe cabe). Reaproveitada
    por ReportsHomeView e ReportsExportView — nao duplicada.

    O whitelist de nomes permitidos depende do `relatorio` informado (mais
    os nomes comuns): um parametro especifico de um relatorio nunca e
    "conhecido" para outro relatorio, mesmo que o nome exista em algum form.
    SEM excecao — inclusive para ReportsHomeView. A navegacao de troca de
    relatorio (REL-12-V/REL-12-V-2) NAO se resolve afrouxando este
    whitelist (uma primeira tentativa nesse sentido foi revertida: violava
    "consulta mantem whitelist estrita" mesmo para requisicoes diretas sem
    nenhuma troca de dropdown envolvida — ver
    ReportQueryStrictWhitelistRegressionTests em
    config/tests/test_reports_hub.py). A solucao real esta na ESTRUTURA de
    `templates/reports/home.html`: a troca de relatorio usa um <form>
    separado (so `relatorio` + comuns), que nunca inclui os campos
    especificos do relatorio anteriormente exibido — entao a requisicao que
    o navegador efetivamente envia numa troca ja e, por construcao, valida
    para este whitelist estrito, sem precisar de nenhuma tolerancia aqui.

    Retorna (extra_context, status, cleaned_data). cleaned_data e None em
    qualquer caso de erro (extra_context/status descrevem o motivo)."""
    extra_context = {}

    relatorio_value = get_params.get("relatorio")
    allowed_names = REPORT_COMMON_PARAM_NAMES | REPORT_SPECIFIC_PARAM_NAMES.get(
        relatorio_value, set()
    )

    for name in allowed_names:
        if len(get_params.getlist(name)) > 1:
            extra_context["query_error"] = (
                f"Parâmetro repetido não é permitido: {name}."
            )
            return extra_context, 400, None

    unknown_params = set(get_params.keys()) - allowed_names
    if unknown_params:
        extra_context["query_error"] = "Parâmetro desconhecido: {}.".format(
            ", ".join(sorted(unknown_params))
        )
        return extra_context, 400, None

    form_class = REPORT_FORM_CLASSES.get(relatorio_value, WhatsAppSealReportQueryForm)
    form = form_class(data=get_params)
    extra_context["form"] = form
    if not form.is_valid():
        return extra_context, 400, None

    if form.cleaned_data["relatorio"] not in available_relatorios:
        extra_context["engine_unavailable"] = True
        if form.cleaned_data["relatorio"] in REPORT_QUERY_ENGINES:
            # Consulta existe, exportacao ainda nao (ex.: Inventario de
            # linhas ate REL-09-E) — mensagem distinta da de relatorio
            # totalmente nao implementado.
            extra_context["engine_unavailable_message"] = (
                "A exportação deste relatório ainda não está disponível nesta etapa."
            )
        else:
            # Inalcancavel para os 6 relatorios do catalogo REL-01 desde
            # que "daily_indicators" ganhou motor de consulta (REL-13-Q):
            # REPORT_QUERY_ENGINES agora cobre todo REPORT_CHOICES. Mantido
            # para um eventual setimo relatorio adicionado ao catalogo sem
            # motor ainda — nao removido, apenas documentado como
            # atualmente inalcancavel (ver REL-13-T,
            # DailyIndicatorsCatalogClosureNote).
            extra_context["engine_unavailable_message"] = (
                "Este relatório ainda não está disponível. Apenas Selos "
                "WhatsApp, Inventário de linhas, Alocações, Pendências, "
                "Histórico da linha e Indicadores diários estão "
                "implementados nesta etapa."
            )
        return extra_context, 400, None

    return extra_context, 200, form.cleaned_data


def _report_filters_from_cleaned_data(cleaned_data):
    common = {
        "data_inicial": cleaned_data["data_inicial"],
        "data_final": cleaned_data["data_final"],
        "incluir_excluidos": cleaned_data.get("incluir_excluidos") or False,
    }
    if cleaned_data["relatorio"] == "line_inventory":
        common.update(
            {
                "status_linha": cleaned_data.get("status_linha") or "",
                "operadora": cleaned_data.get("operadora") or "",
                "origem": cleaned_data.get("origem") or "",
                "canal": cleaned_data.get("canal") or "",
                "com_selo": cleaned_data.get("com_selo") or "",
                "com_vinculo": cleaned_data.get("com_vinculo") or "",
                "linha": cleaned_data.get("linha") or "",
            }
        )
    elif cleaned_data["relatorio"] == "allocations":
        common.update(
            {
                "situacao_alocacao": cleaned_data.get("situacao_alocacao") or "",
                "funcionario": cleaned_data.get("funcionario") or "",
                "linha": cleaned_data.get("linha") or "",
            }
        )
    elif cleaned_data["relatorio"] == "pendencies":
        common.update(
            {
                "situacao_pendencia": cleaned_data.get("situacao_pendencia") or "",
                "motivo_pendencia": cleaned_data.get("motivo_pendencia") or "",
                "com_responsavel": cleaned_data.get("com_responsavel") or "",
                "funcionario": cleaned_data.get("funcionario") or "",
                "linha": cleaned_data.get("linha") or "",
            }
        )
    elif cleaned_data["relatorio"] == "line_history":
        common.update(
            {
                "tipo_evento": cleaned_data.get("tipo_evento") or "",
                "fonte_evento": cleaned_data.get("fonte_evento") or "",
                "ator": cleaned_data.get("ator") or "",
                "linha": cleaned_data.get("linha") or "",
            }
        )
    elif cleaned_data["relatorio"] == "daily_indicators":
        # Sem filtro especifico proprio (REL-13-C secao 3) — `linha` nao e
        # incluido aqui de proposito: o form dedicado ja o rejeita (400)
        # antes deste ponto, entao cleaned_data nunca chega com um valor
        # nao vazio de `linha` para este relatorio.
        pass
    else:
        common.update(
            {
                "selo": cleaned_data.get("selo") or "",
                "pagamento": cleaned_data.get("pagamento") or "",
                "situacao": cleaned_data.get("situacao") or "",
                "linha": cleaned_data.get("linha") or "",
            }
        )
    return common


class ReportsHomeView(RoleRequiredMixin, TemplateView):
    """Coordenacao HTTP fina do hub de relatorios (REL-01..REL-06), da
    consulta de Selos WhatsApp (REL-08-Q) e da consulta de Inventario de
    linhas (REL-09-Q). Sem regra de negocio: validacao de parametros fica no
    form especifico de cada relatorio; escopo/filtros/totais no servico
    dedicado de cada um."""

    allowed_roles = [SystemUser.Role.ADMIN]
    template_name = "reports/home.html"

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        context["report_choices"] = REPORT_CHOICES
        context["raw"] = {
            name: request.GET.get(name, "") for name in ALL_REPORT_PARAM_NAMES
        }

        attempted = "data_inicial" in request.GET or "data_final" in request.GET
        context["attempted"] = attempted
        if not attempted:
            return self.render_to_response(context)

        extra_context, status, cleaned_data = _validate_report_query_params(
            request.GET, available_relatorios=REPORT_QUERY_ENGINES
        )
        context.update(extra_context)
        if cleaned_data is None:
            return self.render_to_response(context, status=status)

        page_number = cleaned_data.get("page") or 1
        filters = _report_filters_from_cleaned_data(cleaned_data)
        try:
            if cleaned_data["relatorio"] == "line_inventory":
                result = build_line_inventory_report(page=page_number, **filters)
            elif cleaned_data["relatorio"] == "allocations":
                result = build_allocations_report(page=page_number, **filters)
            elif cleaned_data["relatorio"] == "pendencies":
                result = build_pendencies_report(page=page_number, **filters)
            elif cleaned_data["relatorio"] == "line_history":
                result = build_line_history_report(page=page_number, **filters)
            elif cleaned_data["relatorio"] == "daily_indicators":
                result = build_daily_indicators_report(page=page_number, **filters)
            else:
                result = build_whatsapp_seal_report(page=page_number, **filters)
        except EmptyPage as exc:
            raise Http404("Página fora do intervalo.") from exc

        context["result"] = result
        context["show_results"] = True
        context["export_available"] = cleaned_data["relatorio"] in REPORT_EXPORT_ENGINES
        return self.render_to_response(context)


EXPORT_FORMATS = {"csv", "xlsx"}


class ReportsExportView(RoleRequiredMixin, View):
    """Exportacao integral CSV/XLSX/ZIP dos seis relatorios do catalogo
    REL-01: Selos WhatsApp (REL-08-E), Inventario de linhas (REL-09-E),
    Alocacoes (REL-10-E), Pendencias (REL-11-E), Historico da linha
    (REL-12-E) e Indicadores diarios (REL-13-E). View fina: autorizacao
    (mixin) e validacao dos parametros precedem qualquer leitura/geracao; a
    serializacao dos arquivos fica em
    core/services/report_export_service (Selos),
    core/services/line_inventory_export_service (Inventario),
    core/services/allocations_export_service (Alocacoes),
    core/services/pendencies_export_service (Pendencias),
    core/services/line_history_export_service (Historico da linha) e
    core/services/daily_indicators_export_service (Indicadores diarios) —
    seis modulos proprios, nenhum generalizado sobre o outro. Reutiliza a
    mesma validacao estrita e os mesmos filtros/escopo/ordenacao/calculo da
    consulta de cada relatorio (REL-08-Q..REL-13-Q) — `page` e aceito pela
    validacao mas nunca usado para limitar o conjunto exportado."""

    allowed_roles = [SystemUser.Role.ADMIN]

    def get(self, request, *args, **kwargs):
        formato = kwargs.get("formato")
        if formato not in EXPORT_FORMATS:
            raise Http404("Formato de exportação desconhecido.")

        extra_context, status, cleaned_data = _validate_report_query_params(
            request.GET, available_relatorios=REPORT_EXPORT_ENGINES
        )
        if cleaned_data is None:
            context = {
                "report_choices": REPORT_CHOICES,
                "raw": {
                    name: request.GET.get(name, "") for name in ALL_REPORT_PARAM_NAMES
                },
                "attempted": True,
                **extra_context,
            }
            return render(request, "reports/home.html", context, status=status)

        filters = _report_filters_from_cleaned_data(cleaned_data)
        if cleaned_data["relatorio"] == "line_inventory":
            return build_line_inventory_export_response(formato=formato, filters=filters)
        if cleaned_data["relatorio"] == "allocations":
            return build_allocations_export_response(formato=formato, filters=filters)
        if cleaned_data["relatorio"] == "pendencies":
            return build_pendencies_export_response(formato=formato, filters=filters)
        if cleaned_data["relatorio"] == "line_history":
            return build_line_history_export_response(formato=formato, filters=filters)
        if cleaned_data["relatorio"] == "daily_indicators":
            return build_daily_indicators_export_response(formato=formato, filters=filters)
        return build_whatsapp_seal_export_response(formato=formato, filters=filters)


class UploadView(RoleRequiredMixin, FormView):
    allowed_roles = [SystemUser.Role.ADMIN]
    template_name = "upload/upload.html"
    form_class = UploadForm
    success_url = reverse_lazy("upload")

    def form_valid(self, form):
        uploaded_file = form.cleaned_data["file"]
        try:
            saved_path = self._persist_file(uploaded_file)
            summary = process_upload_file(saved_path)
        except ValueError as exc:
            messages.error(self.request, str(exc))
            return self.render_to_response(self.get_context_data(form=form))
        except Exception as exc:
            logger.exception("Unexpected error processing upload file")
            messages.error(self.request, f"Erro inesperado ao processar o arquivo: {exc}")
            return self.render_to_response(self.get_context_data(form=form))

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
                f"Usuários criados/atualizados: "
                f"{summary.employees_created}/{summary.employees_updated}. "
                f"SIM cards criados/atualizados: "
                f"{summary.simcards_created}/{summary.simcards_updated}. "
                f"Alocacoes criadas: {summary.allocations_created}."
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


class HealthCheckView(View):
    http_method_names = ["get", "head", "options"]

    def get(self, request, *args, **kwargs):
        if settings.HEALTHCHECK_REQUIRE_AUTH and not request.user.is_authenticated:
            response = JsonResponse({"status": "forbidden"}, status=403)
            response["Cache-Control"] = "no-store"
            return response

        response = JsonResponse({"status": "ok"})
        response["Cache-Control"] = "no-store"
        return response


def custom_permission_denied_view(request, exception=None):
    return render(request, "403.html", status=403)


def custom_page_not_found_view(request, exception=None):
    return render(request, "404.html", status=404)
