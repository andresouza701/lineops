"""Conferência corretiva SVI-05 — I24 (BlipConfigurationForm), fechamento
SVI-02 regra 3: "Se exibir dado salvo, mostrar explicitamente o número A e
sua condição de dado salvo em bloco distinto da seleção."

Fonte da verdade: docs/superpowers/specs/2026-10-05-phone-line-seal-
indicator-design.md.

A entrega anterior de SVI-05 renderizava o indicador IMEDIATAMENTE depois
do `<select>` de phone_number, sem nenhum texto explicitando qual número
(A) ele descreve e sem nenhum bloco visualmente distinto da seleção. Um
usuário trocando a seleção no navegador antes de salvar (B) veria o select
exibindo B enquanto o círculo estático ao lado (de A, dado salvo) parece
pertencer à opção corrente exibida — exatamente o resultado que a borda
aprovada proíbe. `telecom/test_seal_indicator_blip_selection_svi05.py`
nunca testou esse cenário porque o Django test client não simula troca de
`<select>` no navegador antes do POST; só prova o par GET(A)->POST(B)->GET(B).

Este arquivo prova, por inspeção de estrutura HTML (sem navegador, já que
o requisito é estrutural: existência de um bloco textual distinto, não
comportamento de JS), que o número A aparece em texto explícito FORA do
`<select>`, junto com seu indicador, em um elemento separado — nunca dentro
do próprio `<select>`/`<option>`.
"""

import re
from datetime import date

import pytest
from django.urls import reverse
from django.utils import timezone

from telecom.models import BlipConfiguration, PhoneLine, SIMcard
from users.models import SystemUser

PASSWORD = "StrongPass123"
FROZEN_TODAY = date(2026, 9, 17)


@pytest.fixture
def dev_client(client, db):
    user = SystemUser.objects.create_user(
        email="svi05-blip-dev-block@example.com", password=PASSWORD, role=SystemUser.Role.DEV
    )
    client.force_login(user)
    return user, client


@pytest.fixture
def authorized_blip_line(monkeypatch):
    monkeypatch.setattr(timezone, "localdate", lambda: FROZEN_TODAY)
    sim = SIMcard.objects.create(iccid="8900000000000099101", carrier="TIM")
    return PhoneLine.objects.create(
        phone_number="+5511999999101",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        origem=PhoneLine.Origem.BLIP,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=date(2026, 8, 1),
        whatsapp_seal_expires_on=date(2026, 9, 25),
        whatsapp_seal_email="blocka@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )


def _select_block(html):
    match = re.search(r"<select[^>]*name=\"phone_number\"[^>]*>.*?</select>", html, re.DOTALL)
    assert match, "select de phone_number não encontrado"
    return match.group(0)


def test_blip_form_update_shows_saved_number_and_indicator_in_block_distinct_from_select(
    dev_client, authorized_blip_line
):
    _user, client = dev_client
    line = authorized_blip_line
    config = BlipConfiguration.objects.create(
        blip_id="BLIP-SVI05-BLOCK-1",
        type=BlipConfiguration.ConfigurationType.FLOW,
        description="Bloco distinto",
        phone_number=int(line.phone_number),
        key=BlipConfiguration.KeyType.ACCESS,
        value="token-svi05-block-1",
    )
    update_url = reverse("telecom:blip_configuration_update", args=[config.pk])

    response = client.get(update_url)
    content = response.content.decode()

    select_block = _select_block(content)
    # O indicador/circulo nunca pode estar dentro do próprio <select>
    # (contrato: nunca HTML dentro de option nativo).
    assert "seal-indicator" not in select_block

    # O número salvo (A) precisa aparecer em texto explícito, FORA do
    # <select>, com o indicador adjacente, num bloco próprio distinto da
    # seleção.
    after_select = content[content.index("</select>", content.index('name="phone_number"')) :]
    block_match = re.search(
        r'<div[^>]*class="[^"]*seal-indicator-saved-block[^"]*"[^>]*>(.*?)</div>',
        after_select,
        re.DOTALL,
    )
    assert block_match, "Bloco distinto 'Dado salvo' não encontrado após o <select>"
    block_content = block_match.group(1)
    # BlipConfiguration.phone_number e BigIntegerField sem "+" (mesma
    # convencao ja usada por blip_configuration_list.html/Admin — numero
    # exibido sempre como inteiro puro nas telas BLIP).
    assert str(config.phone_number) in block_content
    assert "seal-indicator" in block_content


def test_blip_form_create_has_no_saved_block_and_no_indicator_near_select(dev_client):
    """Cadastro sem instância salva: nenhum bloco 'Dado salvo', nenhum
    indicador — nenhuma seleção ainda confirmada (borda aprovada #3)."""
    _user, client = dev_client

    response = client.get(reverse("telecom:blip_configuration_create"))
    content = response.content.decode()

    assert "seal-indicator-saved-block" not in content
    assert "seal-indicator" not in content
