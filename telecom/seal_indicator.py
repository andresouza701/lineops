"""Projeção semântica compartilhada do indicador visual de selo (SVI-04).

Fonte da verdade: docs/superpowers/specs/2026-10-05-phone-line-seal-
indicator-design.md, seção "SVI-04 — Contrato técnico, testes e
implementação". Camada de apresentação pura: recebe dados já carregados
pelo chamador (nenhum lookup por telefone, nenhuma consulta, nenhuma
escrita) e devolve um objeto serializável com o estado semântico, o texto
acessível e a classe CSS a aplicar. Reaproveita classify_seal_expiry
(telecom/whatsapp_seal.py) para a fronteira de dias e compute_seal_status
para o texto de situação já aprovado — não recalcula nem retraduz nenhuma
das duas coisas.

Nomes de teste de SVI-03 (seal_status, badge, seal-tone-*) não são
requisitos de produto: este módulo e seus nomes são independentes daquele
código legado, que permanece intocado.
"""

from dataclasses import dataclass

from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

from telecom.whatsapp_seal import (
    WhatsAppSeal,
    WhatsAppSealActivationStatus,
    classify_seal_expiry,
    compute_seal_status,
)

UNAVAILABLE_LABEL = "Selo indisponível"
INCONSISTENT_LABEL = "Situação do selo indisponível"
CURRENT_SEAL_PREFIX = "Selo atual"


class SealIndicatorState:
    """Estados semânticos finais do indicador (regras aprovadas em
    docs/superpowers/specs/2026-10-05-..., seção de fechamento SVI-02).
    O valor de cada estado é, por design, também o sufixo da classe CSS
    (ver _seal_indicator.html) — fonte única, sem mapa de tradução
    duplicado entre Python e CSS."""

    GREEN = "green"
    YELLOW = "yellow"
    ORANGE = "orange"
    RED = "red"
    GRAY_NOT_ACTIVATED = "gray_not_activated"
    GRAY_INCONSISTENT = "gray_inconsistent"
    NO_SEAL = "no_seal"
    UNIDENTIFIED = "unidentified"

    CIRCLE_STATES = frozenset(
        {GREEN, YELLOW, ORANGE, RED, GRAY_NOT_ACTIVATED, GRAY_INCONSISTENT}
    )


_STATE_BY_EXPIRY_BUCKET = {
    "ok": SealIndicatorState.GREEN,
    "warning": SealIndicatorState.YELLOW,
    "today": SealIndicatorState.ORANGE,
    "expired": SealIndicatorState.RED,
}


@dataclass(frozen=True)
class SealIndicator:
    """Saída serializável da projeção. Nunca carrega e-mail, forma de
    pagamento ou valor financeiro — apenas os campos abaixo, todos texto
    simples ou booleano."""

    state: str
    show_circle: bool
    render_nothing: bool
    seal_label: str
    situation_label: str
    accessible_text: str

    @property
    def css_class(self):
        return f"seal-indicator--{self.state}"

    def as_dict(self):
        return {
            "state": self.state,
            "show_circle": self.show_circle,
            "render_nothing": self.render_nothing,
            "seal_label": self.seal_label,
            "situation_label": self.situation_label,
            "accessible_text": self.accessible_text,
            "css_class": self.css_class,
        }


def _accessible_text(seal_label, situation_label, is_historical):
    text = f"{seal_label} — {situation_label}" if seal_label else situation_label
    if is_historical:
        text = f"{CURRENT_SEAL_PREFIX} — {text}"
    return text


def _circle_indicator(state, seal_label, situation_label, is_historical):
    return SealIndicator(
        state=state,
        show_circle=True,
        render_nothing=False,
        seal_label=seal_label,
        situation_label=situation_label,
        accessible_text=_accessible_text(seal_label, situation_label, is_historical),
    )


def _unidentified_indicator():
    return SealIndicator(
        state=SealIndicatorState.UNIDENTIFIED,
        show_circle=False,
        render_nothing=False,
        seal_label="",
        situation_label=UNAVAILABLE_LABEL,
        accessible_text=UNAVAILABLE_LABEL,
    )


