"""Exportacao CSV/XLSX/ZIP do relatorio Historico da linha (REL-12-E).

Fonte da verdade: docs/superpowers/specs/2026-09-22-reports-hub-design.md,
secoes REL-07 (contrato comum) e REL-12-C (contrato especifico). Reaproveita
o motor de consulta de REL-12-Q (core/services/line_history_report_service):
mesmo escopo, filtros, ordenacao e projecao de linhas — nenhuma regra e
copiada em outro queryset. `iter_line_history_report_rows` ja percorre o
queryset unido (``union(all=True)``) em LOTES limitados por `chunk_size`,
hidratando cada lote de uma so vez por fonte (nunca por evento, nunca o
historico inteiro em memoria) — ver docstring dessa funcao para a prova de
que a ordem/conteudo do lote batem com o conjunto completo em qualquer
fronteira.

Exportador PROPRIO de Historico da linha, mesmo padrao arquitetural ja usado
por Selos WhatsApp/Inventario/Alocacoes/Pendencias (streaming + limpeza de
temporarios + divisao em ZIP + protecao de formula), com seu proprio
COLUMNS/slug/row-mapping, deliberadamente duplicado em vez de generalizado
(mesma decisao ja registrada em REL-09-C/REL-10-E/REL-11-E: cada relatorio
com seu proprio exportador). Somente leitura: nenhuma escrita de negocio,
model ou migration.

Diferente de Pendencias (todas as colunas texto) e igual a Alocacoes na
tecnica: a coluna "Data/hora do evento" (`occurred_at`, DateTimeField
sempre preenchido nas duas fontes) recebe tratamento de data/hora real no
XLSX (celula datetime com `number_format`, apos conversao para o fuso local
via `timezone.localtime` — REL-07 exige fuso declarado, nao UTC bruto) e
formatacao textual "DD/MM/AAAA HH:MM" no CSV; as demais oito colunas (a
Linha, que comeca por "+" e por isso passa pela mesma protecao de formula
que qualquer texto iniciado por =/+/-/@, incluida) sao texto puro em ambos
os formatos, com a mesma protecao de formula uniforme ja usada pelos quatro
exportadores existentes."""

import csv
import itertools
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from datetime import timezone as dt_timezone
from typing import Iterator

import openpyxl
from openpyxl.cell import WriteOnlyCell
from openpyxl.writer.excel import ExcelWriter
from django.http import StreamingHttpResponse
from django.utils import timezone

from core.services.line_history_report_service import (
    LineHistoryReportRow,
    iter_line_history_report_rows,
)
from telecom.line_timeline import SOURCE_LABELS
from telecom.models import LineDailyActionAuditEvent, PhoneLineHistory

# Limiar de producao (REL-07/REL-12-C): ate este numero de linhas de dados
# por arquivo; acima, ZIP com partes numeradas. Testes de fronteira usam o
# parametro `split_threshold` das funcoes abaixo para reduzir o limiar sem
# tocar este valor de producao.
EXPORT_SPLIT_THRESHOLD = 100_000

COLUMNS = [
    "Linha",
    "Data/hora do evento",
    "Fonte",
    "Tipo de evento",
    "Ator",
    "Alocação relacionada",
    "Alterações",
    "Registro da linha",
    "Funcionário excluído",
]

# Unica coluna datetime (indice 1, "Data/hora do evento"); as demais oito
# sao texto, protegidas uniformemente contra formula (ver docstring do
# modulo).
_DATETIME_COLUMNS = (False, True, False, False, False, False, False, False, False)

# Limite fisico de caracteres por celula de texto no formato XLSX (imposto
# pelo proprio Excel/openpyxl — ver openpyxl.cell.cell.Cell.check_string,
# que hoje trunca silenciosamente em vez de rejeitar). REPORTS_SENIOR_REVIEW
# achado 1: `changes_label` (concatenacao de PhoneLineHistory.old_value/
# new_value, ambos TextField sem max_length) pode ultrapassar esse limite
# em producao. REL-07 proibe entregar "arquivo truncado ou aparentemente
# completo apos falha" — decisao de contrato (2026-09-30): rejeitar
# explicitamente APENAS a exportacao XLSX quando qualquer celula de texto
# exceder o limite (LineHistoryExportCellTooLongError, nunca truncamento
# silencioso nem erro 500 generico), com mensagem indicando o CSV como
# alternativa — o CSV do mesmo relatorio nao tem esse limite fisico e
# sempre entrega o texto integral (ver `_row_to_csv_cells`/`_csv_text`,
# que apenas fazem `str(value)`, sem qualquer corte).
EXCEL_MAX_CELL_TEXT_LENGTH = 32767


