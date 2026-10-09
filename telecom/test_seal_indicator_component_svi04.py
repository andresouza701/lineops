"""SVI-04 — testes do componente visual compartilhado do indicador de
selo, renderizado isoladamente (sem integrar nenhuma tela — SVI-05 fará
isso). Fonte da verdade: docs/superpowers/specs/2026-10-05-phone-line-
seal-indicator-design.md.

Renderiza telecom/_seal_indicator.html via django.template.Template a
partir de um SealIndicator construído diretamente (telecom/
seal_indicator.py), nunca via HTTP/view/página completa.
"""

from django.template import Context, Template

from telecom.seal_indicator import SealIndicator, SealIndicatorState, build_seal_indicator

TAG_SNIPPET = "{% load seal_indicator_tags %}{% seal_indicator indicator %}"


def _render(indicator):
    return Template(TAG_SNIPPET).render(Context({"indicator": indicator})).strip()


# --- estrutura e acessibilidade para estados com circulo -------------------


def test_green_indicator_renders_dot_with_accessible_name_and_visible_text():
    # Constrói o SealIndicator diretamente (estado GREEN fixo), sem
    # depender de nenhuma data real/congelada: este arquivo testa o
    # componente de renderização, não a classificação por vencimento
    # (coberta em telecom/test_seal_indicator_projection_svi04.py).
    indicator = SealIndicator(
        state=SealIndicatorState.GREEN,
        show_circle=True,
        render_nothing=False,
        seal_label="META ONE",
        situation_label="Vence em 25/09/2026",
        accessible_text="META ONE — Vence em 25/09/2026",
    )
    html = _render(indicator)

    assert 'class="seal-indicator seal-indicator--green"' in html
    assert 'seal-indicator__dot' in html
    assert f'aria-label="{indicator.accessible_text}"' in html
    assert f'title="{indicator.accessible_text}"' in html
    # Nao depende exclusivamente de title: ha tambem texto visivel para
    # leitor de tela, independente de foco/hover/toque.
    assert f'<span class="visually-hidden">{indicator.accessible_text}</span>' in html
    assert 'role="img"' in html
    assert 'tabindex="0"' in html


def test_component_does_not_depend_only_on_title_attribute():
    indicator = build_seal_indicator(
        identified=True,
        seal="META_VERIFIED",
        activation_status="NOT_ACTIVATED",
    )
    html = _render(indicator)
    html_without_title = html
    # Remove apenas o atributo title para simular leitura sem suporte a ele;
    # o texto acessivel ainda precisa estar presente por outro caminho.
    import re

    html_without_title = re.sub(r'\s*title="[^"]*"', "", html_without_title)
    assert indicator.accessible_text in html_without_title
    assert 'aria-label="' in html_without_title


def test_all_circle_states_use_single_source_css_class_from_state_name():
    import datetime

    cases = [
        build_seal_indicator(
            identified=True, seal="META_ONE", activation_status="ACTIVE",
            expires_on=datetime.date(2026, 9, 25),
        ),
        build_seal_indicator(identified=True, seal="META_VERIFIED", activation_status="NOT_ACTIVATED"),
        build_seal_indicator(identified=True, seal="META_ONE", activation_status="ACTIVE", expires_on=None),
    ]
    for indicator in cases:
        html = _render(indicator)
        assert f"seal-indicator--{indicator.state}" in html


# --- Sem selo distinto de linha nao identificada, em markup -----------------


def test_no_seal_renders_nothing():
    indicator = build_seal_indicator(identified=True, seal="")
    assert _render(indicator) == ""


def test_unidentified_renders_text_without_any_dot_element():
    indicator = build_seal_indicator(identified=False)
    html = _render(indicator)
    assert "Selo indisponível" in html
    assert "seal-indicator__dot" not in html
    assert 'seal-indicator seal-indicator--unidentified' in html


# --- Sem IDs duplicados ao renderizar varias vezes --------------------------


def test_rendering_the_component_twice_introduces_no_id_attributes():
    indicator = build_seal_indicator(
        identified=True,
        seal="META_ONE",
        activation_status="ACTIVE",
        expires_on=__import__("datetime").date(2026, 9, 25),
    )
    html_1 = _render(indicator)
    html_2 = _render(indicator)
    assert 'id="' not in html_1
    assert 'id="' not in html_2
    assert html_1 == html_2


# --- Escapamento seguro de conteudo textual ---------------------------------


def test_malicious_accessible_text_is_escaped_not_injected_as_html():
    malicious = SealIndicator(
        state=SealIndicatorState.GREEN,
        show_circle=True,
        render_nothing=False,
        seal_label="META_ONE",
        situation_label='"><script>alert(1)</script>',
        accessible_text='"><script>alert(1)</script>',
    )
    html = _render(malicious)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    # O caractere de aspas dentro do atributo precisa estar escapado para
    # nao fechar aria-label/title prematuramente.
    assert 'aria-label="&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;"' in html


# --- Componente so recebe o indicador, nunca telefone/HTML bruto ------------


def test_inclusion_tag_signature_takes_only_the_indicator():
    import inspect

    from telecom.templatetags.seal_indicator_tags import seal_indicator as tag_func

    params = list(inspect.signature(tag_func).parameters)
    assert params == ["indicator"]
