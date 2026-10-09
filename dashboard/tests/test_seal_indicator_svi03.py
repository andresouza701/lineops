"""SVI-03 — testes RED do indicador visual de selo junto ao número.

Fonte da verdade: docs/superpowers/specs/2026-10-05-phone-line-seal-
indicator-design.md. Cobre I11 (daily_user_action_board) e I13-I17
(daily_indicator_day_breakdown: disponiveis/entregues/reconectados/
novos/usuarios com linha) da matriz — todos os cinco, incluindo I15
(reconectados), fechado nesta retificacao via fluxo real de alocacao/
liberacao/realocacao (sem mock de DailyIndicatorService nem de
seal_status).

Nota de execucao: dashboard/tests.py (modulo legado com fixtures
equivalentes) nao e coletavel pelo pytest deste projeto hoje —
"import file mismatch" contra o PACOTE dashboard/tests/ (mesmo nome,
dois tipos de modulo). Confirmado rodando
`pytest dashboard/tests.py --collect-only` isoladamente. Nao e corrigido
aqui (fora do escopo de SVI-03, nenhum codigo de aplicacao ou teste
preexistente alterado) — fixtures abaixo sao construidas do zero, sem
depender daquele arquivo.

Gap tecnico registrado para I13-I17 (nao testado como unidade, por nao
inventar contrato ainda indefinido): available_numbers/new_numbers
chegam ao template como lista de STRINGS; delivered_numbers/
reconnected_numbers chegam como dicts {numero, usuario, carteira}; em
nenhum dos dois casos a identidade de PhoneLine (e portanto o selo)
sobrevive para o template. GREEN esperado: SVI-05, reaproveitando a
projecao central de SVI-04.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from core.services.allocation_service import AllocationService
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser

PASSWORD = "StrongPass123"


def _cell(html, marker, tag="li"):
    idx = html.index(marker)
    start = html.rindex(f"<{tag}", 0, idx)
    end = html.index(f"</{tag}>", idx) + len(f"</{tag}>")
    return html[start:end]


@pytest.fixture
def admin_client(client, db):
    user = SystemUser.objects.create_user(
        email="svi03-dash-admin@example.com", password=PASSWORD, role=SystemUser.Role.ADMIN
    )
    client.force_login(user)
    return user, client


@pytest.fixture
def super_client(client, db):
    # daily_user_action_board oculta linhas "sem pendencia" quando o
    # usuario logado e ADMIN (apply_action_board_visibility_rules /
    # should_hide_row_for_admin). Usar SUPER com escopo direto no
    # funcionario evita esse filtro de visibilidade de negocio, que nao
    # tem relacao com o indicador de selo sob teste aqui.
    user = SystemUser.objects.create_user(
        email="svi03-dash-super@example.com", password=PASSWORD, role=SystemUser.Role.SUPER
    )
    client.force_login(user)
    return user, client


@pytest.fixture
def employee_with_line(super_client):
    admin, client = super_client
    employee = Employee.objects.create(
        full_name="Funcionario Board SVI03",
        corporate_email=admin.email,
        employee_id="SVI03-BOARD-1",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )
    sim = SIMcard.objects.create(iccid="8900000000000077050", carrier="TIM")
    line = PhoneLine.objects.create(
        phone_number="+5511999997750",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=timezone.localdate() - timedelta(days=30),
        whatsapp_seal_expires_on=timezone.localdate() + timedelta(days=8),
        whatsapp_seal_email="board@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    AllocationService.allocate_line(employee=employee, phone_line=line, allocated_by=admin)
    return employee, line


# --- I11 — daily_user_action_board ----------------------------------------


def test_daily_user_action_board_row_shows_seal_indicator_for_its_line(
    super_client, employee_with_line
):
    """I11 · apresentacao/HTTP · GREEN esperado: SVI-05. O modal JS-only
    de detalhe da linha (populado via data-line-*) nao e provado por
    Django test client — registrado como lacuna reservada para SVI-06."""
    _admin, client = super_client
    _employee, line = employee_with_line

    response = client.get(reverse("daily_user_action_board"))
    content = response.content.decode()

    button = _cell(content, line.phone_number, tag="button")
    assert line.seal_status["label"] in button


# --- I13-I17 — daily_indicator_day_breakdown -------------------------------


def test_daily_indicator_day_breakdown_available_list_shows_seal_indicator(admin_client, db):
    """I13 · apresentacao/HTTP · GREEN esperado: SVI-05."""
    _admin, client = admin_client
    sim = SIMcard.objects.create(iccid="8900000000000077051", carrier="TIM")
    line = PhoneLine.objects.create(
        phone_number="+5511999997751",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=timezone.localdate() - timedelta(days=30),
        whatsapp_seal_expires_on=timezone.localdate() + timedelta(days=8),
        whatsapp_seal_email="avail@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )

    today_iso = timezone.localdate().strftime("%Y-%m-%d")
    response = client.get(reverse("daily_indicator_day_breakdown", kwargs={"day": today_iso}))
    indicator = response.context["indicator"]
    assert line.phone_number in indicator["available_numbers"]

    content = response.content.decode()
    item = _cell(content, line.phone_number, tag="li")
    assert line.seal_status["label"] in item


def test_daily_indicator_day_breakdown_delivered_list_shows_seal_indicator(
    super_client, employee_with_line
):
    """I14 · apresentacao/HTTP · GREEN esperado: SVI-05. A alocacao criada
    hoje entra em delivered_numbers do dia corrente."""
    _admin, client = super_client
    _employee, line = employee_with_line

    today_iso = timezone.localdate().strftime("%Y-%m-%d")
    response = client.get(reverse("daily_indicator_day_breakdown", kwargs={"day": today_iso}))
    indicator = response.context["indicator"]
    assert any(item["numero"] == line.phone_number for item in indicator["delivered_numbers"])

    content = response.content.decode()
    item = _cell(content, line.phone_number, tag="li")
    assert line.seal_status["label"] in item


def test_daily_indicator_day_breakdown_reconnected_list_shows_seal_indicator(super_client):
    """I15 · apresentacao/HTTP · GREEN esperado: SVI-05.

    Regra real de reconexao (core/services/daily_indicator_service.py::
    DailyIndicatorService.get_reconnected_allocations_queryset): a MESMA
    linha volta para o MESMO funcionario apos uma liberacao anterior, no
    mesmo dia. Fluxo real via AllocationService (aloca -> libera ->
    realoca), sem mock de calculo de reconectados nem de seal_status.
    """
    admin, client = super_client
    employee = Employee.objects.create(
        full_name="Funcionario Reconectado SVI03",
        corporate_email=admin.email,
        employee_id="SVI03-RECONNECT-1",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )
    sim = SIMcard.objects.create(iccid="8900000000000077053", carrier="TIM")
    line = PhoneLine.objects.create(
        phone_number="+5511999997753",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_VERIFIED",
        whatsapp_seal_activation_status="NOT_ACTIVATED",
    )

    first_allocation = AllocationService.allocate_line(
        employee=employee, phone_line=line, allocated_by=admin
    )
    AllocationService.release_line(first_allocation, released_by=admin)
    AllocationService.allocate_line(employee=employee, phone_line=line, allocated_by=admin)

    today_iso = timezone.localdate().strftime("%Y-%m-%d")
    response = client.get(reverse("daily_indicator_day_breakdown", kwargs={"day": today_iso}))
    indicator = response.context["indicator"]

    # Comprova a elegibilidade ANTES de avaliar o indicador: o numero
    # precisa estar de fato em Reconectados, nao em outra lista.
    assert any(
        item["numero"] == line.phone_number for item in indicator["reconnected_numbers"]
    )

    content = response.content.decode()
    item = _cell(content, line.phone_number, tag="li")
    assert line.seal_status["label"] in item


def test_daily_indicator_day_breakdown_new_list_shows_seal_indicator(admin_client, db):
    """I16 · apresentacao/HTTP · GREEN esperado: SVI-05. Linha criada hoje
    conta como numero novo do dia (created_at = hoje)."""
    _admin, client = admin_client
    sim = SIMcard.objects.create(iccid="8900000000000077052", carrier="TIM")
    line = PhoneLine.objects.create(
        phone_number="+5511999997752",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_VERIFIED",
        whatsapp_seal_activation_status="NOT_ACTIVATED",
    )

    today_iso = timezone.localdate().strftime("%Y-%m-%d")
    response = client.get(reverse("daily_indicator_day_breakdown", kwargs={"day": today_iso}))
    indicator = response.context["indicator"]
    assert line.phone_number in indicator["new_numbers"]

    content = response.content.decode()
    item = _cell(content, line.phone_number, tag="li")
    assert line.seal_status["label"] in item


def test_daily_indicator_day_breakdown_users_with_line_shows_seal_indicator(
    super_client, employee_with_line
):
    """I17 · apresentacao/HTTP · GREEN esperado: SVI-05."""
    _admin, client = super_client
    employee, line = employee_with_line

    today_iso = timezone.localdate().strftime("%Y-%m-%d")
    response = client.get(
        reverse("daily_indicator_day_breakdown", kwargs={"day": today_iso})
    )
    indicator = response.context["indicator"]
    assert any(
        user.get("linha") == line.phone_number for user in indicator["users_with_line"]
    )

    content = response.content.decode()
    item = _cell(content, line.phone_number, tag="li")
    assert line.seal_status["label"] in item
