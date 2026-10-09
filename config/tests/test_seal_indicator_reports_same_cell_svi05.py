"""Conferência corretiva SVI-05 — indicador deve ficar na MESMA célula do
número em reports/home.html, sem coluna adicional (contrato SVI-01: "círculo
junto ao número, preservando colunas existentes").

Fonte da verdade: docs/superpowers/specs/2026-10-05-phone-line-seal-
indicator-design.md. A entrega anterior de SVI-05 (relatada como concluída)
acrescentou uma coluna nova "Indicador" ao final de cada uma das 5 tabelas
de reports/home.html e moveu o círculo para essa coluna; a célula do
telefone ganhou apenas um atributo `title` redundante. Isso viola
"preservando colunas existentes" e "junto ao número" — os testes de SVI-03
(config/tests/test_seal_indicator_reports_svi03.py) não detectaram o desvio
porque seu helper `_cell()` casa os atributos do `<td>` de abertura (então
`title="...label..."` já satisfazia `label in cell`), nunca exigindo que o
rótulo estivesse no CONTEÚDO visível da célula.

Este arquivo prova o desvio (RED) e fixa o contrato: mesma quantidade/ordem
de colunas aprovadas, componente visível (`class="seal-indicator"`) dentro
do MESMO <td> do número.
"""

from datetime import date, datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from allocations.models import LineAllocation
from core.services.allocation_service import AllocationService
from employees.models import Employee
from pendencies.models import AllocationPendency
from telecom.models import LineDailyActionAuditEvent, PhoneLine, SIMcard
from users.models import SystemUser

PASSWORD = "StrongPass123"
PERIOD_START = "2026-08-01"
PERIOD_END = "2026-09-24"

APPROVED_HEADERS = {
    "line_inventory": [
        "Linha", "Status", "Operadora", "Origem", "Canal", "Selo",
        "Vínculo atual", "Data de cadastro", "Registro",
    ],
    "allocations": [
        "Linha", "Usuário vinculado", "Carteira", "Data de alocação",
        "Data de liberação", "Situação", "Registro da linha",
        "Funcionário excluído",
    ],
    "pendencies": [
        "Linha", "Funcionário", "Solicitante", "Responsável", "Situação",
        "Motivo", "Tempo em aberto", "Registro", "Funcionário excluído",
    ],
    "line_history": [
        "Linha", "Data/hora do evento", "Fonte", "Tipo de evento", "Ator",
        "Alocação relacionada", "Alterações", "Registro da linha",
        "Funcionário excluído",
    ],
    "whatsapp_seal": [
        "Linha", "Tipo do selo", "Ativação do selo", "Pagamento",
        "E-mail cadastrado", "Vencimento", "Situação do vencimento",
        "Registro",
    ],
}


def _report_url(relatorio, **extra):
    from urllib.parse import urlencode

    pairs = [
        ("relatorio", relatorio),
        ("data_inicial", PERIOD_START),
        ("data_final", PERIOD_END),
    ]
    pairs.extend(extra.items())
    return f"{reverse('reports_home')}?{urlencode(pairs)}"


def _thead_block(html):
    start = html.index("<thead>")
    end = html.index("</thead>", start)
    return html[start:end]


def _headers(html):
    import re

    # "<th(?=[\\s>])" evita casar "<thead>" (que tambem comeca com "<th").
    return re.findall(r"<th(?=[\s>])[^>]*>(.*?)</th>", _thead_block(html), re.DOTALL)


def _phone_cell(html, phone_number):
    import re

    pattern = re.compile(
        rf"<td[^>]*>\s*{re.escape(phone_number)}.*?</td>", re.DOTALL
    )
    match = pattern.search(html)
    if not match:
        raise AssertionError(f"Nenhum <td> contendo {phone_number!r} encontrado.")
    return match.group(0)


@pytest.fixture
def admin_client(client, db, monkeypatch):
    monkeypatch.setattr(timezone, "localdate", lambda: date(2026, 9, 17))
    user = SystemUser.objects.create_user(
        email="svi05-same-cell-admin@example.com", password=PASSWORD, role=SystemUser.Role.ADMIN
    )
    client.force_login(user)
    return user, client


@pytest.fixture
def sim(db):
    return SIMcard.objects.create(iccid="8900000000000088070", carrier="TIM")


