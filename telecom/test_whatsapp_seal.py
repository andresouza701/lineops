from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from allocations.models import LineAllocation
from core.services.allocation_service import AllocationService
from employees.models import Employee
from telecom.forms import PhoneLineForm, PhoneLineUpdateForm
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser


@pytest.fixture
def sim(db):
    return SIMcard.objects.create(iccid="8900000000000088881", carrier="TIM")


@pytest.fixture
def payload(sim):
    return {
        "phone_number": "+5511999998881", "sim_card": sim.pk,
        "whatsapp_seal": "META_ONE",
        "whatsapp_seal_activated_on": "2026-09-01",
        "whatsapp_seal_expires_on": "2026-10-17",
        "whatsapp_seal_email": "seal@example.com",
        "whatsapp_seal_payment": "CREDIT_CARD",
    }


@pytest.mark.parametrize("seal", ["META_ONE", "META_VERIFIED"])
@pytest.mark.parametrize("missing", ["whatsapp_seal_activated_on", "whatsapp_seal_expires_on", "whatsapp_seal_email", "whatsapp_seal_payment"])
def test_seal_requires_each_field(payload, seal, missing):
    payload.update(whatsapp_seal=seal)
    payload[missing] = ""
    form = PhoneLineForm(data=payload)
    assert not form.is_valid()
    assert missing in form.errors


@pytest.mark.parametrize("seal,payment", [("META_ONE", "CREDIT_CARD"), ("META_VERIFIED", "GOOGLE_GIFT_CARD")])
def test_create_persists_manual_dates(payload, seal, payment):
    payload.update(whatsapp_seal=seal, whatsapp_seal_payment=payment)
    form = PhoneLineForm(data=payload)
    assert form.is_valid(), form.errors
    line = form.save()
    line.refresh_from_db()
    assert line.whatsapp_seal == seal
    assert line.whatsapp_seal_expires_on == date(2026, 10, 17)
    assert line.whatsapp_seal_activated_on == date(2026, 9, 1)
    assert line.whatsapp_seal_email == "seal@example.com"
    assert line.whatsapp_seal_payment == payment
    assert line.activated_at is None


@pytest.mark.parametrize("field,value", [("whatsapp_seal", "OTHER"), ("whatsapp_seal_email", "invalid"), ("whatsapp_seal_payment", "CASH"), ("whatsapp_seal_expires_on", "2026-08-31")])
def test_invalid_seal_data(payload, field, value):
    payload[field] = value
    form = PhoneLineForm(data=payload)
    assert not form.is_valid()
    assert field in form.errors


def test_equal_dates_accepted(payload):
    payload["whatsapp_seal_expires_on"] = payload["whatsapp_seal_activated_on"]
    form = PhoneLineForm(data=payload)
    assert form.is_valid(), form.errors


def test_invalid_format_error_not_duplicated_with_required_message(payload):
    """SEL-10: um valor preenchido em formato inválido (ex.: e-mail sem "@")
    falha na validação de campo do Django (EmailField) e por isso fica de
    fora de cleaned_data; construct_instance() então não atualiza o atributo
    da instância, que permanece vazio, e PhoneLine.clean() (via
    validate_seal_fields, disparado automaticamente por _post_clean) soma a
    mensagem de obrigatoriedade à mesma lista de erros — mesmo o campo tendo
    sido preenchido. Mensagem contraditória: diz que o campo é obrigatório
    quando na verdade um valor foi digitado, só que num formato inválido."""
    payload["whatsapp_seal_email"] = "nao-e-um-email"
    form = PhoneLineForm(data=payload)
    assert not form.is_valid()
    assert form.errors["whatsapp_seal_email"] == [
        "Insira um endereço de email válido."
    ]


