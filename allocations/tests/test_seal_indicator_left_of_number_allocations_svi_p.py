"""SVI-P02/P03 — ajuste aprovado 2026-10-11: indicador de selo antes do
numero, um unico espaco de separador. Cobre I10 (allocations:allocation_edit,
campo readonly) e I27 (admin LineAllocation, telefone vem do __str__
composto "numero - status").

Fonte da verdade: docs/superpowers/specs/2026-10-05-phone-line-seal-
indicator-design.md, secao "Ajuste aprovado — indicador à esquerda do
número — 2026-10-11".
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
FROZEN_TODAY = date(2026, 9, 17)


def _cell(html, marker, tag="td"):
    idx = html.index(marker)
    start = html.rindex(f"<{tag}", 0, idx)
    end = html.index(f"</{tag}>", idx) + len(f"</{tag}>")
    return html[start:end]


def _assert_indicator_immediately_before(html, number):
    idx = html.index(number)
    assert html[idx - 1] == " ", (
        f"esperado um unico espaco antes do numero, achou {html[idx - 2:idx]!r}"
    )
    assert html[idx - 2] == ">", (
        f"esperado espaco logo depois do fechamento do indicador, achou {html[idx - 3:idx]!r}"
    )
    assert "seal-indicator" in html[:idx]


@pytest.fixture
def admin_client(client, db):
    user = SystemUser.objects.create_user(
        email="svi-p-alloc-admin@example.com", password=PASSWORD, role=SystemUser.Role.ADMIN
    )
    client.force_login(user)
    return user, client


@pytest.fixture
def superuser_client(client, db):
    user = SystemUser.objects.create_superuser(
        email="svi-p-alloc-root@example.com", password=PASSWORD, role=SystemUser.Role.ADMIN
    )
    client.force_login(user)
    return user, client


@pytest.fixture
def employee(db):
    return Employee.objects.create(
        full_name="Funcionario SVI-P Alocacao",
        corporate_email="svi-p-alocacao@example.com",
        employee_id="SVI-P-ALLOC-1",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )


@pytest.fixture
def line_green(monkeypatch):
    monkeypatch.setattr(timezone, "localdate", lambda: FROZEN_TODAY)
    sim = SIMcard.objects.create(iccid="8900000000000092001", carrier="TIM")
    return PhoneLine.objects.create(
        phone_number="+5511999992001",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=date(2026, 8, 1),
        whatsapp_seal_expires_on=date(2026, 9, 25),
        whatsapp_seal_email="svi-p-alloc@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )


# --- I10 — allocations:allocation_edit -------------------------------------


def test_allocation_edit_places_indicator_before_readonly_input(
    admin_client, employee, line_green
):
    admin, client = admin_client
    AllocationService.allocate_line(employee=employee, phone_line=line_green, allocated_by=admin)
    allocation = LineAllocation.objects.get(
        employee=employee, phone_line=line_green, is_active=True
    )

    response = client.get(reverse("allocations:allocation_edit", args=[allocation.pk]))
    content = response.content.decode()

    # O indicador precisa vir ANTES da tag <input> (nao depois), e o value
    # do input precisa continuar intacto (sem decoracao por dentro).
    value_idx = content.index(f'value="{line_green.phone_number}"')
    input_tag_start = content.rindex("<input", 0, value_idx)
    assert "seal-indicator" in content[:input_tag_start]
    assert content[input_tag_start - 1] == " ", (
        f"esperado um espaco antes de <input>, achou {content[input_tag_start - 2:input_tag_start]!r}"
    )
    assert content[input_tag_start - 2] == ">"
    assert f'value="{line_green.phone_number}seal' not in content


# --- SVI-P06 achado C — composicao lateral explicita (sem input full-width)


def test_allocation_edit_wraps_indicator_and_input_in_inline_container(
    admin_client, employee, line_green
):
    """O input .form-control e display:block com largura 100%
    (Bootstrap). So colocar o indicador antes da tag nao compoe os dois
    lado a lado — precisa de um wrapper flex dedicado
    (.seal-field-inline, ver static/css/styles.css)."""
    admin, client = admin_client
    AllocationService.allocate_line(employee=employee, phone_line=line_green, allocated_by=admin)
    allocation = LineAllocation.objects.get(
        employee=employee, phone_line=line_green, is_active=True
    )

    response = client.get(reverse("allocations:allocation_edit", args=[allocation.pk]))
    content = response.content.decode()

    wrapper_marker = '<div class="seal-field-inline">'
    assert wrapper_marker in content
    wrapper_idx = content.index(wrapper_marker)
    seal_idx = content.index("seal-indicator", wrapper_idx)
    value_idx = content.index(f'value="{line_green.phone_number}"', seal_idx)
    close_idx = content.index("</div>", value_idx)
    assert wrapper_idx < seal_idx < value_idx < close_idx


# --- I27 — admin:allocations_lineallocation_changelist ---------------------


def test_line_allocation_admin_places_indicator_before_number(superuser_client, employee, line_green):
    admin, client = superuser_client
    AllocationService.allocate_line(employee=employee, phone_line=line_green, allocated_by=admin)
    line_green.refresh_from_db()  # allocate_line muda o status para ALLOCATED

    response = client.get(reverse("admin:allocations_lineallocation_changelist"))
    content = response.content.decode()

    cell = _cell(content, line_green.phone_number, tag="td")
    _assert_indicator_immediately_before(cell, line_green.phone_number)
    # O sufixo " - status" do __str__ de PhoneLine (nao alterado por este
    # ajuste) precisa continuar DEPOIS do numero, nunca antes.
    idx = cell.index(line_green.phone_number) + len(line_green.phone_number)
    assert cell[idx:].startswith(f" - {line_green.status}")
