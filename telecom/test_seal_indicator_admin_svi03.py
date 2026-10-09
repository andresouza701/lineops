"""SVI-03 — testes RED do indicador visual de selo junto ao número.

Fonte da verdade: docs/superpowers/specs/2026-10-05-phone-line-seal-
indicator-design.md. Cobre I25 (admin SIMcard) e I26 (admin
BlipConfiguration) da matriz — borda aprovada #4 do fechamento SVI-02:
"Django Admin incluído... preservando permissões staff/modelo". Nenhum
teste aqui modifica __str__ dos modelos nem permissoes do Admin.

GREEN esperado: SVI-05, reaproveitando a projecao central de SVI-04.
"""

from datetime import date

import pytest
from django.urls import reverse
from django.utils import timezone

from telecom.models import BlipConfiguration, PhoneLine, SIMcard
from users.models import SystemUser

PASSWORD = "StrongPass123"


def _cell(html, marker, tag="td"):
    idx = html.index(marker)
    start = html.rindex(f"<{tag}", 0, idx)
    end = html.index(f"</{tag}>", idx) + len(f"</{tag}>")
    return html[start:end]


@pytest.fixture
def superuser_client(client, db):
    user = SystemUser.objects.create_superuser(
        email="svi03-root@example.com", password=PASSWORD, role=SystemUser.Role.ADMIN
    )
    client.force_login(user)
    return client


def test_simcard_admin_changelist_shows_seal_indicator_next_to_line(
    superuser_client, monkeypatch
):
    """I25 · apresentacao/HTTP (Admin) · GREEN esperado: SVI-05."""
    monkeypatch.setattr(timezone, "localdate", lambda: date(2026, 9, 17))
    sim = SIMcard.objects.create(iccid="8900000000000077030", carrier="TIM")
    PhoneLine.objects.create(
        phone_number="+5511999997730",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=date(2026, 8, 1),
        whatsapp_seal_expires_on=date(2026, 9, 25),
        whatsapp_seal_email="simadmin@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )

    response = superuser_client.get(reverse("admin:telecom_simcard_changelist"))
    content = response.content.decode()

    cell = _cell(content, "+5511999997730", tag="td")
    assert sim.phone_line.seal_status["label"] in cell


def test_blip_configuration_admin_changelist_shows_seal_indicator(superuser_client, monkeypatch):
    """I26 · apresentacao/HTTP (Admin) · mesma lacuna de associacao sem FK
    de I23. GREEN esperado: SVI-05."""
    monkeypatch.setattr(timezone, "localdate", lambda: date(2026, 9, 17))
    sim = SIMcard.objects.create(iccid="8900000000000077031", carrier="TIM")
    line = PhoneLine.objects.create(
        phone_number="+5511999997731",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        origem=PhoneLine.Origem.BLIP,
        whatsapp_seal="META_VERIFIED",
        whatsapp_seal_activation_status="NOT_ACTIVATED",
    )
    BlipConfiguration.objects.create(
        blip_id="BLIP-SVI03-ADMIN-1",
        type=BlipConfiguration.ConfigurationType.FLOW,
        description="Fluxo admin",
        phone_number=int(line.phone_number),
        key=BlipConfiguration.KeyType.ACCESS,
        value="token-admin",
    )

    response = superuser_client.get(reverse("admin:telecom_blipconfiguration_changelist"))
    content = response.content.decode()

    cell = _cell(content, str(int(line.phone_number)), tag="td")
    assert line.seal_status["label"] in cell
