"""SVI-P02/P03 — ajuste aprovado 2026-10-11: indicador antes do numero,
um unico espaco de separador. Cobre reports/home.html (relatorio de
inventario de linhas), sem alterar colunas/contrato de exportacao.

Fonte da verdade: docs/superpowers/specs/2026-10-05-phone-line-seal-
indicator-design.md.
"""

from datetime import date, datetime
from urllib.parse import urlencode

import pytest
from django.urls import reverse
from django.utils import timezone

from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser

PASSWORD = "StrongPass123"
PERIOD_START = "2026-08-01"
PERIOD_END = "2026-09-24"


def _report_url(relatorio, **extra):
    pairs = [
        ("relatorio", relatorio),
        ("data_inicial", PERIOD_START),
        ("data_final", PERIOD_END),
    ]
    pairs.extend(extra.items())
    return f"{reverse('reports_home')}?{urlencode(pairs)}"


def _phone_cell(html, phone_number):
    import re

    pattern = re.compile(rf"<td[^>]*>\s*.*?{re.escape(phone_number)}.*?</td>", re.DOTALL)
    match = pattern.search(html)
    assert match, f"Nenhum <td> contendo {phone_number!r} encontrado."
    return match.group(0)


@pytest.fixture
def admin_client(client, db, monkeypatch):
    monkeypatch.setattr(timezone, "localdate", lambda: date(2026, 9, 17))
    user = SystemUser.objects.create_user(
        email="svi-p-report-admin@example.com", password=PASSWORD, role=SystemUser.Role.ADMIN
    )
    client.force_login(user)
    return user, client


@pytest.fixture
def line_green(db):
    sim = SIMcard.objects.create(iccid="8900000000000096001", carrier="TIM")
    line = PhoneLine.objects.create(
        phone_number="+5511999996001",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=date(2026, 8, 1),
        whatsapp_seal_expires_on=date(2026, 9, 25),
        whatsapp_seal_email="svi-p-report@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    PhoneLine.objects.filter(pk=line.pk).update(
        created_at=timezone.make_aware(datetime(2026, 9, 10, 10, 0))
    )
    return line


def test_line_inventory_report_places_indicator_before_number(admin_client, line_green):
    _admin, client = admin_client
    response = client.get(_report_url("line_inventory", linha=line_green.phone_number))
    content = response.content.decode()

    cell = _phone_cell(content, line_green.phone_number)
    idx = cell.index(line_green.phone_number)
    assert cell[idx - 1] == " ", f"esperado espaco antes do numero, achou {cell[idx - 2:idx]!r}"
    assert cell[idx - 2] == ">"
    assert "seal-indicator" in cell[:idx]
