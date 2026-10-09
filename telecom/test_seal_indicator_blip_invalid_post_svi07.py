"""SVI-07 (revisão final do diff) — achado real P2: POST inválido no
formulário de edição de BlipConfiguration mostrava o número SUBMETIDO
(ainda não salvo) como se fosse o "Dado salvo", com o indicador de selo
da linha errada.

Causa confirmada: `BlipConfigurationUpdateView.get_context_data` lia
`self.object.phone_number`. `ModelForm.is_valid()` chama `_post_clean`,
que escreve os campos válidos da submissão na MESMA instância que é
`self.object` — mesmo quando outro campo (`value`, por exemplo) falha e
nada é persistido no banco. O GET-apos-POST-inválido (`form_invalid` →
`render_to_response` → `get_context_data`) lia então a seleção nova (B)
como se fosse o dado salvo, embora o banco continuasse com A.

Reprodução original desta rodada: `docs/superpowers/evidence/SVI-07/
final-diff-review-2026-10-09/review_probes.py::
test_invalid_post_preserves_saved_number` (preservado como artefato
histórico da revisão, não apagado). Este arquivo é a cobertura
permanente, com os cenários completos pedidos na correção.
"""

from datetime import date

import pytest
from django.urls import reverse
from django.utils import timezone

from telecom.models import BlipConfiguration
from telecom.test_seal_indicator_blip_selection_svi05 import (  # noqa: F401
    dev_client,
    two_authorized_blip_lines,
)

FROZEN_TODAY = date(2026, 9, 17)


@pytest.fixture
def saved_blip_config(two_authorized_blip_lines):
    line_a, _line_b = two_authorized_blip_lines
    return BlipConfiguration.objects.create(
        blip_id="BLIP-SVI07-INVALID-POST",
        type=BlipConfiguration.ConfigurationType.FLOW,
        description="Fluxo POST invalido",
        phone_number=int(line_a.phone_number),
        key=BlipConfiguration.KeyType.ACCESS,
        value="token-svi07-invalid-post",
    )


def _invalid_payload(line_b, blip_id="BLIP-SVI07-INVALID-POST"):
    # 'value' vazio: campo obrigatorio do form, torna o POST invalido sem
    # tocar phone_number — exatamente o cenario que expos o defeito (um
    # campo diferente falha, mas phone_number ja foi escrito na instancia
    # pelo _post_clean antes da falha geral ser determinada).
    return {
        "blip_id": blip_id,
        "type": BlipConfiguration.ConfigurationType.FLOW,
        "description": "Fluxo POST invalido",
        "phone_number": line_b.phone_number,
        "key": BlipConfiguration.KeyType.ACCESS,
        "value": "",
    }


def test_invalid_post_response_is_200_with_form_errors(
    dev_client, two_authorized_blip_lines, saved_blip_config
):
    """P2 · POST invalido nao redireciona; renderiza a mesma pagina com
    erros do formulario."""
    _user, client = dev_client
    _line_a, line_b = two_authorized_blip_lines
    update_url = reverse("telecom:blip_configuration_update", args=[saved_blip_config.pk])

    response = client.post(update_url, _invalid_payload(line_b))

    assert response.status_code == 200
    assert response.context["form"].errors


def test_invalid_post_form_retains_submitted_selection(
    dev_client, two_authorized_blip_lines, saved_blip_config
):
    """P2 · o formulario reexibido preserva a selecao B que o usuario
    submeteu, para ele poder corrigir o outro campo sem perder a escolha."""
    _user, client = dev_client
    _line_a, line_b = two_authorized_blip_lines
    update_url = reverse("telecom:blip_configuration_update", args=[saved_blip_config.pk])

    response = client.post(update_url, _invalid_payload(line_b))

    bound_value = response.context["form"]["phone_number"].value()
    assert str(bound_value) == str(line_b.phone_number)


def test_invalid_post_does_not_persist_submitted_selection(
    dev_client, two_authorized_blip_lines, saved_blip_config
):
    """P2 · nenhuma escrita ocorre como efeito do POST invalido — o banco
    continua com o numero original (A)."""
    _user, client = dev_client
    line_a, line_b = two_authorized_blip_lines
    update_url = reverse("telecom:blip_configuration_update", args=[saved_blip_config.pk])

    client.post(update_url, _invalid_payload(line_b))

    saved_blip_config.refresh_from_db()
    assert saved_blip_config.phone_number == int(line_a.phone_number)


def test_invalid_post_saved_block_shows_persisted_line_never_submitted_one(
    dev_client, two_authorized_blip_lines, saved_blip_config
):
    """P2 · garantia central: apos POST invalido, o bloco "Dado salvo" e o
    indicador mostram a linha PERSISTIDA (A) — nunca a selecao submetida
    e nao salva (B). Banco tambem continua A (nao gravado pela consulta)."""
    _user, client = dev_client
    line_a, line_b = two_authorized_blip_lines
    update_url = reverse("telecom:blip_configuration_update", args=[saved_blip_config.pk])

    response = client.post(update_url, _invalid_payload(line_b))

    saved_blip_config.refresh_from_db()
    assert saved_blip_config.phone_number == int(line_a.phone_number)

    assert response.context["saved_phone_number"] == int(line_a.phone_number)
    content = response.content.decode()
    assert f"Dado salvo: {int(line_a.phone_number)}" in content
    assert line_a.seal_status["label"] in content
    assert line_b.seal_status["label"] not in content


def test_valid_post_after_fixing_the_other_field_saves_the_new_selection(
    dev_client, two_authorized_blip_lines, saved_blip_config
):
    """P2 · fluxo feliz permanece intacto: corrigindo o campo que faltava,
    o POST salva B normalmente, e o GET seguinte mostra B como dado
    salvo."""
    _user, client = dev_client
    line_a, line_b = two_authorized_blip_lines
    update_url = reverse("telecom:blip_configuration_update", args=[saved_blip_config.pk])

    valid_payload = _invalid_payload(line_b)
    valid_payload["value"] = "token-corrigido"
    response = client.post(update_url, valid_payload)
    assert response.status_code == 302, response.context.get("form") and response.context["form"].errors

    saved_blip_config.refresh_from_db()
    assert saved_blip_config.phone_number == int(line_b.phone_number)

    after = client.get(update_url)
    after_content = after.content.decode()
    assert f"Dado salvo: {int(line_b.phone_number)}" in after_content
    assert line_b.seal_status["label"] in after_content
    assert line_a.seal_status["label"] not in after_content
