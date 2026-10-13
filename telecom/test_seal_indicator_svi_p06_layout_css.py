"""SVI-P06 — correcao dos 3 achados de disposicao visual da revisao
SVI-P02-P05 (modal I11, detalhamento diario, formularios). Fonte da
verdade: docs/superpowers/specs/2026-10-05-phone-line-seal-indicator-
design.md, secao "SVI-P06 — Achados de disposicao visual".

Inspecao estatica do CSS (nao requer navegador): prova que a solucao do
achado C (formularios) usa um wrapper dedicado (.seal-field-inline), sem
reduzir indevidamente o input, e que a solucao do achado B (detalhamento
diario) NAO usa os atalhos proibidos pelo plano aprovado
(flex-direction: row em .detail-list-item, order, row-reverse). A prova
de geometria real (indicador e numero realmente lado a lado, sem overflow)
fica para a validacao em navegador real (Playwright), registrada no
Compliance Report.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEAL_CSS_PATH = ROOT / "static" / "css" / "seal_indicator.css"
STYLES_CSS_PATH = ROOT / "static" / "css" / "styles.css"

FORM_TEMPLATES = [
    ROOT / "templates" / "allocations" / "allocation_edit.html",
    ROOT / "templates" / "telecom" / "phoneline_form.html",
]
BREAKDOWN_TEMPLATE = ROOT / "templates" / "dashboard" / "daily_indicator_day_breakdown.html"


def _text(path):
    return path.read_text(encoding="utf-8")


def _rule_block(css, selector):
    idx = css.index(selector)
    start = css.index("{", idx) + 1
    end = css.index("}", start)
    return css[start:end]


def test_seal_field_inline_wrapper_exists_and_is_a_flex_row():
    css = _text(STYLES_CSS_PATH) + _text(SEAL_CSS_PATH)
    assert ".seal-field-inline {" in css, (
        "wrapper dedicado para compor indicador + controle de formulario "
        "lado a lado nao encontrado"
    )
    block = _rule_block(css, ".seal-field-inline {")
    assert "display: flex" in block or "display:flex" in block
    assert "align-items" in block


def test_seal_field_inline_does_not_shrink_the_control_below_usable_width():
    """SVI-P06 (pendencia de foco, 2026-10-12): `min-width: 0` sem piso
    permitia que o indicador EXPANDIDO (foco revela o texto acessivel,
    SVI-07) espremesse o input para larguras inuteis (medido 26px em
    390/360px com o texto acessivel mais longo do dominio) — reproduzido
    em navegador real com Tab ate o proprio circulo (nao apenas foco no
    campo status), ver docs/superpowers/evidence/SVI-P06/focus_smoke.cjs.
    O input precisa de um PISO de largura utilizavel, nao min-width: 0."""
    css = _text(STYLES_CSS_PATH) + _text(SEAL_CSS_PATH)
    assert ".seal-field-inline .form-control" in css or ".seal-field-inline input" in css, (
        "regra que garante o input utilizavel (flex: 1, min-width com piso) nao encontrada"
    )
    selector = (
        ".seal-field-inline .form-control"
        if ".seal-field-inline .form-control" in css
        else ".seal-field-inline input"
    )
    block = _rule_block(css, selector + " {")
    assert re.search(r"flex\s*:\s*1", block), "input precisa crescer (flex: 1) no wrapper"
    min_width_match = re.search(r"min-width:\s*([0-9.]+)(px|rem|em)", block)
    assert min_width_match, "input precisa de um piso de largura minima (min-width > 0)"
    assert float(min_width_match.group(1)) > 0, (
        "min-width: 0 no input permite que o indicador expandido (foco) o esmague "
        "para uma largura inutil"
    )


def test_seal_field_inline_indicator_can_shrink_and_wrap_when_focus_expands_it():
    """O indicador precisa poder encolher (flex-shrink + min-width: 0) e
    quebrar linha internamente (herdado de `.seal-indicator:focus
    .visually-hidden { white-space: normal !important; }`, SVI-07) quando
    o texto revelado nao caberia inteiro sem espremer o input abaixo do
    piso garantido acima — sem isso, `flex: 0 0 auto` forcava o indicador
    a manter sua largura de conteudo cheia, tirando todo o espaco do
    input."""
    css = _text(STYLES_CSS_PATH) + _text(SEAL_CSS_PATH)
    assert ".seal-field-inline .seal-indicator" in css
    block = _rule_block(css, ".seal-field-inline .seal-indicator {")
    flex_match = re.search(r"flex:\s*(\d+)\s+(\d+)\s+auto", block)
    assert flex_match, "declaracao flex (grow shrink auto) do indicador nao encontrada"
    assert flex_match.group(2) != "0", (
        "flex-shrink 0 impede o indicador de ceder espaco ao input quando o "
        "texto revelado no foco cresce"
    )
    assert "min-width: 0" in block or "min-width:0" in block, (
        "sem min-width: 0 o indicador nao consegue encolher abaixo do seu "
        "conteudo, mesmo com flex-shrink"
    )


def test_seal_field_inline_wrapper_used_in_both_form_templates():
    for path in FORM_TEMPLATES:
        html = _text(path)
        assert '<div class="seal-field-inline">' in html, (
            f"{path.name}: wrapper .seal-field-inline nao encontrado envolvendo "
            "indicador + controle"
        )


def test_detail_list_item_keeps_column_direction_unchanged():
    """Guarda de regressao: o plano aprovado proibe aplicar
    flex-direction: row globalmente em .detail-list-item (isso afetaria
    nome/carteira/metadados de outras listas) — a correcao do achado B
    precisa usar um wrapper novo (.detail-list-line), nao mudar esta regra."""
    css = _text(STYLES_CSS_PATH)
    block = _rule_block(css, ".detail-list-item {")
    assert "flex-direction: column" in block


def test_breakdown_template_does_not_use_order_or_row_reverse_as_shortcut():
    html = _text(BREAKDOWN_TEMPLATE)
    assert "row-reverse" not in html
    assert re.search(r"\border\s*:", html) is None
