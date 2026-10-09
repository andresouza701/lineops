"""SVI-03 — testes RED do indicador visual de selo junto ao número.

Fonte da verdade: docs/superpowers/specs/2026-10-05-phone-line-seal-
indicator-design.md. Cobre I08 (employee_list, inicial+AJAX) e I09
(employee_detail, historico de alocacoes inclusive liberadas) da matriz.

Gap tecnico registrado (nao testado como unidade, por nao inventar
contrato ainda indefinido): employees/views.py::EmployeeListView.
_get_employee_lines retorna HOJE uma STRING ja concatenada ("num1, num2")
— a identidade de cada PhoneLine se perde antes do template (mesma
observacao da fonte da verdade para I13-I17). Os testes abaixo provam o
efeito observavel dessa perda (impossibilidade de distinguir o selo de
duas linhas do mesmo funcionario), sem presumir qual sera o novo formato
de dado.

GREEN esperado: SVI-05, reaproveitando a projecao central de SVI-04.
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
        email="svi03-emp-admin@example.com", password=PASSWORD, role=SystemUser.Role.ADMIN
    )
    client.force_login(user)
    return user, client


# --- I08 — employees:employee_list ----------------------------------------


def test_employee_list_initial_distinguishes_seal_of_two_own_lines(admin_client, monkeypatch):
    """I08 · apresentacao/HTTP · multiplas linhas do mesmo funcionario com
    selos diferentes: hoje line_display e uma unica string concatenada,
    incapaz de carregar dois indicadores distintos. GREEN esperado:
    SVI-05."""
    monkeypatch.setattr(timezone, "localdate", lambda: FROZEN_TODAY)
    admin, client = admin_client
    employee = Employee.objects.create(
        full_name="Funcionario Multi-Linha",
        corporate_email="multi-linha@example.com",
        employee_id="SVI03-EMP-1",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )
    sim_a = SIMcard.objects.create(iccid="8900000000000077001", carrier="TIM")
    sim_b = SIMcard.objects.create(iccid="8900000000000077002", carrier="TIM")
    line_green = PhoneLine.objects.create(
        phone_number="+5511999997701",
        sim_card=sim_a,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=date(2026, 8, 1),
        whatsapp_seal_expires_on=date(2026, 9, 25),
        whatsapp_seal_email="green@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    line_gray = PhoneLine.objects.create(
        phone_number="+5511999997702",
        sim_card=sim_b,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_VERIFIED",
        whatsapp_seal_activation_status="NOT_ACTIVATED",
    )
    AllocationService.allocate_line(employee=employee, phone_line=line_green, allocated_by=admin)
    AllocationService.allocate_line(employee=employee, phone_line=line_gray, allocated_by=admin)

    response = client.get(reverse("employees:employee_list"))
    content = response.content.decode()

    # Controle positivo: os dois rotulos de dominio sao de fato distintos.
    assert line_green.seal_status["label"] != line_gray.seal_status["label"]

    row = _cell(content, employee.full_name, tag="tr")
    assert line_green.seal_status["label"] in row
    assert line_gray.seal_status["label"] in row


def test_employee_list_ajax_payload_distinguishes_seal_of_two_own_lines(
    admin_client, monkeypatch
):
    """I08 · JSON · mesma lacuna no payload "line" do AJAX de load more
    (employees/views.py::_handle_ajax_request). GREEN esperado: SVI-05."""
    monkeypatch.setattr(timezone, "localdate", lambda: FROZEN_TODAY)
    admin, client = admin_client
    employee = Employee.objects.create(
        full_name="Funcionario Multi-Linha AJAX",
        corporate_email="multi-linha-ajax@example.com",
        employee_id="SVI03-EMP-2",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )
    sim_a = SIMcard.objects.create(iccid="8900000000000077003", carrier="TIM")
    sim_b = SIMcard.objects.create(iccid="8900000000000077004", carrier="TIM")
    line_green = PhoneLine.objects.create(
        phone_number="+5511999997703",
        sim_card=sim_a,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=date(2026, 8, 1),
        whatsapp_seal_expires_on=date(2026, 9, 25),
        whatsapp_seal_email="green2@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    line_gray = PhoneLine.objects.create(
        phone_number="+5511999997704",
        sim_card=sim_b,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_VERIFIED",
        whatsapp_seal_activation_status="NOT_ACTIVATED",
    )
    AllocationService.allocate_line(employee=employee, phone_line=line_green, allocated_by=admin)
    AllocationService.allocate_line(employee=employee, phone_line=line_gray, allocated_by=admin)

    response = client.get(
        reverse("employees:employee_list"),
        {"offset": 0, "limit": 10},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )
    payload = response.json()
    row = next(item for item in payload["data"] if item["id"] == employee.pk)

    # Guarda explicita (nao "JSON impresso"), executada e comprovada
    # ANTES do assert de RED abaixo: nenhum campo financeiro/e-mail do
    # selo pode ser introduzido no payload por causa do indicador. GREEN
    # comprovado hoje (campos nao existem no payload atual); continua
    # obrigatorio quando SVI-05 adicionar a chave de selo por linha.
    serialized_row = str(row)
    assert "whatsapp_seal_email" not in row
    assert "whatsapp_seal_payment" not in row
    assert "whatsapp_seal_monthly_value" not in row
    assert line_green.whatsapp_seal_email not in serialized_row
    assert line_green.get_whatsapp_seal_payment_display() not in serialized_row

    # RED esperado: "line" hoje e so a string concatenada; nenhuma chave
    # por-linha com o selo de cada numero existe ainda no payload.
    assert line_green.seal_status["label"] in row["line"]
    assert line_gray.seal_status["label"] in row["line"]


# --- I09 — employees:employee_detail ---------------------------------------


def test_employee_detail_history_shows_seal_for_active_and_released_allocation(
    admin_client, monkeypatch
):
    """I09 · apresentacao/HTTP · historico de alocacoes do funcionario,
    inclusive liberadas: cada evento usa o FK da PROPRIA alocacao, nao o
    vinculo atual do funcionario. GREEN esperado: SVI-05."""
    monkeypatch.setattr(timezone, "localdate", lambda: FROZEN_TODAY)
    admin, client = admin_client
    employee = Employee.objects.create(
        full_name="Funcionario Historico",
        corporate_email="historico@example.com",
        employee_id="SVI03-EMP-3",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )
    sim_released = SIMcard.objects.create(iccid="8900000000000077005", carrier="TIM")
    sim_active = SIMcard.objects.create(iccid="8900000000000077006", carrier="TIM")
    line_released = PhoneLine.objects.create(
        phone_number="+5511999997705",
        sim_card=sim_released,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_VERIFIED",
        whatsapp_seal_activation_status="NOT_ACTIVATED",
    )
    line_active = PhoneLine.objects.create(
        phone_number="+5511999997706",
        sim_card=sim_active,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=date(2026, 8, 1),
        whatsapp_seal_expires_on=date(2026, 9, 25),
        whatsapp_seal_email="active@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    released_allocation = AllocationService.allocate_line(
        employee=employee, phone_line=line_released, allocated_by=admin
    )
    AllocationService.release_line(released_allocation, released_by=admin)
    AllocationService.allocate_line(employee=employee, phone_line=line_active, allocated_by=admin)

    response = client.get(reverse("employees:employee_detail", args=[employee.pk]))
    content = response.content.decode()

    row_released = _cell(content, line_released.phone_number, tag="tr")
    row_active = _cell(content, line_active.phone_number, tag="tr")

    assert line_released.seal_status["label"] in row_released
    assert line_active.seal_status["label"] in row_active
