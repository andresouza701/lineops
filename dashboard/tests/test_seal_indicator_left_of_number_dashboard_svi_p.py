"""SVI-P02/P03 — ajuste aprovado 2026-10-11: indicador antes do numero.
Cobre I11 (daily_user_action_board, botao inicial server-renderizado) e
I13/I17 (daily_indicator_day_breakdown — lista simples de numero, e lista
"Usuarios com linha" onde o numero vem APOS um outro span de nome, caso
estrutural distinto dos demais).

Fonte da verdade: docs/superpowers/specs/2026-10-05-phone-line-seal-
indicator-design.md. O modal JS-only (lineDetailModal/pendencyLinha) nao e
provado aqui — requer navegador real (DOM construido via seal_indicator.js
em resposta a evento `show.bs.modal`), registrado como pendente no relatorio
de conformidade.
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


def _assert_indicator_immediately_before(html, number):
    idx = html.index(number)
    assert html[idx - 1] == " ", (
        f"esperado um unico espaco antes do numero, achou {html[idx - 2:idx]!r}"
    )
    assert html[idx - 2] == ">"
    assert "seal-indicator" in html[:idx]


def _assert_indicator_immediately_before_marker(html, marker):
    """Como _assert_indicator_immediately_before, mas para os casos em que
    o numero vem envolto no seu PROPRIO <span> (o indicador precisa vir
    logo antes da ABERTURA desse span, nao antes do texto do numero, que
    fica mais adiante, do outro lado da tag de abertura do span)."""
    idx = html.index(marker)
    assert html[idx - 1] == " ", (
        f"esperado um unico espaco antes de {marker!r}, achou {html[idx - 2:idx]!r}"
    )
    assert html[idx - 2] == ">"
    assert "seal-indicator" in html[:idx]


@pytest.fixture
def admin_client(client, db):
    user = SystemUser.objects.create_user(
        email="svi-p-dash-admin@example.com", password=PASSWORD, role=SystemUser.Role.ADMIN
    )
    client.force_login(user)
    return user, client


@pytest.fixture
def super_client(client, db):
    user = SystemUser.objects.create_user(
        email="svi-p-dash-super@example.com", password=PASSWORD, role=SystemUser.Role.SUPER
    )
    client.force_login(user)
    return user, client


@pytest.fixture
def employee_with_line(super_client):
    admin, client = super_client
    employee = Employee.objects.create(
        full_name="Funcionario Board SVI-P",
        corporate_email=admin.email,
        employee_id="SVI-P-BOARD-1",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )
    sim = SIMcard.objects.create(iccid="8900000000000095001", carrier="TIM")
    line = PhoneLine.objects.create(
        phone_number="+5511999995001",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=timezone.localdate() - timedelta(days=30),
        whatsapp_seal_expires_on=timezone.localdate() + timedelta(days=8),
        whatsapp_seal_email="svi-p-board@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    AllocationService.allocate_line(employee=employee, phone_line=line, allocated_by=admin)
    return employee, line


# --- I11 — daily_user_action_board (botao inicial) -------------------------


def test_daily_user_action_board_places_indicator_before_number(
    super_client, employee_with_line
):
    _admin, client = super_client
    _employee, line = employee_with_line

    response = client.get(reverse("daily_user_action_board"))
    content = response.content.decode()

    # O numero tambem aparece no atributo data-line-number do <button>,
    # ANTES do conteudo visivel — ancorar pelo marcador do badge visivel
    # (unico nesta pagina, so uma linha com has_line=True) evita casar
    # com o atributo por engano.
    marker = '<span class="badge text-bg-success">'
    button = _cell(content, marker, tag="button")
    _assert_indicator_immediately_before_marker(button, marker)


# --- I13 — daily_indicator_day_breakdown (numeros disponiveis) -------------


def test_daily_indicator_day_breakdown_available_places_indicator_before_number(
    admin_client, db
):
    _admin, client = admin_client
    sim = SIMcard.objects.create(iccid="8900000000000095002", carrier="TIM")
    line = PhoneLine.objects.create(
        phone_number="+5511999995002",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=timezone.localdate() - timedelta(days=30),
        whatsapp_seal_expires_on=timezone.localdate() + timedelta(days=8),
        whatsapp_seal_email="svi-p-avail@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )

    today_iso = timezone.localdate().strftime("%Y-%m-%d")
    response = client.get(reverse("daily_indicator_day_breakdown", kwargs={"day": today_iso}))
    content = response.content.decode()

    item = _cell(content, line.phone_number, tag="li")
    _assert_indicator_immediately_before_marker(item, '<span class="detail-list-main metric-mono">')


# --- I17 — daily_indicator_day_breakdown (usuarios com linha) --------------


def test_daily_indicator_day_breakdown_users_with_line_places_indicator_before_number(
    super_client, employee_with_line
):
    """Estrutura distinta das demais listas: o numero vem depois de um
    outro <span> (nome do usuario) na mesma <li> — o indicador precisa
    ficar colado ao NUMERO, nao ao inicio do item nem antes do nome."""
    _admin, client = super_client
    employee, line = employee_with_line

    today_iso = timezone.localdate().strftime("%Y-%m-%d")
    response = client.get(reverse("daily_indicator_day_breakdown", kwargs={"day": today_iso}))
    content = response.content.decode()

    # O mesmo numero tambem aparece na lista "Números entregues" (I14,
    # mesmo dia da alocacao) — recortar a partir do titulo da secao
    # "Usuários com linha" evita casar com o <li> errado.
    section = content[content.index("Usuários com linha") :]
    item = _cell(section, line.phone_number, tag="li")
    _assert_indicator_immediately_before_marker(item, '<span class="detail-list-meta metric-mono">')
    # O indicador nao pode vir antes do nome do usuario (o nome continua
    # sendo o primeiro conteudo visivel do item).
    name_idx = item.index(employee.full_name)
    indicator_idx = item.index("seal-indicator")
    assert name_idx < indicator_idx


# --- SVI-P06 achado B — indicador e numero empilhados pelo flex-column ----
#
# static/css/styles.css define `.detail-list-item { display: flex;
# flex-direction: column; }`. Ate aqui, indicador e numero eram filhos
# DIRETOS e SEPARADOS de .detail-list-item — cada filho direto de um flex
# container em coluna ocupa sua propria linha, logo o indicador renderiza
# ACIMA do numero, nao ao lado, mesmo vindo antes no DOM. Os testes de
# ordem acima (substring) nao detectam isso porque ordem DOM e agrupamento
# visual sao coisas distintas. Estes testes provam containment: indicador
# e numero precisam compartilhar um unico wrapper inline
# (.detail-list-line), nao serem dois filhos separados de .detail-list-item.


def _assert_indicator_and_number_share_inline_wrapper(item, number_marker):
    wrapper_marker = '<span class="detail-list-line">'
    assert wrapper_marker in item, (
        "indicador e numero precisam compartilhar um wrapper inline "
        "(.detail-list-line) — sem ele, cada um e um filho direto de "
        ".detail-list-item (flex-direction: column) e fica em linha "
        "separada, nao lado a lado"
    )
    wrapper_idx = item.index(wrapper_marker)
    seal_idx = item.index("seal-indicator", wrapper_idx)
    marker_idx = item.index(number_marker, seal_idx)
    close_idx = item.index("</span></span>", marker_idx)
    assert wrapper_idx < seal_idx < marker_idx < close_idx, (
        "indicador e numero precisam estar ambos DENTRO do mesmo "
        ".detail-list-line, nao apenas perto um do outro no HTML"
    )


def test_breakdown_available_numbers_wraps_indicator_and_number_together(
    admin_client, db
):
    _admin, client = admin_client
    sim = SIMcard.objects.create(iccid="8900000000000095010", carrier="TIM")
    line = PhoneLine.objects.create(
        phone_number="+5511999995010",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=timezone.localdate() - timedelta(days=30),
        whatsapp_seal_expires_on=timezone.localdate() + timedelta(days=8),
        whatsapp_seal_email="svi-p06-avail@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )

    today_iso = timezone.localdate().strftime("%Y-%m-%d")
    response = client.get(reverse("daily_indicator_day_breakdown", kwargs={"day": today_iso}))
    content = response.content.decode()

    item = _cell(content, line.phone_number, tag="li")
    _assert_indicator_and_number_share_inline_wrapper(
        item, '<span class="detail-list-main metric-mono">'
    )


def test_breakdown_delivered_numbers_wraps_indicator_and_number_together(
    super_client, employee_with_line
):
    _admin, client = super_client
    _employee, line = employee_with_line

    today_iso = timezone.localdate().strftime("%Y-%m-%d")
    response = client.get(reverse("daily_indicator_day_breakdown", kwargs={"day": today_iso}))
    content = response.content.decode()

    section = content[content.index("Números entregues") :]
    item = _cell(section, line.phone_number, tag="li")
    _assert_indicator_and_number_share_inline_wrapper(
        item, '<span class="detail-list-main metric-mono">'
    )


def test_breakdown_reconnected_numbers_wraps_indicator_and_number_together(
    super_client,
):
    """Regra real de reconexao (core/services/daily_indicator_service.py::
    DailyIndicatorService.get_reconnected_allocations_queryset): a MESMA
    linha volta para o MESMO funcionario apos uma liberacao anterior, no
    mesmo dia. Mesmo fluxo de dashboard/tests/test_seal_indicator_svi03.py."""
    admin, client = super_client
    employee = Employee.objects.create(
        full_name="Funcionario Reconectado SVI-P06",
        corporate_email=admin.email,
        employee_id="SVI-P06-REC-1",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )
    sim = SIMcard.objects.create(iccid="8900000000000095011", carrier="TIM")
    line = PhoneLine.objects.create(
        phone_number="+5511999995011",
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
    assert any(
        item["numero"] == line.phone_number for item in indicator["reconnected_numbers"]
    )

    content = response.content.decode()
    section = content[content.index("Números reconectados") :]
    item = _cell(section, line.phone_number, tag="li")
    _assert_indicator_and_number_share_inline_wrapper(
        item, '<span class="detail-list-main metric-mono">'
    )


def test_breakdown_new_numbers_wraps_indicator_and_number_together(admin_client, db):
    """Linha criada hoje conta como numero novo do dia (created_at = hoje),
    mesmo fluxo de dashboard/tests/test_seal_indicator_svi03.py."""
    _admin, client = admin_client
    sim = SIMcard.objects.create(iccid="8900000000000095012", carrier="TIM")
    line = PhoneLine.objects.create(
        phone_number="+5511999995012",
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
    section = content[content.index("Números novos") :]
    item = _cell(section, line.phone_number, tag="li")
    _assert_indicator_and_number_share_inline_wrapper(
        item, '<span class="detail-list-main metric-mono">'
    )


def test_breakdown_users_with_line_wraps_indicator_and_number_together(
    super_client, employee_with_line
):
    _admin, client = super_client
    employee, line = employee_with_line

    today_iso = timezone.localdate().strftime("%Y-%m-%d")
    response = client.get(reverse("daily_indicator_day_breakdown", kwargs={"day": today_iso}))
    content = response.content.decode()

    section = content[content.index("Usuários com linha") :]
    item = _cell(section, line.phone_number, tag="li")
    _assert_indicator_and_number_share_inline_wrapper(
        item, '<span class="detail-list-meta metric-mono">'
    )
    # Nome continua fora do wrapper, como primeiro conteudo do item.
    name_idx = item.index(employee.full_name)
    wrapper_idx = item.index('<span class="detail-list-line">')
    assert name_idx < wrapper_idx


# --- SVI-P06 achado A — modal I11 mantem campo "Selo" redundante ----------
#
# O contrato aprovado (SVI-P03) e indicador + espaco + telefone no MESMO
# campo visual — nao um campo "Selo" isolado. O JS inline deste template
# insere o indicador apenas no slot data-line-detail="seal" (separado do
# campo Numero); estes testes provam, de forma estatica no HTML renderizado
# (o <script> faz parte da resposta), que esse slot foi removido e que o
# indicador passa a ser construido dentro do campo Numero.


def test_line_detail_modal_has_no_separate_seal_field(super_client, employee_with_line):
    _admin, client = super_client
    response = client.get(reverse("daily_user_action_board"))
    content = response.content.decode()

    assert 'data-line-detail="seal"' not in content, (
        "slot 'Selo' separado deveria ter sido removido — indicador "
        "pertence ao campo Numero"
    )
    assert '<dt class="col-sm-4">Selo</dt>' not in content


def test_line_detail_modal_js_builds_indicator_into_number_field(
    super_client, employee_with_line
):
    _admin, client = super_client
    response = client.get(reverse("daily_user_action_board"))
    content = response.content.decode()

    js_start = content.index("lineModalEl.addEventListener")
    js_block = content[js_start : js_start + 3000]
    number_target_idx = js_block.index('data-line-detail="number"')
    createnode_idx = js_block.index("SealIndicator.createNode(", number_target_idx)
    assert number_target_idx < createnode_idx, (
        "o indicador precisa ser construido e inserido dentro do mesmo "
        "slot do campo Numero, nao de um slot separado"
    )
