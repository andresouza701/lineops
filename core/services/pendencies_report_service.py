"""Leitura do relatorio Pendencias (REL-11-Q).

Fonte da verdade: docs/superpowers/specs/2026-09-22-reports-hub-design.md,
secoes REL-07 (contrato comum) e REL-11-C (contrato especifico). Somente
leitura: nenhuma escrita de negocio, model ou migration. Nenhuma
assuncao/liberacao/resolucao/reabertura de pendencia, nenhum evento de
negocio gerado.

Granularidade por AllocationPendency (estado do ciclo atual, nao por evento
de auditoria); conjunto elegivel exige `pendency_submitted_at` preenchido
(exclui pendencias "inertes" nunca realmente abertas). Periodo por
`pendency_submitted_at` ("aberta/criada no periodo").

Solicitante (quem abriu/reabriu o ciclo atual) e Responsavel-quando-resolvida
(quem resolveu) dependem de uma UNICA consulta em lote combinada a
`LineDailyActionAuditEvent` (source=ALLOCATION_PENDENCY), correlacionada por
igualdade exata de `occurred_at` com `pendency_submitted_at`/`resolved_at` —
nunca por proximidade/ordem, nunca uma consulta por linha (REL-11-C, secao
"Exportacoes e volume")."""

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.utils import timezone

from pendencies.models import AllocationPendency
from telecom.models import LineDailyActionAuditEvent
from telecom.seal_indicator import build_seal_indicator

PAGE_SIZE = 50

ActionType = AllocationPendency.ActionType
EventType = LineDailyActionAuditEvent.EventType
Source = LineDailyActionAuditEvent.Source

NOT_ASSIGNED_LABEL = "Não atribuída"
NOT_AVAILABLE_LABEL = "Não disponível (anterior à auditoria)"
NO_LINE_LABEL = "Sem linha"

_OPEN_EVENT_TYPES = (EventType.OPENED, EventType.REOPENED)


@dataclass
class PendenciesReportRow:
    phone_number: str
    employee_full_name: str
    solicitante_label: str
    responsavel_label: str
    situacao_label: str
    motivo_label: str
    tempo_aberto_label: str
    registro_label: str
    funcionario_excluido_label: str
    seal_indicator: object = None


@dataclass
class PendenciesReportTotals:
    total: int
    linhas_distintas: int
    funcionarios_distintos: int
    abertas: int
    resolvidas: int
    sem_responsavel: int


@dataclass
class PendenciesReportResult:
    rows: list
    totals: PendenciesReportTotals
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
    situacao_pendencia: str = "",
    motivo_pendencia: str = "",
    com_responsavel: str = "",
    funcionario: str = "",
    linha: str = "",
):
    """Escopo/filtros/ordenacao unicos do relatorio (REL-11-C), reaproveitados
    pela tela paginada (REL-11-Q); reaproveitavel por uma futura exportacao
    integral (REL-11-E, nao construida nesta task) sem duplicar regra."""
    start, end = _period_bounds(data_inicial, data_final)

    queryset = AllocationPendency.objects.select_related(
        "employee",
        "allocation",
        "allocation__phone_line",
        "allocation__phone_line__sim_card",
        "technical_responsible",
    ).filter(
        pendency_submitted_at__isnull=False,
        pendency_submitted_at__gte=start,
        pendency_submitted_at__lt=end,
    )

    if not incluir_excluidos:
        queryset = queryset.filter(employee__is_deleted=False).filter(
            Q(allocation__isnull=True)
            | Q(
                allocation__phone_line__is_deleted=False,
                allocation__phone_line__sim_card__is_deleted=False,
            )
        )

    if situacao_pendencia == "aberta":
        queryset = queryset.exclude(action=ActionType.NO_ACTION)
    elif situacao_pendencia == "resolvida":
        queryset = queryset.filter(action=ActionType.NO_ACTION)

    if motivo_pendencia:
        queryset = queryset.filter(last_submitted_action=motivo_pendencia)

    if com_responsavel == "com":
        queryset = queryset.filter(technical_responsible__isnull=False)
    elif com_responsavel == "sem":
        queryset = queryset.filter(technical_responsible__isnull=True)

    if funcionario:
        queryset = queryset.filter(employee__full_name__icontains=funcionario)
    if linha:
        queryset = queryset.filter(allocation__phone_line__phone_number__icontains=linha)

    return queryset.order_by("-pendency_submitted_at", "-pk")


