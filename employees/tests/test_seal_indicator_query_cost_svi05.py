"""SVI-05 — custo de consulta do indicador de selo em I08 (employee_list).

Ver telecom/test_seal_indicator_query_cost_svi05.py para o contexto geral
desta prova. Aqui: a identidade de cada PhoneLine ja vem prefetched
(Prefetch("allocations", ...select_related("phone_line"))) antes da
projecao do indicador — o numero de consultas do AJAX de load more precisa
ser o mesmo entre poucos e muitos funcionarios/linhas.
"""

from datetime import date

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from core.services.allocation_service import AllocationService
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser

PASSWORD = "StrongPass123"
FROZEN_TODAY = date(2026, 9, 17)


@pytest.fixture
def admin_client(client, db):
    user = SystemUser.objects.create_user(
        email="svi05-emp-cost-admin@example.com", password=PASSWORD, role=SystemUser.Role.ADMIN
    )
    client.force_login(user)
    return user, client


def _make_employees_with_lines(admin, count, prefix):
    for i in range(count):
        employee = Employee.objects.create(
            full_name=f"Funcionario Custo {prefix}-{i}",
            corporate_email=f"custo-{prefix}-{i}@example.com",
            employee_id=f"SVI05-COST-{prefix}-{i}",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        sim = SIMcard.objects.create(iccid=f"890000000000097{prefix}{i:03d}", carrier="TIM")
        line = PhoneLine.objects.create(
            phone_number=f"+551177777{prefix}{i:03d}",
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
            whatsapp_seal="META_ONE",
            whatsapp_seal_activation_status="ACTIVE",
            whatsapp_seal_activated_on=date(2026, 8, 1),
            whatsapp_seal_expires_on=date(2026, 9, 25),
            whatsapp_seal_email=f"emp-cost-{prefix}-{i}@example.com",
            whatsapp_seal_payment="CREDIT_CARD",
        )
        AllocationService.allocate_line(employee=employee, phone_line=line, allocated_by=admin)


@pytest.mark.django_db
def test_employee_list_ajax_seal_indicator_query_count_does_not_grow_with_employee_count(
    admin_client, monkeypatch
):
    """I08 · custo de consulta · numero de consultas do AJAX e o mesmo para
    um lote pequeno e um lote grande de funcionarios/linhas."""
    monkeypatch.setattr(timezone, "localdate", lambda: FROZEN_TODAY)
    admin, client = admin_client
    url = reverse("employees:employee_list")

    _make_employees_with_lines(admin, 2, "1")
    with CaptureQueriesContext(connection) as small_ctx:
        small_response = client.get(
            url, {"offset": 0, "limit": 50}, HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
    assert small_response.status_code == 200

    _make_employees_with_lines(admin, 20, "2")
    with CaptureQueriesContext(connection) as large_ctx:
        large_response = client.get(
            url, {"offset": 0, "limit": 50}, HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
    assert large_response.status_code == 200
    assert len(large_response.json()["data"]) > len(small_response.json()["data"])

    assert len(large_ctx) == len(small_ctx), (
        "Consultas do AJAX de funcionarios cresceram com o numero de "
        f"linhas: {len(small_ctx)} (pequeno) vs {len(large_ctx)} (grande)."
    )