@pytest.fixture
def line_green(sim):
    line = PhoneLine.objects.create(
        phone_number="+5511999998870",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=date(2026, 8, 1),
        whatsapp_seal_expires_on=date(2026, 9, 25),
        whatsapp_seal_email="report-samecell@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    PhoneLine.objects.filter(pk=line.pk).update(
        created_at=timezone.make_aware(datetime(2026, 9, 10, 10, 0))
    )
    return line


def test_whatsapp_seal_report_keeps_approved_columns_and_indicator_in_phone_cell(
    admin_client, line_green
):
    _admin, client = admin_client
    response = client.get(_report_url("whatsapp_seal", linha=line_green.phone_number))
    content = response.content.decode()

    assert _headers(content) == APPROVED_HEADERS["whatsapp_seal"]
    cell = _phone_cell(content, line_green.phone_number)
    assert "seal-indicator" in cell


def test_line_inventory_report_keeps_approved_columns_and_indicator_in_phone_cell(
    admin_client, line_green
):
    _admin, client = admin_client
    response = client.get(_report_url("line_inventory", linha=line_green.phone_number))
    content = response.content.decode()

    assert _headers(content) == APPROVED_HEADERS["line_inventory"]
    cell = _phone_cell(content, line_green.phone_number)
    assert "seal-indicator" in cell


def test_allocations_report_keeps_approved_columns_and_indicator_in_phone_cell(
    admin_client, line_green
):
    admin, client = admin_client
    employee = Employee.objects.create(
        full_name="Funcionario Mesma Celula Alocacoes",
        corporate_email="mesma-celula-alocacoes@example.com",
        employee_id="SVI05-SAME-CELL-ALLOC-1",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )
    AllocationService.allocate_line(employee=employee, phone_line=line_green, allocated_by=admin)
    LineAllocation.objects.filter(employee=employee, phone_line=line_green, is_active=True).update(
        allocated_at=timezone.make_aware(datetime(2026, 9, 10, 10, 0))
    )

    response = client.get(_report_url("allocations", linha=line_green.phone_number))
    content = response.content.decode()

    assert _headers(content) == APPROVED_HEADERS["allocations"]
    cell = _phone_cell(content, line_green.phone_number)
    assert "seal-indicator" in cell


def test_pendencies_report_keeps_approved_columns_and_indicator_in_phone_cell(
    admin_client, line_green
):
    admin, client = admin_client
    employee = Employee.objects.create(
        full_name="Funcionario Mesma Celula Pendencias",
        corporate_email="mesma-celula-pendencias@example.com",
        employee_id="SVI05-SAME-CELL-PEND-1",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )
    AllocationService.allocate_line(employee=employee, phone_line=line_green, allocated_by=admin)
    allocation = LineAllocation.objects.get(
        employee=employee, phone_line=line_green, is_active=True
    )
    pendency = AllocationPendency.objects.create(
        employee=employee,
        allocation=allocation,
        action=AllocationPendency.ActionType.PENDING,
    )
    AllocationPendency.objects.filter(pk=pendency.pk).update(
        pendency_submitted_at=timezone.make_aware(datetime(2026, 9, 10, 10, 0))
    )

    response = client.get(_report_url("pendencies", linha=line_green.phone_number))
    content = response.content.decode()

    assert _headers(content) == APPROVED_HEADERS["pendencies"]
    cell = _phone_cell(content, line_green.phone_number)
    assert "seal-indicator" in cell


def test_line_history_report_keeps_approved_columns_and_indicator_in_phone_cell(
    admin_client, line_green
):
    _admin, client = admin_client
    LineDailyActionAuditEvent.objects.create(
        event_type=LineDailyActionAuditEvent.EventType.OPENED,
        source=LineDailyActionAuditEvent.Source.LINE_ALLOCATION,
        source_object_id=line_green.pk,
        occurred_at=timezone.make_aware(datetime(2026, 9, 10, 10, 0)),
        phone_line=line_green,
        before_state={},
        after_state={},
    )

    response = client.get(_report_url("line_history", linha=line_green.phone_number))
    content = response.content.decode()

    assert _headers(content) == APPROVED_HEADERS["line_history"]
    cell = _phone_cell(content, line_green.phone_number)
    assert "seal-indicator" in cell
