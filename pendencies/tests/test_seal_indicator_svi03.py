"""SVI-03 — testes RED do indicador visual de selo junto ao número.

Fonte da verdade: docs/superpowers/specs/2026-10-05-phone-line-seal-
indicator-design.md. Cobre I12 (pendencies:detail, payload JSON do modal
de linha/pendencia) da matriz.

_pendency_to_json (pendencies/views.py) hoje devolve a chave "linha" so
com o numero (string); nenhuma chave equivalente a tipo/situacao do selo
existe no payload. GREEN esperado: SVI-05, reaproveitando a projecao
central de SVI-04. Autorizacao/escopo proprios dos endpoints de pendencia
sao preservados — o teste nao amplia nem reduz quem pode ver o payload.
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


@pytest.fixture
def admin_client(client, db):
    user = SystemUser.objects.create_user(
        email="svi03-pend-admin@example.com", password=PASSWORD, role=SystemUser.Role.ADMIN
    )
    client.force_login(user)
    return user, client


def test_pendency_detail_json_carries_no_seal_indicator_for_its_line(admin_client, monkeypatch):
    """I12 · JSON · GREEN esperado: SVI-05."""
    monkeypatch.setattr(timezone, "localdate", lambda: date(2026, 9, 17))
    admin, client = admin_client
    employee = Employee.objects.create(
        full_name="Funcionario Pendencia",
        corporate_email="pendencia@example.com",
        employee_id="SVI03-PEND-1",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )
    sim = SIMcard.objects.create(iccid="8900000000000077020", carrier="TIM")
    line = PhoneLine.objects.create(
        phone_number="+5511999997720",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=date(2026, 8, 1),
        whatsapp_seal_expires_on=date(2026, 9, 25),
        whatsapp_seal_email="pend@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    AllocationService.allocate_line(employee=employee, phone_line=line, allocated_by=admin)
    allocation = LineAllocation.objects.get(employee=employee, phone_line=line, is_active=True)

    response = client.get(
        reverse("pendencies:detail"),
        {"employee_id": employee.pk, "allocation_id": allocation.pk},
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["linha"] == line.phone_number
    serialized = str(payload)

    # Guarda explicita (nao "JSON impresso"), executada e comprovada
    # ANTES do assert de RED abaixo: nenhum campo financeiro/e-mail do
    # selo pode ser introduzido no payload por causa do indicador. GREEN
    # comprovado hoje (campos nao existem no payload atual); continua
    # obrigatorio quando SVI-05 adicionar a chave de selo.
    assert "whatsapp_seal_email" not in payload
    assert "whatsapp_seal_payment" not in payload
    assert "whatsapp_seal_monthly_value" not in payload
    assert line.whatsapp_seal_email not in serialized
    assert line.get_whatsapp_seal_payment_display() not in serialized

    # RED esperado: nenhuma chave do payload hoje carrega o rotulo do selo
    # da linha (nem "seal_status", nem embutido em "linha").
    assert line.seal_status["label"] in serialized