def test_invalid_email_format_on_edit_does_not_reuse_stale_value(payload):
    """SEL-11: mesma classe de bug de test_invalid_format_error_not_duplicated_
    with_required_message, mas na edição, onde a instância já tem um valor
    antigo salvo. construct_instance() pula o campo com erro de formato e
    mantém o e-mail antigo na instância; sem cobertura anterior, uma
    regressão que voltasse a reutilizar esse valor antigo para mascarar
    (silenciar) o erro de formato do valor novo passaria despercebida."""
    form = PhoneLineForm(data=payload)
    assert form.is_valid(), form.errors
    line = form.save()
    assert line.whatsapp_seal_email == "seal@example.com"

    edit_payload = dict(payload)
    edit_payload.update(status="AVAILABLE", whatsapp_seal_email="ainda-invalido")
    edit = PhoneLineUpdateForm(data=edit_payload, instance=line, can_edit_origem=True)

    assert not edit.is_valid()
    assert edit.errors["whatsapp_seal_email"] == [
        "Insira um endereço de email válido."
    ]

    line.refresh_from_db()
    assert line.whatsapp_seal_email == "seal@example.com"


def test_without_seal_ignores_stale_hidden_values(payload):
    payload.update(whatsapp_seal="", whatsapp_seal_email="invalid", whatsapp_seal_expires_on="invalid")
    form = PhoneLineForm(data=payload)
    assert form.is_valid(), form.errors
    line = form.save()
    assert line.whatsapp_seal == ""
    assert line.whatsapp_seal_expires_on is None
    assert line.whatsapp_seal_activated_on is None
    assert line.whatsapp_seal_email == ""
    assert line.whatsapp_seal_payment == ""


def test_removing_seal_clears_data(payload):
    form = PhoneLineForm(data=payload)
    assert form.is_valid(), form.errors
    line = form.save()
    payload.update(whatsapp_seal="", status="AVAILABLE")
    edit = PhoneLineUpdateForm(data=payload, instance=line, can_edit_origem=True)
    assert edit.is_valid(), edit.errors
    edit.save()
    line.refresh_from_db()
    assert line.whatsapp_seal_email == ""
    assert line.whatsapp_seal_expires_on is None
    assert line.status == "AVAILABLE"


def test_reactivation_does_not_restore_old_seal(payload, sim):
    form = PhoneLineForm(data=payload)
    assert form.is_valid(), form.errors
    line = form.save()
    line.delete()
    restored = PhoneLine.create_or_reuse(phone_number=line.phone_number, sim_card=sim, status="AVAILABLE")
    restored.refresh_from_db()
    assert restored.pk == line.pk
    assert restored.whatsapp_seal == ""
    assert restored.whatsapp_seal_expires_on is None


def test_switching_between_seal_types_persists_new_values_without_mixing_old(payload):
    """SEL-09: troca de selo (META_ONE -> META_VERIFIED) deve persistir só
    os valores novos, sem misturar nenhum campo do selo anterior."""
    form = PhoneLineForm(data=payload)
    assert form.is_valid(), form.errors
    line = form.save()
    assert line.whatsapp_seal == "META_ONE"

    edit_payload = dict(payload)
    edit_payload.update(
        status="AVAILABLE",
        whatsapp_seal="META_VERIFIED",
        whatsapp_seal_activated_on="2026-09-05",
        whatsapp_seal_expires_on="2026-11-20",
        whatsapp_seal_email="verified@example.com",
        whatsapp_seal_payment="GOOGLE_GIFT_CARD",
    )
    edit = PhoneLineUpdateForm(data=edit_payload, instance=line, can_edit_origem=True)
    assert edit.is_valid(), edit.errors
    edit.save()

    line.refresh_from_db()
    assert line.whatsapp_seal == "META_VERIFIED"
    assert line.whatsapp_seal_activated_on == date(2026, 9, 5)
    assert line.whatsapp_seal_expires_on == date(2026, 11, 20)
    assert line.whatsapp_seal_email == "verified@example.com"
    assert line.whatsapp_seal_payment == "GOOGLE_GIFT_CARD"


