"""Leitura do relatorio Selos WhatsApp (REL-08-Q).

Fonte da verdade: docs/superpowers/specs/2026-09-22-reports-hub-design.md,
secoes REL-07 (contrato comum) e REL-08-C (contrato especifico). Somente
leitura: nenhuma escrita de negocio, model ou migration.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.utils import timezone

from telecom.models import PhoneLine
from telecom.seal_indicator import build_seal_indicator
from telecom.whatsapp_seal import WhatsAppSeal

PAGE_SIZE = 50

SITUATION_LABELS = {
    "missing_expiry": "Sem vencimento informado",
    "today": "Vence hoje",
}

_SITUATION_TONES = {
    "regular": "neutral",
    "warning": "warning",
    "today": "today",
    "expired": "expired",
    "missing_expiry": "neutral",
}


@dataclass
class WhatsAppSealReportRow:
    phone_number: str
    seal_display: str
    activated_on: Optional[date]
    payment_display: str
    email: str
    expires_on: Optional[date]
    situation_key: str
    situation_tone: str
    situation_label: str
    dates_inverted: bool
    registro_label: str
    seal_indicator: object = None


@dataclass
class WhatsAppSealReportTotals:
    total: int
    meta_one: int
    meta_verified: int
    regular: int
    warning: int
    today: int
    expired: int
    missing_expiry: int


@dataclass
class WhatsAppSealReportResult:
    rows: list
    totals: WhatsAppSealReportTotals
    page_number: int
    num_pages: int
    reference_date: date
    generated_at: object


def _situation_key(expires_on: Optional[date], reference_date: date) -> str:
    if expires_on is None:
        return "missing_expiry"
    delta = (expires_on - reference_date).days
    if delta > 7:
        return "regular"
    if delta > 0:
        return "warning"
    if delta == 0:
        return "today"
    return "expired"


def _situation_label(key: str, expires_on: Optional[date], reference_date: date) -> str:
    if key in SITUATION_LABELS:
        return SITUATION_LABELS[key]
    if key == "regular":
        return f"Vence em {expires_on.strftime('%d/%m/%Y')}"
    if key == "warning":
        delta = (expires_on - reference_date).days
        unit = "dia" if delta == 1 else "dias"
        return f"Vence em {delta} {unit}"
    overdue = (reference_date - expires_on).days
    unit = "dia" if overdue == 1 else "dias"
    return f"Vencido há {overdue} {unit}"


def _registro_label(line_deleted: bool, sim_deleted: bool) -> str:
    if line_deleted and sim_deleted:
        return "Linha e SIMcard excluídos"
    if line_deleted:
        return "Linha excluída"
    if sim_deleted:
        return "SIMcard excluído"
    return "Não excluído"


def _situation_filter(key: str, reference_date: date) -> Q:
    if key == "regular":
        return Q(whatsapp_seal_expires_on__gt=reference_date + timedelta(days=7))
    if key == "warning":
        return Q(
            whatsapp_seal_expires_on__gt=reference_date,
            whatsapp_seal_expires_on__lte=reference_date + timedelta(days=7),
        )
    if key == "today":
        return Q(whatsapp_seal_expires_on=reference_date)
    if key == "expired":
        return Q(whatsapp_seal_expires_on__lt=reference_date)
    if key == "missing_expiry":
        return Q(whatsapp_seal_expires_on__isnull=True)
    return Q()


def _build_queryset(
    *,
    data_inicial: date,
    data_final: date,
    incluir_excluidos: bool = False,
    selo: str = "",
    pagamento: str = "",
    situacao: str = "",
    linha: str = "",
    reference_date: date,
):
    """Escopo/filtros/ordenacao unicos do relatorio (REL-08-C), reaproveitados
    pela tela (paginada, REL-08-Q) e pela exportacao integral (REL-08-E) —
    nenhuma regra e duplicada em outro queryset."""
    queryset = PhoneLine.all_objects.select_related("sim_card").filter(
        whatsapp_seal__in=[WhatsAppSeal.META_ONE, WhatsAppSeal.META_VERIFIED],
        whatsapp_seal_activated_on__gte=data_inicial,
        whatsapp_seal_activated_on__lte=data_final,
    )

    if not incluir_excluidos:
        queryset = queryset.filter(is_deleted=False, sim_card__is_deleted=False)

    if selo:
        queryset = queryset.filter(whatsapp_seal=selo)
    if pagamento:
        queryset = queryset.filter(whatsapp_seal_payment=pagamento)
    if linha:
        queryset = queryset.filter(phone_number__icontains=linha)
    if situacao:
        queryset = queryset.filter(_situation_filter(situacao, reference_date))

    return queryset.order_by("-whatsapp_seal_activated_on", "-pk")


def _row_from_line(line: PhoneLine, reference_date: date) -> WhatsAppSealReportRow:
    situation_key = _situation_key(line.whatsapp_seal_expires_on, reference_date)
    return WhatsAppSealReportRow(
        phone_number=line.phone_number,
        seal_display=line.get_whatsapp_seal_display(),
        activated_on=line.whatsapp_seal_activated_on,
        payment_display=line.get_whatsapp_seal_payment_display(),
        email=line.whatsapp_seal_email,
        expires_on=line.whatsapp_seal_expires_on,
        situation_key=situation_key,
        situation_tone=_SITUATION_TONES[situation_key],
        situation_label=_situation_label(
            situation_key, line.whatsapp_seal_expires_on, reference_date
        ),
        dates_inverted=bool(
            line.whatsapp_seal_expires_on
            and line.whatsapp_seal_activated_on
            and line.whatsapp_seal_expires_on < line.whatsapp_seal_activated_on
        ),
        registro_label=_registro_label(line.is_deleted, line.sim_card.is_deleted),
        seal_indicator=build_seal_indicator(
            identified=True,
            seal=line.whatsapp_seal,
            activation_status=line.whatsapp_seal_activation_status,
            expires_on=line.whatsapp_seal_expires_on,
        ),
    )


def build_whatsapp_seal_report(
    *,
    data_inicial: date,
    data_final: date,
    incluir_excluidos: bool = False,
    selo: str = "",
    pagamento: str = "",
    situacao: str = "",
    linha: str = "",
    page: int = 1,
    reference_date: Optional[date] = None,
) -> WhatsAppSealReportResult:
    """Monta o conjunto do relatorio Selos WhatsApp e pagina o resultado.

    Uma unica data local de referencia (reference_date, ou timezone.localdate()
    se omitida) e usada para todas as classificacoes de vencimento e para os
    totalizadores desta chamada, conforme REL-08-C. Pode levantar
    django.core.paginator.EmptyPage quando `page` esta fora do intervalo.
    """
    reference_date = reference_date or timezone.localdate()
    generated_at = timezone.now()

    queryset = _build_queryset(
        data_inicial=data_inicial,
        data_final=data_final,
        incluir_excluidos=incluir_excluidos,
        selo=selo,
        pagamento=pagamento,
        situacao=situacao,
        linha=linha,
        reference_date=reference_date,
    )

    type_counts = queryset.aggregate(
        meta_one=Count("pk", filter=Q(whatsapp_seal=WhatsAppSeal.META_ONE)),
        meta_verified=Count("pk", filter=Q(whatsapp_seal=WhatsAppSeal.META_VERIFIED)),
    )
    situation_counts = queryset.aggregate(
        regular=Count("pk", filter=_situation_filter("regular", reference_date)),
        warning=Count("pk", filter=_situation_filter("warning", reference_date)),
        today=Count("pk", filter=_situation_filter("today", reference_date)),
        expired=Count("pk", filter=_situation_filter("expired", reference_date)),
        missing_expiry=Count("pk", filter=_situation_filter("missing_expiry", reference_date)),
    )

    paginator = Paginator(queryset, PAGE_SIZE)
    total = paginator.count
    page_obj = paginator.page(page)

    rows = [_row_from_line(line, reference_date) for line in page_obj.object_list]

    totals = WhatsAppSealReportTotals(
        total=total,
        meta_one=type_counts["meta_one"] or 0,
        meta_verified=type_counts["meta_verified"] or 0,
        regular=situation_counts["regular"] or 0,
        warning=situation_counts["warning"] or 0,
        today=situation_counts["today"] or 0,
        expired=situation_counts["expired"] or 0,
        missing_expiry=situation_counts["missing_expiry"] or 0,
    )

    return WhatsAppSealReportResult(
        rows=rows,
        totals=totals,
        page_number=page_obj.number,
        num_pages=paginator.num_pages,
        reference_date=reference_date,
        generated_at=generated_at,
    )


def count_whatsapp_seal_report_rows(
    *,
    data_inicial: date,
    data_final: date,
    incluir_excluidos: bool = False,
    selo: str = "",
    pagamento: str = "",
    situacao: str = "",
    linha: str = "",
    reference_date: date,
) -> int:
    """Contagem do mesmo conjunto de `_build_queryset`, usada pela exportacao
    (REL-08-E) para dimensionar partes/ZIP antes de gerar os arquivos."""
    return _build_queryset(
        data_inicial=data_inicial,
        data_final=data_final,
        incluir_excluidos=incluir_excluidos,
        selo=selo,
        pagamento=pagamento,
        situacao=situacao,
        linha=linha,
        reference_date=reference_date,
    ).count()


def iter_whatsapp_seal_report_rows(
    *,
    data_inicial: date,
    data_final: date,
    incluir_excluidos: bool = False,
    selo: str = "",
    pagamento: str = "",
    situacao: str = "",
    linha: str = "",
    reference_date: date,
    chunk_size: int = 2000,
):
    """Itera TODO o conjunto (sem paginacao), mesmo escopo/filtros/ordenacao
    de `_build_queryset`, em lotes via `.iterator()` — sem materializar o
    resultado inteiro em memoria. Usado exclusivamente pela exportacao
    (REL-08-E)."""
    queryset = _build_queryset(
        data_inicial=data_inicial,
        data_final=data_final,
        incluir_excluidos=incluir_excluidos,
        selo=selo,
        pagamento=pagamento,
        situacao=situacao,
        linha=linha,
        reference_date=reference_date,
    )
    for line in queryset.iterator(chunk_size=chunk_size):
        yield _row_from_line(line, reference_date)