def _no_seal_indicator():
    return SealIndicator(
        state=SealIndicatorState.NO_SEAL,
        show_circle=False,
        render_nothing=True,
        seal_label="",
        situation_label="",
        accessible_text="",
    )


def build_seal_indicator(
    *, identified, seal="", activation_status="", expires_on=None, is_historical=False
):
    """Projeção pura. Nenhum parâmetro é um objeto de modelo: todas as
    entradas são explícitas (bool/str/date), para impedir lookup oculto e
    deixar a função testável sem banco de dados.

    - identified=False: linha não identificada/resolvível (snapshot sem
      FK, BLIP sem correspondência exata/única/autorizada, etc.) — nenhum
      círculo, "Selo indisponível". Demais parâmetros são ignorados.
    - seal vazio (linha identificada): Sem selo — nenhum círculo, nenhum
      texto (render_nothing=True); quem chama mantém seu próprio texto
      "Sem selo" já existente, sem duplicação.
    - activation_status != ACTIVE e != NOT_ACTIVATED (inclui token
      desconhecido, ou ACTIVE sem expires_on): dados inconsistentes —
      cinza, "Situação do selo indisponível". Nunca verde por fallback.
    - is_historical=True e identified=True: antepõe "Selo atual" ao texto
      acessível, para o indicador nunca ser lido como estado no instante
      do evento histórico.
    """
    if not identified:
        return _unidentified_indicator()

    seal = seal or ""
    activation_status = activation_status or ""

    if not seal:
        return _no_seal_indicator()

    try:
        seal_label = WhatsAppSeal(seal).label
    except ValueError:
        # Token de tipo de selo desconhecido: mesma política de dados
        # inconsistentes do token de situação desconhecido — nunca cinza
        # "Não ativado" nem verde por fallback.
        return _circle_indicator(
            SealIndicatorState.GRAY_INCONSISTENT, "", INCONSISTENT_LABEL, is_historical
        )

    if activation_status == WhatsAppSealActivationStatus.NOT_ACTIVATED:
        situation_label = compute_seal_status(seal, None, activation_status)["label"]
        return _circle_indicator(
            SealIndicatorState.GRAY_NOT_ACTIVATED, seal_label, situation_label, is_historical
        )

    if activation_status != WhatsAppSealActivationStatus.ACTIVE or not expires_on:
        return _circle_indicator(
            SealIndicatorState.GRAY_INCONSISTENT, seal_label, INCONSISTENT_LABEL, is_historical
        )

    bucket = classify_seal_expiry(expires_on)["bucket"]
    state = _STATE_BY_EXPIRY_BUCKET[bucket]
    situation_label = compute_seal_status(seal, expires_on, activation_status)["label"]
    return _circle_indicator(state, seal_label, situation_label, is_historical)


def seal_indicator_for_phone_line(phone_line, *, is_historical=False):
    """Adaptador de integração (SVI-05): único ponto que lê campos de selo
    de uma instância de PhoneLine já carregada (nenhum atravessamento de
    FK, nenhuma consulta) e delega a build_seal_indicator. phone_line=None
    (número sem linha resolvível — snapshot sem FK, BLIP sem
    correspondência exata/única/autorizada) sempre devolve o indicador
    "unidentified", sem inspecionar nenhum outro campo."""
    if phone_line is None:
        return build_seal_indicator(identified=False)
    return build_seal_indicator(
        identified=True,
        seal=phone_line.whatsapp_seal,
        activation_status=phone_line.whatsapp_seal_activation_status,
        expires_on=phone_line.whatsapp_seal_expires_on,
        is_historical=is_historical,
    )


def render_seal_indicator_html(phone_line, *, is_historical=False):
    """Renderiza o componente compartilhado (telecom/_seal_indicator.html)
    como SafeString, para contextos fora do motor de template padrao (ex.:
    métodos de list_display do Django Admin, I25-I28). Mesma projeção de
    seal_indicator_for_phone_line — nenhuma regra nova."""
    return mark_safe(
        render_to_string(
            "telecom/_seal_indicator.html",
            {"indicator": seal_indicator_for_phone_line(phone_line, is_historical=is_historical)},
        )
    )
