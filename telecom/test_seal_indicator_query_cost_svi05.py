"""SVI-05 — custo de consulta do indicador de selo POR SUPERFICIE integrada.

Fonte da verdade: docs/superpowers/specs/2026-10-05-phone-line-seal-
indicator-design.md. SVI-03/04 provaram que `seal_status`/`build_seal_
indicator`, isolados, custam zero consulta — isso NAO prova ausencia de
N+1 nas superficies integradas (cada view ainda precisa buscar PhoneLine
em lote). Este arquivo fecha essa lacuna para I01 (overview AJAX) e I23
(lista BLIP): compara o numero de consultas entre um dataset PEQUENO e um
GRANDE das mesmas linhas/configuracoes — a contagem precisa ser IGUAL
(nao crescer por linha), nao necessariamente um numero fixo escolhido a
priori.
"""

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
def admin_client(client, db):
    user = SystemUser.objects.create_user(
        email="svi05-cost-admin@example.com", password=PASSWORD, role=SystemUser.Role.ADMIN
    )
    client.force_login(user)
    return client


@pytest.fixture
def dev_client(client, db):
    user = SystemUser.objects.create_user(
        email="svi05-cost-dev@example.com", password=PASSWORD, role=SystemUser.Role.DEV
    )
    client.force_login(user)
    return user, client


def _make_lines(count, prefix):
    lines = []
    for i in range(count):
        sim = SIMcard.objects.create(iccid=f"890000000000099{prefix}{i:03d}", carrier="TIM")
        lines.append(
            PhoneLine.objects.create(
                phone_number=f"+551199999{prefix}{i:03d}",
                sim_card=sim,
                status=PhoneLine.Status.AVAILABLE,
                whatsapp_seal="META_ONE",
                whatsapp_seal_activation_status="ACTIVE",
                whatsapp_seal_activated_on=date(2026, 8, 1),
                whatsapp_seal_expires_on=date(2026, 9, 25),
                whatsapp_seal_email=f"line{i}@example.com",
                whatsapp_seal_payment="CREDIT_CARD",
            )
        )
    return lines


@pytest.mark.django_db
def test_overview_ajax_seal_indicator_query_count_does_not_grow_with_line_count(
    admin_client, monkeypatch
):
    """I01 · custo de consulta · AJAX "Carregar mais": o numero de consultas
    disparadas pela view (inclusive o enriquecimento com seal_indicator) e
    o MESMO para um lote pequeno e um lote grande de linhas na mesma
    pagina — o indicador nao soma uma query por linha."""
    monkeypatch.setattr(timezone, "localdate", lambda: FROZEN_TODAY)
    small_lines = _make_lines(2, "1")
    url = reverse("telecom:overview")

    with CaptureQueriesContext(connection) as small_ctx:
        response_small = admin_client.get(
            url, {"offset": 0, "limit": 50}, HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
    assert response_small.status_code == 200
    assert len(response_small.json()["data"]) == len(small_lines)

    large_lines = _make_lines(20, "2")

    with CaptureQueriesContext(connection) as large_ctx:
        response_large = admin_client.get(
            url, {"offset": 0, "limit": 50}, HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
    assert response_large.status_code == 200
    assert len(response_large.json()["data"]) == len(small_lines) + len(large_lines)

    assert len(large_ctx) == len(small_ctx), (
        "Consultas cresceram com o numero de linhas: "
        f"{len(small_ctx)} (pequeno, {len(small_lines)} linhas) vs "
        f"{len(large_ctx)} (grande, {len(small_lines) + len(large_lines)} linhas)."
    )


@pytest.mark.django_db
def test_blip_list_seal_indicator_query_count_does_not_grow_with_config_count(
    dev_client, monkeypatch
):
    """I23 · custo de consulta · a resolucao em lote (build_authorized_
    blip_line_index) e feita UMA vez por requisicao, nao uma vez por
    BlipConfiguration — o numero de consultas da listagem e o mesmo com
    poucas e com muitas configuracoes/linhas BLIP."""
    monkeypatch.setattr(timezone, "localdate", lambda: FROZEN_TODAY)
    _user, client = dev_client
    url = reverse("telecom:blip_configuration_list")

    def _make_blip_configs(count, prefix):
        for i in range(count):
            sim = SIMcard.objects.create(
                iccid=f"890000000000098{prefix}{i:03d}", carrier="TIM"
            )
            line = PhoneLine.objects.create(
                phone_number=f"+551188888{prefix}{i:03d}",
                sim_card=sim,
                status=PhoneLine.Status.AVAILABLE,
                origem=PhoneLine.Origem.BLIP,
                whatsapp_seal="META_ONE",
                whatsapp_seal_activation_status="ACTIVE",
                whatsapp_seal_activated_on=date(2026, 8, 1),
                whatsapp_seal_expires_on=date(2026, 9, 25),
                whatsapp_seal_email=f"blip{prefix}{i}@example.com",
                whatsapp_seal_payment="CREDIT_CARD",
            )
            BlipConfiguration.objects.create(
                blip_id=f"BLIP-COST-{prefix}-{i}",
                type=BlipConfiguration.ConfigurationType.FLOW,
                description="Custo de consulta",
                phone_number=int(line.phone_number),
                key=BlipConfiguration.KeyType.ACCESS,
                value="token-cost",
            )

    _make_blip_configs(2, "1")
    with CaptureQueriesContext(connection) as small_ctx:
        small_response = client.get(url)
    assert small_response.status_code == 200

    _make_blip_configs(20, "2")
    with CaptureQueriesContext(connection) as large_ctx:
        large_response = client.get(url)
    assert large_response.status_code == 200

    assert len(large_ctx) == len(small_ctx), (
        "Consultas da lista BLIP cresceram com o numero de configuracoes: "
        f"{len(small_ctx)} (pequeno) vs {len(large_ctx)} (grande)."
    )
