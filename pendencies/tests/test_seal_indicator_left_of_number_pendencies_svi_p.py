"""SVI-P02/P03 — ajuste aprovado 2026-10-11: indicador antes do numero.
Cobre I28 (admin AllocationPendency): telefone chega indiretamente via
`str(obj.allocation)` ("funcionario - numero - status"); o indicador
precisa ficar colado ao NUMERO, nao ao inicio da celula inteira.

Fonte da verdade: docs/superpowers/specs/2026-10-05-phone-line-seal-
indicator-design.md.
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
FROZEN_TODAY = date(2026, 9, 17)


@pytest.fixture
def superuser_client(client, db):
    user = SystemUser.objects.create_superuser(
        email="svi-p-pend-root@example.com", password=PASSWORD, role=SystemUser.Role.ADMIN
    )
    client.force_login(user)
    return user, client


def test_allocation_pendency_admin_places_indicator_before_number_not_before_employee(
    superuser_client, monkeypatch
):
    monkeypatch.setattr(timezone, "localdate", lambda: FROZEN_TODAY)
    admin, client = superuser_client
    employee = Employee.objects.create(
        full_name="Funcionario SVI-P Pendencia",
        corporate_email="svi-p-pendencia@example.com",
        employee_id="SVI-P-PEND-1",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )
    sim = SIMcard.objects.create(iccid="8900000000000093001", carrier="TIM")
    line = PhoneLine.objects.create(
        phone_number="+5511999993001",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=date(2026, 8, 1),
        whatsapp_seal_expires_on=date(2026, 9, 25),
        whatsapp_seal_email="svi-p-pend@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    AllocationService.allocate_line(employee=employee, phone_line=line, allocated_by=admin)
    allocation = LineAllocation.objects.get(employee=employee, phone_line=line, is_active=True)
    AllocationPendency.objects.create(employee=employee, allocation=allocation)

    response = client.get(reverse("admin:pendencies_allocationpendency_changelist"))
    content = response.content.decode()

    # Isola a celula da coluna "allocation_display" pela sua classe real
    # do Admin — o numero tambem aparece (sem relacao com este contrato)
    # dentro do aria-label do checkbox de selecao da linha, ANTES desta
    # celula; buscar direto pelo numero no <tr> inteiro pegaria aquele
    # texto por engano.
    marker = 'class="field-allocation_display">'
    cell_start = content.index(marker) + len(marker)
    cell_end = content.index("</td>", cell_start)
    cell = content[cell_start:cell_end]

    # Indicador colado ao numero.
    number_idx_in_cell = cell.index(line.phone_number)
    assert cell[number_idx_in_cell - 1] == " "
    assert cell[number_idx_in_cell - 2] == ">"
    assert "seal-indicator" in cell[:number_idx_in_cell]

    # Mas NAO colado ao nome do funcionario (o " - " entre funcionario e
    # numero, do __str__ de LineAllocation, precisa continuar intacto
    # imediatamente antes do indicador, nao ser engolido por ele).
    employee_idx = cell.index(employee.full_name)
    indicator_tag_idx = cell.index("<span", employee_idx)
    text_between = cell[employee_idx + len(employee.full_name) : indicator_tag_idx]
    assert text_between.strip().endswith("-"), (
        f"esperado texto terminando em '-' entre funcionario e indicador, achou {text_between!r}"
    )
