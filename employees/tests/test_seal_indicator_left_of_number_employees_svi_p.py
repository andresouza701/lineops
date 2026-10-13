"""SVI-P02/P03 — ajuste aprovado 2026-10-11: indicador antes do numero,
um unico espaco de separador. Cobre I08 (employees:employee_list, varios
numeros na mesma celula separados por virgula — cada indicador precisa
continuar ligado ao SEU proprio numero, mesmo com dois na mesma celula) e
I09 (employees:employee_detail).

Fonte da verdade: docs/superpowers/specs/2026-10-05-phone-line-seal-
indicator-design.md.
"""

from datetime import date

import pytest
from django.urls import reverse
from django.utils import timezone

from core.services.allocation_service import AllocationService
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser

PASSWORD = "StrongPass123"
FROZEN_TODAY = date(2026, 9, 17)


def _cell(html, marker, tag="td"):
    idx = html.index(marker)
    start = html.rindex(f"<{tag}", 0, idx)
    end = html.index(f"</{tag}>", idx) + len(f"</{tag}>")
    return html[start:end]


@pytest.fixture
def admin_client(client, db):
    user = SystemUser.objects.create_user(
        email="svi-p-emp-admin@example.com", password=PASSWORD, role=SystemUser.Role.ADMIN
    )
    client.force_login(user)
    return user, client


def test_employee_list_each_number_keeps_its_own_indicator_immediately_before_it(
    admin_client, monkeypatch
):
    monkeypatch.setattr(timezone, "localdate", lambda: FROZEN_TODAY)
    admin, client = admin_client
    employee = Employee.objects.create(
        full_name="Funcionario SVI-P Multi-Linha",
        corporate_email="svi-p-multi-linha@example.com",
        employee_id="SVI-P-EMP-1",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )
    sim_a = SIMcard.objects.create(iccid="8900000000000094001", carrier="TIM")
    sim_b = SIMcard.objects.create(iccid="8900000000000094002", carrier="TIM")
    line_green = PhoneLine.objects.create(
        phone_number="+5511999994001",
        sim_card=sim_a,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=date(2026, 8, 1),
        whatsapp_seal_expires_on=date(2026, 9, 25),
        whatsapp_seal_email="svi-p-emp-green@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    line_gray = PhoneLine.objects.create(
        phone_number="+5511999994002",
        sim_card=sim_b,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_VERIFIED",
        whatsapp_seal_activation_status="NOT_ACTIVATED",
    )
    AllocationService.allocate_line(employee=employee, phone_line=line_green, allocated_by=admin)
    AllocationService.allocate_line(employee=employee, phone_line=line_gray, allocated_by=admin)

    response = client.get(reverse("employees:employee_list"))
    content = response.content.decode()

    row = _cell(content, employee.full_name, tag="tr")
    lines_cell = _cell(row, "metric-mono", tag="td")
    # Mesmo separador textual do template (", " entre numeros da mesma
    # celula) usado para isolar o par indicador+numero de CADA linha.
    segments = lines_cell.split(", ")
    assert len(segments) == 2

    for line in (line_green, line_gray):
        segment = next(s for s in segments if line.phone_number in s)
        idx = segment.index(line.phone_number)
        assert segment[idx - 1] == " ", (
            f"esperado espaco antes de {line.phone_number}, achou {segment[idx - 2:idx]!r}"
        )
        assert segment[idx - 2] == ">"
        assert "seal-indicator" in segment[:idx]
        # Associacao correta: o indicador DESTE segmento carrega o estado
        # da PROPRIA linha, nunca o da outra.
        assert line.seal_status["label"] != (
            line_gray.seal_status["label"] if line is line_green else line_green.seal_status["label"]
        )
        assert line.seal_status["label"] in segment[:idx]


def test_employee_detail_places_indicator_before_number_in_history_row(
    admin_client, monkeypatch
):
    monkeypatch.setattr(timezone, "localdate", lambda: FROZEN_TODAY)
    admin, client = admin_client
    employee = Employee.objects.create(
        full_name="Funcionario SVI-P Historico",
        corporate_email="svi-p-historico@example.com",
        employee_id="SVI-P-EMP-2",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )
    sim = SIMcard.objects.create(iccid="8900000000000094003", carrier="TIM")
    line = PhoneLine.objects.create(
        phone_number="+5511999994003",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=date(2026, 8, 1),
        whatsapp_seal_expires_on=date(2026, 9, 25),
        whatsapp_seal_email="svi-p-emp-detail@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    AllocationService.allocate_line(employee=employee, phone_line=line, allocated_by=admin)

    response = client.get(reverse("employees:employee_detail", args=[employee.pk]))
    content = response.content.decode()

    cell = _cell(content, line.phone_number, tag="td")
    idx = cell.index(line.phone_number)
    assert cell[idx - 1] == " "
    assert cell[idx - 2] == ">"
    assert "seal-indicator" in cell[:idx]
