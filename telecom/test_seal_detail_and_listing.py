"""SEL-08 — detalhe da linha, indicadores na listagem e payloads JSON."""

from datetime import date

import pytest
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from core.services.allocation_service import AllocationService
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser


@pytest.fixture
def sim(db):
    return SIMcard.objects.create(iccid="8900000000000077771", carrier="TIM")


@pytest.fixture
def admin_client(client, db):
    user = SystemUser.objects.create_user(
        email="sel08-admin@example.com", password="test-only", role=SystemUser.Role.ADMIN
    )
    client.force_login(user)
    return client


@pytest.fixture
def line_with_seal(sim):
    return PhoneLine.objects.create(
        phone_number="+5511999997771",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activated_on=date(2026, 9, 1),
        whatsapp_seal_expires_on=date(2026, 10, 17),
        whatsapp_seal_email="seal@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )


@pytest.fixture
def line_without_seal(sim):
    other_sim = SIMcard.objects.create(iccid="8900000000000077772", carrier="TIM")
    return PhoneLine.objects.create(
        phone_number="+5511999997772",
        sim_card=other_sim,
        status=PhoneLine.Status.AVAILABLE,
    )


# --- Detalhe -----------------------------------------------------------


@pytest.mark.parametrize(
    "seal,seal_display",
    [("META_ONE", "META ONE"), ("META_VERIFIED", "META VERIFICADO")],
)
def test_detail_shows_full_seal_block(admin_client, sim, seal, seal_display):
    line = PhoneLine.objects.create(
        phone_number="+5511999996001",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal=seal,
        whatsapp_seal_activated_on=date(2026, 9, 1),
        whatsapp_seal_expires_on=date(2026, 10, 17),
        whatsapp_seal_email="seal@example.com",
        whatsapp_seal_payment="GOOGLE_GIFT_CARD",
    )

    response = admin_client.get(reverse("telecom:phoneline_detail", args=[line.pk]))

    assert response.status_code == 200
    content = response.content.decode()
    assert "SELO WHATS LINEOPS" in content
    assert seal_display in content
    assert "01/09/2026" in content
    assert "17/10/2026" in content
    assert "seal@example.com" in content
    assert "GIFT CARD GOOGLE" in content
    assert line.seal_status["label"] in content


def test_detail_shows_sem_selo_without_expiry_alert(admin_client, line_without_seal):
    response = admin_client.get(
        reverse("telecom:phoneline_detail", args=[line_without_seal.pk])
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "SELO WHATS LINEOPS" in content
    assert "Sem selo" in content
    assert "Data da ativação" not in content
    assert "Data do vencimento" not in content
    assert "E-mail cadastrado" not in content
    assert "Tipo de pagamento" not in content


@pytest.mark.parametrize(
    "days,tone,label,css_class",
    [
        (8, "neutral", "Vence em 25/09/2026", "seal-tone-neutral"),
        (7, "warning", "Vence em 7 dias", "seal-tone-warning"),
        (1, "warning", "Vence em 1 dia", "seal-tone-warning"),
        (0, "today", "Vence hoje", "seal-tone-today"),
        (-1, "expired", "Vencido há 1 dia", "seal-tone-expired"),
    ],
)
def test_detail_indicator_tone_and_label(
    admin_client, sim, monkeypatch, days, tone, label, css_class
):
    monkeypatch.setattr(timezone, "localdate", lambda: date(2026, 9, 17))
    line = PhoneLine.objects.create(
        phone_number=f"+551199999{6100 + days}",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activated_on=date(2026, 8, 1),
        whatsapp_seal_expires_on=date(2026, 9, 17 + days) if days >= 0 else date(2026, 9, 16),
        whatsapp_seal_email="seal@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    assert line.seal_status == {"tone": tone, "label": label}

    response = admin_client.get(reverse("telecom:phoneline_detail", args=[line.pk]))
    content = response.content.decode()

    assert label in content
    assert css_class in content


# --- Listagem (overview) ------------------------------------------------


def test_overview_initial_listing_shows_seal_type_and_indicator(
    admin_client, line_with_seal, line_without_seal
):
    response = admin_client.get(reverse("telecom:overview"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "META ONE" in content
    assert "Sem selo" in content


def test_overview_ajax_main_payload_uses_seal_status_and_omits_email(
    admin_client, line_with_seal
):
    response = admin_client.get(
        reverse("telecom:overview"),
        {"table": "main", "offset": 0},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )

    assert response.status_code == 200
    payload = response.json()
    row = next(item for item in payload["data"] if item["id"] == line_with_seal.pk)

    assert row["seal_status"] == line_with_seal.seal_status
    assert row["whatsapp_seal_display"] == "META ONE"
    assert "whatsapp_seal_email" not in row
    assert "whatsapp_seal_activated_on" not in row
    assert "whatsapp_seal_expires_on" not in row
    assert "whatsapp_seal_payment" not in row
    assert "seal@example.com" not in response.content.decode()


def test_overview_ajax_load_more_second_page_matches_first_page_shape(
    admin_client, sim
):
    lines = []
    for i in range(3):
        lines.append(
            PhoneLine.objects.create(
                phone_number=f"+551199999510{i}",
                sim_card=SIMcard.objects.create(
                    iccid=f"890000000000008888{i}", carrier="TIM"
                ),
                status=PhoneLine.Status.AVAILABLE,
                whatsapp_seal="META_VERIFIED" if i == 1 else "",
                whatsapp_seal_activated_on=date(2026, 9, 1) if i == 1 else None,
                whatsapp_seal_expires_on=date(2026, 9, 18) if i == 1 else None,
                whatsapp_seal_email="seal2@example.com" if i == 1 else "",
                whatsapp_seal_payment="CREDIT_CARD" if i == 1 else "",
            )
        )

    first_page = admin_client.get(
        reverse("telecom:overview"),
        {"table": "main", "offset": 0, "limit": 1},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    ).json()
    second_page = admin_client.get(
        reverse("telecom:overview"),
        {"table": "main", "offset": 1, "limit": 1},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    ).json()

    assert set(first_page["data"][0].keys()) == set(second_page["data"][0].keys())
    assert "seal_status" in first_page["data"][0]
    assert "seal_status" in second_page["data"][0]
    assert "whatsapp_seal_display" in first_page["data"][0]
    assert "whatsapp_seal_display" in second_page["data"][0]


def test_overview_scope_excludes_unauthorized_line_seal_data(sim):
    from django.test import Client

    manager = SystemUser.objects.create_user(
        email="sel08-manager@example.com", password="123456", role=SystemUser.Role.GERENTE
    )
    supervisor = SystemUser.objects.create_user(
        email="sel08-super@example.com",
        password="123456",
        role=SystemUser.Role.SUPER,
        manager_email="sel08-manager@example.com",
    )
    backoffice = SystemUser.objects.create_user(
        email="sel08-backoffice@example.com",
        password="123456",
        role=SystemUser.Role.BACKOFFICE,
        supervisor_email="sel08-super@example.com",
    )
    other_supervisor = SystemUser.objects.create_user(
        email="sel08-other-super@example.com",
        password="123456",
        role=SystemUser.Role.SUPER,
        manager_email="sel08-manager@example.com",
    )

    managed_employee = Employee.objects.create(
        full_name="Vinculado SEL08",
        corporate_email=supervisor.email,
        employee_id="SEL08-1",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )
    unmanaged_employee = Employee.objects.create(
        full_name="Nao Vinculado SEL08",
        corporate_email=other_supervisor.email,
        employee_id="SEL08-2",
        teams="Araquari",
        status=Employee.Status.ACTIVE,
    )

    managed_line = PhoneLine.objects.create(
        phone_number="+5511999995201",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        origem=PhoneLine.Origem.SRVMEMU_01,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activated_on=date(2026, 9, 1),
        whatsapp_seal_expires_on=date(2026, 10, 17),
        whatsapp_seal_email="managed-seal@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    unmanaged_line = PhoneLine.objects.create(
        phone_number="+5511999995202",
        sim_card=SIMcard.objects.create(iccid="8900000000000099993", carrier="TIM"),
        status=PhoneLine.Status.AVAILABLE,
        origem=PhoneLine.Origem.SRVMEMU_02,
        whatsapp_seal="META_VERIFIED",
        whatsapp_seal_activated_on=date(2026, 9, 1),
        whatsapp_seal_expires_on=date(2026, 10, 17),
        whatsapp_seal_email="unmanaged-seal@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    AllocationService.allocate_line(
        employee=managed_employee, phone_line=managed_line, allocated_by=manager
    )
    AllocationService.allocate_line(
        employee=unmanaged_employee, phone_line=unmanaged_line, allocated_by=manager
    )

    client = Client()
    client.force_login(backoffice)

    detail_allowed = client.get(reverse("telecom:phoneline_detail", args=[managed_line.pk]))
    detail_denied = client.get(reverse("telecom:phoneline_detail", args=[unmanaged_line.pk]))
    assert detail_allowed.status_code == 200
    assert detail_denied.status_code == 404

    ajax = client.get(
        reverse("telecom:overview"),
        {"table": "main", "offset": 0},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    ).json()
    visible_ids = {row["id"] for row in ajax["data"]}
    assert managed_line.pk in visible_ids
    assert unmanaged_line.pk not in visible_ids
    assert b"unmanaged-seal@example.com" not in client.get(reverse("telecom:overview")).content


def test_overview_ajax_seal_indicator_adds_no_per_line_query(admin_client, sim):
    for i in range(3):
        PhoneLine.objects.create(
            phone_number=f"+551199999530{i}",
            sim_card=SIMcard.objects.create(
                iccid=f"890000000000008899{i}", carrier="TIM"
            ),
            status=PhoneLine.Status.AVAILABLE,
            whatsapp_seal="META_ONE",
            whatsapp_seal_activated_on=date(2026, 9, 1),
            whatsapp_seal_expires_on=date(2026, 10, 17),
            whatsapp_seal_email="seal@example.com",
            whatsapp_seal_payment="CREDIT_CARD",
        )

    with CaptureQueriesContext(connection) as ctx_one:
        admin_client.get(
            reverse("telecom:overview"),
            {"table": "main", "offset": 0, "limit": 1},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
    with CaptureQueriesContext(connection) as ctx_three:
        admin_client.get(
            reverse("telecom:overview"),
            {"table": "main", "offset": 0, "limit": 3},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    assert len(ctx_one) == len(ctx_three)


def test_overview_js_seal_cell_uses_safe_dom_apis_not_raw_innerhtml():
    with open("templates/telecom/overview.html", encoding="utf-8") as fh:
        source = fh.read()

    assert "createSealCell" in source or "createSealBadge" in source
    # A célula do selo não deve ser montada por interpolação de template
    # string dentro de innerHTML (linha.whatsapp_seal_display / seal_status).
    assert "${line.whatsapp_seal_display}" not in source
    assert "${line.seal_status" not in source