class LineHistoryExportCellTooLongError(Exception):
    """Uma celula de texto do XLSX excederia o limite fisico do Excel
    (EXCEL_MAX_CELL_TEXT_LENGTH). Levantada ANTES de escrever a celula
    (nunca apos truncamento silencioso do openpyxl) — propaga pelo mesmo
    caminho de limpeza de temporarios ja usado para qualquer outra falha de
    geracao (`_write_xlsx_chunk`/`generate_line_history_export`: nenhum
    arquivo parcial e entregue, workbook abandonado e temp_dir sao
    limpos). A view (config/views.py) mapeia esta excecao especifica para
    um erro de campo compreensivel (400), nunca um 500 generico."""

_CONTENT_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
_ZIP_CONTENT_TYPE = "application/zip"

_BLOCK_SIZE = 65536

_LEADING_WS_CONTROL = re.compile(r"^[\s\x00-\x1f]+")
_FORMULA_TRIGGERS = ("=", "+", "-", "@")

_SLUG = "historico_linha"

_FONTE_EVENTO_LABELS = {"": "Todas", **SOURCE_LABELS}
_TIPO_EVENTO_LABELS = {"": "Todos"}
_TIPO_EVENTO_LABELS.update(dict(PhoneLineHistory.ActionType.choices))
_TIPO_EVENTO_LABELS.update(dict(LineDailyActionAuditEvent.EventType.choices))


@dataclass
class ExportFile:
    path: str
    filename: str
    content_type: str
    temp_dir: str


def _looks_like_formula(value: str) -> bool:
    trimmed = _LEADING_WS_CONTROL.sub("", value)
    return trimmed.startswith(_FORMULA_TRIGGERS)


def _csv_text(value) -> str:
    if value is None:
        return ""
    text = str(value)
    return f"'{text}" if _looks_like_formula(text) else text


def _row_to_csv_cells(row: LineHistoryReportRow) -> list:
    return [
        _csv_text(row.phone_number),
        timezone.localtime(row.occurred_at).strftime("%d/%m/%Y %H:%M"),
        _csv_text(row.source_label),
        _csv_text(row.event_type_label),
        _csv_text(row.actor_label),
        _csv_text(row.allocation_label),
        _csv_text(row.changes_label),
        _csv_text(row.registro_label),
        _csv_text(row.funcionario_excluido_label),
    ]


def _xlsx_text_cell(worksheet, value: str):
    if value is None:
        return None
    if _looks_like_formula(value):
        # openpyxl infere data_type='f' (formula) para qualquer string
        # iniciada por =/+/-/@ atribuida diretamente a uma celula — o
        # contrato (REL-07) exige texto puro, nunca formula, no XLSX.
        # Forcar data_type='s' apos a construcao (nao no `value=` do
        # construtor, que reexecuta a mesma inferencia) grava a string
        # literal sem interpretacao.
        cell = WriteOnlyCell(worksheet, value=value)
        cell.data_type = "s"
        return cell
    return value


def _row_to_xlsx_cells(worksheet, row: LineHistoryReportRow) -> list:
    values = [
        row.phone_number,
        timezone.localtime(row.occurred_at).replace(tzinfo=None),
        row.source_label,
        row.event_type_label,
        row.actor_label,
        row.allocation_label,
        row.changes_label,
        row.registro_label,
        row.funcionario_excluido_label,
    ]
    cells = []
    for value, is_datetime in zip(values, _DATETIME_COLUMNS):
        if is_datetime:
            # `value` ja chegou convertido para o fuso local
            # (America/Sao_Paulo) e sem tzinfo (openpyxl/Excel nao aceita
            # datetime timezone-aware — "Excel does not support timezones
            # in datetimes"); a conversao para wall-clock local ja ocorreu
            # em `_row_to_xlsx_cells`, so o marcador de fuso e removido.
            cell = WriteOnlyCell(worksheet, value=value)
            cell.number_format = "DD/MM/YYYY HH:MM"
            cells.append(cell)
        elif isinstance(value, str):
            if len(value) > EXCEL_MAX_CELL_TEXT_LENGTH:
                raise LineHistoryExportCellTooLongError(
                    f"A exportação em XLSX do Histórico da linha não está "
                    f"disponível para este período: um registro da linha "
                    f"{row.phone_number} ({timezone.localtime(row.occurred_at).strftime('%d/%m/%Y %H:%M')}) "
                    f"tem um campo com {len(value)} caracteres, acima do "
                    f"limite de {EXCEL_MAX_CELL_TEXT_LENGTH} caracteres por "
                    f"célula do Excel. Baixe em CSV para obter o texto "
                    f"completo."
                )
            cells.append(_xlsx_text_cell(worksheet, value))
        else:
            cells.append(value)
    return cells


