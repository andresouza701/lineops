"""Leitura do relatorio Inventario de linhas (REL-09-Q).

Fonte da verdade: docs/superpowers/specs/2026-09-22-reports-hub-design.md,
secoes REL-07 (contrato comum), REL-09-C (contrato especifico) e REL-09-T
(definicoes aprovadas em 2026-09-25: tokens com/sem, limite de operadora).
Somente leitura: nenhuma escrita de negocio, model ou migration.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional

from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q
from django.utils import timezone

from allocations.models import LineAllocation
from telecom.models import PhoneLine
from telecom.seal_indicator import build_seal_indicator

PAGE_SIZE = 50


@dataclass
class LineInventoryReportRow:
    phone_number: str
    status_display: str
    operadora: str
    origem_display: str
    canal_display: str
    selo_display: str
    vinculo_label: str
    created_at: datetime
    registro_label: str
    seal_indicator: object = None


@dataclass
class LineInventoryReportTotals:
    total: int
    by_status: list
    com_vinculo: int
    sem_vinculo: int


@dataclass
class LineInventoryReportResult:
    rows: list
    totals: LineInventoryReportTotals
    page_number: int
    num_pages: int
    generated_at: datetime


def _selo_label(line: PhoneLine) -> str:
    if not line.whatsapp_seal:
        return "Sem selo"
    return f"Com selo ({line.get_whatsapp_seal_display()})"


def _vinculo_label(active_allocations: list) -> str:
    count = len(active_allocations)
    if count == 0:
        return "Não"
    if count == 1:
        return "Sim"
    return f"Sim (inconsistente: {count} ativos)"


def _registro_label(line_deleted: bool, sim_deleted: bool) -> str:
    if line_deleted and sim_deleted:
        return "Linha e SIMcard excluídos"
    if line_deleted:
        return "Linha excluída"
    if sim_deleted:
        return "SIMcard excluído"
    return "Não excluído"


def _period_bounds(data_inicial: date, data_final: date):
    """Inicio local inclusivo ate inicio local do dia posterior ao fim,
    exclusivo, no fuso configurado (settings.TIME_ZONE), conforme REL-07."""
    start = timezone.make_aware(datetime.combine(data_inicial, time.min))
    end = timezone.make_aware(datetime.combine(data_final + timedelta(days=1), time.min))
    return start, end


def _build_queryset(
    *,
    data_inicial: date,
    data_final: date,
    incluir_excluidos: bool = False,
    status_linha: str = "",
    operadora: str = "",
    origem: str = "",
    canal: str = "",
    com_selo: str = "",
    com_vinculo: str = "",
    linha: str = "",
):
    """Escopo/filtros/ordenacao unicos do relatorio (REL-09-C), reaproveitados
    pela tela (paginada, REL-09-Q); reaproveitavel por uma futura exportacao
    integral (REL-09-E, nao construida nesta task) sem duplicar regra."""
    start, end = _period_bounds(data_inicial, data_final)

    queryset = PhoneLine.all_objects.select_related("sim_card").filter(
        created_at__gte=start,
        created_at__lt=end,
    )

    if not incluir_excluidos:
        queryset = queryset.filter(is_deleted=False, sim_card__is_deleted=False)

    if status_linha:
        queryset = queryset.filter(status=status_linha)
    if origem:
        queryset = queryset.filter(origem=origem)
    if canal:
        queryset = queryset.filter(canal=canal)
    if operadora:
        queryset = queryset.filter(sim_card__carrier__icontains=operadora)
    if linha:
        queryset = queryset.filter(phone_number__icontains=linha)

    if com_selo == "com":
        queryset = queryset.exclude(whatsapp_seal="")
    elif com_selo == "sem":
        queryset = queryset.filter(whatsapp_seal="")

    linked_line_ids = LineAllocation.objects.filter(is_active=True).values("phone_line_id")
    if com_vinculo == "com":
        queryset = queryset.filter(pk__in=linked_line_ids)
    elif com_vinculo == "sem":
        queryset = queryset.exclude(pk__in=linked_line_ids)

    active_allocations_queryset = (
        LineAllocation.objects.filter(is_active=True)
        .select_related("employee")
        .order_by("-allocated_at", "-pk")
    )
    queryset = queryset.prefetch_related(
        Prefetch(
            "allocations",
            queryset=active_allocations_queryset,
            to_attr="active_allocations",
        )
    )

    return queryset.order_by("phone_number", "pk")


def _row_from_line(line: PhoneLine) -> LineInventoryReportRow:
    active_allocations = getattr(line, "active_allocations", [])
    return LineInventoryReportRow(
        phone_number=line.phone_number,
        status_display=line.get_status_display(),
        operadora=line.sim_card.carrier,
        origem_display=line.get_origem_display() if line.origem else "Não informado",
        canal_display=line.get_canal_display() if line.canal else "Não informado",
        selo_display=_selo_label(line),
        vinculo_label=_vinculo_label(active_allocations),
        created_at=timezone.localtime(line.created_at),
        registro_label=_registro_label(line.is_deleted, line.sim_card.is_deleted),
        seal_indicator=build_seal_indicator(
            identified=True,
            seal=line.whatsapp_seal,
            activation_status=line.whatsapp_seal_activation_status,
            expires_on=line.whatsapp_seal_expires_on,
        ),
    )


def build_line_inventory_report(
    *,
    data_inicial: date,
    data_final: date,
    incluir_excluidos: bool = False,
    status_linha: str = "",
    operadora: str = "",
    origem: str = "",
    canal: str = "",
    com_selo: str = "",
    com_vinculo: str = "",
    linha: str = "",
    page: int = 1,
) -> LineInventoryReportResult:
    """Monta o conjunto do relatorio Inventario de linhas e pagina o
    resultado. Totalizadores (total, por status, com/sem vinculo) cobrem
    TODO o conjunto filtrado, independente da pagina. Pode levantar
    django.core.paginator.EmptyPage quando `page` esta fora do intervalo."""
    generated_at = timezone.now()

    queryset = _build_queryset(
        data_inicial=data_inicial,
        data_final=data_final,
        incluir_excluidos=incluir_excluidos,
        status_linha=status_linha,
        operadora=operadora,
        origem=origem,
        canal=canal,
        com_selo=com_selo,
        com_vinculo=com_vinculo,
        linha=linha,
    )

    status_aggregate_kwargs = {
        code: Count("pk", filter=Q(status=code)) for code, _ in PhoneLine.Status.choices
    }
    status_counts = queryset.aggregate(**status_aggregate_kwargs)
    by_status = [
        (label, status_counts[code] or 0) for code, label in PhoneLine.Status.choices
    ]

    linked_line_ids = LineAllocation.objects.filter(is_active=True).values("phone_line_id")
    vinculo_counts = queryset.aggregate(
        com_vinculo=Count("pk", filter=Q(pk__in=linked_line_ids), distinct=True),
        sem_vinculo=Count("pk", filter=~Q(pk__in=linked_line_ids), distinct=True),
    )

    paginator = Paginator(queryset, PAGE_SIZE)
    total = paginator.count
    page_obj = paginator.page(page)

    rows = [_row_from_line(line) for line in page_obj.object_list]

    totals = LineInventoryReportTotals(
        total=total,
        by_status=by_status,
        com_vinculo=vinculo_counts["com_vinculo"] or 0,
        sem_vinculo=vinculo_counts["sem_vinculo"] or 0,
    )

    return LineInventoryReportResult(
        rows=rows,
        totals=totals,
        page_number=page_obj.number,
        num_pages=paginator.num_pages,
        generated_at=generated_at,
    )


def iter_line_inventory_report_rows(
    *,
    data_inicial: date,
    data_final: date,
    incluir_excluidos: bool = False,
    status_linha: str = "",
    operadora: str = "",
    origem: str = "",
    canal: str = "",
    com_selo: str = "",
    com_vinculo: str = "",
    linha: str = "",
    chunk_size: int = 2000,
):
    """Itera TODO o conjunto (sem paginacao), mesmo escopo/filtros/ordenacao
    de `_build_queryset` (inclusive o Prefetch de vinculo atual sem N+1), em
    lotes via `.iterator(chunk_size=...)` — sem materializar o resultado
    inteiro em memoria. Usado exclusivamente pela exportacao (REL-09-E).

    UMA UNICA consulta dirige toda a divisao em partes do exportador: nao ha
    `count()` previo separado, pelo mesmo motivo ja corrigido em REL-08-E
    (duas consultas independentes podem divergir por mudanca de dados entre
    elas). Django 5.2 suporta prefetch_related() combinado com iterator()
    desde que chunk_size seja informado (o prefetch e refeito por lote)."""
    queryset = _build_queryset(
        data_inicial=data_inicial,
        data_final=data_final,
        incluir_excluidos=incluir_excluidos,
        status_linha=status_linha,
        operadora=operadora,
        origem=origem,
        canal=canal,
        com_selo=com_selo,
        com_vinculo=com_vinculo,
        linha=linha,
    )
    for line in queryset.iterator(chunk_size=chunk_size):
        yield _row_from_line(line)
