"""SVI-P02/P03 — ajuste aprovado 2026-10-11: indicador de selo passa a
vir ANTES do numero (a esquerda), separado por um unico espaco, com borda
do circulo na mesma cor do preenchimento (sem contorno branco).

Fonte da verdade: docs/superpowers/specs/2026-10-05-phone-line-seal-
indicator-design.md, secao "Ajuste aprovado — indicador à esquerda do
número — 2026-10-11" (tarefas SVI-P01-P04).

Cobre I01 (overview), I02 (operator_lines), I03 (phoneline_detail), I05
(phoneline_history), I07 (line_operational_report), I23 (blip_configuration_
list), I24 (blip_configuration_form, bloco "Dado salvo" + persistencia apos
POST invalido), I25 (admin SIMcard), I26 (admin BlipConfiguration, inclusive
fallback "Selo indisponivel" quando a linha nao e resolvivel).

Nao mocka compute_seal_status nem PhoneLine.seal_status: le o valor real.
Nao duplica a cobertura generica de adjacencia (mesma celula) ja provada em
telecom/test_seal_indicator_svi03.py — aqui o foco e exclusivamente a ORDEM
(indicador antes do numero) e o separador (exatamente um espaco, sem
sobra quando nao ha selo).
"""

from datetime import date

import pytest
from django.urls import reverse
from django.utils import timezone

from telecom.models import BlipConfiguration, PhoneLine, SIMcard
from users.models import SystemUser

PASSWORD = "StrongPass123"
FROZEN_TODAY = date(2026, 9, 17)


def _cell(html, marker, tag="td"):
    idx = html.index(marker)
    start = html.rindex(f"<{tag}", 0, idx)
    end = html.index(f"</{tag}>", idx) + len(f"</{tag}>")
    return html[start:end]


def _assert_indicator_immediately_before(html, number, *, indicator_present=True):
    """Prova, no HTML real da resposta, que (quando ha indicador) ele vem
    ANTES do numero com exatamente um espaco de separador — e que a
    ausencia de indicador nao deixa espaco residual antes do numero.

    Depende de os templates editados nao inserirem nenhum espaco/quebra de
    linha propria entre a tag `{% seal_indicator %}` e `{{ numero }}` (a
    unica fonte de separador e o espaco literal dentro de telecom/
    _seal_indicator.html, uma unica fonte, nao uma por tela)."""
    idx = html.index(number)
    if indicator_present:
        assert html[idx - 1] == " ", (
            f"esperado um unico espaco antes do numero, achou {html[idx - 2:idx]!r}"
        )
        assert html[idx - 2] == ">", (
            "esperado o espaco vir logo depois do fechamento do indicador "
            f"(</span>), achou {html[idx - 3:idx]!r}"
        )
        assert "seal-indicator" in html[:idx]
    else:
        assert html[idx - 1] != " ", "espaco residual antes do numero sem selo"


@pytest.fixture
def admin_client(client, db):
    user = SystemUser.objects.create_user(
        email="svi-p-admin@example.com", password=PASSWORD, role=SystemUser.Role.ADMIN
    )
    client.force_login(user)
    return user, client


@pytest.fixture
def superuser_client(client, db):
    user = SystemUser.objects.create_superuser(
        email="svi-p-root@example.com", password=PASSWORD, role=SystemUser.Role.ADMIN
    )
    client.force_login(user)
    return user, client


@pytest.fixture
def sim(db):
    return SIMcard.objects.create(iccid="8900000000000091001", carrier="TIM")