def _filters_label(filters: dict) -> str:
    return (
        f"Período: {filters['data_inicial'].strftime('%d/%m/%Y')} a "
        f"{filters['data_final'].strftime('%d/%m/%Y')}; "
        f"Tipo de evento: "
        f"{_TIPO_EVENTO_LABELS.get(filters.get('tipo_evento', ''), filters.get('tipo_evento', ''))}; "
        f"Fonte: "
        f"{_FONTE_EVENTO_LABELS.get(filters.get('fonte_evento', ''), filters.get('fonte_evento', ''))}; "
        f"Ator: {filters.get('ator') or '(vazio)'}; "
        f"Linha: {filters.get('linha') or '(vazio)'}; "
        f"Incluir excluídos: {'Sim' if filters.get('incluir_excluidos') else 'Não'}"
    )


def _write_csv_chunk(path: str, rows: Iterator[LineHistoryReportRow], threshold: int) -> int:
    """Escreve ate `threshold` linhas do MESMO iterator (uma unica consulta
    de escopo/filtros para toda a exportacao, hidratada em lotes internos
    por `iter_line_history_report_rows`) e retorna quantas linhas foram
    efetivamente escritas. `written < threshold` sinaliza iterator esgotado
    — usado pelo chamador para decidir se ha mais partes, sem depender de
    nenhuma contagem calculada antes da iteracao (mesmo padrao corrigido em
    REL-08-E para evitar divergencia entre contagem previa e conjunto
    realmente iterado)."""
    written = 0
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(COLUMNS)
        for row in itertools.islice(rows, threshold):
            writer.writerow(_row_to_csv_cells(row))
            written += 1
    return written


def _close_abandoned_workbook(workbook) -> None:
    """Fecha um workbook write-only abandonado antes de `save()` — mesmo
    raciocinio e mesma correcao de vazamento de arquivo temporario interno
    do openpyxl (`sheet._writer.out`/`ALL_TEMP_FILES`, ver
    REPORTS_SENIOR_REVIEW achado 2) ja documentados em
    core/services/allocations_export_service."""
    for sheet in workbook.worksheets:
        if getattr(sheet, "_rows", None) is not None and not sheet.closed:
            try:
                sheet.close()
            except Exception:
                pass
        writer = getattr(sheet, "_writer", None)
        if writer is not None:
            try:
                writer.cleanup()
            except Exception:
                pass
    workbook.close()


def _write_xlsx_chunk(path: str, rows: Iterator[LineHistoryReportRow], threshold: int):
    """Mesmo contrato de `_write_csv_chunk`, mas para XLSX: os dados sao
    escritos de imediato (write-only, sem materializar linhas em memoria),
    porem a planilha "Contexto" (que depende do total/numero de partes,
    conhecidos somente apos esgotar o iterator inteiro) e adicionada depois
    por `_finalize_xlsx_chunk` — o workbook so e salvo nesse momento."""
    workbook = openpyxl.Workbook(write_only=True)
    sheet = workbook.create_sheet("Histórico da linha")
    sheet.append(COLUMNS)
    written = 0
    try:
        for row in itertools.islice(rows, threshold):
            sheet.append(_row_to_xlsx_cells(sheet, row))
            written += 1
    except Exception:
        # Sem isto, uma falha no meio do iterator (ex.: erro de banco, ou
        # LineHistoryExportIntegrityError) abandona o worksheet write-only
        # com seu generator interno suspenso; o GC eventual o fecha fora de
        # ordem e emite "ValueError: I/O operation on closed file" como
        # warning nao tratado, em vez de liberar o recurso aqui, de forma
        # limpa.
        _close_abandoned_workbook(workbook)
        raise
    return workbook, written


def _save_xlsx_workbook(workbook, path: str) -> None:
    """Salva `workbook` em `path` sendo dono explicito do arquivo ZIP de
    saida — nao apenas `workbook.save(path)` — ver docstring completa em
    core/services/allocations_export_service. Fechamento em falha usa
    `archive.close()` normal (metodo publico do `zipfile`), nao mais
    manipulacao direta de `archive.fp`: essa tentativa anterior confundia
    fechar o recurso com entregar o recurso — a entrega HTTP ja e
    impedida pela propagacao da excecao (nunca chega a
    `build_line_history_export_response`) e pela remocao de `temp_dir` no
    `except` externo de `generate_line_history_export`, qualquer que seja
    o conteudo do ZIP parcial no disco. Falha SECUNDARIA durante este
    `close()` de limpeza nao substitui a excecao original (por isso e
    engolida so aqui, ponto estreito e documentado). `archive.fp` nao e
    mais tocado. `workbook.properties.modified` e atualizado aqui para
    preservar o mesmo comportamento de `Workbook.save(path)`."""
    workbook.properties.modified = datetime.now(dt_timezone.utc).replace(tzinfo=None)
    archive = zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, allowZip64=True)
    try:
        ExcelWriter(workbook, archive).save()
    except Exception:
        try:
            archive.close()
        except Exception:
            pass
        raise


