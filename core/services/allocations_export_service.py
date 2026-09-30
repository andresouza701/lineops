"""Exportacao CSV/XLSX/ZIP do relatorio Alocacoes (REL-10-E).

Fonte da verdade: docs/superpowers/specs/2026-09-22-reports-hub-design.md,
secoes REL-07 (contrato comum) e REL-10-C (contrato especifico). Reaproveita
o motor de consulta de REL-10-Q (core/services/allocations_report_service):
mesmo escopo, filtros, ordenacao e projecao de linhas — nenhuma regra e
copiada em outro queryset.

Exportador PROPRIO de Alocacoes, nao uma generalizacao dos exportadores de
Selos WhatsApp (core/services/report_export_service.py) ou Inventario
(core/services/line_inventory_export_service.py): mesmo padrao arquitetural
(streaming + limpeza de temporarios + divisao em ZIP + protecao de formula),
mas com seu proprio COLUMNS/slug/row-mapping, deliberadamente duplicado em
vez de importado/generalizado, mesma decisao ja registrada em REL-09-C ("nao
generalizar o modulo existente nesta task"). Somente leitura: nenhuma
escrita de negocio, model ou migration.
"""

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

from core.services.allocations_report_service import (
    AllocationsReportRow,
    iter_allocations_report_rows,
)

# Limiar de producao (REL-07/REL-10-C): ate este numero de linhas de dados
# por arquivo; acima, ZIP com partes numeradas. Testes de fronteira usam o
# parametro `split_threshold` das funcoes abaixo para reduzir o limiar sem
# tocar este valor de producao.
EXPORT_SPLIT_THRESHOLD = 100_000

COLUMNS = [
    "Linha",
    "Usuário vinculado",
    "Carteira",
    "Data de alocação",
    "Data de liberação",
    "Situação",
    "Registro da linha",
    "Funcionário excluído",
]

_DATE_COLUMNS = (False, False, False, True, True, False, False, False)

_CONTENT_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
_ZIP_CONTENT_TYPE = "application/zip"

_BLOCK_SIZE = 65536

_LEADING_WS_CONTROL = re.compile(r"^[\s\x00-\x1f]+")
_FORMULA_TRIGGERS = ("=", "+", "-", "@")

_SLUG = "alocacoes"

_SITUACAO_ALOCACAO_LABELS = {"": "Todas", "ativa": "Ativa", "liberada": "Liberada"}


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


def _row_to_csv_cells(row: AllocationsReportRow) -> list:
    return [
        _csv_text(row.phone_number),
        _csv_text(row.employee_full_name),
        _csv_text(row.employee_id),
        row.allocated_at.strftime("%d/%m/%Y") if row.allocated_at else "",
        row.released_at.strftime("%d/%m/%Y") if row.released_at else "",
        _csv_text(row.situacao_label),
        _csv_text(row.registro_label),
        _csv_text(row.funcionario_excluido_label),
    ]


def _row_to_xlsx_cells(worksheet, row: AllocationsReportRow) -> list:
    values = [
        row.phone_number,
        row.employee_full_name,
        row.employee_id,
        row.allocated_at,
        row.released_at,
        row.situacao_label,
        row.registro_label,
        row.funcionario_excluido_label,
    ]
    cells = []
    for value, is_date in zip(values, _DATE_COLUMNS):
        if is_date:
            if value is None:
                cells.append(None)
            else:
                cell = WriteOnlyCell(worksheet, value=value)
                cell.number_format = "DD/MM/YYYY"
                cells.append(cell)
        elif isinstance(value, str) and _looks_like_formula(value):
            # openpyxl infere data_type='f' (formula) para qualquer string
            # iniciada por =/+/-/@ atribuida diretamente a uma celula — o
            # contrato (REL-07) exige texto puro, nunca formula, no XLSX.
            # Forcar data_type='s' apos a construcao (nao no `value=` do
            # construtor, que reexecuta a mesma inferencia) grava a string
            # literal sem interpretacao.
            cell = WriteOnlyCell(worksheet, value=value)
            cell.data_type = "s"
            cells.append(cell)
        else:
            cells.append(value)
    return cells


