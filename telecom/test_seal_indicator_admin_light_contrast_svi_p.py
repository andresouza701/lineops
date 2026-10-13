"""SVI-P05 — correcao de contraste aprovada 2026-10-12: circulo do selo
no Django Admin em tema CLARO precisa de >=3:1 (WCAG 1.4.11) contra os
fundos reais do Admin (`--body-bg` #fff e `--darkened-bg` #f8f8f8).

Fonte da verdade: docs/superpowers/specs/2026-10-05-phone-line-seal-
indicator-design.md, secao "Correcao de contraste — circulo do selo no
Admin claro — 2026-10-12".

Nao basta procurar um hexadecimal novo no CSS: este arquivo CALCULA a
razao de contraste real (formula WCAG de luminancia relativa, mesma usada
em docs/superpowers/evidence/SVI-07/contrast_measure.cjs e
SVI-P04/smoke_round2.cjs) a partir das cores efetivamente declaradas no
CSS real da aplicacao (static/css/seal_indicator.css), e confere que a
regra esta corretamente ESCOPADA ao Admin claro (nunca ao app, nunca ao
Admin escuro) pela mesma logica real de tema do Django (venv/Lib/
site-packages/django/contrib/admin/static/admin/{css/dark_mode.css,
js/theme.js}): "efetivamente claro" = data-theme="light" OU
(data-theme="auto" E prefers-color-scheme nao e dark) — confirmado
empiricamente em docs/superpowers/evidence/SVI-P04/theme_probe.cjs.
"""

import re
from pathlib import Path

CSS_PATH = Path(__file__).resolve().parent.parent / "static" / "css" / "seal_indicator.css"
APP_BASE_TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "base" / "base.html"

WHITE = (255, 255, 255)
DARKENED_BG = (248, 248, 248)  # --darkened-bg real do Admin (linhas zebradas), pior caso

STATE_ORIGINAL_HEX = {
    "green": "#10b981",
    "yellow": "#f59e0b",
    "orange": "#ff8c00",
    "gray_not_activated": "#9aa5b1",
    "gray_inconsistent": "#9aa5b1",
    "red": "#ef4444",
}


def _css():
    return CSS_PATH.read_text(encoding="utf-8")


def _hex_to_rgb(hex_str):
    hex_str = hex_str.lstrip("#")
    return tuple(int(hex_str[i : i + 2], 16) for i in (0, 2, 4))


def _rel_luminance(rgb):
    def lin(c):
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _ratio(rgb1, rgb2):
    l1 = _rel_luminance(rgb1) + 0.05
    l2 = _rel_luminance(rgb2) + 0.05
    return max(l1, l2) / min(l1, l2)


def _rule_block(css, selector, start_from=0):
    idx = css.index(selector, start_from)
    start = css.index("{", idx) + 1
    end = css.index("}", start)
    return css[start:end], idx


def _resolve_color(css, block):
    """Extrai a cor efetiva de background-color num bloco de regra.

    Resolve var(--token) procurando primeiro uma DECLARACAO de --token em
    qualquer lugar do arquivo (:root ou a propria regra); se nao houver
    declaracao local (caso dos tokens --status-* deste arquivo, que so
    tem FALLBACK aqui — a declaracao real vive em styles.css, carregado
    so no app, nao no Admin isolado), usa o fallback explicito de
    var(--token, fallback) — nunca assume hex hardcoded sem passar pela
    variavel primeiro."""
    m = re.search(r"background-color:\s*([^;]+);", block)
    assert m, "background-color nao encontrado no bloco"
    value = m.group(1).strip()
    var_match = re.match(r"var\((--[\w-]+)(?:,\s*([^)]+))?\)", value)
    if var_match:
        token, fallback = var_match.group(1), var_match.group(2)
        token_decl = re.search(rf"(?<!,\s){re.escape(token)}:\s*(#[0-9a-fA-F]{{6}})\s*;", css)
        if token_decl:
            return token_decl.group(1)
        assert fallback, f"{token}: sem declaracao local E sem fallback em var()"
        hex_match = re.match(r"#[0-9a-fA-F]{6}", fallback.strip())
        assert hex_match, f"fallback de {token} nao e um hex reconhecivel: {fallback!r}"
        return hex_match.group(0)
    hex_match = re.match(r"#[0-9a-fA-F]{6}", value)
    assert hex_match, f"valor de cor nao reconhecido: {value!r}"
    return hex_match.group(0)


def _border_matches_background(block):
    bg = re.search(r"background-color:\s*([^;]+);", block).group(1).strip()
    border = re.search(r"border(?:-color)?:\s*([^;]+);", block)
    assert border, "nenhuma declaracao de border/border-color no bloco"
    border_value = border.group(1).strip()
    # "1px solid <cor>" ou so "<cor>" (border-color) — a COR precisa bater
    # com o valor de background-color, nao so a sintaxe.
    assert bg in border_value or border_value.endswith(bg), (
        f"border nao usa a mesma cor do preenchimento: bg={bg!r} border={border_value!r}"
    )


# --- App nunca define data-theme: premissa de que as regras abaixo sao
# inertes fora do Admin, verificada, nao presumida. ----------------------


def test_app_base_template_never_sets_data_theme_attribute():
    html = APP_BASE_TEMPLATE.read_text(encoding="utf-8")
    assert "data-theme" not in html, (
        "app principal passou a definir data-theme — as regras CSS escopadas por "
        "html[data-theme=...] deixariam de ser exclusivas do Admin"
    )


