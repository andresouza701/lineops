"""SVI-03 — testes RED do indicador visual de selo junto ao número.

Fonte da verdade: docs/superpowers/specs/2026-10-05-phone-line-seal-
indicator-design.md. Cobre I10 (allocations:allocation_edit) da matriz.

GREEN esperado: SVI-05, reaproveitando a projecao central de SVI-04.
"""

from datetime import date

import pytest
from django.urls import reverse
from django.utils import timezone

from allocations.models import LineAllocation
from core.services.allocation_service import AllocationService
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser

PASSWORD = "StrongPass123"


def _window(html, marker, length=600):
    idx = html.index(marker) + len(marker)
    return html[idx : idx + length]


@pytest.fixture
def admin_client(client, db):
    user = SystemUser.objects.create_user(
        email="svi03-alloc-admin@example.com", password=PASSWORD, role=SystemUser.Role.ADMIN
    )
    client.force_login(user)
    return user, client


def test_allocation_edit_shows_indicator_adjacent_to_readonly_line_field(
    admin_client, monkeypatch
):
    """I10 · apresentacao/HTTP · borda aprovada #3: indicador junto ao
    campo readonly da linha, referente ao dado salvo — nunca inserido
    dentro do value do input. GREEN esperado: SVI-05."""
    monkeypatch.setattr(timezone, "localdate", lambda: date(2026, 9, 17))
    admin, client = admin_client
    employee = Employee.objects.create(
        full_name="Funcionario Alocacao",
        corporate_email="alocacao@example.com",
        employee_id="SVI03-ALLOC-1",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )
    sim = SIMcard.objects.create(iccid="8900000000000077010", carrier="TIM")
    line = PhoneLine.objects.create(
        phone_number="+5511999997710",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=date(2026, 8, 1),
        whatsapp_seal_expires_on=date(2026, 9, 25),
        whatsapp_seal_email="alloc@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    AllocationService.allocate_line(employee=employee, phone_line=line, allocated_by=admin)
    allocation = LineAllocation.objects.get(employee=employee, phone_line=line, is_active=True)

    response = client.get(reverse("allocations:allocation_edit", args=[allocation.pk]))
    content = response.content.decode()

    window = _window(content, f'value="{line.phone_number}"', length=600)
    assert line.seal_status["label"] in window
    # Nunca dentro do proprio value do input readonly.
    assert f'value="{line.phone_number}{line.seal_status["label"]}"' not in content
