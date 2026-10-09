"""SVI-03 — testes RED do indicador visual de selo junto ao número.

Fonte da verdade: docs/superpowers/specs/2026-10-05-phone-line-seal-
indicator-design.md. Cobre I28 (admin AllocationPendency) da matriz —
telefone exibido INDIRETAMENTE pela coluna "allocation"
(LineAllocation.__str__ contem o numero). Nao altera __str__ do model.

GREEN esperado: SVI-05, reaproveitando a projecao central de SVI-04.
"""

from datetime import date

import pytest
from django.urls import reverse
from django.utils import timezone

from allocations.models import LineAllocation
from core.services.allocation_service import AllocationService
from employees.models import Employee
from pendencies.models import AllocationPendency
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser

PASSWORD = "StrongPass123"


@pytest.fixture
def superuser_client(client, db):
    user = SystemUser.objects.create_superuser(
        email="svi03-pend-root@example.com", password=PASSWORD, role=SystemUser.Role.ADMIN
    )
    client.force_login(user)
    return user, client


def test_allocation_pendency_admin_changelist_shows_seal_indicator(superuser_client, monkeypatch):
    """I28 · apresentacao/HTTP (Admin) · telefone indireto via relacao.
    GREEN esperado: SVI-05."""
    monkeypatch.setattr(timezone, "localdate", lambda: date(2026, 9, 17))
    admin, client = superuser_client
    employee = Employee.objects.create(
        full_name="Funcionario Admin Pendencia",
        corporate_email="admin-pendencia@example.com",
        employee_id="SVI03-ADMIN-PEND-1",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )
    sim = SIMcard.objects.create(iccid="8900000000000077041", carrier="TIM")
    line = PhoneLine.objects.create(
        phone_number="+5511999997741",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_VERIFIED",
        whatsapp_seal_activation_status="NOT_ACTIVATED",
    )
    AllocationService.allocate_line(employee=employee, phone_line=line, allocated_by=admin)
    allocation = LineAllocation.objects.get(employee=employee, phone_line=line, is_active=True)
    AllocationPendency.objects.create(employee=employee, allocation=allocation)

    response = client.get(reverse("admin:pendencies_allocationpendency_changelist"))
    content = response.content.decode()

    # A linha contendo o __str__ da alocacao e que precisa do indicador;
    # usa-se o numero como ancora, assim como nas demais telas do Admin.
    idx = content.index(line.phone_number)
    row_start = content.rindex("<tr", 0, idx)
    row_end = content.index("</tr>", idx) + len("</tr>")
    row = content[row_start:row_end]

    assert line.seal_status["label"] in row
