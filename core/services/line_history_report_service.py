"""Leitura do relatorio Historico da linha (REL-12-Q).

Fonte da verdade: docs/superpowers/specs/2026-09-22-reports-hub-design.md,
secoes REL-07 (contrato comum) e REL-12-C (contrato especifico, decisoes
A-F). Somente leitura: nenhuma escrita de negocio, model ou migration.

Uniao, sem deduplicar, de duas fontes com formatos distintos --
``PhoneLineHistory`` (legado, fonte fixa ``PHONE_LINE_HISTORY``) e
``LineDailyActionAuditEvent`` (fonte real gravada no evento) -- generalizada
para MULTIPLAS linhas (decisao A), diferente de ``telecom/line_timeline.py``
(T6, escopo de uma unica ``PhoneLine``). Reaproveita a semantica ja aceita em
producao do T6 (identidade por ``row_source``/``row_id``, projecao
homogenea, ``union(all=True)`` antes de paginar, hidratacao em lote por ids
depois de obter a pagina) sem presumir que a implementacao por-linha escala
por si so: o filtro de linha deixa de ser fixo, o filtro de exclusao logica
precisa alcancar a linha/SIMcard/funcionario relacionados a CADA evento (nao
uma unica linha ja conhecida), e o desempate global passa a exigir
``phone_number`` como criterio intermediario (REL-12-C, "Ordenacao e
paginacao") porque agora ha multiplas linhas no mesmo conjunto.

``Linhas distintas`` e calculado por uma consulta UNION (sem ``all=True``,
que deduplica) apenas da coluna ``phone_number`` de cada fonte, seguida de
``count()`` -- as unicas operacoes oficialmente suportadas pelo Django sobre
querysets combinados por operacao de conjunto sao fatiamento, ``count()`` e
``order_by()``; ``aggregate()``/``distinct()`` sobre o queryset ja unido nao
sao garantidos. Nenhuma consulta por linha, nenhum historico completo
materializado em Python para ordenar/paginar/contar.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.core.paginator import Paginator
from django.db.models import CharField, F, Q, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from telecom.line_timeline import (
    SOURCE_LABELS,
    SOURCE_PHONE_LINE_HISTORY,
    LineTimelineChange,
    _actor_label_audit,
    _allocation_label,
    _audit_changes,
)
from telecom.models import LineDailyActionAuditEvent, PhoneLineHistory
from telecom.seal_indicator import build_seal_indicator

PAGE_SIZE = 50

AUTOR_NAO_DISPONIVEL = "Autor não disponível"
FUNCIONARIO_NAO_APLICAVEL = "Não aplicável"


class LineHistoryExportIntegrityError(RuntimeError):
    """Levantado quando um evento selecionado pela consulta combinada
    desaparece antes da hidratacao (row_source+row_id sem correspondencia em
    PhoneLineHistory/LineDailyActionAuditEvent no momento da busca em lote).

    REL-12-C documenta que nenhuma das duas fontes tem exclusao propria: "o
    evento em si nunca e excluido" -- ou e append-only (auditoria, guard de
    aplicacao + trigger Postgres) ou, no minimo, nunca apagado pela
    aplicacao (PhoneLineHistory, sem guard, mas tambem sem fluxo de exclusao
    fisica em uso — CASCADE existe no schema mas nenhum caminho da aplicacao
    o aciona hoje). Diante dessa garantia documentada, uma linha selecionada
    que some entre a projecao e a hidratacao em lote e uma ANOMALIA DE
    INTEGRIDADE, nao um caso de negocio esperado — a menor estrategia
    compativel com o contrato de exportacao ("todas as linhas filtradas",
    "nunca entregar arquivo truncado ou aparentemente completo") e recusar
    entregar um arquivo que perderia essa linha silenciosamente. Usada
    apenas por `iter_line_history_report_rows` (exportacao, REL-12-E); a
    tela paginada (`build_line_history_report`, REL-12-Q) mantem o
    comportamento original de `_hydrate` (descarte silencioso de uma linha
    ausente na pagina), inalterado por esta task."""


@dataclass
class LineHistoryReportRow:
    phone_number: str
    occurred_at: datetime
    source_label: str
    event_type_label: str
    actor_label: str
    allocation_label: str
    changes_label: str
    registro_label: str
    funcionario_excluido_label: str
    seal_indicator: object = None


@dataclass
class LineHistoryReportTotals:
    total_eventos: int
    linhas_distintas: int


@dataclass
class LineHistoryReportResult:
    rows: list
    totals: LineHistoryReportTotals
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


def _actor_label_legacy(history: PhoneLineHistory) -> str:
    """Decisao F (REL-12-C): sem snapshot para provar acao de sistema, um
    ``changed_by`` nulo em PhoneLineHistory nunca vira 'Sistema' -- sempre
    'Autor não disponível'."""
    if history.changed_by_id:
        user = history.changed_by
        return user.get_full_name().strip() or user.email
    return AUTOR_NAO_DISPONIVEL


def _format_changes(changes: list) -> str:
    if not changes:
        return "-"
    return "; ".join(f"{change.label}: {change.before_value} → {change.after_value}" for change in changes)


def _legacy_base_queryset(
    *, start, end, incluir_excluidos, tipo_evento, fonte_evento, ator, linha
):
    qs = PhoneLineHistory.objects.filter(changed_at__gte=start, changed_at__lt=end)

    if fonte_evento and fonte_evento != SOURCE_PHONE_LINE_HISTORY:
        # Fonte legada tem codigo fixo: qualquer outro valor de fonte_evento
        # nunca corresponde a um registro de PhoneLineHistory.
        qs = qs.none()

    if tipo_evento:
        qs = qs.filter(action=tipo_evento)

    if ator:
        qs = qs.filter(
            Q(changed_by__first_name__icontains=ator)
            | Q(changed_by__last_name__icontains=ator)
            | Q(changed_by__email__icontains=ator)
        )

    if linha:
        qs = qs.filter(phone_line__phone_number__icontains=linha)

    if not incluir_excluidos:
        qs = qs.filter(phone_line__is_deleted=False, phone_line__sim_card__is_deleted=False)

    return qs


def _audit_base_queryset(
    *, start, end, incluir_excluidos, tipo_evento, fonte_evento, ator, linha
):
    qs = LineDailyActionAuditEvent.objects.filter(occurred_at__gte=start, occurred_at__lt=end)

    if fonte_evento:
        qs = qs.filter(source=fonte_evento)

    if tipo_evento:
        qs = qs.filter(event_type=tipo_evento)

    if ator:
        qs = qs.filter(
            Q(performed_by__first_name__icontains=ator)
            | Q(performed_by__last_name__icontains=ator)
            | Q(performed_by__email__icontains=ator)
            | Q(performed_by_name_snapshot__icontains=ator)
            | Q(performed_by_email_snapshot__icontains=ator)
        )

    if linha:
        qs = qs.filter(
            Q(phone_line__phone_number__icontains=linha)
            | Q(phone_line__isnull=True, phone_number_snapshot__icontains=linha)
        )

    if not incluir_excluidos:
        qs = qs.filter(
            phone_line__isnull=False,
            phone_line__is_deleted=False,
            phone_line__sim_card__is_deleted=False,
        ).filter(Q(employee__isnull=True) | Q(employee__is_deleted=False))

    return qs


def _legacy_projection(qs):
    return (
        qs.order_by()
        .annotate(
            row_source=Value(SOURCE_PHONE_LINE_HISTORY, output_field=CharField(max_length=30)),
            row_id=F("pk"),
            sort_at=F("changed_at"),
            phone_number=F("phone_line__phone_number"),
        )
        .values("row_source", "row_id", "sort_at", "phone_number")
    )


def _audit_projection(qs):
    return (
        qs.order_by()
        .annotate(
            row_source=F("source"),
            row_id=F("pk"),
            sort_at=F("occurred_at"),
            phone_number=Coalesce(F("phone_line__phone_number"), F("phone_number_snapshot")),
        )
        .values("row_source", "row_id", "sort_at", "phone_number")
    )


def _combined_queryset(*, legacy_qs, audit_qs):
    combined = _legacy_projection(legacy_qs).union(_audit_projection(audit_qs), all=True)
    # Desempate global (REL-12-C, "Ordenacao e paginacao"): sort_at desc,
    # phone_number asc (criterio intermediario, necessario so porque ha
    # multiplas linhas no mesmo conjunto), depois row_source/row_id -- mesmo
    # desempate ja aprovado e testado em telecom/line_timeline.py (T6). Como
    # row_id e sempre unico dentro da propria tabela de origem, o par
    # (row_source, row_id) ja resolve qualquer empate remanescente --
    # inclusive entre dois PhoneLineHistory com o mesmo changed_at, que so
    # colidem por instante, nunca por identidade.
    return combined.order_by("-sort_at", "phone_number", "row_source", "-row_id")


def _distinct_lines_count(*, legacy_qs, audit_qs):
    """COUNT(DISTINCT) por UNION (sem all=True, que deduplica) da coluna
    phone_number de cada fonte -- contagem, ordenacao e fatiamento sao as
    unicas operacoes garantidas pelo Django sobre queryset ja combinado por
    operacao de conjunto; aggregate()/distinct() adicionais sobre o
    resultado unido nao sao suportados oficialmente. Limitacao documentada
    (REL-12-C): eventos de auditoria com phone_line nulo usam
    phone_number_snapshot como identificador alternativo, que pode
    sub/superestimar caso o numero seja reaproveitado por outra linha."""
    legacy_numbers = legacy_qs.order_by().annotate(
        phone_number=F("phone_line__phone_number")
    ).values("phone_number")
    audit_numbers = audit_qs.order_by().annotate(
        phone_number=Coalesce(F("phone_line__phone_number"), F("phone_number_snapshot"))
    ).values("phone_number")
    return legacy_numbers.union(audit_numbers).count()


def _hydrate(rows: list, *, strict: bool = False) -> list:
    """Hidrata em UM lote por fonte (nunca uma consulta por evento) e
    reconstroi a ordem original de `rows` no final -- nunca concatenando
    todos os eventos de uma fonte antes da outra. `strict=True` (usado pela
    exportacao, ver `iter_line_history_report_rows`) levanta
    `LineHistoryExportIntegrityError` em vez de descartar silenciosamente um
    row_id selecionado que nao foi encontrado na hidratacao; `strict=False`
    (comportamento original, usado pela tela paginada) preserva o descarte
    silencioso ja testado e aceito por REL-12-Q, inalterado por esta task."""
    legacy_ids = [row["row_id"] for row in rows if row["row_source"] == SOURCE_PHONE_LINE_HISTORY]
    audit_ids = [row["row_id"] for row in rows if row["row_source"] != SOURCE_PHONE_LINE_HISTORY]

    legacy_map = {}
    if legacy_ids:
        legacy_map = {
            obj.pk: obj
            for obj in PhoneLineHistory.objects.filter(pk__in=legacy_ids).select_related(
                "changed_by", "phone_line", "phone_line__sim_card"
            )
        }

    audit_map = {}
    if audit_ids:
        audit_map = {
            obj.pk: obj
            for obj in LineDailyActionAuditEvent.objects.filter(pk__in=audit_ids).select_related(
                "performed_by", "allocation", "employee", "phone_line", "phone_line__sim_card"
            )
        }

    items = []
    for row in rows:
        is_legacy = row["row_source"] == SOURCE_PHONE_LINE_HISTORY
        obj = legacy_map.get(row["row_id"]) if is_legacy else audit_map.get(row["row_id"])
        if obj is None:
            if strict:
                raise LineHistoryExportIntegrityError(
                    "Evento selecionado nao encontrado na hidratacao: "
                    f"row_source={row['row_source']!r} row_id={row['row_id']!r}"
                )
            continue
        items.append(_row_from_legacy(obj) if is_legacy else _row_from_audit(obj))
    return items


def _row_from_legacy(history: PhoneLineHistory) -> LineHistoryReportRow:
    line = history.phone_line
    changes = [
        LineTimelineChange(
            label="Alteração",
            before_value=history.old_value or "-",
            after_value=history.new_value or "-",
        )
    ]
    return LineHistoryReportRow(
        phone_number=line.phone_number,
        occurred_at=history.changed_at,
        source_label=SOURCE_LABELS[SOURCE_PHONE_LINE_HISTORY],
        event_type_label=history.get_action_display(),
        actor_label=_actor_label_legacy(history),
        allocation_label="-",
        changes_label=_format_changes(changes),
        registro_label=_registro_label(line.is_deleted, line.sim_card.is_deleted),
        funcionario_excluido_label=FUNCIONARIO_NAO_APLICAVEL,
        seal_indicator=build_seal_indicator(
            identified=True,
            seal=line.whatsapp_seal,
            activation_status=line.whatsapp_seal_activation_status,
            expires_on=line.whatsapp_seal_expires_on,
            is_historical=True,
        ),
    )


def _row_from_audit(event: LineDailyActionAuditEvent) -> LineHistoryReportRow:
    if event.phone_line_id:
        phone_number = event.phone_line.phone_number
        registro_label = _registro_label(event.phone_line.is_deleted, event.phone_line.sim_card.is_deleted)
        seal_indicator = build_seal_indicator(
            identified=True,
            seal=event.phone_line.whatsapp_seal,
            activation_status=event.phone_line.whatsapp_seal_activation_status,
            expires_on=event.phone_line.whatsapp_seal_expires_on,
            is_historical=True,
        )
    else:
        # Snapshot sem FK (phone_number_snapshot): nunca herda selo por
        # coincidencia de numero com outra PhoneLine (borda aprovada
        # fechamento SVI-02 #2) — sempre "nao identificado".
        phone_number = event.phone_number_snapshot
        registro_label = "-"
        seal_indicator = build_seal_indicator(identified=False)

    if event.employee_id:
        funcionario_excluido_label = "Sim" if event.employee.is_deleted else "Não"
    else:
        funcionario_excluido_label = FUNCIONARIO_NAO_APLICAVEL

    return LineHistoryReportRow(
        phone_number=phone_number,
        occurred_at=event.occurred_at,
        source_label=SOURCE_LABELS.get(event.source, event.source),
        event_type_label=event.get_event_type_display(),
        actor_label=_actor_label_audit(event),
        allocation_label=_allocation_label(event),
        changes_label=_format_changes(_audit_changes(event.before_state, event.after_state)),
        registro_label=registro_label,
        funcionario_excluido_label=funcionario_excluido_label,
        seal_indicator=seal_indicator,
    )


def build_line_history_report(
    *,
    data_inicial: date,
    data_final: date,
    incluir_excluidos: bool = False,
    tipo_evento: str = "",
    fonte_evento: str = "",
    ator: str = "",
    linha: str = "",
    page: int = 1,
) -> LineHistoryReportResult:
    """Monta o conjunto unificado do relatorio Historico da linha e pagina o
    resultado. Totalizadores (Total de eventos, Linhas distintas) cobrem
    TODO o conjunto filtrado, independente da pagina. Pode levantar
    django.core.paginator.EmptyPage quando `page` esta fora do intervalo."""
    generated_at = timezone.now()
    start, end = _period_bounds(data_inicial, data_final)

    legacy_qs = _legacy_base_queryset(
        start=start, end=end, incluir_excluidos=incluir_excluidos,
        tipo_evento=tipo_evento, fonte_evento=fonte_evento, ator=ator, linha=linha,
    )
    audit_qs = _audit_base_queryset(
        start=start, end=end, incluir_excluidos=incluir_excluidos,
        tipo_evento=tipo_evento, fonte_evento=fonte_evento, ator=ator, linha=linha,
    )

    combined = _combined_queryset(legacy_qs=legacy_qs, audit_qs=audit_qs)

    paginator = Paginator(combined, PAGE_SIZE)
    total_eventos = paginator.count
    linhas_distintas = _distinct_lines_count(legacy_qs=legacy_qs, audit_qs=audit_qs)
    page_obj = paginator.page(page)

    items = _hydrate(list(page_obj.object_list))

    totals = LineHistoryReportTotals(total_eventos=total_eventos, linhas_distintas=linhas_distintas)

    return LineHistoryReportResult(
        rows=items,
        totals=totals,
        page_number=page_obj.number,
        num_pages=paginator.num_pages,
        generated_at=generated_at,
    )


def iter_line_history_report_rows(
    *,
    data_inicial: date,
    data_final: date,
    incluir_excluidos: bool = False,
    tipo_evento: str = "",
    fonte_evento: str = "",
    ator: str = "",
    linha: str = "",
    chunk_size: int = 2000,
):
    """Itera TODO o conjunto combinado (sem paginacao), na MESMA ordem
    global aprovada (`_combined_queryset`), em LOTES limitados por
    `chunk_size` (REL-12-E, secao 4 do enunciado) -- usada exclusivamente
    pela exportacao, nunca pela tela paginada.

    O queryset unido por ``union(all=True)`` e percorrido via
    ``.iterator(chunk_size=...)`` (confirmado por teste dedicado que a
    ordem/conteudo batem exatamente com ``list(combined)`` em qualquer
    fronteira de lote -- ``.iterator()``/fatiamento/``count()``/``order_by()``
    sao as operacoes garantidas pelo Django sobre queryset ja combinado por
    operacao de conjunto). Cada lote e hidratado de uma so vez
    (`_hydrate(..., strict=True)`, que ja separa ids por fonte, busca cada
    fonte em UMA consulta e reconstroi a ordem original do proprio lote) --
    nunca concatenando todos os eventos de uma fonte antes da outra, nunca
    uma consulta por evento, nunca o historico inteiro em memoria. Um evento
    selecionado que desaparece entre a selecao e a hidratacao do seu lote
    levanta `LineHistoryExportIntegrityError` (ver docstring da excecao),
    nunca e silenciado."""
    start, end = _period_bounds(data_inicial, data_final)

    legacy_qs = _legacy_base_queryset(
        start=start, end=end, incluir_excluidos=incluir_excluidos,
        tipo_evento=tipo_evento, fonte_evento=fonte_evento, ator=ator, linha=linha,
    )
    audit_qs = _audit_base_queryset(
        start=start, end=end, incluir_excluidos=incluir_excluidos,
        tipo_evento=tipo_evento, fonte_evento=fonte_evento, ator=ator, linha=linha,
    )
    combined = _combined_queryset(legacy_qs=legacy_qs, audit_qs=audit_qs)

    batch = []
    for row in combined.iterator(chunk_size=chunk_size):
        batch.append(row)
        if len(batch) >= chunk_size:
            yield from _hydrate(batch, strict=True)
            batch = []
    if batch:
        yield from _hydrate(batch, strict=True)
