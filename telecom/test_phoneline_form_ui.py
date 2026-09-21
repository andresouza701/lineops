"""Testes de template/JS do cadastro/edição de linha (SEL-07).

Cobrem apenas apresentação (blocos, campos, obrigatoriedade HTML,
preservação de valores, ação Liberar). Regras de domínio já são
cobertas por telecom/test_whatsapp_seal.py.
"""

import re
from datetime import date

import pytest
from django.urls import reverse

from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser


def field_tag(content, field_name):
    match = re.search(r'<(?:input|select)[^>]*name="%s"[^>]*>' % re.escape(field_name), content)
    assert match, f"campo {field_name} não encontrado no HTML"
    return match.group(0)


def select_block(content, field_name):
    match = re.search(
        r'<select[^>]*name="%s"[^>]*>.*?</select>' % re.escape(field_name), content, re.S
    )
    assert match, f"select {field_name} não encontrado no HTML"
    return match.group(0)


SEAL_DETAIL_FIELD_NAMES = [
    "whatsapp_seal_activated_on",
    "whatsapp_seal_expires_on",
    "whatsapp_seal_email",
    "whatsapp_seal_payment",
]


@pytest.fixture
def sim(db):
    return SIMcard.objects.create(iccid="8900000000000077771", carrier="TIM")


@pytest.fixture
def admin_client(client, db):
    user = SystemUser.objects.create_user(
        email="seal-ui-admin@example.com", password="test-only", role=SystemUser.Role.ADMIN
    )
    client.force_login(user)
    return client


@pytest.fixture
def payload(sim):
    return {
        "phone_number": "+5511999997771",
        "sim_card": sim.pk,
        "whatsapp_seal": "META_ONE",
        "whatsapp_seal_activated_on": "2026-09-01",
        "whatsapp_seal_expires_on": "2026-10-17",
        "whatsapp_seal_email": "seal@example.com",
        "whatsapp_seal_payment": "CREDIT_CARD",
    }


def test_get_create_shows_both_blocks_and_loads_script(admin_client):
    response = admin_client.get(reverse("telecom:phoneline_create"))
    assert response.status_code == 200
    content = response.content.decode()
    assert "DADOS DA LINHA" in content
    assert "SELO WHATS LINEOPS" in content
    assert "phone-line-form.js" in content
    assert "Cadastro de linha" in content


def test_create_shows_no_seal_hint(admin_client):
    response = admin_client.get(reverse("telecom:phoneline_create"))
    content = response.content.decode()
    assert "Nenhum selo cadastrado" in content
    assert 'id="seal-detail-fields"' in content


