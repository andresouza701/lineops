"""Leitura do relatorio Alocacoes (REL-10-Q).

Fonte da verdade: docs/superpowers/specs/2026-09-22-reports-hub-design.md,
secoes REL-07 (contrato comum) e REL-10-C (contrato especifico). Somente
leitura: nenhuma escrita de negocio, model ou migration.

Granularidade por evento (uma linha de resultado por LineAllocation, ativas
e liberadas), periodo por allocated_at ("alocado no periodo"). Diferente do
Inventario (REL-09-Q), nao ha necessidade de Prefetch: a unidade do
relatorio ja e o proprio evento, entao select_related basta para evitar
N+1 (confirmado em REL-10-C)."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.utils import timezone

from allocations.models import LineAllocation
from telecom.seal_indicator import build_seal_indicator

PAGE_SIZE = 50


@dataclass
class AllocationsReportRow:
    phone_number: str
    employee_full_name: str
    employee_id: str
    allocated_at: date
    released_at: Optional[date]
    situacao_label: str
    registro_label: str
    funcionario_excluido_label: str
    seal_indicator: object = None


@dataclass
class AllocationsReportTotals:
    total: int
    linhas_distintas: int
    funcionarios_distintos: int
    ativas: int
    liberadas: int


@dataclass
class AllocationsReportResult:
    rows: list
    totals: AllocationsReportTotals
    page_number: int
    num_pages: int
    generated_at: datetime


def _period_bounds(data_inicial: date, data_final: date):
    """Inicio local inclusivo ate inicio local do dia posterior ao fim,
    exclusivo, no fuso configurado (settings.TIME_ZONE), conforme REL-07."""
    start = timezone.make_aware(datetime.combine(data_inicial, time.min))
    end = timezone.make_aware(datetime.combine(data_final + timedelta(days=1), time.min))
    return start, end


def _registro_label(line_deleted: bool, sim_deleted: bool) -> str:
    if line_deleted and sim_deleted:
        return "Linha e SIMcard excluídos"
    if line_deleted:
        return "Linha excluída"
    if sim_deleted:
        return "SIMcard excluído"
    return "Não excluído"


def _build_queryset(
    *,
    data_inicial: date,
    data_final: date,
    incluir_excluidos: bool = False,
    situacao_alocacao: str = "",
    funcionario: str = "",
    linha: str = "",
):
    """Escopo/filtros/ordenacao unicos do relatorio (REL-10-C), reaproveitados
    pela tela (paginada, REL-10-Q); reaproveitavel por uma futura exportacao
    integral (REL-10-E, nao construida nesta task) sem duplicar regra."""
    start, end = _period_bounds(data_inicial, data_final)

    queryset = LineAllocation.objects.select_related(
        "employee", "phone_line", "phone_line__sim_card"
    ).filter(
        allocated_at__gte=start,
        allocated_at__lt=end,
    )

    if not incluir_excluidos:
        queryset = queryset.filter(
            phone_line__is_deleted=False,
            phone_line__sim_card__is_deleted=False,
            employee__is_deleted=False,
        )

    if situacao_alocacao == "ativa":
        queryset = queryset.filter(is_active=True)
    elif situacao_alocacao == "liberada":
        queryset = queryset.filter(is_active=False)

    if funcionario:
        queryset = queryset.filter(
            Q(employee__full_name__icontains=funcionario)
            | Q(employee__employee_id__icontains=funcionario)
        )
    if linha:
        queryset = queryset.filter(phone_line__phone_number__icontains=linha)

    return queryset.order_by("-allocated_at", "-pk")


def _row_from_allocation(allocation: LineAllocation) -> AllocationsReportRow:
    line = allocation.phone_line
    employee = allocation.employee
    return AllocationsReportRow(
        phone_number=line.phone_number,
        employee_full_name=employee.full_name,
        employee_id=employee.employee_id,
        allocated_at=timezone.localtime(allocation.allocated_at).date(),
        released_at=(
            timezone.localtime(allocation.released_at).date()
            if allocation.released_at
            else None
        ),
        situacao_label="Ativa" if allocation.is_active else "Liberada",
        registro_label=_registro_label(line.is_deleted, line.sim_card.is_deleted),
        funcionario_excluido_label="Sim" if employee.is_deleted else "Não",
        seal_indicator=build_seal_indicator(
            identified=True,
            seal=line.whatsapp_seal,
            activation_status=line.whatsapp_seal_activation_status,
            expires_on=line.whatsapp_seal_expires_on,
        ),
    )


def build_allocations_report(
    *,
    data_inicial: date,
    data_final: date,
    incluir_excluidos: bool = False,
    situacao_alocacao: str = "",
    funcionario: str = "",
    linha: str = "",
    page: int = 1,
) -> AllocationsReportResult:
    """Monta o conjunto do relatorio Alocacoes e pagina o resultado.
    Totalizadores (total de alocacoes, linhas distintas, funcionarios
    distintos, ativas/liberadas) cobrem TODO o conjunto filtrado,
    independente da pagina. Pode levantar django.core.paginator.EmptyPage
    quando `page` esta fora do intervalo."""
    generated_at = timezone.now()

    queryset = _build_queryset(
        data_inicial=data_inicial,
        data_final=data_final,
        incluir_excluidos=incluir_excluidos,
        situacao_alocacao=situacao_alocacao,
        funcionario=funcionario,
        linha=linha,
    )

    aggregates = queryset.aggregate(
        linhas_distintas=Count("phone_line_id", distinct=True),
        funcionarios_distintos=Count("employee_id", distinct=True),
        ativas=Count("pk", filter=Q(is_active=True)),
        liberadas=Count("pk", filter=Q(is_active=False)),
    )

    paginator = Paginator(queryset, PAGE_SIZE)
    total = paginator.count
    page_obj = paginator.page(page)

    rows = [_row_from_allocation(allocation) for allocation in page_obj.object_list]

    totals = AllocationsReportTotals(
        total=total,
        linhas_distintas=aggregates["linhas_distintas"] or 0,
        funcionarios_distintos=aggregates["funcionarios_distintos"] or 0,
        ativas=aggregates["ativas"] or 0,
        liberadas=aggregates["liberadas"] or 0,
    )

    return AllocationsReportResult(
        rows=rows,
        totals=totals,
        page_number=page_obj.number,
        num_pages=paginator.num_pages,
        generated_at=generated_at,
    )


def iter_allocations_report_rows(
    *,
    data_inicial: date,
    data_final: date,
    incluir_excluidos: bool = False,
    situacao_alocacao: str = "",
    funcionario: str = "",
    linha: str = "",
    chunk_size: int = 2000,
):
    """Itera TODO o conjunto (sem paginacao), mesmo escopo/filtros/ordenacao
    de `_build_queryset`, em lotes via `.iterator(chunk_size=...)` — sem
    materializar o resultado inteiro em memoria. Usado exclusivamente pela
    exportacao (REL-10-E). select_related basta para evitar N+1 mesmo por
    lote (granularidade por evento dispensa Prefetch, confirmado em
    REL-10-C)."""
    queryset = _build_queryset(
        data_inicial=data_inicial,
        data_final=data_final,
        incluir_excluidos=incluir_excluidos,
        situacao_alocacao=situacao_alocacao,
        funcionario=funcionario,
        linha=linha,
    )
    for allocation in queryset.iterator(chunk_size=chunk_size):
        yield _row_from_allocation(allocation)
