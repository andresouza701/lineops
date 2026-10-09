"""SVI-05 — mecanismo do seletor sem JS de I24 (BlipConfigurationForm).

Fonte da verdade: docs/superpowers/specs/2026-10-05-phone-line-seal-
indicator-design.md, I24. Requisito aprovado (fechamento SVI-02 #3): o
indicador adjacente ao <select> de numero BLIP nunca pode representar uma
selecao anterior/nao confirmada. SVI-03/04 registraram essa lacuna como
"mecanismo tecnico ainda a definir, nao testavel sem inventar contrato" —
este arquivo fecha a definicao: SEM JavaScript, o indicador e sempre
derivado do DADO SALVO (`self.object` recarregado do banco no GET), nunca
do valor corrente/nao submetido do <select>. Isso garante, por construcao,
que uma troca de selecao so pode mudar o indicador DEPOIS de um POST valido
e um novo GET (nunca durante a edicao em andamento, nunca mantendo o
circulo da selecao anterior apos confirmar uma nova).
"""

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
        email="svi05-blip-dev@example.com", password=PASSWORD, role=SystemUser.Role.DEV
    )
    client.force_login(user)
    return user, client


@pytest.fixture
def two_authorized_blip_lines(monkeypatch):
    monkeypatch.setattr(timezone, "localdate", lambda: FROZEN_TODAY)
    sim_a = SIMcard.objects.create(iccid="8900000000000099001", carrier="TIM")
    sim_b = SIMcard.objects.create(iccid="8900000000000099002", carrier="TIM")
    line_a = PhoneLine.objects.create(
        phone_number="+5511999999001",
        sim_card=sim_a,
        status=PhoneLine.Status.AVAILABLE,
        origem=PhoneLine.Origem.BLIP,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=date(2026, 8, 1),
        whatsapp_seal_expires_on=date(2026, 9, 25),
        whatsapp_seal_email="a@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    line_b = PhoneLine.objects.create(
        phone_number="+5511999999002",
        sim_card=sim_b,
        status=PhoneLine.Status.AVAILABLE,
        origem=PhoneLine.Origem.BLIP,
        whatsapp_seal="META_VERIFIED",
        whatsapp_seal_activation_status="NOT_ACTIVATED",
    )
    return line_a, line_b


def test_blip_form_update_never_shows_previous_selection_circle_after_confirmed_change(
    dev_client, two_authorized_blip_lines
):
    """I24 · seletor sem JS · GET inicial mostra o indicador da linha A
    (salva). POST troca para a linha B (selecao confirmada/salva). O
    PROXIMO GET precisa mostrar o indicador de B e NUNCA o de A — prova de
    que o indicador nunca fica "preso" a uma selecao anterior, mesmo sem
    nenhum mecanismo de JS envolvido."""
    _user, client = dev_client
    line_a, line_b = two_authorized_blip_lines
    config = BlipConfiguration.objects.create(
        blip_id="BLIP-SVI05-1",
        type=BlipConfiguration.ConfigurationType.FLOW,
        description="Fluxo seletor sem JS",
        phone_number=int(line_a.phone_number),
        key=BlipConfiguration.KeyType.ACCESS,
        value="token-svi05-1",
    )
    update_url = reverse("telecom:blip_configuration_update", args=[config.pk])

    initial_response = client.get(update_url)
    initial_content = initial_response.content.decode()
    assert line_a.seal_status["label"] in initial_content
    assert line_b.seal_status["label"] not in initial_content

    post_response = client.post(
        update_url,
        {
            "blip_id": "BLIP-SVI05-1",
            "type": BlipConfiguration.ConfigurationType.FLOW,
            "description": "Fluxo seletor sem JS",
            "phone_number": line_b.phone_number,
            "key": BlipConfiguration.KeyType.ACCESS,
            "value": "token-svi05-1",
        },
    )
    assert post_response.status_code == 302, post_response.context["form"].errors

    after_response = client.get(update_url)
    after_content = after_response.content.decode()
    assert line_b.seal_status["label"] in after_content
    # Garantia central da borda: o circulo da selecao ANTERIOR (A) nunca
    # reaparece depois que B foi confirmado e salvo.
    assert line_a.seal_status["label"] not in after_content


def test_blip_form_create_shows_no_indicator_for_unconfirmed_selection(
    dev_client, two_authorized_blip_lines
):
    """I24 · nunca associar um indicador salvo a uma selecao nova ainda nao
    confirmada: tela de cadastro (sem instancia salva) nao mostra nenhum
    circulo/"Selo indisponível" junto ao seletor, mesmo havendo linhas
    autorizadas disponiveis nas opcoes."""
    _user, client = dev_client
    line_a, _line_b = two_authorized_blip_lines

    response = client.get(reverse("telecom:blip_configuration_create"))
    content = response.content.decode()

    assert "seal-indicator" not in content
    assert "Selo indisponível" not in content
    assert line_a.seal_status["label"] not in content