def _user_label(user) -> str:
    return user.get_full_name().strip() or user.email


def _fetch_audit_events(pendency_ids):
    """Consulta unica em lote (REL-11-C): retorna dois dicts, chaveados por
    (source_object_id, occurred_at exato) -> nome do performed_by (snapshot,
    nunca join ao usuario atual — preserva identidade mesmo apos exclusao
    fisica). Um so cobre Solicitante (OPENED/REOPENED); o outro cobre
    Responsavel-quando-resolvida (RESOLVED)."""
    if not pendency_ids:
        return {}, {}

    events = LineDailyActionAuditEvent.objects.filter(
        source=Source.ALLOCATION_PENDENCY,
        source_object_id__in=pendency_ids,
        event_type__in=[EventType.OPENED, EventType.REOPENED, EventType.RESOLVED],
    ).values("source_object_id", "event_type", "occurred_at", "performed_by_name_snapshot")

    open_events = {}
    resolved_events = {}
    for event in events:
        key = (event["source_object_id"], event["occurred_at"])
        name = event["performed_by_name_snapshot"]
        if event["event_type"] in _OPEN_EVENT_TYPES:
            open_events[key] = name
        else:
            resolved_events[key] = name
    return open_events, resolved_events


def _solicitante_label(pendency, open_events) -> str:
    key = (pendency.pk, pendency.pendency_submitted_at)
    name = open_events.get(key)
    return name if name else NOT_AVAILABLE_LABEL


def _responsavel_label(pendency, resolved_events) -> str:
    if pendency.is_open:
        if pendency.technical_responsible_id:
            return _user_label(pendency.technical_responsible)
        return NOT_ASSIGNED_LABEL
    key = (pendency.pk, pendency.resolved_at)
    name = resolved_events.get(key)
    return name if name else NOT_AVAILABLE_LABEL


def _tempo_aberto_label(pendency, generated_at: datetime) -> str:
    end = generated_at if pendency.is_open else pendency.resolved_at
    if end is None:
        return "-"
    delta = end - pendency.pendency_submitted_at
    if delta.total_seconds() < 0:
        return "-"
    return str(math.floor(delta.total_seconds() / 86400))


def _row_from_pendency(pendency: AllocationPendency, *, generated_at, open_events, resolved_events) -> PendenciesReportRow:
    allocation = pendency.allocation
    employee = pendency.employee
    if allocation and allocation.phone_line_id:
        line = allocation.phone_line
        phone_number = line.phone_number
        registro_label = _registro_label(line.is_deleted, line.sim_card.is_deleted)
        seal_indicator = build_seal_indicator(
            identified=True,
            seal=line.whatsapp_seal,
            activation_status=line.whatsapp_seal_activation_status,
            expires_on=line.whatsapp_seal_expires_on,
        )
    else:
        # Sem linha (allocation ausente/sem FK): nunca "Selo indisponível"
        # (reservado a linha identificada porem irresolvivel) nem resolvido
        # pelo funcionario atual — nenhum icone (I21, inventario SVI-02).
        phone_number = NO_LINE_LABEL
        registro_label = NO_LINE_LABEL
        seal_indicator = build_seal_indicator(identified=True, seal="")

    return PendenciesReportRow(
        phone_number=phone_number,
        employee_full_name=employee.full_name,
        solicitante_label=_solicitante_label(pendency, open_events),
        responsavel_label=_responsavel_label(pendency, resolved_events),
        situacao_label="Aberta" if pendency.is_open else "Resolvida",
        motivo_label=pendency.get_last_submitted_action_display(),
        tempo_aberto_label=_tempo_aberto_label(pendency, generated_at),
        registro_label=registro_label,
        funcionario_excluido_label="Sim" if employee.is_deleted else "Não",
        seal_indicator=seal_indicator,
    )


