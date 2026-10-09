"""SVI-05 — custo de consulta do indicador de selo no Django Admin (I25-I28).

Ver telecom/test_seal_indicator_query_cost_svi05.py para o contexto geral.
SIMcardAdmin/LineAllocationAdmin ganharam list_select_related; Blip
ConfigurationAdmin/AllocationPendencyAdmin resolvem a identidade em UMA
consulta por changelist (get_queryset), nao por linha."""

from datetime import date

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from telecom.models import BlipConfiguration, PhoneLine, SIMcard
from users.models import SystemUser

PASSWORD = "StrongPass123"
FROZEN_TODAY = date(2026, 9, 17)


@pytest.fixture
def superuser_client(client, db):
    user = SystemUser.objects.create_superuser(
        email="svi05-admin-cost-root@example.com", password=PASSWORD, role=SystemUser.Role.ADMIN
    )
    client.force_login(user)
    return client


def _make_simcards_with_lines(count, prefix):
    for i in range(count):
        sim = SIMcard.objects.create(iccid=f"890000000000094{prefix}{i:03d}", carrier="TIM")
        PhoneLine.objects.create(
            phone_number=f"+551144444{prefix}{i:03d}",
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
            whatsapp_seal="META_ONE",
            whatsapp_seal_activation_status="ACTIVE",
            whatsapp_seal_activated_on=date(2026, 8, 1),
            whatsapp_seal_expires_on=date(2026, 9, 25),
            whatsapp_seal_email=f"admin-cost-{prefix}-{i}@example.com",
            whatsapp_seal_payment="CREDIT_CARD",
        )


@pytest.mark.django_db
def test_simcard_admin_seal_indicator_query_count_does_not_grow_with_row_count(
    superuser_client, monkeypatch
):
    """I25 · custo de consulta."""
    monkeypatch.setattr(timezone, "localdate", lambda: FROZEN_TODAY)
    url = reverse("admin:telecom_simcard_changelist")

    _make_simcards_with_lines(2, "1")
    with CaptureQueriesContext(connection) as small_ctx:
        small_response = superuser_client.get(url)
    assert small_response.status_code == 200

    _make_simcards_with_lines(20, "2")
    with CaptureQueriesContext(connection) as large_ctx:
        large_response = superuser_client.get(url)
    assert large_response.status_code == 200

    assert len(large_ctx) == len(small_ctx), (
        "Consultas do Admin de SIMcard cresceram com o numero de linhas: "
        f"{len(small_ctx)} (pequeno) vs {len(large_ctx)} (grande)."
    )


@pytest.mark.django_db
def test_blip_configuration_admin_seal_indicator_query_count_does_not_grow_with_row_count(
    superuser_client, monkeypatch
):
    """I26 · custo de consulta."""
    monkeypatch.setattr(timezone, "localdate", lambda: FROZEN_TODAY)
    url = reverse("admin:telecom_blipconfiguration_changelist")

    def _make_configs(count, prefix):
        for i in range(count):
            sim = SIMcard.objects.create(
                iccid=f"890000000000093{prefix}{i:03d}", carrier="TIM"
            )
            line = PhoneLine.objects.create(
                phone_number=f"+551133333{prefix}{i:03d}",
                sim_card=sim,
                status=PhoneLine.Status.AVAILABLE,
                origem=PhoneLine.Origem.BLIP,
                whatsapp_seal="META_VERIFIED",
                whatsapp_seal_activation_status="NOT_ACTIVATED",
            )
            BlipConfiguration.objects.create(
                blip_id=f"BLIP-ADMIN-COST-{prefix}-{i}",
                type=BlipConfiguration.ConfigurationType.FLOW,
                description="Custo admin",
                phone_number=int(line.phone_number),
                key=BlipConfiguration.KeyType.ACCESS,
                value="token-admin-cost",
            )

    _make_configs(2, "1")
    with CaptureQueriesContext(connection) as small_ctx:
        small_response = superuser_client.get(url)
    assert small_response.status_code == 200

    _make_configs(20, "2")
    with CaptureQueriesContext(connection) as large_ctx:
        large_response = superuser_client.get(url)
    assert large_response.status_code == 200

    assert len(large_ctx) == len(small_ctx), (
        "Consultas do Admin de BlipConfiguration cresceram com o numero de "
        f"configuracoes: {len(small_ctx)} (pequeno) vs {len(large_ctx)} (grande)."
    )
