"""SVI-05 — custo de consulta do indicador de selo em I13-I17
(daily_indicator_day_breakdown).

Ver telecom/test_seal_indicator_query_cost_svi05.py para o contexto geral.
Aqui: build_seal_indicator_index_for_breakdown (dashboard/views.py) faz
UMA unica consulta em lote (PhoneLine.all_objects.filter(phone_number__in=...))
para TODOS os numeros do detalhamento do dia, independente de quantos
numeros existam — o numero de consultas extra precisa ser o mesmo entre um
dia com poucos numeros e um dia com muitos.
"""

from datetime import date, timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser

PASSWORD = "StrongPass123"


@pytest.fixture
def admin_client(client, db):
    user = SystemUser.objects.create_user(
        email="svi05-dash-cost-admin@example.com", password=PASSWORD, role=SystemUser.Role.ADMIN
    )
    client.force_login(user)
    return user, client


def _make_new_lines_for_today(count, prefix):
    for i in range(count):
        sim = SIMcard.objects.create(iccid=f"890000000000096{prefix}{i:03d}", carrier="TIM")
        PhoneLine.objects.create(
            phone_number=f"+551166666{prefix}{i:03d}",
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
            whatsapp_seal="META_ONE",
            whatsapp_seal_activation_status="ACTIVE",
            whatsapp_seal_activated_on=timezone.localdate() - timedelta(days=30),
            whatsapp_seal_expires_on=timezone.localdate() + timedelta(days=8),
            whatsapp_seal_email=f"dash-cost-{prefix}-{i}@example.com",
            whatsapp_seal_payment="CREDIT_CARD",
        )


@pytest.mark.django_db
def test_daily_indicator_day_breakdown_seal_indicator_query_count_does_not_grow_with_number_count(
    admin_client,
):
    """I13-I17 · custo de consulta · a resolucao em lote do indicador por
    numero e UMA unica consulta extra, independente de quantos numeros
    aparecem no detalhamento do dia."""
    _admin, client = admin_client
    today_iso = timezone.localdate().strftime("%Y-%m-%d")
    url = reverse("daily_indicator_day_breakdown", kwargs={"day": today_iso})

    _make_new_lines_for_today(2, "1")
    with CaptureQueriesContext(connection) as small_ctx:
        small_response = client.get(url)
    assert small_response.status_code == 200
    small_new_numbers = len(small_response.context["indicator"]["new_numbers"])

    _make_new_lines_for_today(20, "2")
    with CaptureQueriesContext(connection) as large_ctx:
        large_response = client.get(url)
    assert large_response.status_code == 200
    large_new_numbers = len(large_response.context["indicator"]["new_numbers"])
    assert large_new_numbers > small_new_numbers

    assert len(large_ctx) == len(small_ctx), (
        "Consultas do detalhamento diario cresceram com o numero de "
        f"linhas novas: {len(small_ctx)} (pequeno, {small_new_numbers} "
        f"numeros) vs {len(large_ctx)} (grande, {large_new_numbers} numeros)."
    )
