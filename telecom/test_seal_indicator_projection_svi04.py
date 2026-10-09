"""SVI-04 — testes da projeção semântica compartilhada do indicador de
selo (camada de apresentação pura, sem integração de tela — isso é
SVI-05).

Fonte da verdade: docs/superpowers/specs/2026-10-05-phone-line-seal-
indicator-design.md, seção "SVI-04 — Contrato técnico, testes e
implementação". Testa telecom/seal_indicator.py::build_seal_indicator e a
preservação de compute_seal_status/classify_seal_expiry (telecom/
whatsapp_seal.py) após a extração feita nesta task.

Nenhum teste aqui usa a fixture `db`: build_seal_indicator não recebe
PhoneLine nem qualquer objeto de modelo, só valores primitivos — se o
código tentasse qualquer acesso a banco, pytest-django levantaria erro
por falta da fixture, o que por si só é evidência de ausência de
lookup oculto.
"""

from datetime import date

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from telecom.seal_indicator import SealIndicatorState, build_seal_indicator
from telecom.whatsapp_seal import classify_seal_expiry, compute_seal_status

FROZEN_TODAY = date(2026, 9, 17)


# --- fronteiras de dias, ambos os tipos de selo ---------------------------


@pytest.mark.parametrize("seal", ["META_ONE", "META_VERIFIED"])
@pytest.mark.parametrize(
    "days,expected_state",
    [
        (8, SealIndicatorState.GREEN),
        (7, SealIndicatorState.YELLOW),
        (1, SealIndicatorState.YELLOW),
        (0, SealIndicatorState.ORANGE),
        (-1, SealIndicatorState.RED),
    ],
)
def test_build_seal_indicator_classifies_active_line_by_expiry_boundary(
    monkeypatch, seal, days, expected_state
):
    from django.utils import timezone

    monkeypatch.setattr(timezone, "localdate", lambda: FROZEN_TODAY)
    expires_on = FROZEN_TODAY + __import__("datetime").timedelta(days=days)
    indicator = build_seal_indicator(
        identified=True,
        seal=seal,
        activation_status="ACTIVE",
        expires_on=expires_on,
        is_historical=False,
    )

    assert indicator.state == expected_state
    assert indicator.show_circle is True
    assert indicator.css_class == f"seal-indicator--{expected_state}"


# --- Não ativado distinto de inconsistente --------------------------------


def test_not_activated_valid_line_is_gray_not_activated_not_inconsistent():
    indicator = build_seal_indicator(
        identified=True,
        seal="META_VERIFIED",
        activation_status="NOT_ACTIVATED",
        expires_on=None,
    )
    assert indicator.state == SealIndicatorState.GRAY_NOT_ACTIVATED
    assert indicator.situation_label == "Não ativado"
    assert indicator.show_circle is True


def test_active_without_expiry_is_inconsistent_not_not_activated():
    indicator = build_seal_indicator(
        identified=True,
        seal="META_ONE",
        activation_status="ACTIVE",
        expires_on=None,
    )
    assert indicator.state == SealIndicatorState.GRAY_INCONSISTENT
    assert indicator.situation_label == "Situação do selo indisponível"
    assert indicator.situation_label != "Não ativado"


def test_unknown_activation_status_token_with_expiry_is_inconsistent_not_green():
    indicator = build_seal_indicator(
        identified=True,
        seal="META_ONE",
        activation_status="TOKEN_DESCONHECIDO",
        expires_on=date(2026, 9, 25),
    )
    assert indicator.state == SealIndicatorState.GRAY_INCONSISTENT
    assert indicator.state != SealIndicatorState.GREEN
    assert indicator.situation_label == "Situação do selo indisponível"


def test_unknown_seal_type_token_is_inconsistent_not_green_nor_crash():
    indicator = build_seal_indicator(
        identified=True,
        seal="TOKEN_DE_SELO_DESCONHECIDO",
        activation_status="ACTIVE",
        expires_on=date(2026, 9, 25),
    )
    assert indicator.state == SealIndicatorState.GRAY_INCONSISTENT
    assert indicator.seal_label == ""


# --- Sem selo distinto de linha não identificada --------------------------


def test_identified_line_without_seal_renders_nothing():
    indicator = build_seal_indicator(identified=True, seal="")
    assert indicator.state == SealIndicatorState.NO_SEAL
    assert indicator.show_circle is False
    assert indicator.render_nothing is True
    assert indicator.accessible_text == ""


def test_unidentified_line_shows_no_circle_and_unavailable_label():
    indicator = build_seal_indicator(identified=False)
    assert indicator.state == SealIndicatorState.UNIDENTIFIED
    assert indicator.show_circle is False
    assert indicator.render_nothing is False
    assert indicator.accessible_text == "Selo indisponível"


def test_unidentified_ignores_seal_payload_even_if_present():
    """Linha não identificada não deve herdar selo mesmo se, por engano,
    o chamador ainda passar seal/expires_on (ex.: snapshot com número
    igual ao de outra linha com selo) — identified=False sempre vence."""
    indicator = build_seal_indicator(
        identified=False,
        seal="META_ONE",
        activation_status="ACTIVE",
        expires_on=date(2026, 9, 25),
    )
    assert indicator.state == SealIndicatorState.UNIDENTIFIED
    assert indicator.accessible_text == "Selo indisponível"


