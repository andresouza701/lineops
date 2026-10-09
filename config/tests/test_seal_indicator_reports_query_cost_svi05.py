"""SVI-05 — custo de consulta do indicador de selo nos relatorios (I18-I22).

Ver telecom/test_seal_indicator_query_cost_svi05.py para o contexto geral.
Aqui: build_seal_indicator é chamado por linha dentro de `_row_from_line`/
`_row_from_allocation`/`_row_from_pendency`/`_row_from_legacy`/`_row_from_
audit`, mas lendo apenas campos JA carregados na mesma instancia buscada
pelo `_build_queryset` de cada relatorio (select_related/`.values()`
existente) — nenhuma consulta adicional por linha. Prova: mesmo numero de
consultas entre um relatorio com poucas e com muitas linhas na mesma
pagina (PAGE_SIZE=50, ambos os datasets abaixo cabem numa unica pagina).
"""

from datetime import date, datetime
from urllib.parse import urlencode

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser

PASSWORD = "StrongPass123"
PERIOD_START = "2026-08-01"
PERIOD_END = "2026-09-24"


@pytest.fixture
def admin_client(client, db, monkeypatch):
    monkeypatch.setattr(timezone, "localdate", lambda: date(2026, 9, 17))
    user = SystemUser.objects.create_user(
        email="svi05-reports-cost-admin@example.com", password=PASSWORD, role=SystemUser.Role.ADMIN
    )
    client.force_login(user)
    return user, client


def _report_url(**extra):
    pairs = [
        ("relatorio", "line_inventory"),
        ("data_inicial", PERIOD_START),
        ("data_final", PERIOD_END),
    ]
    pairs.extend(extra.items())
    return f"{reverse('reports_home')}?{urlencode(pairs)}"


def _make_lines(count, prefix):
    for i in range(count):
        sim = SIMcard.objects.create(iccid=f"890000000000095{prefix}{i:03d}", carrier="TIM")
        line = PhoneLine.objects.create(
            phone_number=f"+551155555{prefix}{i:03d}",
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
            whatsapp_seal="META_ONE",
            whatsapp_seal_activation_status="ACTIVE",
            whatsapp_seal_activated_on=date(2026, 8, 1),
            whatsapp_seal_expires_on=date(2026, 9, 25),
            whatsapp_seal_email=f"rep-cost-{prefix}-{i}@example.com",
            whatsapp_seal_payment="CREDIT_CARD",
        )
        PhoneLine.objects.filter(pk=line.pk).update(
            created_at=timezone.make_aware(datetime(2026, 9, 10, 10, 0))
        )


@pytest.mark.django_db
def test_line_inventory_report_seal_indicator_query_count_does_not_grow_with_line_count(
    admin_client,
):
    """I19 · custo de consulta · numero de consultas da tela e o mesmo para
    um relatorio pequeno e um grande (ambos cabem numa unica pagina)."""
    _admin, client = admin_client

    _make_lines(2, "1")
    with CaptureQueriesContext(connection) as small_ctx:
        small_response = client.get(_report_url())
    assert small_response.status_code == 200

    _make_lines(20, "2")
    with CaptureQueriesContext(connection) as large_ctx:
        large_response = client.get(_report_url())
    assert large_response.status_code == 200

    assert len(large_ctx) == len(small_ctx), (
        "Consultas do relatorio de inventario cresceram com o numero de "
        f"linhas: {len(small_ctx)} (pequeno) vs {len(large_ctx)} (grande)."
    )