def _finalize_xlsx_chunk(
    workbook,
    path: str,
    *,
    part_index: int,
    num_parts: int,
    total: int,
    count: int,
    generated_at: datetime,
    filters_label: str,
) -> None:
    context_sheet = workbook.create_sheet("Contexto")
    context_sheet.append(["Campo", "Valor"])
    context_sheet.append(["Relatório", "Histórico da linha"])
    context_sheet.append(["Filtros", filters_label])
    context_sheet.append(["Gerado em", generated_at.strftime("%d/%m/%Y %H:%M:%S")])
    context_sheet.append(["Quantidade total", total])
    context_sheet.append(["Quantidade nesta parte", count])
    if num_parts > 1:
        context_sheet.append(["Parte", f"{part_index} de {num_parts}"])

    _save_xlsx_workbook(workbook, path)


def _build_base_name(data_inicial: date, data_final: date, generated_at: datetime) -> str:
    return (
        f"{_SLUG}_{data_inicial.strftime('%Y%m%d')}-{data_final.strftime('%Y%m%d')}"
        f"_{generated_at.strftime('%Y%m%dT%H%M%S')}"
    )


def generate_line_history_export(
    *,
    formato: str,
    filters: dict,
    split_threshold: int = EXPORT_SPLIT_THRESHOLD,
) -> ExportFile:
    """Gera o(s) arquivo(s) completo(s) do relatorio Historico da linha em
    arquivos temporarios privados, ANTES de qualquer resposta HTTP ser
    iniciada (sem envio parcial). `split_threshold` e a interface tecnica
    explicita de teste para a fronteira de divisao/ZIP — a rota HTTP nunca o
    passa, mantendo producao em EXPORT_SPLIT_THRESHOLD (100.000).

    Uma UNICA consulta de escopo/filtros (o iterator de
    `iter_line_history_report_rows`, que por sua vez hidrata em lotes
    internos limitados) dirige toda a divisao em partes: nao ha `count()`
    previo separado. Total, numero de partes e quantidade por parte sao
    derivados do que efetivamente foi escrito, nunca de uma contagem
    calculada antes da iteracao — mesmo raciocinio da correcao de risco
    documentada em REL-08-E (duas consultas independentes podem divergir por
    mudanca de dados entre elas). Uma anomalia de integridade
    (`LineHistoryExportIntegrityError`, evento selecionado que sumiu antes
    da hidratacao do seu lote) propaga como qualquer outra excecao: nenhum
    arquivo parcial e entregue, temporarios sao limpos pelo `except` abaixo."""
    if formato not in _CONTENT_TYPES:
        raise ValueError(f"Formato de exportacao desconhecido: {formato}")

    generated_at = timezone.now()

    temp_dir = tempfile.mkdtemp(prefix="lineops_line_history_export_")
    # Declarado ANTES do try: se uma excecao ocorrer antes/durante o
    # preenchimento desta lista, o except abaixo ainda precisa fecha-la
    # (workbooks write-only ja criados e ainda nao salvos nao podem ficar
    # para o GC fechar fora de ordem).
    xlsx_parts = []  # (workbook, path) — save() adiado ate total/num_parts conhecidos
    try:
        rows = iter_line_history_report_rows(**filters)

        base_name = _build_base_name(filters["data_inicial"], filters["data_final"], generated_at)
        filters_label = _filters_label(filters)

        part_paths = []
        part_counts = []
        part_index = 0
        while True:
            part_index += 1
            part_path = os.path.join(temp_dir, f"_part_{part_index:03d}.{formato}")
            if formato == "csv":
                written = _write_csv_chunk(part_path, rows, split_threshold)
            else:
                workbook, written = _write_xlsx_chunk(part_path, rows, split_threshold)

            if written == 0 and part_index > 1:
                # Iterator esgotou exatamente no limiar da parte anterior
                # (ex.: total multiplo exato de split_threshold): esta parte
                # extra e vazia e espuria, nao um resultado real.
                if formato == "csv":
                    os.remove(part_path)
                else:
                    _close_abandoned_workbook(workbook)
                part_index -= 1
                break

            part_paths.append(part_path)
            part_counts.append(written)
            if formato == "xlsx":
                xlsx_parts.append((workbook, part_path))
            if written < split_threshold:
                break

        total = sum(part_counts)
        num_parts = len(part_paths)

        if formato == "xlsx":
            for index, (workbook, part_path) in enumerate(xlsx_parts, start=1):
                _finalize_xlsx_chunk(
                    workbook,
                    part_path,
                    part_index=index,
                    num_parts=num_parts,
                    total=total,
                    count=part_counts[index - 1],
                    generated_at=generated_at,
                    filters_label=filters_label,
                )

        if num_parts == 1:
            final_path = os.path.join(temp_dir, f"{base_name}.{formato}")
            os.replace(part_paths[0], final_path)
            return ExportFile(
                path=final_path,
                filename=os.path.basename(final_path),
                content_type=_CONTENT_TYPES[formato],
                temp_dir=temp_dir,
            )

        zip_path = os.path.join(temp_dir, f"{base_name}.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for index, part_path in enumerate(part_paths, start=1):
                arcname = f"{base_name}_parte{index:03d}de{num_parts:03d}.{formato}"
                archive.write(part_path, arcname=arcname)
        for part_path in part_paths:
            os.remove(part_path)

        return ExportFile(
            path=zip_path,
            filename=os.path.basename(zip_path),
            content_type=_ZIP_CONTENT_TYPE,
            temp_dir=temp_dir,
        )
    except Exception:
        # O arquivo ZIP de saida de uma falha durante `_finalize_xlsx_chunk`
        # ja e fechado explicitamente dentro de `_save_xlsx_workbook`
        # (traceback.clear_frames foi tentado antes e descartado por nao
        # alcancar exc.__cause__/exc.__context__ de uma excecao encadeada,
        # ver docstring de `_save_xlsx_workbook` em
        # core/services/allocations_export_service) — resta so fechar os
        # worksheets write-only ainda nao salvos.
        for pending_workbook, _pending_path in xlsx_parts:
            _close_abandoned_workbook(pending_workbook)
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def _stream_and_cleanup(path: str, temp_dir: str, block_size: int = _BLOCK_SIZE):
    """Gerador que serve o arquivo ja concluido e remove o diretorio
    temporario ao fim — consumo total, parcial ou desconexao do cliente
    APOS o primeiro chunk. Um generator so roda seu `finally` ao receber
    `.close()` se ja estiver suspenso em algum `yield`; se `.close()` for
    chamado ANTES de qualquer `next()`, o `finally` NAO executa — por isso
    o caminho "fechado antes do primeiro byte" e coberto por
    `_CleanupStreamingHttpResponse.close()`, nao por este generator (mesmo
    raciocinio documentado na correcao de REL-08-E)."""
    try:
        with open(path, "rb") as handle:
            while True:
                chunk = handle.read(block_size)
                if not chunk:
                    break
                yield chunk
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


class _CleanupStreamingHttpResponse(StreamingHttpResponse):
    """StreamingHttpResponse que garante a remocao do diretorio temporario
    em `close()`, inclusive quando a resposta e encerrada antes de qualquer
    iteracao. `close()` e metodo publico de HttpResponseBase, sempre
    chamado pelo servidor WSGI real ao final de toda resposta, independente
    de streaming_content ter sido consumido. Nao usa nenhum atributo
    privado do Django. Idempotente via flag propria."""

    def __init__(self, streaming_content, *, temp_dir: str, **kwargs):
        super().__init__(streaming_content, **kwargs)
        self._export_temp_dir = temp_dir
        self._export_temp_dir_cleaned = False

    def close(self):
        try:
            super().close()
        finally:
            self._cleanup_export_temp_dir()

    def _cleanup_export_temp_dir(self):
        if self._export_temp_dir_cleaned:
            return
        self._export_temp_dir_cleaned = True
        shutil.rmtree(self._export_temp_dir, ignore_errors=True)


def build_line_history_export_response(
    *,
    formato: str,
    filters: dict,
    split_threshold: int = EXPORT_SPLIT_THRESHOLD,
) -> StreamingHttpResponse:
    export = generate_line_history_export(
        formato=formato, filters=filters, split_threshold=split_threshold
    )
    response = _CleanupStreamingHttpResponse(
        _stream_and_cleanup(export.path, export.temp_dir),
        temp_dir=export.temp_dir,
        content_type=export.content_type,
    )
    response["Content-Disposition"] = f'attachment; filename="{export.filename}"'
    response["Cache-Control"] = "private, no-store"
    return response
