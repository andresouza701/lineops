"""Composicao de relatorios individuais de linha.

Reusa os servicos T6 (timeline) e T7 (operacional), sem recalcular ciclos
nem consultar estado operacional fora dos eventos de auditoria.
"""

from dataclasses import dataclass
from datetime import date

from telecom.line_operational_report import (
    LineOperationalReportFilters,
    build_line_operational_report,
)
from telecom.line_timeline import LineTimelineFilters, get_line_timeline_page
from telecom.models import PhoneLine


@dataclass(frozen=True)
class LineReportsResult:
    operational_row: object
    timeline_page: object


def build_line_reports(
    phone_line: PhoneLine,
    *,
    start_date: date,
    end_date: date,
    page: int = 1,
) -> LineReportsResult:
    """Gera os dois relatorios para uma unica linha e mesmo intervalo."""
    operational_rows = build_line_operational_report(
        PhoneLine.objects.filter(pk=phone_line.pk),
        LineOperationalReportFilters(start_date=start_date, end_date=end_date),
    )
    return LineReportsResult(
        operational_row=operational_rows[0] if operational_rows else None,
        timeline_page=get_line_timeline_page(
            phone_line,
            LineTimelineFilters(
                start_date=start_date,
                end_date=end_date,
                page=page,
            ),
        ),
    )