def test_no_seal_and_unidentified_are_distinct_states():
    no_seal = build_seal_indicator(identified=True, seal="")
    unidentified = build_seal_indicator(identified=False)
    assert no_seal.state != unidentified.state
    assert no_seal.render_nothing is True
    assert unidentified.render_nothing is False


# --- Histórico descreve estado atual ---------------------------------------


def test_historical_identified_line_prefixes_description_with_current_seal():
    indicator = build_seal_indicator(
        identified=True,
        seal="META_ONE",
        activation_status="ACTIVE",
        expires_on=date(2026, 9, 25),
        is_historical=True,
    )
    assert indicator.accessible_text.startswith("Selo atual —")
    assert indicator.situation_label in indicator.accessible_text


def test_historical_flag_does_not_change_state_or_situation_only_description():
    live = build_seal_indicator(
        identified=True,
        seal="META_VERIFIED",
        activation_status="NOT_ACTIVATED",
        is_historical=False,
    )
    historical = build_seal_indicator(
        identified=True,
        seal="META_VERIFIED",
        activation_status="NOT_ACTIVATED",
        is_historical=True,
    )
    assert live.state == historical.state
    assert live.situation_label == historical.situation_label
    assert live.accessible_text != historical.accessible_text


def test_historical_unidentified_line_does_not_claim_current_seal():
    indicator = build_seal_indicator(identified=False, is_historical=True)
    assert indicator.state == SealIndicatorState.UNIDENTIFIED
    assert "Selo atual" not in indicator.accessible_text


# --- Saída serializável, sem dados financeiros/pessoais ---------------------


def test_as_dict_output_is_json_serializable_without_sensitive_fields():
    import json

    indicator = build_seal_indicator(
        identified=True,
        seal="META_ONE",
        activation_status="ACTIVE",
        expires_on=date(2026, 9, 25),
    )
    payload = indicator.as_dict()
    serialized = json.dumps(payload)

    lowered = serialized.lower()
    for forbidden in ("email", "payment", "pagamento", "valor", "monthly_value", "r$"):
        assert forbidden not in lowered
    assert set(payload.keys()) == {
        "state",
        "show_circle",
        "render_nothing",
        "seal_label",
        "situation_label",
        "accessible_text",
        "css_class",
    }


# --- Sem consulta oculta, sem escrita ---------------------------------------


def test_build_seal_indicator_costs_no_database_query(db):
    with CaptureQueriesContext(connection) as ctx:
        build_seal_indicator(
            identified=True,
            seal="META_ONE",
            activation_status="ACTIVE",
            expires_on=date(2026, 9, 25),
        )
    assert len(ctx) == 0


def test_build_seal_indicator_signature_has_no_phone_or_model_parameter():
    import inspect

    params = inspect.signature(build_seal_indicator).parameters
    for forbidden_name in ("phone_line", "phone_number", "instance", "line"):
        assert forbidden_name not in params


# --- Regressão: extração não alterou compute_seal_status/classify_seal_expiry


class TestComputeSealStatusRegressionAfterExtraction:
    """Prova que a extração de classify_seal_expiry não alterou nenhuma
    saída de compute_seal_status nas fronteiras aprovadas (SVI-01/02)."""

    def test_no_seal(self):
        assert compute_seal_status("", None) == {"tone": "neutral", "label": "Sem selo"}

    def test_not_activated_without_dates(self):
        assert compute_seal_status("META_ONE", None, "NOT_ACTIVATED") == {
            "tone": "neutral",
            "label": "Não ativado",
        }

    def test_active_without_expiry_is_legacy_not_activated_label(self):
        """Comportamento legado preservado: compute_seal_status (sem o
        contrato novo de SVI-04) continua tratando ACTIVE sem vencimento
        como "Não ativado" — é exatamente a lacuna que build_seal_indicator
        corrige na camada de apresentação, sem tocar esta função."""
        assert compute_seal_status("META_ONE", None, "ACTIVE") == {
            "tone": "neutral",
            "label": "Não ativado",
        }

    @pytest.mark.parametrize(
        "days,expected_tone,expected_label",
        [
            (8, "neutral", "Vence em 25/09/2026"),
            (7, "warning", "Vence em 7 dias"),
            (1, "warning", "Vence em 1 dia"),
            (0, "today", "Vence hoje"),
            (-1, "expired", "Vencido há 1 dia"),
        ],
    )
    def test_active_with_expiry_boundaries(self, monkeypatch, days, expected_tone, expected_label):
        from django.utils import timezone

        monkeypatch.setattr(timezone, "localdate", lambda: date(2026, 9, 17))
        expires_on = date(2026, 9, 17) + __import__("datetime").timedelta(days=days)
        result = compute_seal_status("META_ONE", expires_on, "ACTIVE")
        assert result["tone"] == expected_tone
        if days == 8:
            assert result["label"] == expected_label

    def test_classify_seal_expiry_matches_compute_seal_status_bucket_boundaries(self, monkeypatch):
        from django.utils import timezone

        monkeypatch.setattr(timezone, "localdate", lambda: date(2026, 9, 17))
        assert classify_seal_expiry(date(2026, 9, 25))["bucket"] == "ok"
        assert classify_seal_expiry(date(2026, 9, 24))["bucket"] == "warning"
        assert classify_seal_expiry(date(2026, 9, 18))["bucket"] == "warning"
        assert classify_seal_expiry(date(2026, 9, 17))["bucket"] == "today"
        assert classify_seal_expiry(date(2026, 9, 16))["bucket"] == "expired"