def build_pendencies_report(
    *,
    data_inicial: date,
    data_final: date,
    incluir_excluidos: bool = False,
    situacao_pendencia: str = "",
    motivo_pendencia: str = "",
    com_responsavel: str = "",
    funcionario: str = "",
    linha: str = "",
    page: int = 1,
) -> PendenciesReportResult:
    """Monta o conjunto do relatorio Pendencias e pagina o resultado.
    Totalizadores (total, linhas distintas, funcionarios distintos,
    abertas/resolvidas, sem responsavel dentro das abertas) cobrem TODO o
    conjunto filtrado, independente da pagina. Pode levantar
    django.core.paginator.EmptyPage quando `page` esta fora do intervalo."""
    generated_at = timezone.now()

    queryset = _build_queryset(
        data_inicial=data_inicial,
        data_final=data_final,
        incluir_excluidos=incluir_excluidos,
        situacao_pendencia=situacao_pendencia,
        motivo_pendencia=motivo_pendencia,
        com_responsavel=com_responsavel,
        funcionario=funcionario,
        linha=linha,
    )

    aggregates = queryset.aggregate(
        linhas_distintas=Count("allocation__phone_line_id", distinct=True),
        funcionarios_distintos=Count("employee_id", distinct=True),
        abertas=Count("pk", filter=~Q(action=ActionType.NO_ACTION)),
        resolvidas=Count("pk", filter=Q(action=ActionType.NO_ACTION)),
        sem_responsavel=Count(
            "pk",
            filter=~Q(action=ActionType.NO_ACTION) & Q(technical_responsible__isnull=True),
        ),
    )

    paginator = Paginator(queryset, PAGE_SIZE)
    total = paginator.count
    page_obj = paginator.page(page)

    pendencies_page = list(page_obj.object_list)
    open_events, resolved_events = _fetch_audit_events(
        [pendency.pk for pendency in pendencies_page]
    )

    rows = [
        _row_from_pendency(
            pendency,
            generated_at=generated_at,
            open_events=open_events,
            resolved_events=resolved_events,
        )
        for pendency in pendencies_page
    ]

    totals = PendenciesReportTotals(
        total=total,
        linhas_distintas=aggregates["linhas_distintas"] or 0,
        funcionarios_distintos=aggregates["funcionarios_distintos"] or 0,
        abertas=aggregates["abertas"] or 0,
        resolvidas=aggregates["resolvidas"] or 0,
        sem_responsavel=aggregates["sem_responsavel"] or 0,
    )

    return PendenciesReportResult(
        rows=rows,
        totals=totals,
        page_number=page_obj.number,
        num_pages=paginator.num_pages,
        generated_at=generated_at,
    )


def iter_pendencies_report_rows(
    *,
    data_inicial: date,
    data_final: date,
    incluir_excluidos: bool = False,
    situacao_pendencia: str = "",
    motivo_pendencia: str = "",
    com_responsavel: str = "",
    funcionario: str = "",
    linha: str = "",
    generated_at: Optional[datetime] = None,
    chunk_size: int = 2000,
):
    """Itera TODO o conjunto (sem paginacao), mesmo escopo/filtros/ordenacao
    de `_build_queryset`, em LOTES limitados (REL-11-E, secao 4 do
    enunciado): cada lote busca `LineDailyActionAuditEvent` somente para as
    pendencias do proprio lote (`_fetch_audit_events`, ja em lote unico por
    chamada), nunca uma consulta por linha nem o historico inteiro de
    auditoria em memoria. `chunk_size` tambem delimita o `.iterator(...)` do
    banco, entao cada lote corresponde a uma unica pagina fisica buscada do
    banco. `generated_at` e capturado uma unica vez por chamada (parametro
    para permitir reaproveito por testes/instante fixo); usado como
    referencia de "agora" para pendencias ainda abertas, igual a tela
    (REL-11-C, "Cálculo de tempo em aberto")."""
    if generated_at is None:
        generated_at = timezone.now()

    queryset = _build_queryset(
        data_inicial=data_inicial,
        data_final=data_final,
        incluir_excluidos=incluir_excluidos,
        situacao_pendencia=situacao_pendencia,
        motivo_pendencia=motivo_pendencia,
        com_responsavel=com_responsavel,
        funcionario=funcionario,
        linha=linha,
    )

    batch = []
    for pendency in queryset.iterator(chunk_size=chunk_size):
        batch.append(pendency)
        if len(batch) >= chunk_size:
            yield from _rows_for_batch(batch, generated_at)
            batch = []
    if batch:
        yield from _rows_for_batch(batch, generated_at)


def _rows_for_batch(batch, generated_at):
    open_events, resolved_events = _fetch_audit_events(
        [pendency.pk for pendency in batch]
    )
    for pendency in batch:
        yield _row_from_pendency(
            pendency,
            generated_at=generated_at,
            open_events=open_events,
            resolved_events=resolved_events,
        )