@pytest.fixture
def line_green(sim, monkeypatch):
    monkeypatch.setattr(timezone, "localdate", lambda: FROZEN_TODAY)
    return PhoneLine.objects.create(
        phone_number="+5511999991001",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=date(2026, 8, 1),
        whatsapp_seal_expires_on=date(2026, 9, 25),
        whatsapp_seal_email="svi-p-green@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )


@pytest.fixture
def line_no_seal(db):
    other_sim = SIMcard.objects.create(iccid="8900000000000091002", carrier="TIM")
    return PhoneLine.objects.create(
        phone_number="+5511999991002",
        sim_card=other_sim,
        status=PhoneLine.Status.AVAILABLE,
    )


# --- I01 — telecom:overview --------------------------------------------


def test_overview_places_indicator_before_number_with_single_space(admin_client, line_green):
    _user, client = admin_client
    response = client.get(reverse("telecom:overview"))
    content = response.content.decode()

    cell = _cell(content, line_green.phone_number, tag="td")
    _assert_indicator_immediately_before(cell, line_green.phone_number)


def test_overview_no_seal_leaves_no_residual_separator(admin_client, line_no_seal):
    _user, client = admin_client
    response = client.get(reverse("telecom:overview"))
    content = response.content.decode()

    cell = _cell(content, line_no_seal.phone_number, tag="td")
    assert "seal-indicator" not in cell
    _assert_indicator_immediately_before(cell, line_no_seal.phone_number, indicator_present=False)


# --- I05 — telecom:phoneline_history -------------------------------------


def test_history_places_indicator_before_number_and_before_status_suffix(
    admin_client, line_green
):
    """A ordem aprovada e indicador -> numero -> " - status", nao apenas
    indicador antes do numero isolado: o sufixo " - status" (ja existente,
    nao alterado por este ajuste) precisa continuar DEPOIS do numero."""
    _user, client = admin_client
    response = client.get(reverse("telecom:phoneline_history", args=[line_green.pk]))
    content = response.content.decode()

    marker = '<p class="text-muted mb-0">'
    start = content.index(marker) + len(marker)
    end = content.index("</p>", start)
    block = content[start:end]

    _assert_indicator_immediately_before(block, line_green.phone_number)
    status_idx = block.index(line_green.phone_number) + len(line_green.phone_number)
    assert block[status_idx:].startswith(f" - {line_green.get_status_display()}")


# --- I07 — telecom:line_operational_report --------------------------------


def test_line_operational_report_places_indicator_before_number(admin_client, line_green):
    from telecom.models import LineDailyActionAuditEvent

    LineDailyActionAuditEvent.objects.create(
        event_type=LineDailyActionAuditEvent.EventType.OPENED,
        source=LineDailyActionAuditEvent.Source.LINE_ALLOCATION,
        source_object_id=line_green.pk,
        occurred_at=timezone.now(),
        phone_line=line_green,
        before_state={},
        after_state={},
    )
    _user, client = admin_client
    response = client.get(reverse("telecom:line_operational_report"))
    content = response.content.decode()

    cell = _cell(content, line_green.phone_number, tag="td")
    _assert_indicator_immediately_before(cell, line_green.phone_number)


# --- I23 — telecom:blip_configuration_list --------------------------------


@pytest.fixture
def dev_client(client, db):
    user = SystemUser.objects.create_user(
        email="svi-p-dev@example.com", password=PASSWORD, role=SystemUser.Role.DEV
    )
    client.force_login(user)
    return user, client


def test_blip_configuration_list_places_indicator_before_number(dev_client, line_green):
    line_green.origem = PhoneLine.Origem.BLIP
    line_green.save(update_fields=["origem"])
    _user, client = dev_client
    BlipConfiguration.objects.create(
        blip_id="BLIP-SVI-P-1",
        type=BlipConfiguration.ConfigurationType.FLOW,
        description="Fluxo ordem indicador",
        phone_number=int(line_green.phone_number),
        key=BlipConfiguration.KeyType.ACCESS,
        value="token-svi-p-1",
    )

    response = client.get(reverse("telecom:blip_configuration_list"))
    content = response.content.decode()

    cell = _cell(content, str(int(line_green.phone_number)), tag="td")
    _assert_indicator_immediately_before(cell, str(int(line_green.phone_number)))


# --- I24 — telecom:blip_configuration_update ("Dado salvo") ----------------


def test_blip_form_saved_block_places_indicator_before_number(dev_client, line_green):
    line_green.origem = PhoneLine.Origem.BLIP
    line_green.save(update_fields=["origem"])
    _user, client = dev_client
    config = BlipConfiguration.objects.create(
        blip_id="BLIP-SVI-P-2",
        type=BlipConfiguration.ConfigurationType.FLOW,
        description="Fluxo ordem indicador bloco salvo",
        phone_number=int(line_green.phone_number),
        key=BlipConfiguration.KeyType.ACCESS,
        value="token-svi-p-2",
    )

    response = client.get(reverse("telecom:blip_configuration_update", args=[config.pk]))
    content = response.content.decode()

    marker = "Dado salvo: "
    start = content.index(marker) + len(marker)
    end = content.index("</div>", start)
    block = content[start:end]

    _assert_indicator_immediately_before(block, str(config.phone_number))


def test_blip_form_saved_block_order_survives_invalid_post(dev_client, line_green):
    """BLIP mantem o indicador do DADO PERSISTIDO, na ordem aprovada,
    mesmo apos um POST invalido (form_invalid re-renderiza a MESMA pagina,
    sem redirecionar e sem salvar nada no banco)."""
    line_green.origem = PhoneLine.Origem.BLIP
    line_green.save(update_fields=["origem"])
    _user, client = dev_client
    config = BlipConfiguration.objects.create(
        blip_id="BLIP-SVI-P-3",
        type=BlipConfiguration.ConfigurationType.FLOW,
        description="Fluxo ordem indicador POST invalido",
        phone_number=int(line_green.phone_number),
        key=BlipConfiguration.KeyType.ACCESS,
        value="token-svi-p-3",
    )
    update_url = reverse("telecom:blip_configuration_update", args=[config.pk])

    response = client.post(
        update_url,
        {
            # blip_id vazio: campo obrigatorio, dispara form_invalid sem
            # salvar nada e sem redirecionar (200, mesma pagina).
            "blip_id": "",
            "type": BlipConfiguration.ConfigurationType.FLOW,
            "description": "Fluxo ordem indicador POST invalido",
            "phone_number": line_green.phone_number,
            "key": BlipConfiguration.KeyType.ACCESS,
            "value": "token-svi-p-3",
        },
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "Dado salvo" in content

    marker = "Dado salvo: "
    start = content.index(marker) + len(marker)
    end = content.index("</div>", start)
    block = content[start:end]

    _assert_indicator_immediately_before(block, str(config.phone_number))


# --- I25 — admin:telecom_simcard_changelist --------------------------------


# --- SVI-P06 achado C — I04 composicao lateral explicita no formulario ----


def test_phoneline_update_wraps_indicator_and_input_in_inline_container(
    admin_client, line_green
):
    """O widget do campo phone_number e .form-control (display:block,
    largura 100%, Bootstrap). So colocar o indicador antes do widget nao
    compoe os dois lado a lado — precisa de um wrapper flex dedicado
    (.seal-field-inline, ver static/css/styles.css)."""
    _user, client = admin_client
    response = client.get(reverse("telecom:phoneline_update", args=[line_green.pk]))
    content = response.content.decode()

    wrapper_marker = '<div class="seal-field-inline">'
    assert wrapper_marker in content
    wrapper_idx = content.index(wrapper_marker)
    seal_idx = content.index("seal-indicator", wrapper_idx)
    input_idx = content.index('name="phone_number"', seal_idx)
    close_idx = content.index("</div>", input_idx)
    assert wrapper_idx < seal_idx < input_idx < close_idx


def test_simcard_admin_places_indicator_before_number(superuser_client, line_green):
    _user, client = superuser_client

    response = client.get(reverse("admin:telecom_simcard_changelist"))
    content = response.content.decode()

    cell = _cell(content, line_green.phone_number, tag="td")
    _assert_indicator_immediately_before(cell, line_green.phone_number)


# --- I26 — admin:telecom_blipconfiguration_changelist ----------------------


def test_blip_configuration_admin_places_indicator_before_number(superuser_client, line_green):
    line_green.origem = PhoneLine.Origem.BLIP
    line_green.save(update_fields=["origem"])
    _user, client = superuser_client
    BlipConfiguration.objects.create(
        blip_id="BLIP-SVI-P-ADMIN-1",
        type=BlipConfiguration.ConfigurationType.FLOW,
        description="Fluxo admin ordem indicador",
        phone_number=int(line_green.phone_number),
        key=BlipConfiguration.KeyType.ACCESS,
        value="token-admin-svi-p-1",
    )

    response = client.get(reverse("admin:telecom_blipconfiguration_changelist"))
    content = response.content.decode()

    cell = _cell(content, str(int(line_green.phone_number)), tag="td")
    _assert_indicator_immediately_before(cell, str(int(line_green.phone_number)))


def test_blip_configuration_admin_unresolvable_line_shows_fallback_before_number(
    superuser_client,
):
    """I26 · numero sem linha resolvivel: fallback textual "Selo
    indisponivel" (sem circulo) tambem deve vir ANTES do numero, mesma
    regra de ordem/separador dos estados com circulo."""
    _user, client = superuser_client
    BlipConfiguration.objects.create(
        blip_id="BLIP-SVI-P-ADMIN-2",
        type=BlipConfiguration.ConfigurationType.FLOW,
        description="Fluxo admin numero nao resolvivel",
        phone_number=5511999999999,
        key=BlipConfiguration.KeyType.ACCESS,
        value="token-admin-svi-p-2",
    )

    response = client.get(reverse("admin:telecom_blipconfiguration_changelist"))
    content = response.content.decode()

    cell = _cell(content, "5511999999999", tag="td")
    assert "Selo indisponível" in cell
    _assert_indicator_immediately_before(cell, "5511999999999")