def _filters_label(filters: dict) -> str:
    return (
        f"Período: {filters['data_inicial'].strftime('%d/%m/%Y')} a "
        f"{filters['data_final'].strftime('%d/%m/%Y')}; "
        f"Situação da alocação: "
        f"{_SITUACAO_ALOCACAO_LABELS.get(filters.get('situacao_alocacao', ''), filters.get('situacao_alocacao', ''))}; "
        f"Funcionário: {filters.get('funcionario') or '(vazio)'}; "
        f"Linha: {filters.get('linha') or '(vazio)'}; "
        f"Incluir excluídos: {'Sim' if filters.get('incluir_excluidos') else 'Não'}"
    )


def _write_csv_chunk(path: str, rows: Iterator[AllocationsReportRow], threshold: int) -> int:
    """Escreve ate `threshold` linhas do MESMO iterator (uma unica consulta
    para toda a exportacao) e retorna quantas linhas foram efetivamente
    escritas. `written < threshold` sinaliza iterator esgotado — usado pelo
    chamador para decidir se ha mais partes, sem depender de nenhuma
    contagem calculada antes da iteracao (mesmo padrao corrigido em
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
    """Fecha um workbook write-only abandonado antes de `save()`.
    `Workbook.close()` sozinho so fecha o arquivo do archive, sem finalizar
    o generator interno (`_write_rows`) de cada worksheet que ja recebeu
    `.append()` — deixando-o suspenso ate o GC eventual fecha-lo fora de
    ordem, emitindo 'ValueError: I/O operation on closed file' como warning
    nao tratado. Fechar cada worksheet primeiro (o header via `.append()`
    garante que o generator sempre existe) evita esse leak.

    `sheet.close()` sozinho tambem NAO remove o arquivo temporario interno
    do openpyxl (`sheet._writer.out`, criado por
    `openpyxl.worksheet._writer.create_temporary_file` com prefixo
    "openpyxl." e registrado em `ALL_TEMP_FILES`): esse arquivo so e
    removido quando `WorksheetWriter.cleanup()` roda — o que openpyxl faz
    sozinho apenas dentro de `ExcelWriter.write_worksheet` (fluxo normal de
    `workbook.save()`, nunca alcancado quando o workbook e abandonado antes
    de salvar). Sem chamar `cleanup()` aqui, esse XML fica no disco ate o
    `atexit` do proprio openpyxl (REPORTS_SENIOR_REVIEW achado 2: XML de
    927 bytes para workbook vazio, 34.208 bytes apos uma linha escrita) —
    inaceitavel num worker persistente, que so encerra o processo no
    deploy. `writer.cleanup()` e API publica do proprio openpyxl (mesma
    chamada que `ExcelWriter.write_worksheet` faz no fluxo normal); o
    unico jeito de alcanca-la antes de `save()` e via `sheet._writer`, sem
    equivalente publico na `WriteOnlyWorksheet` — por isso encapsulado
    aqui, com teste dedicado de ausencia de arquivo residual (nao apenas
    ausencia de warning)."""
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


def _write_xlsx_chunk(path: str, rows: Iterator[AllocationsReportRow], threshold: int):
    """Mesmo contrato de `_write_csv_chunk`, mas para XLSX: os dados sao
    escritos de imediato (write-only, sem materializar linhas em memoria),
    porem a planilha "Contexto" (que depende do total/numero de partes,
    conhecidos somente apos esgotar o iterator inteiro) e adicionada depois
    por `_finalize_xlsx_chunk` — o workbook so e salvo nesse momento."""
    workbook = openpyxl.Workbook(write_only=True)
    sheet = workbook.create_sheet("Alocações")
    sheet.append(COLUMNS)
    written = 0
    try:
        for row in itertools.islice(rows, threshold):
            sheet.append(_row_to_xlsx_cells(sheet, row))
            written += 1
    except Exception:
        # Sem isto, uma falha no meio do iterator (ex.: erro de banco)
        # abandona o worksheet write-only com seu generator interno
        # suspenso; o GC eventual o fecha fora de ordem e emite
        # "ValueError: I/O operation on closed file" como warning nao
        # tratado, em vez de liberar o recurso aqui, de forma limpa.
        _close_abandoned_workbook(workbook)
        raise
    return workbook, written


def _save_xlsx_workbook(workbook, path: str) -> None:
    """Salva `workbook` em `path` sendo dono explicito do arquivo ZIP de
    saida — nao apenas `workbook.save(path)`.

    `Workbook.save(path)` delega a `openpyxl.writer.excel.save_workbook`,
    que abre o `zipfile.ZipFile` de destino como variavel LOCAL dessa
    funcao (`archive = ZipFile(path, 'w', ...)`) e so o fecha
    (`archive.close()`) na linha seguinte a que grava cada worksheet — se
    essa gravacao falhar (ex.: erro de I/O real, `OSError` do SO
    encadeado por um `RuntimeError` mais especifico via `raise ... from`),
    `archive.close()` nunca roda, e o handle do arquivo fica aberto. Duas
    tentativas anteriores de corrigir isso foram descartadas:

    1. `traceback.clear_frames` (limpar as variaveis locais da frame que
       prende o `archive`): INSUFICIENTE contra excecao ENCADEADA
       (`raise Y from X`) — `clear_frames` so percorre `tb.tb_next` da
       excecao fornecida, nunca `exc.__cause__`/`exc.__context__`, entao
       `X` mantem `archive` vivo fora do alcance de
       `clear_frames(Y.__traceback__)`. Depender de refcount/GC tambem
       falha: o momento do GC nao e garantido, e o Windows bloqueia a
       remocao de um arquivo com handle aberto.

    2. Fechar `archive.fp` diretamente e marca-lo `None`, SEM chamar
       `archive.close()` de verdade — a justificativa era evitar que
       `close()` escrevesse o registro de encerramento do ZIP a partir de
       `self.filelist` PARCIAL, produzindo um arquivo "aparentemente
       completo" e violando REL-07 ("nunca entregar arquivo... parcial
       apos falha"). Essa justificativa confundia FECHAR o recurso com
       ENTREGAR o recurso: fechar o ZIP (mesmo truncado) nao o entrega a
       ninguem. A entrega HTTP ja e impedida por dois mecanismos
       estruturais independentes de como o handle e fechado — esta
       excecao se propaga por `_finalize_xlsx_chunk` ate o `except`
       externo de `generate_allocations_export`, que (a) nunca retorna
       `ExportFile`, entao `build_allocations_export_response` nunca roda
       nem inicia streaming, e (b) remove `temp_dir` inteiro (arquivo
       parcial incluido) via `shutil.rmtree` antes de relancar. Manipular
       `archive.fp` (sem sublinhado, mas tambem sem contrato publico
       documentado) era estado interno do `ZipFile` alterado sem
       necessidade comprovada.

    Correcao atual: construir o `ZipFile` de destino AQUI, como variavel
    local desta funcao (nao de uma funcao interna do openpyxl),
    reaproveitando `openpyxl.writer.excel.ExcelWriter` (a mesma classe que
    `save_workbook` usa por baixo) — isso da posse explicita do arquivo.
    `ExcelWriter` e importavel sem sublinhado, mas NAO e um contrato
    publico estavel/documentado do openpyxl (a documentacao oficial
    ensina `Workbook.save(path)`, nunca instanciar `ExcelWriter`
    diretamente) — e uma dependencia da estrutura INTERNA da versao
    instalada (`openpyxl==3.1.5`, pinado em `requirements.txt`, nao
    `>=`); uma atualizacao de versao pode mudar sua assinatura sem aviso
    de breaking change formal. Por isso `_save_xlsx_workbook` tambem
    replica manualmente o efeito colateral de `workbook.properties.modified`
    que `save_workbook` faria por nos (ver abaixo) — usar `ExcelWriter`
    direto significa reproduzir TODO efeito colateral relevante que
    `save_workbook` faria, nao so a escrita dos dados. Em caso de
    excecao durante `writer.save()`, o fechamento usa
    `archive.close()` NORMAL (metodo publico e documentado do proprio
    `zipfile`), nao manipulacao de `fp`. Isso e seguro mesmo com escrita
    parcial: `ZipFile.write()` so adiciona uma entrada a `self.filelist`
    APOS gravar seu conteudo com sucesso, entao uma falha no meio de
    `write()` deixa `self.filelist` consistente — so com as entradas ja
    bem-sucedidas — e `close()` grava o registro de encerramento a partir
    dele sem reexecutar a escrita que falhou. Provado empiricamente (mock
    de `ZipFile.write` levantando excecao, seguido de `close()` real):
    `close()` completa sem erro e o arquivo resultante e removivel por
    `shutil.rmtree` no mesmo processo — a unica coisa que o handle aberto
    bloqueava no Windows.

    Falha SECUNDARIA durante este `close()` de limpeza (ex.: disco cheio
    de verdade, handle ja invalido por outro motivo) NAO deve substituir
    a excecao ORIGINAL que motivou a limpeza — por isso e engolida aqui,
    apenas neste ponto estreito e documentado (nao um `except: pass`
    generico de limpeza espalhado pelo modulo). A excecao original (tipo,
    mensagem, `__cause__`, `__context__`, traceback) nunca e tocada —
    apenas relancada (`raise` sem argumento).

    `workbook.properties.modified` e atualizado aqui porque
    `Workbook.save(path)` (API publica) tambem o faz via `save_workbook`
    logo antes de escrever — comportamento preservado mesmo chamando
    `ExcelWriter` diretamente em vez de `save_workbook`. Nao ha `close()`
    explicito no caminho de SUCESSO desta funcao: `ExcelWriter.save()` ja
    chama `self._archive.close()` internamente ao terminar (mesmo
    contrato de `save_workbook`)."""
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
    context_sheet.append(["Relatório", "Alocações"])
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


def generate_allocations_export(
    *,
    formato: str,
    filters: dict,
    split_threshold: int = EXPORT_SPLIT_THRESHOLD,
) -> ExportFile:
    """Gera o(s) arquivo(s) completo(s) do relatorio Alocacoes em arquivos
    temporarios privados, ANTES de qualquer resposta HTTP ser iniciada (sem
    envio parcial). `split_threshold` e a interface tecnica explicita de
    teste para a fronteira de divisao/ZIP — a rota HTTP nunca o passa,
    mantendo producao em EXPORT_SPLIT_THRESHOLD (100.000).

    Uma UNICA consulta ao banco (o iterator de
    `iter_allocations_report_rows`) dirige toda a divisao em partes: nao ha
    `count()` previo separado. Total, numero de partes e quantidade por
    parte sao derivados do que efetivamente foi escrito, nunca de uma
    contagem calculada antes da iteracao — mesmo raciocinio da correcao de
    risco documentada em REL-08-E (duas consultas independentes podem
    divergir por mudanca de dados entre elas)."""
    if formato not in _CONTENT_TYPES:
        raise ValueError(f"Formato de exportacao desconhecido: {formato}")

    generated_at = timezone.now()

    temp_dir = tempfile.mkdtemp(prefix="lineops_allocations_export_")
    # Declarado ANTES do try: se uma excecao ocorrer antes/durante o
    # preenchimento desta lista, o except abaixo ainda precisa fecha-la
    # (workbooks write-only ja criados e ainda nao salvos nao podem ficar
    # para o GC fechar fora de ordem).
    xlsx_parts = []  # (workbook, path) — save() adiado ate total/num_parts conhecidos
    try:
        rows = iter_allocations_report_rows(**filters)

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
        # Cada workbook write-only pendente e fechado individualmente
        # (nunca `ALL_TEMP_FILES`/`openpyxl.*` globalmente) — o arquivo
        # ZIP de saida de uma falha durante `_finalize_xlsx_chunk` ja e
        # fechado explicitamente dentro de `_save_xlsx_workbook` (ver seu
        # docstring: `traceback.clear_frames` foi tentado antes e
        # descartado por nao alcancar `exc.__cause__`/`exc.__context__` de
        # uma excecao encadeada) — nao ha nada pendente a fechar aqui
        # alem dos worksheets write-only ainda nao salvos.
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


def build_allocations_export_response(
    *,
    formato: str,
    filters: dict,
    split_threshold: int = EXPORT_SPLIT_THRESHOLD,
) -> StreamingHttpResponse:
    export = generate_allocations_export(
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
