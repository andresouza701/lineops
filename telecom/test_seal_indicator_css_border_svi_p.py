"""SVI-P01b/P03 — decisao de borda registrada em docs/superpowers/specs/
2026-10-05-phone-line-seal-indicator-design.md ("Decisao adicional —
borda do circulo"): a borda do circulo passa a usar a MESMA variavel de
cor do preenchimento de cada estado, substituindo o contorno branco fixo
(`box-shadow: 0 0 0 1px rgba(248, 250, 252, ...)`) compartilhado entre
todos os estados. O anel de foco (outline, no wrapper) e um mecanismo CSS
distinto e precisa continuar existindo, sem depender de border/box-shadow
do dot.

Inspecao direta do arquivo fonte (static/css/seal_indicator.css) — nao
requer navegador: a regra e estrutural (qual propriedade/seletor existe),
nao uma medida de renderizacao (essa fica para a validacao em navegador
real, registrada em SVI-P04)."""

import re
from pathlib import Path

CSS_PATH = Path(__file__).resolve().parent.parent / "static" / "css" / "seal_indicator.css"

STATE_FILL_VARS = {
    "green": "--status-success",
    "yellow": "--status-warning",
    "orange": "--status-today",
    "red": "--status-danger",
}


def _css():
    return CSS_PATH.read_text(encoding="utf-8")


def _rule_block(css, selector):
    idx = css.index(selector)
    start = css.index("{", idx) + 1
    end = css.index("}", start)
    return css[start:end]


def test_dot_no_longer_has_the_shared_white_outline_box_shadow():
    css = _css()
    dot_block = _rule_block(css, ".seal-indicator__dot {")
    assert "rgba(248, 250, 252" not in dot_block, (
        "contorno branco compartilhado deveria ter sido removido do dot"
    )


def test_focus_ring_stays_on_wrapper_not_on_the_dot():
    css = _css()
    # O seletor de foco precisa continuar mirando o wrapper
    # (.seal-indicator), nao o .seal-indicator__dot — mecanismo distinto
    # de border/box-shadow do circulo.
    assert ".seal-indicator:focus {" in css
    focus_block = _rule_block(css, ".seal-indicator:focus {")
    assert "outline" in focus_block
    dot_block = _rule_block(css, ".seal-indicator__dot {")
    assert "outline" not in dot_block


def test_each_circle_state_border_uses_the_same_var_as_its_fill():
    css = _css()
    for state, fill_var in STATE_FILL_VARS.items():
        selector = f".seal-indicator--{state} .seal-indicator__dot {{"
        block = _rule_block(css, selector)
        assert fill_var in block, f"{state}: var de preenchimento {fill_var} ausente"
        assert "background-color" in block
        assert "border" in block, f"{state}: nenhuma propriedade border definida"
        # A MESMA var precisa aparecer tanto no valor de background-color
        # quanto no de border — nao uma cor fixa diferente/hardcoded.
        fill_value = re.search(
            rf"background-color:\s*([^;]+);", block
        ).group(1).strip()
        border_decl = re.search(r"border(?:-color)?:\s*([^;]+);", block)
        assert border_decl, f"{state}: declaracao de border nao encontrada"
        assert fill_var in border_decl.group(1), (
            f"{state}: border nao usa a mesma var do preenchimento ({fill_value!r})"
        )


def test_gray_states_border_also_uses_the_shared_fill_var():
    css = _css()
    selector = (
        ".seal-indicator--gray_not_activated .seal-indicator__dot,\n"
        ".seal-indicator--gray_inconsistent .seal-indicator__dot {"
    )
    idx = css.find(selector)
    assert idx != -1, "seletor combinado dos estados cinza nao encontrado (ou foi reformatado)"
    block = _rule_block(css, selector)
    assert "--status-neutral-dot" in block
    assert "border" in block
    border_decl = re.search(r"border(?:-color)?:\s*([^;]+);", block)
    assert border_decl and "--status-neutral-dot" in border_decl.group(1)
