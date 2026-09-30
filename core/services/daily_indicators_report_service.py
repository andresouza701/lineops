"""Leitura do relatorio Indicadores diarios (REL-13-Q).

Fonte da verdade: docs/superpowers/specs/2026-09-22-reports-hub-design.md,
secoes REL-07 (contrato comum) e REL-13-C (contrato especifico, decisoes
A-D de 2026-09-30). Somente leitura: nenhuma escrita de negocio, model ou
migration — reutiliza integralmente `build_indicator_for_day`
(dashboard/views.py), a mesma formula ja em producao no widget do
dashboard, sem redefinir nenhum calculo.

Granularidade por dia calendario (uma linha de resultado por `day` do
periodo inclusivo, nunca por evento/entidade): diferente dos outros cinco
relatorios (uma linha por registro-fonte filtrado), aqui cada linha e o
resultado de uma funcao f(day) -> dict, entao TODO dia do periodo aparece,
mesmo sem nenhum registro-fonte (zero-preenchimento estrutural, nao uma
escolha de filtro).

Custo e estrategia de medicao (REL-13-C secao 3, decisao D): o custo deste
relatorio escala com o numero de DIAS do periodo, nao com o volume de
registros-fonte. Para evitar computar o indicador completo (~8-10
consultas/dia) para dias fora da pagina atual — que nunca sao exibidos —,
apenas os dias da PAGINA ATUAL usam `build_indicator_for_day` (fonte unica
da formula completa, inclusive das 6 colunas de estoque). Os totalizadores
globais (Entregues/Reconectados/Novos, unicas colunas com totalizador
aprovado — decisao B) sao calculados separadamente, sobre o periodo
INTEIRO independente da pagina:
- Entregues/Novos: uma UNICA consulta agregada por todo o periodo (nao um
  loop por dia). Comprovadamente equivalente a somar o resultado diario
  (REL-13-C secao 1): o predicado de visibilidade historica
  (`_phone_line_visible_at_reference_q`, reaproveitado de
  dashboard/views.py, nao redefinido) compara cada linha contra o proprio
  campo de data daquela linha (`F(reference_field)`), nunca contra um
  limite fixo do dia — o resultado de uma consulta pelo periodo inteiro e
  identico a soma das consultas por dia, sem aproximacao.
- Reconectados: combina tres fontes (ORM, DailyUserAction legado,
  AllocationPendency — ver `count_reconnected_numbers_for_day`,
  dashboard/views.py), e a checagem de visibilidade de um dia HISTORICO
  usa um limite FIXO daquele dia especifico (`start_of_day`), nao um
  campo por linha — batching em uma unica consulta multi-dia mudaria esse
  limite silenciosamente (RISCO identificado em REL-13-C secao 3, "mais
  arriscado de reescrever sem mudar comportamento"). Mantido como soma de
  `count_reconnected_numbers_for_day(day)` por dia do periodo (mesma
  funcao ja usada pela formula, nao reimplementada) — custo O(dias),
  linear, nao otimizado nesta task por seguranca de nao alterar o
  resultado calculado.

Redundancia aceita e documentada: para os dias que calham de estar na
pagina atual, `count_reconnected_numbers_for_day` acaba sendo chamado
duas vezes (uma dentro de `build_indicator_for_day`, para a linha exibida;
outra dentro do totalizador). Nao eliminada nesta task — exigiria plumbing
adicional (reaproveitar os valores da pagina no totalizador) por um ganho
pequeno (no maximo PAGE_SIZE=50 chamadas duplicadas por consulta), REL-13-C
decisao D permite otimizacao futura sem promessa de latencia constante."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.core.paginator import Paginator
from django.utils import timezone

from allocations.models import LineAllocation
from dashboard.views import (
    _phone_line_visible_at_reference_q,
    build_indicator_for_day,
    count_reconnected_numbers_for_day,
)
from telecom.models import PhoneLine

PAGE_SIZE = 50

REPORT_ROW_KEYS = (
    "data",
    "pessoas_logadas",
    "perc_sem_whats",
    "b2b_sem_whats",
    "b2c_sem_whats",
    "numeros_disponiveis",
    "numeros_entregues",
    "reconectados",
    "novos",
    "total_descoberto_dia",
)


@dataclass
class DailyIndicatorsReportTotals:
    numeros_entregues: int
    reconectados: int
    novos: int


@dataclass
class DailyIndicatorsReportResult:
    rows: list
    totals: DailyIndicatorsReportTotals
    page_number: int
    num_pages: int
    generated_at: datetime


def _day_range(data_inicial: date, data_final: date) -> list[date]:
    total_days = (data_final - data_inicial).days + 1
    return [data_inicial + timedelta(days=offset) for offset in range(total_days)]


def _period_bounds(data_inicial: date, data_final: date):
    """Inicio local do primeiro dia ate o ultimo instante local do ultimo
    dia, ambos inclusivos — cada dia do periodo e avaliado com seus proprios
    `start_of_day`/`end_of_day` internos por `build_indicator_for_day`; este
    par so delimita a consulta agregada dos totalizadores de fluxo."""
    start = timezone.make_aware(datetime.combine(data_inicial, time.min))
    end = timezone.make_aware(datetime.combine(data_final, time.max))
    return start, end


def _row_from_indicator(indicator: dict) -> dict:
    return {key: indicator[key] for key in REPORT_ROW_KEYS}


def entregues_novos_period_totals(data_inicial: date, data_final: date) -> tuple[int, int]:
    """Totais agregados de Entregues/Novos para o periodo INTEIRO, em UMA
    unica consulta cada (O(1), nao O(dias)) — reaproveitado pela tela
    (REL-13-Q, via `_flow_totals_for_period` abaixo) e pela exportacao
    (REL-13-E, `core/services/daily_indicators_export_service.py`).
    Comprovadamente equivalente a somar o resultado diario (REL-13-C secao
    1): o predicado de visibilidade historica compara cada linha contra o
    proprio campo de data daquela linha (`F(reference_field)`), nunca
    contra um limite fixo do dia."""
    start, end = _period_bounds(data_inicial, data_final)

    numeros_entregues = (
        LineAllocation.objects.filter(allocated_at__range=(start, end))
        .filter(_phone_line_visible_at_reference_q("allocated_at", prefix="phone_line__"))
        .count()
    )

    novos = (
        PhoneLine.all_objects.filter(created_at__range=(start, end))
        .filter(_phone_line_visible_at_reference_q("created_at"))
        .count()
    )

    return numeros_entregues, novos


def _flow_totals_for_period(
    data_inicial: date, data_final: date, days: list[date]
) -> DailyIndicatorsReportTotals:
    numeros_entregues, novos = entregues_novos_period_totals(data_inicial, data_final)
    reconectados = sum(count_reconnected_numbers_for_day(day) for day in days)

    return DailyIndicatorsReportTotals(
        numeros_entregues=numeros_entregues,
        reconectados=reconectados,
        novos=novos,
    )


def iter_daily_indicators_report_rows(
    *,
    data_inicial: date,
    data_final: date,
    incluir_excluidos: bool = False,
):
    """Itera TODO o periodo (sem paginacao — REL-13-E: exportacao nunca
    limita pela pagina da tela), um dia por vez, reutilizando
    `build_indicator_for_day` — mesma fonte de calculo da tela (REL-13-Q),
    nenhuma formula redefinida. `incluir_excluidos` aceito por simetria de
    assinatura com `build_daily_indicators_report` (REL-13-C decisao C),
    nunca lido. Custo por dia e o mesmo da tela (~8-10 consultas); aqui
    TODOS os dias do periodo pagam esse custo, nao so os da pagina — ver
    `core/services/daily_indicators_export_service.py` para a medicao
    real desse caminho (REL-13-E)."""
    for day in _day_range(data_inicial, data_final):
        yield _row_from_indicator(build_indicator_for_day(day, user=None))


def build_daily_indicators_report(
    *,
    data_inicial: date,
    data_final: date,
    incluir_excluidos: bool = False,
    page: int = 1,
) -> DailyIndicatorsReportResult:
    """Monta o conjunto do relatorio Indicadores diarios e pagina o
    resultado. `incluir_excluidos` e aceito por simetria de assinatura com
    os demais relatorios, mas nunca lido — decisao C/REL-13-C: a
    visibilidade historica ja e decidida por `build_indicator_for_day` em
    funcao do proprio dia, sem alternancia por checkbox. Totalizadores
    (Entregues/Reconectados/Novos) cobrem TODO o periodo filtrado,
    independente da pagina. Pode levantar django.core.paginator.EmptyPage
    quando `page` esta fora do intervalo."""
    generated_at = timezone.now()
    days = _day_range(data_inicial, data_final)

    paginator = Paginator(days, PAGE_SIZE)
    page_obj = paginator.page(page)

    rows = [
        _row_from_indicator(build_indicator_for_day(day, user=None))
        for day in page_obj.object_list
    ]

    totals = _flow_totals_for_period(data_inicial, data_final, days)

    return DailyIndicatorsReportResult(
        rows=rows,
        totals=totals,
        page_number=page_obj.number,
        num_pages=paginator.num_pages,
        generated_at=generated_at,
    )