def test_seal_detail_fields_accessible_without_js_by_default(admin_client, sim, payload):
    """Melhoria progressiva: HTML base nunca oculta nem exige os campos do
    selo — isso é papel exclusivo do JavaScript. Sem scripts, o usuário
    precisa conseguir ver e preencher os quatro campos em qualquer estado
    (cadastro com Sem selo, cadastro/edição com selo, POST inválido)."""
    create_response = admin_client.get(reverse("telecom:phoneline_create"))
    create_content = create_response.content.decode()
    assert 'id="seal-detail-fields" hidden' not in create_content
    for field_name in SEAL_DETAIL_FIELD_NAMES:
        assert "required" not in field_tag(create_content, field_name)

    line = PhoneLine.create_or_reuse(
        phone_number="+5511999995551",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activated_on=date(2026, 9, 1),
        whatsapp_seal_expires_on=date(2026, 10, 17),
        whatsapp_seal_email="seal@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    edit_response = admin_client.get(reverse("telecom:phoneline_update", args=[line.pk]))
    edit_content = edit_response.content.decode()
    assert 'id="seal-detail-fields" hidden' not in edit_content
    for field_name in SEAL_DETAIL_FIELD_NAMES:
        assert "required" not in field_tag(edit_content, field_name)


def test_seal_fields_rendered_with_labels_and_widgets(admin_client):
    response = admin_client.get(reverse("telecom:phoneline_create"))
    content = response.content.decode()
    assert 'for="id_whatsapp_seal"' in content
    assert 'for="id_whatsapp_seal_activated_on"' in content
    assert 'for="id_whatsapp_seal_expires_on"' in content
    assert 'for="id_whatsapp_seal_email"' in content
    assert 'for="id_whatsapp_seal_payment"' in content
    assert "META ONE" in content
    assert "META VERIFICADO" in content
    assert "CART" in content and "CRÉDITO" in content
    assert "GIFT CARD GOOGLE" in content
    assert 'type="date"' in content


def test_get_edit_preserves_seal_data(admin_client, sim, payload):
    line = PhoneLine.create_or_reuse(
        phone_number="+5511999996661",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_VERIFIED",
        whatsapp_seal_activated_on=date(2026, 9, 1),
        whatsapp_seal_expires_on=date(2026, 10, 17),
        whatsapp_seal_email="edit-seal@example.com",
        whatsapp_seal_payment="GOOGLE_GIFT_CARD",
    )
    response = admin_client.get(reverse("telecom:phoneline_update", args=[line.pk]))
    content = response.content.decode()
    assert response.status_code == 200
    assert "Editar linha" in content
    assert 'value="2026-09-01"' in content
    assert 'value="2026-10-17"' in content
    assert "edit-seal@example.com" in content
    assert 'id="seal-detail-fields" hidden' not in content


def test_invalid_post_shows_errors_and_keeps_values(admin_client, payload):
    payload["whatsapp_seal_expires_on"] = ""
    response = admin_client.post(reverse("telecom:phoneline_create"), payload)
    assert response.status_code == 200
    content = response.content.decode()
    assert "Data de vencimento do selo é obrigatória." in content
    assert "seal@example.com" in content
    assert 'id="seal-detail-fields" hidden' not in content
    assert not PhoneLine.objects.exists()


def test_invalid_edit_keeps_seal_block_open(admin_client, payload):
    from telecom.forms import PhoneLineForm

    form = PhoneLineForm(data=payload)
    assert form.is_valid(), form.errors
    line = form.save()

    edit_payload = dict(payload)
    edit_payload.update(status="AVAILABLE", whatsapp_seal_activated_on="2026-11-01", whatsapp_seal_expires_on="")
    response = admin_client.post(reverse("telecom:phoneline_update", args=[line.pk]), edit_payload)
    content = response.content.decode()
    assert response.status_code == 200
    assert 'id="seal-detail-fields" hidden' not in content
    assert 'value="2026-11-01"' in content


def test_release_action_bypasses_html_validation(admin_client, payload):
    from telecom.forms import PhoneLineForm

    form = PhoneLineForm(data=payload)
    assert form.is_valid(), form.errors
    line = form.save()
    response = admin_client.get(reverse("telecom:phoneline_update", args=[line.pk]))
    content = response.content.decode()
    assert 'name="action" value="release_line"' in content
    assert "formnovalidate" in content


def test_release_action_still_works_http(admin_client, payload):
    from telecom.forms import PhoneLineForm

    form = PhoneLineForm(data=payload)
    assert form.is_valid(), form.errors
    line = form.save()
    response = admin_client.post(
        reverse("telecom:phoneline_update", args=[line.pk]), {"action": "release_line"}
    )
    assert response.status_code == 302
    line.refresh_from_db()
    assert line.status == PhoneLine.Status.AVAILABLE


def test_whatsapp_seal_blank_choice_label_is_sem_selo(admin_client):
    """Achado 2 da conferência real: opção vazia mostrava '---------'."""
    response = admin_client.get(reverse("telecom:phoneline_create"))
    content = response.content.decode()
    block = select_block(content, "whatsapp_seal")
    assert "---------" not in block
    assert re.search(r'<option value=""[^>]*>Sem selo</option>', block)


def test_error_summary_uses_friendly_ptbr_labels(admin_client, payload):
    """Achado 3 da conferência real: resumo mostrava 'Whatsapp seal expires
    on' em vez do rótulo amigável 'Vencimento'."""
    payload["whatsapp_seal_expires_on"] = "2026-08-31"  # anterior à ativação
    response = admin_client.post(reverse("telecom:phoneline_create"), payload)
    content = response.content.decode()
    assert response.status_code == 200
    assert "Whatsapp seal" not in content
    assert "Vencimento" in content
    assert re.search(r'<a href="#id_whatsapp_seal_expires_on">Vencimento</a>', content)


def test_seal_field_labels_are_ptbr():
    from telecom.forms import PhoneLineForm

    form = PhoneLineForm()
    assert form.fields["whatsapp_seal"].label == "Selo"
    assert form.fields["whatsapp_seal_activated_on"].label == "Ativação"
    assert form.fields["whatsapp_seal_expires_on"].label == "Vencimento"
    assert form.fields["whatsapp_seal_email"].label == "E-mail cadastrado"
    assert form.fields["whatsapp_seal_payment"].label == "Pagamento"


def test_switching_existing_seal_to_none_without_js_saves_and_clears(admin_client, sim, payload):
    """Achado 1 (consequência): sem JS, nenhum required residual pode
    bloquear a troca de um selo existente para Sem selo, mesmo deixando os
    campos de detalhe com valores antigos no POST (o navegador não os
    apagou, pois isso é responsabilidade do JavaScript). O servidor deve
    aceitar e limpar os dados, como já fazia PhoneLineForm.full_clean()."""
    from telecom.forms import PhoneLineForm

    form = PhoneLineForm(data=payload)
    assert form.is_valid(), form.errors
    line = form.save()

    edit_payload = dict(payload)
    edit_payload.update(status="AVAILABLE", whatsapp_seal="")
    response = admin_client.post(
        reverse("telecom:phoneline_update", args=[line.pk]), edit_payload
    )
    assert response.status_code == 302
    line.refresh_from_db()
    assert line.whatsapp_seal == ""
    assert line.whatsapp_seal_expires_on is None
    assert line.whatsapp_seal_email == ""
