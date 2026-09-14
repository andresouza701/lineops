"""
Servico de leitura do relatorio operacional por linha (T7).

Deriva ciclos de OPENED/REOPENED -> RESOLVED exclusivamente a partir de
LineDailyActionAuditEvent — nunca de PhoneLineHistory (legado, exclusivo da
timeline T6) e nunca por inferencia do estado atual de DailyUserAction,
AllocationPendency ou LineAllocation. Leitura pura: nenhuma escrita.

Custo de query constante em relacao ao numero de linhas/eventos: uma query
para as linhas visiveis (`values("id", "phone_number")`), uma query para
todos os eventos de auditoria dessas linhas ate a referencia temporal
(`values(...)`, ordenada `occurred_at ASC, id ASC`, dobrada em memoria numa
unica passada), e uma terceira query em lote para resolver os atores ainda
vivos (`SystemUser.objects.filter(pk__in=...)`) usados como "ultimo ator".
Nenhuma query por linha ou por evento.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from django.utils import timezone
from django.utils.dateparse import parse_date

from telecom.models import LineDailyActionAuditEvent
from users.models import SystemUser

PAGE_SIZE = 50

OPENING_EVENT_TYPES = {
    LineDailyActionAuditEvent.EventType.OPENED,
    LineDailyActionAuditEvent.EventType.REOPENED,
}
CLOSING_EVENT_TYPES = {LineDailyActionAuditEvent.EventType.RESOLVED}


def _parse_page(raw):
    """Pagina invalida/ausente vira pagina 1, nunca excecao."""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 1
    return value if value > 0 else 1


@dataclass(frozen=True)
class LineOperationalReportFilters:
    """Filtros GET, ja parseados de forma tolerante: valor invalido vira
    filtro ausente, nunca 500."""

    start_date: object = None
    end_date: object = None
    page: int = 1

    @classmethod
    def from_get_params(cls, get_params):
        return cls(
            start_date=parse_date((get_params.get("start_date") or "").strip()),
            end_date=parse_date((get_params.get("end_date") or "").strip()),
            page=_parse_page(get_params.get("page")),
        )

    @property
    def start_at(self):
        if not self.start_date:
            return None
        naive = datetime.combine(self.start_date, time.min)
        return timezone.make_aware(naive, timezone.get_current_timezone())

    @property
    def end_at(self):
        if not self.end_date:
            return None
        naive = datetime.combine(self.end_date, time.max)
        return timezone.make_aware(naive, timezone.get_current_timezone())

    @property
    def reference_at(self):
        """Sem end_date, referencia e agora; com end_date, e o fim daquele
        dia — eventos depois disso nunca sao lidos, entao o relatorio
        reproduz o estado exatamente como estava no fim daquele dia."""
        return self.end_at or timezone.now()


@dataclass
class _Cycle:
    """Resultado interno da dobra de eventos numa chave
    (phone_line_id, source, source_object_id)."""

    opened_at: object
    resolved_at: object = None


@dataclass(frozen=True)
class LineOperationalReportRow:
    """DTO renderizavel: so tipos simples, reutilizavel por HTML e CSV."""

    phone_number: str
    entradas: int
    saidas: int
    ciclos: int
    situacao: str
    duracao_aberta: str
    ultima_acao: str
    ultimo_ator: str


def _format_duration(delta: timedelta) -> str:
    total_seconds = max(int(delta.total_seconds()), 0)
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    if days:
        return f"{days}d {hours:02d}h{minutes:02d}m"
    return f"{hours:02d}h{minutes:02d}m"


def _actor_label(performed_by_id, name_snapshot, email_snapshot, users_by_id):
    if performed_by_id and performed_by_id in users_by_id:
        user = users_by_id[performed_by_id]
        return user.get_full_name().strip() or user.email
    if name_snapshot:
        return name_snapshot
    if email_snapshot:
        return email_snapshot
    return "Sistema"


def build_line_operational_report(phone_lines_queryset, filters: LineOperationalReportFilters):
    """Retorna todas as linhas do relatorio (nao paginado) para o escopo e
    filtros dados — usado tanto pela view HTML (que pagina em Python) quanto
    pela exportacao CSV (que exporta o conjunto completo)."""
    lines = list(phone_lines_queryset.values("id", "phone_number"))
    if not lines:
        return []

    line_ids = [line["id"] for line in lines]
    phone_number_by_id = {line["id"]: line["phone_number"] for line in lines}

    reference_at = filters.reference_at
    start_at = filters.start_at

    events = list(
        LineDailyActionAuditEvent.objects.filter(
            phone_line_id__in=line_ids,
            occurred_at__lte=reference_at,
        )
        .order_by("occurred_at", "id")
        .values(
            "id",
            "phone_line_id",
            "source",
            "source_object_id",
            "event_type",
            "occurred_at",
            "performed_by_id",
            "performed_by_name_snapshot",
            "performed_by_email_snapshot",
        )
    )

    open_cycle_by_key = {}
    cycles_by_line = defaultdict(list)
    entradas_by_line = Counter()
    saidas_by_line = Counter()
    last_event_by_line = {}

    for event in events:
        line_id = event["phone_line_id"]
        key = (line_id, event["source"], event["source_object_id"])
        event_type = event["event_type"]
        occurred_at = event["occurred_at"]
        in_period = start_at is None or occurred_at >= start_at

        if event_type in OPENING_EVENT_TYPES:
            if in_period:
                entradas_by_line[line_id] += 1
            cycle = _Cycle(opened_at=occurred_at)
            cycles_by_line[line_id].append(cycle)
            # Ciclo ja aberto para a chave permanece aberto: nao fecha o
            # anterior, apenas passa a ser o "ciclo corrente" desta chave.
            open_cycle_by_key[key] = cycle
        elif event_type in CLOSING_EVENT_TYPES:
            if in_period:
                saidas_by_line[line_id] += 1
            cycle = open_cycle_by_key.pop(key, None)
            if cycle is not None:
                cycle.resolved_at = occurred_at
            # RESOLVED sem ciclo aberto para a chave e orfao: nao cria nada.

        # Eventos ordenados occurred_at ASC, id ASC: a ultima sobrescrita
        # desta linha e sempre o evento mais recente (desempate id DESC).
        last_event_by_line[line_id] = event

    performed_by_ids = {
        event["performed_by_id"]
        for event in last_event_by_line.values()
        if event["performed_by_id"]
    }
    users_by_id = (
        {user.pk: user for user in SystemUser.objects.filter(pk__in=performed_by_ids)}
        if performed_by_ids
        else {}
    )

    event_type_labels = dict(LineDailyActionAuditEvent.EventType.choices)

    rows = []
    for line_id in line_ids:
        cycles = cycles_by_line.get(line_id, [])
        overlapping = [
            cycle
            for cycle in cycles
            if cycle.resolved_at is None
            or start_at is None
            or cycle.resolved_at >= start_at
        ]
        if not overlapping:
            continue

        open_cycles = [cycle for cycle in overlapping if cycle.resolved_at is None]
        if open_cycles:
            situacao = "Aberta"
            oldest_open = min(open_cycles, key=lambda cycle: cycle.opened_at)
            duration_str = _format_duration(reference_at - oldest_open.opened_at)
            duracao_aberta = (
                f"({len(open_cycles)}) {duration_str}"
                if len(open_cycles) > 1
                else duration_str
            )
        else:
            situacao = "Resolvida"
            duracao_aberta = "-"

        last_event = last_event_by_line.get(line_id)
        ultima_acao = event_type_labels.get(
            last_event["event_type"], last_event["event_type"]
        )
        ultimo_ator = _actor_label(
            last_event["performed_by_id"],
            last_event["performed_by_name_snapshot"],
            last_event["performed_by_email_snapshot"],
            users_by_id,
        )

        rows.append(
            LineOperationalReportRow(
                phone_number=phone_number_by_id[line_id],
                entradas=entradas_by_line.get(line_id, 0),
                saidas=saidas_by_line.get(line_id, 0),
                ciclos=len(overlapping),
                situacao=situacao,
                duracao_aberta=duracao_aberta,
                ultima_acao=ultima_acao,
                ultimo_ator=ultimo_ator,
            )
        )

    rows.sort(key=lambda row: row.phone_number)
    return rows
