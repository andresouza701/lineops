"""SVI-03 — testes RED do indicador visual de selo junto ao número.

Fonte da verdade: docs/superpowers/specs/2026-10-05-phone-line-seal-
indicator-design.md. Cobre I27 (admin LineAllocation) da matriz — telefone
exibido via coluna/FK phone_line. Nao altera __str__ do model.

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


def _cell(html, marker, tag="td"):
    idx = html.index(marker)
    start = html.rindex(f"<{tag}", 0, idx)
    end = html.index(f"</{tag}>", idx) + len(f"</{tag}>")
    return html[start:end]


@pytest.fixture
def superuser_client(client, db):
    user = SystemUser.objects.create_superuser(
        email="svi03-alloc-root@example.com", password=PASSWORD, role=SystemUser.Role.ADMIN
    )
    client.force_login(user)
    return user, client


def test_line_allocation_admin_changelist_shows_seal_indicator(superuser_client, monkeypatch):
    """I27 · apresentacao/HTTP (Admin) · GREEN esperado: SVI-05."""
    monkeypatch.setattr(timezone, "localdate", lambda: date(2026, 9, 17))
    admin, client = superuser_client
    employee = Employee.objects.create(
        full_name="Funcionario Admin Alocacao",
        corporate_email="admin-alocacao@example.com",
        employee_id="SVI03-ADMIN-ALLOC-1",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )
    sim = SIMcard.objects.create(iccid="8900000000000077040", carrier="TIM")
    line = PhoneLine.objects.create(
        phone_number="+5511999997740",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=date(2026, 8, 1),
        whatsapp_seal_expires_on=date(2026, 9, 25),
        whatsapp_seal_email="adminalloc@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    AllocationService.allocate_line(employee=employee, phone_line=line, allocated_by=admin)

    response = client.get(reverse("admin:allocations_lineallocation_changelist"))
    content = response.content.decode()

    cell = _cell(content, line.phone_number, tag="td")
    assert line.seal_status["label"] in cell
