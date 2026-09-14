"""
Servico de leitura da timeline unificada de linha (T6).

Mistura, sem deduplicar, duas fontes com formatos distintos:

- ``PhoneLineHistory`` (legado, fonte fixa ``PHONE_LINE_HISTORY``);
- ``LineDailyActionAuditEvent`` (novo, fonte real gravada no evento:
  ``DAILY_USER_ACTION``, ``ALLOCATION_PENDENCY`` ou ``LINE_ALLOCATION``).

A mesma mudanca de negocio pode gerar um evento legado e um evento
auditavel novo: ambos sao mostrados, pois sao fatos de fontes diferentes,
nao duplicatas.

Paginacao ocorre no banco: as duas fontes sao projetadas em colunas
homogeneas (``row_source``, ``row_id``, ``sort_at``), filtradas e unidas via
``QuerySet.union(all=True)`` *antes* de paginar. So depois de obter os ids da
pagina pedida e que os objetos completos sao carregados, em no maximo duas
queries (uma por fonte), com ``select_related`` para nao disparar N+1 no
template. A view nunca materializa o historico inteiro em Python.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, time

from django.core.paginator import Paginator
from django.db.models import CharField, F, Value
from django.utils import timezone
from django.utils.dateparse import parse_date

from allocations.models import LineAllocation
from telecom.models import LineDailyActionAuditEvent, PhoneLine, PhoneLineHistory
from users.models import SystemUser

PAGE_SIZE = 50

SOURCE_PHONE_LINE_HISTORY = "PHONE_LINE_HISTORY"

SOURCE_LABELS = {
    SOURCE_PHONE_LINE_HISTORY: "Histórico da linha",
    LineDailyActionAuditEvent.Source.DAILY_USER_ACTION: "Ações do Dia",
    LineDailyActionAuditEvent.Source.ALLOCATION_PENDENCY: "Pendência",
    LineDailyActionAuditEvent.Source.LINE_ALLOCATION: "Status da linha",
}


def _parse_positive_int(raw):
    """Converte para int positivo ou None. Nunca levanta: valor invalido
    (nao numerico, negativo, vazio) e tratado como filtro ausente — nunca
    causa erro 500 nem vaza dados por acidente."""
    if raw is None or raw == "":
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


@dataclass(frozen=True)
class LineTimelineFilters:
    """Filtros GET da timeline, ja parseados e validados de forma tolerante:
    valor invalido vira filtro ausente, nunca excecao."""

    start_date: object = None
    end_date: object = None
    event_type: str = ""
    actor_id: object = None
    allocation_id: object = None
    page: int = 1

    @classmethod
    def from_get_params(cls, get_params):
        return cls(
            start_date=parse_date((get_params.get("start_date") or "").strip()),
            end_date=parse_date((get_params.get("end_date") or "").strip()),
            event_type=(get_params.get("event_type") or "").strip(),
            actor_id=_parse_positive_int(get_params.get("actor_id")),
            allocation_id=_parse_positive_int(get_params.get("allocation_id")),
            page=_parse_positive_int(get_params.get("page")) or 1,
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


@dataclass(frozen=True)
class LineTimelineChange:
    label: str
    before_value: str
    after_value: str


@dataclass(frozen=True)
class LineTimelineItem:
    """DTO renderizavel: so tipos simples, nenhum acesso lazy a FK no
    template — tudo ja resolvido em memoria na hidratacao em lote."""

    occurred_at: object
    source: str
    source_label: str
    event_type: str
    event_type_label: str
    actor_label: str
    allocation_label: str
    changes: list
    before_display: str
    after_display: str
    details: str
    has_technical_json: bool


@dataclass
class LineTimelinePage:
    items: list
    page_obj: object


@dataclass(frozen=True)
class LineTimelineFilterOptions:
    event_type_choices: list = field(default_factory=list)
    actor_choices: list = field(default_factory=list)
    allocation_choices: list = field(default_factory=list)


def has_line_activity(phone_line) -> bool:
    """True se a linha tem qualquer fato registrado, ignorando filtros —
    usado para distinguir 'linha sem atividade' de 'filtro sem resultado'."""
    return (
        PhoneLineHistory.objects.filter(phone_line=phone_line).exists()
        or LineDailyActionAuditEvent.objects.filter(phone_line=phone_line).exists()
    )


def get_line_timeline_filter_options(phone_line) -> LineTimelineFilterOptions:
    event_type_choices = list(PhoneLineHistory.ActionType.choices) + list(
        LineDailyActionAuditEvent.EventType.choices
    )

    changed_by_ids = (
        PhoneLineHistory.objects.filter(phone_line=phone_line)
        .exclude(changed_by_id=None)
        .values_list("changed_by_id", flat=True)
    )
    performed_by_ids = (
        LineDailyActionAuditEvent.objects.filter(phone_line=phone_line)
        .exclude(performed_by_id=None)
        .values_list("performed_by_id", flat=True)
    )
    actor_ids = set(changed_by_ids) | set(performed_by_ids)
    actor_choices = [
        (user.pk, user.get_full_name().strip() or user.email)
        for user in SystemUser.objects.filter(pk__in=actor_ids).order_by("email")
    ]

    allocation_choices = [
        (allocation.pk, f"#{allocation.pk}")
        for allocation in LineAllocation.objects.filter(
            phone_line=phone_line
        ).order_by("-allocated_at")
    ]

    return LineTimelineFilterOptions(
        event_type_choices=event_type_choices,
        actor_choices=actor_choices,
        allocation_choices=allocation_choices,
    )


def _legacy_projection(phone_line, filters: LineTimelineFilters):
    qs = PhoneLineHistory.objects.filter(phone_line=phone_line)
    if filters.start_at:
        qs = qs.filter(changed_at__gte=filters.start_at)
    if filters.end_at:
        qs = qs.filter(changed_at__lte=filters.end_at)
    if filters.event_type:
        qs = qs.filter(action=filters.event_type)
    if filters.actor_id:
        qs = qs.filter(changed_by_id=filters.actor_id)
    # Limpa a ordenacao padrao do Meta: branches de union() nao podem ter
    # ORDER BY proprio, so o queryset combinado final pode.
    return qs.order_by().annotate(
        row_source=Value(SOURCE_PHONE_LINE_HISTORY, output_field=CharField(max_length=30)),
        row_id=F("pk"),
        sort_at=F("changed_at"),
    ).values("row_source", "row_id", "sort_at")


def _audit_projection(phone_line, filters: LineTimelineFilters):
    qs = LineDailyActionAuditEvent.objects.filter(phone_line=phone_line)
    if filters.start_at:
        qs = qs.filter(occurred_at__gte=filters.start_at)
    if filters.end_at:
        qs = qs.filter(occurred_at__lte=filters.end_at)
    if filters.event_type:
        qs = qs.filter(event_type=filters.event_type)
    if filters.actor_id:
        qs = qs.filter(performed_by_id=filters.actor_id)
    if filters.allocation_id:
        qs = qs.filter(allocation_id=filters.allocation_id)
    return qs.order_by().annotate(
        row_source=F("source"),
        row_id=F("pk"),
        sort_at=F("occurred_at"),
    ).values("row_source", "row_id", "sort_at")


def _combined_queryset(phone_line, filters: LineTimelineFilters):
    projections = []
    # Historico legado nao tem alocacao historica confiavel: com
    # allocation_id, exclui o legado inteiramente em vez de tentar inferir.
    if not filters.allocation_id:
        projections.append(_legacy_projection(phone_line, filters))
    projections.append(_audit_projection(phone_line, filters))

    combined = projections[0]
    for extra in projections[1:]:
        combined = combined.union(extra, all=True)
    return combined.order_by("-sort_at", "row_source", "-row_id")


def _actor_label_legacy(history: PhoneLineHistory) -> str:
    if history.changed_by_id:
        user = history.changed_by
        return user.get_full_name().strip() or user.email
    return "Sistema"


def _actor_label_audit(event: LineDailyActionAuditEvent) -> str:
    if event.performed_by_id:
        user = event.performed_by
        return user.get_full_name().strip() or user.email
    if event.performed_by_name_snapshot:
        return event.performed_by_name_snapshot
    if event.performed_by_email_snapshot:
        return event.performed_by_email_snapshot
    return "Sistema"


def _allocation_label(event: LineDailyActionAuditEvent) -> str:
    if event.allocation_id:
        return f"#{event.allocation_id}"
    if event.allocation_id_snapshot:
        return f"#{event.allocation_id_snapshot} (removida)"
    return "-"


def _state_value(value, *, kind):
    if kind in {"action", "line_status"}:
        if isinstance(value, dict):
            return value.get("label") or value.get("code") or "-"
    elif kind == "technical_responsible":
        if not value:
            return "Não atribuído"
        if isinstance(value, dict):
            return value.get("name") or value.get("email") or "Não atribuído"
    elif kind == "note":
        return value or "Sem nota"
    elif kind == "resolution":
        if isinstance(value, dict):
            return "Resolvida" if value.get("is_resolved") else "Aberta"
    return str(value) if value is not None else "-"


def _audit_changes(before_state, after_state) -> list[LineTimelineChange]:
    changes = []
    for key, label in (
        ("action", "Ação"),
        ("note", "Nota"),
        ("line_status", "Status da linha"),
        ("technical_responsible", "Responsável técnico"),
        ("resolution", "Situação"),
    ):
        before_value = before_state.get(key)
        after_value = after_state.get(key)
        if before_value != after_value:
            changes.append(
                LineTimelineChange(
                    label=label,
                    before_value=_state_value(before_value, kind=key),
                    after_value=_state_value(after_value, kind=key),
                )
            )

    if before_state.get("source_state") != after_state.get("source_state"):
        changes.append(
            LineTimelineChange(
                label="Contexto da origem",
                before_value="Anterior",
                after_value="Atualizado",
            )
        )
    return changes


def _item_from_legacy(history: PhoneLineHistory) -> LineTimelineItem:
    return LineTimelineItem(
        occurred_at=history.changed_at,
        source=SOURCE_PHONE_LINE_HISTORY,
        source_label=SOURCE_LABELS[SOURCE_PHONE_LINE_HISTORY],
        event_type=history.action,
        event_type_label=history.get_action_display(),
        actor_label=_actor_label_legacy(history),
        allocation_label="-",
        changes=[
            LineTimelineChange(
                label="Alteração",
                before_value=history.old_value or "-",
                after_value=history.new_value or "-",
            )
        ],
        before_display=history.old_value or "-",
        after_display=history.new_value or "-",
        details=history.description or "",
        has_technical_json=False,
    )


def _item_from_audit(event: LineDailyActionAuditEvent) -> LineTimelineItem:
    return LineTimelineItem(
        occurred_at=event.occurred_at,
        source=event.source,
        source_label=SOURCE_LABELS.get(event.source, event.source),
        event_type=event.event_type,
        event_type_label=event.get_event_type_display(),
        actor_label=_actor_label_audit(event),
        allocation_label=_allocation_label(event),
        changes=_audit_changes(event.before_state, event.after_state),
        before_display=json.dumps(
            event.before_state, ensure_ascii=False, indent=2, sort_keys=True
        ),
        after_display=json.dumps(
            event.after_state, ensure_ascii=False, indent=2, sort_keys=True
        ),
        details="",
        has_technical_json=True,
    )


def get_line_timeline_page(phone_line: PhoneLine, filters: LineTimelineFilters) -> LineTimelinePage:
    combined = _combined_queryset(phone_line, filters)
    paginator = Paginator(combined, PAGE_SIZE)
    page_obj = paginator.get_page(filters.page)
    rows = list(page_obj.object_list)

    legacy_ids = [row["row_id"] for row in rows if row["row_source"] == SOURCE_PHONE_LINE_HISTORY]
    audit_ids = [row["row_id"] for row in rows if row["row_source"] != SOURCE_PHONE_LINE_HISTORY]

    legacy_map = {}
    if legacy_ids:
        legacy_map = {
            obj.pk: obj
            for obj in PhoneLineHistory.objects.filter(pk__in=legacy_ids).select_related(
                "changed_by"
            )
        }

    audit_map = {}
    if audit_ids:
        audit_map = {
            obj.pk: obj
            for obj in LineDailyActionAuditEvent.objects.filter(pk__in=audit_ids).select_related(
                "performed_by", "allocation", "employee"
            )
        }

    items = []
    for row in rows:
        if row["row_source"] == SOURCE_PHONE_LINE_HISTORY:
            obj = legacy_map.get(row["row_id"])
            if obj is not None:
                items.append(_item_from_legacy(obj))
        else:
            obj = audit_map.get(row["row_id"])
            if obj is not None:
                items.append(_item_from_audit(obj))

    return LineTimelinePage(items=items, page_obj=page_obj)