def test_updating_seal_preserves_activated_at_status_and_allocation(admin_client, payload):
    """SEL-09: editar só os campos do selo não pode alterar
    PhoneLine.activated_at, status nem a alocação/histórico operacional
    (contrato explícito da spec, ponto 9 do gap analysis)."""
    form = PhoneLineForm(data=payload)
    assert form.is_valid(), form.errors
    line = form.save()

    fixed_activated_at = timezone.now() - timedelta(days=30)
    line.activated_at = fixed_activated_at
    line.save(update_fields=["activated_at"])

    employee = Employee.objects.create(
        full_name="Selo Allocation Test",
        corporate_email="selo-alloc@example.com",
        employee_id="SEL09-ALLOC-1",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )
    allocator = SystemUser.objects.create_user(
        email="seal-allocator@example.com", password="test-only", role=SystemUser.Role.ADMIN
    )
    allocation = AllocationService.allocate_line(
        employee=employee, phone_line=line, allocated_by=allocator
    )
    line.refresh_from_db()
    history_count_before = line.history.count()

    edit_payload = dict(payload)
    edit_payload.update(
        status="ALLOCATED",
        employee=employee.pk,
        whatsapp_seal_expires_on="2026-12-30",
    )
    response = admin_client.post(
        reverse("telecom:phoneline_update", args=[line.pk]), edit_payload
    )
    assert response.status_code == 302

    line.refresh_from_db()
    allocation.refresh_from_db()
    assert line.whatsapp_seal_expires_on == date(2026, 12, 30)
    assert line.status == "ALLOCATED"
    assert line.activated_at == fixed_activated_at
    assert allocation.is_active is True
    assert allocation.employee_id == employee.pk
    assert LineAllocation.objects.filter(phone_line=line, is_active=True).count() == 1
    assert line.history.count() == history_count_before


@pytest.mark.parametrize("days,tone,label", [(8, "neutral", "Vence em 25/09/2026"), (7, "warning", "Vence em 7 dias"), (1, "warning", "Vence em 1 dia"), (0, "today", "Vence hoje"), (-1, "expired", "Vencido há 1 dia"), (-5, "expired", "Vencido há 5 dias")])
def test_expiry_boundaries(monkeypatch, days, tone, label):
    monkeypatch.setattr(timezone, "localdate", lambda: date(2026, 9, 17))
    line = PhoneLine()
    line.whatsapp_seal = "META_ONE"
    line.whatsapp_seal_expires_on = date(2026, 9, 17) + timedelta(days=days)
    assert line.seal_status == {"tone": tone, "label": label}


def test_without_seal_has_no_alert():
    assert PhoneLine().seal_status == {"tone": "neutral", "label": "Sem selo"}


def test_model_validation_requires_seal_details(sim):
    line = PhoneLine(phone_number="+5511999998881", sim_card=sim)
    line.whatsapp_seal = "META_ONE"
    with pytest.raises(ValidationError) as exc:
        line.full_clean()
    assert "whatsapp_seal_expires_on" in exc.value.message_dict


@pytest.fixture
def admin_client(client, db):
    user = SystemUser.objects.create_user(email="seal-admin@example.com", password="test-only", role=SystemUser.Role.ADMIN)
    client.force_login(user)
    return client