# --- Admin ESCURO e app: cores base continuam as mesmas (regressao) -----


def test_base_unscoped_rules_keep_original_colors_for_dark_contexts():
    """A regra SEM data-theme (usada pelo app e pelo Admin escuro) precisa
    continuar com os hex ORIGINAIS — esta correcao e so para Admin claro."""
    css = _css()
    for state, original_hex in STATE_ORIGINAL_HEX.items():
        if state == "gray_inconsistent":
            selector = ".seal-indicator--gray_inconsistent .seal-indicator__dot"
        else:
            selector = f".seal-indicator--{state} .seal-indicator__dot"
        # A primeira ocorrencia no arquivo precisa ser a regra BASE, sem
        # prefixo html[data-theme=...] antes dela na mesma regra.
        idx = css.index(selector)
        line_start = css.rindex("\n", 0, idx) + 1
        preceding_same_rule = css[line_start:idx]
        assert "data-theme" not in preceding_same_rule, (
            f"{state}: primeira ocorrencia de {selector!r} no arquivo already esta "
            "escopada por data-theme — a regra base precisa vir antes"
        )
        block, _ = _rule_block(css, selector)
        resolved = _resolve_color(css, block)
        assert resolved.lower() == original_hex.lower(), (
            f"{state}: cor base mudou ({resolved} != {original_hex}) — app/Admin escuro "
            "nao deveriam ser afetados por esta correcao"
        )


# --- Admin CLARO: contraste real >=3:1 para os 4 estados corrigidos -----


def test_admin_light_explicit_theme_has_scoped_rule_with_sufficient_contrast():
    css = _css()
    for state in ("green", "yellow", "orange", "gray_not_activated", "gray_inconsistent"):
        selector = f'html[data-theme="light"] .seal-indicator--{state} .seal-indicator__dot'
        assert selector in css, f"{state}: regra escopada a Admin claro (explicito) nao encontrada"
        block, _ = _rule_block(css, selector)
        resolved_hex = _resolve_color(css, block)
        rgb = _hex_to_rgb(resolved_hex)
        ratio_white = _ratio(rgb, WHITE)
        ratio_darkened = _ratio(rgb, DARKENED_BG)
        assert ratio_white >= 3.0, f"{state}: {ratio_white:.2f}:1 contra #fff, abaixo de 3:1"
        assert ratio_darkened >= 3.0, (
            f"{state}: {ratio_darkened:.2f}:1 contra #f8f8f8 (--darkened-bg), abaixo de 3:1"
        )
        _border_matches_background(block)


def test_admin_light_auto_theme_media_query_has_same_scoped_rule():
    """data-theme="auto" com preferencia CLARA (ou sem preferencia) precisa
    da MESMA correcao — nao so o data-theme="light" explicito."""
    css = _css()
    media_idx = css.index("@media (prefers-color-scheme: light)")
    media_end = css.index("}\n}", media_idx) + 3  # fecha @media (bloco interno + externo)
    media_block = css[media_idx:media_end]
    for state in ("green", "yellow", "orange", "gray_not_activated", "gray_inconsistent"):
        selector = f'html[data-theme="auto"] .seal-indicator--{state} .seal-indicator__dot'
        assert selector in media_block, (
            f"{state}: regra para data-theme=auto (efetivamente claro) nao encontrada "
            "dentro do @media (prefers-color-scheme: light)"
        )
        block, idx = _rule_block(media_block, selector)
        # Mesmo valor resolvido da regra explicita (fonte unica via var()).
        explicit_block, _ = _rule_block(css, f'html[data-theme="light"] .seal-indicator--{state} .seal-indicator__dot')
        assert _resolve_color(css, block) == _resolve_color(css, explicit_block), (
            f"{state}: cor de data-theme=auto (claro efetivo) diverge da cor de data-theme=light explicito"
        )
        _border_matches_background(block)


def test_admin_light_rule_is_never_unconditional_on_dark_theme():
    """Garante que a regra NAO vaza para data-theme="dark" (nem para o
    app, que nunca define data-theme) — a correcao e so do claro."""
    css = _css()
    assert 'html[data-theme="dark"] .seal-indicator--green' not in css
    assert 'html[data-theme="dark"] .seal-indicator--yellow' not in css
    assert 'html[data-theme="dark"] .seal-indicator--orange' not in css
    assert 'html[data-theme="dark"] .seal-indicator--gray_not_activated' not in css


def test_red_state_keeps_original_color_no_new_admin_light_rule():
    """Vermelho ja passava (3.76:1) — instrucao explicita: nao criar regra
    nova para ele."""
    css = _css()
    assert 'html[data-theme="light"] .seal-indicator--red' not in css
    assert 'html[data-theme="auto"] .seal-indicator--red' not in css


def test_gray_not_activated_and_gray_inconsistent_share_the_same_admin_light_color():
    """Fonte unica: os dois estados cinza continuam resolvendo para a
    MESMA cor no Admin claro, como ja faziam na regra base (mesma
    var(--status-neutral-dot) la, mesmo valor aqui)."""
    css = _css()
    block_a, _ = _rule_block(css, 'html[data-theme="light"] .seal-indicator--gray_not_activated .seal-indicator__dot')
    block_b, _ = _rule_block(css, 'html[data-theme="light"] .seal-indicator--gray_inconsistent .seal-indicator__dot')
    assert _resolve_color(css, block_a) == _resolve_color(css, block_b)