def test_http_create_detail_list_and_edit(admin_client, payload):
    url = reverse("telecom:phoneline_create")
    page = admin_client.get(url)
    assert page.status_code == 200
    assert b"SELO WHATS LINEOPS" in page.content
    assert b'phone-line-form.js' in page.content
    response = admin_client.post(url, payload)
    assert response.status_code == 302
    line = PhoneLine.objects.get(phone_number=payload["phone_number"])
    detail = admin_client.get(reverse("telecom:phoneline_detail", args=[line.pk]))
    assert b"seal@example.com" in detail.content
    overview = admin_client.get(reverse("telecom:overview"))
    assert b"META ONE" in overview.content
    ajax = admin_client.get(reverse("telecom:overview"), {"table": "main", "offset": 0}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
    assert ajax.json()["data"][0]["seal_status"] == line.seal_status
    payload.update(status="AVAILABLE", whatsapp_seal_expires_on="2026-12-30")
    edited = admin_client.post(reverse("telecom:phoneline_update", args=[line.pk]), payload)
    assert edited.status_code == 302
    line.refresh_from_db()
    assert line.whatsapp_seal_expires_on == date(2026, 12, 30)


def test_invalid_http_post_keeps_errors(admin_client, payload):
    payload["whatsapp_seal_expires_on"] = ""
    response = admin_client.post(reverse("telecom:phoneline_create"), payload)
    assert response.status_code == 200
    assert "whatsapp_seal_expires_on" in response.context["form"].errors
    assert not PhoneLine.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_migration_preserves_existing_lines_as_no_seal():
    sim = SIMcard.objects.create(iccid="8900000000000099991", carrier="TIM")
    line = PhoneLine.objects.create(
        phone_number="+5511999990000", sim_card=sim, status="AVAILABLE"
    )
    try:
        call_command("migrate", "telecom", "0020", verbosity=0)
        call_command("migrate", "telecom", "0021", verbosity=0)
        line.refresh_from_db()
        assert line.whatsapp_seal == ""
        assert line.whatsapp_seal_activated_on is None
        assert line.whatsapp_seal_expires_on is None
        assert line.whatsapp_seal_email == ""
        assert line.whatsapp_seal_payment == ""
        assert line.status == "AVAILABLE"
    finally:
        call_command("migrate", "telecom", verbosity=0)


@pytest.mark.django_db(transaction=True)
def test_migration_0021_is_reversible():
    call_command("migrate", "telecom", "0020", verbosity=0)
    call_command("migrate", "telecom", verbosity=0)


def test_missing_seal_field_error_message_not_duplicated(payload):
    """Model.clean() roda sempre via ModelForm._post_clean (Django 5.2, sem
    relação com exclude vazio). Chamada explícita de validate_seal_fields em
    PhoneLineForm.clean() soma-se a essa validação automática e duplica a
    mesma mensagem na mesma lista de erros do campo."""
    payload["whatsapp_seal_expires_on"] = ""
    form = PhoneLineForm(data=payload)
    assert not form.is_valid()
    assert form.errors["whatsapp_seal_expires_on"] == [
        "Data de vencimento do selo é obrigatória."
    ]


def test_invalid_edit_does_not_reuse_stale_value_for_contradictory_message(
    payload, sim
):
    """add_error() remove o campo de cleaned_data; construct_instance() pula
    campos ausentes de cleaned_data e mantém o valor ANTIGO da instância.
    Na edição, isso faz o Model.clean() automático revalidar com o
    vencimento antigo (ainda salvo) somado à nova data de ativação, gerando
    segunda mensagem contraditória no mesmo campo."""
    form = PhoneLineForm(data=payload)
    assert form.is_valid(), form.errors
    line = form.save()

    edit_payload = dict(payload)
    edit_payload.update(
        status="AVAILABLE",
        whatsapp_seal_activated_on="2026-11-01",
        whatsapp_seal_expires_on="",
    )
    edit = PhoneLineUpdateForm(data=edit_payload, instance=line, can_edit_origem=True)

    assert not edit.is_valid()
    assert edit.errors["whatsapp_seal_expires_on"] == [
        "Data de vencimento do selo é obrigatória."
    ]

    line.refresh_from_db()
    assert line.whatsapp_seal_expires_on == date(2026, 10, 17)
    assert line.whatsapp_seal_activated_on == date(2026, 9, 1)


def test_invalid_http_edit_keeps_errors_and_does_not_persist_partial_data(
    admin_client, payload
):
    form = PhoneLineForm(data=payload)
    assert form.is_valid(), form.errors
    line = form.save()

    edit_payload = dict(payload)
    edit_payload.update(
        status="AVAILABLE",
        whatsapp_seal_activated_on="2026-11-01",
        whatsapp_seal_expires_on="",
    )
    response = admin_client.post(
        reverse("telecom:phoneline_update", args=[line.pk]), edit_payload
    )
    assert response.status_code == 200
    assert response.context["form"].errors["whatsapp_seal_expires_on"] == [
        "Data de vencimento do selo é obrigatória."
    ]

    line.refresh_from_db()
    assert line.whatsapp_seal_expires_on == date(2026, 10, 17)
    assert line.whatsapp_seal_activated_on == date(2026, 9, 1)


def test_operator_cannot_create_seal(client, payload):
    user = SystemUser.objects.create_user(email="seal-operator@example.com", password="test-only", role=SystemUser.Role.OPERATOR)
    client.force_login(user)
    response = client.post(reverse("telecom:phoneline_create"), payload)
    assert response.status_code == 403
    assert not PhoneLine.objects.exists()
