"""SVI-03 — testes RED do indicador visual de selo junto ao número.

Fonte da verdade: docs/superpowers/specs/2026-10-05-phone-line-seal-
indicator-design.md (SVI-01/02 concluidas, fechamento de bordas aprovado em
05/10/2026). Cobre I01 (overview), I02 (operator_lines), I03 (phoneline_
detail), I04 (phoneline_form/update), I05 (phoneline_history), I06 (line_
reports), I07 (line_operational_report), I23 (blip_configuration_list) e
I24 (blip_configuration_form) da matriz de inventario.

Requisito sob teste: um circulo/indicador acessivel (tipo + situacao) deve
aparecer JUNTO ao numero (na mesma celula/elemento que hoje so contem o
numero), nao em coluna/bloco separado. Hoje o selo (quando exibido) vive em
coluna "Selo"/painel "SELO WHATS LINEOPS" totalmente separada da celula do
numero — estes testes fixam essa lacuna de adjacencia, nao duplicam a
cobertura textual generica ja existente em test_seal_detail_and_listing.py
(SEL-08), que verifica o selo em qualquer parte da pagina.

GREEN esperado: SVI-05 (integracao de superficie), reaproveitando a
projecao central de SVI-04 quando esta decidir o texto/cor final de
"verde" vs "cinza" (hoje ambos colapsam em tone=neutral — ver nota na
classe de bordas abaixo). Nenhum teste aqui mocka compute_seal_status ou
PhoneLine.seal_status: todos leem o valor real calculado pelo dominio.
"""

from datetime import date

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from telecom.models import BlipConfiguration, PhoneLine, PhoneLineHistory, SIMcard
from users.models import SystemUser

PASSWORD = "StrongPass123"
FROZEN_TODAY = date(2026, 9, 17)


def _cell(html, marker, tag="td"):
    """Extrai o elemento <tag>...</tag> mais interno que envolve `marker`.

    Fronteira estrutural ja existente no template (td/dd), nao um seletor
    inventado: usada para provar adjacencia (ou a falta dela) entre o
    numero e qualquer indicador, em vez de aceitar texto em qualquer parte
    da pagina como falso-positivo.
    """
    idx = html.index(marker)
    start = html.rindex(f"<{tag}", 0, idx)
    end = html.index(f"</{tag}>", idx) + len(f"</{tag}>")
    return html[start:end]


def _window(html, marker, length=500):
    """Janela de texto apos `marker`, para blocos sem fronteira td/dd clara
    (ex.: campo de formulario, cabecalho de historico)."""
    idx = html.index(marker) + len(marker)
    return html[idx : idx + length]


@pytest.fixture
def sim(db):
    return SIMcard.objects.create(iccid="8900000000000088001", carrier="TIM")


@pytest.fixture
def admin_client(client, db):
    user = SystemUser.objects.create_user(
        email="svi03-admin@example.com", password=PASSWORD, role=SystemUser.Role.ADMIN
    )
    client.force_login(user)
    return client


@pytest.fixture
def dev_client(client, db):
    user = SystemUser.objects.create_user(
        email="svi03-dev@example.com", password=PASSWORD, role=SystemUser.Role.DEV
    )
    client.force_login(user)
    return user, client


@pytest.fixture
def line_green(sim, monkeypatch):
    """Ativo, vencimento em +8 dias (> 7): deveria ser verde."""
    monkeypatch.setattr(timezone, "localdate", lambda: FROZEN_TODAY)
    return PhoneLine.objects.create(
        phone_number="+5511999998001",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=date(2026, 8, 1),
        whatsapp_seal_expires_on=date(2026, 9, 25),
        whatsapp_seal_email="green@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )


@pytest.fixture
def line_gray(monkeypatch):
    """Nao ativado: deveria ser cinza, distinto do verde acima apesar de
    ambos usarem hoje tone=neutral na badge existente."""
    monkeypatch.setattr(timezone, "localdate", lambda: FROZEN_TODAY)
    other_sim = SIMcard.objects.create(iccid="8900000000000088002", carrier="TIM")
    return PhoneLine.objects.create(
        phone_number="+5511999998002",
        sim_card=other_sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_VERIFIED",
        whatsapp_seal_activation_status="NOT_ACTIVATED",
    )


# --- I01 — telecom:overview ---------------------------------------------


def test_overview_initial_number_cell_shows_seal_indicator_for_green_line(
    admin_client, line_green
):
    """I01 · apresentacao/HTTP · GREEN esperado: SVI-05."""
    response = admin_client.get(reverse("telecom:overview"))
    content = response.content.decode()

    cell = _cell(content, line_green.phone_number, tag="td")

    assert line_green.get_whatsapp_seal_display() in cell
    assert line_green.seal_status["label"] in cell


def test_overview_initial_number_cell_shows_seal_indicator_for_gray_line(
    admin_client, line_gray
):
    """I01 · apresentacao/HTTP · GREEN esperado: SVI-05."""
    response = admin_client.get(reverse("telecom:overview"))
    content = response.content.decode()

    cell = _cell(content, line_gray.phone_number, tag="td")

    assert line_gray.get_whatsapp_seal_display() in cell
    assert line_gray.seal_status["label"] in cell


def test_overview_ajax_payload_links_seal_status_to_its_own_line_number(admin_client, sim):
    """I01 · JSON · segurança de identidade: o selo de UMA linha nao deve
    aparecer associado ao numero de OUTRA linha na mesma pagina. Hoje o
    payload AJAX ja carrega seal_status/whatsapp_seal_display por linha
    (SEL-08) — este teste prova que a pagina HTML (nao o JSON) ainda nao
    expõe nada equivalente junto ao numero, usando uma segunda linha como
    controle negativo real (nao um assert negativo isolado)."""
    other_sim = SIMcard.objects.create(iccid="8900000000000088003", carrier="TIM")
    line_a = PhoneLine.objects.create(
        phone_number="+5511999998011",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=date(2026, 8, 1),
        whatsapp_seal_expires_on=date(2026, 9, 25),
        whatsapp_seal_email="a@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    line_b = PhoneLine.objects.create(
        phone_number="+5511999998012",
        sim_card=other_sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_VERIFIED",
        whatsapp_seal_activation_status="NOT_ACTIVATED",
    )

    response = admin_client.get(reverse("telecom:overview"))
    content = response.content.decode()

    cell_a = _cell(content, line_a.phone_number, tag="td")
    cell_b = _cell(content, line_b.phone_number, tag="td")

    # Controle positivo: os rotulos sao realmente diferentes no dominio.
    assert line_a.seal_status["label"] != line_b.seal_status["label"]
    # RED esperado: nenhuma das duas celulas contem hoje o rotulo da OUTRA
    # linha (nao ha vazamento) nem o da PROPRIA linha (indicador ausente).
    assert line_a.seal_status["label"] not in cell_b
    assert line_b.seal_status["label"] not in cell_a
    assert line_a.seal_status["label"] in cell_a  # falha hoje: ausente
    assert line_b.seal_status["label"] in cell_b  # falha hoje: ausente


# --- I02 — telecom:operator_lines ----------------------------------------


def test_operator_lines_number_cell_shows_seal_indicator(client, db, sim):
    """I02 · apresentacao/HTTP · GREEN esperado: SVI-05. Sem paginacao —
    nao e motivo para excluir a superficie (contrato SVI-02/03)."""
    operator = SystemUser.objects.create_user(
        email="svi03-operator@example.com", password=PASSWORD, role=SystemUser.Role.OPERATOR
    )
    line = PhoneLine.objects.create(
        phone_number="+5511999998021",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=date(2026, 8, 1),
        whatsapp_seal_expires_on=date(2026, 9, 25),
        whatsapp_seal_email="op@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    from core.services.allocation_service import AllocationService
    from employees.models import Employee

    employee = Employee.objects.create(
        full_name="Operador Vinculado",
        email=operator.email,
        corporate_email=operator.email,
        employee_id="SVI03-OP-1",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )
    AllocationService.allocate_line(employee=employee, phone_line=line, allocated_by=operator)

    client.force_login(operator)
    response = client.get(reverse("telecom:operator_lines"))
    content = response.content.decode()

    cell = _cell(content, line.phone_number, tag="td")
    assert line.seal_status["label"] in cell


def test_operator_lines_does_not_leak_other_operators_line_seal(client, db, sim, monkeypatch):
    """I02 · autorizacao/isolamento entre usuarios: OPERATOR A nao pode
    ver numero nem selo da linha do OPERATOR B. Escopo testado e o de
    get_visible_phone_lines_queryset/PhoneLine.visible_to_user para role
    operator (telecom/models.py:236-244, filtro por
    employee__email__iexact=user.email) — NAO coberto antes por nenhum
    teste novo desta task; os testes anteriores de I02 só provavam a
    propria linha do operador, nunca a ausencia da linha de outro."""
    monkeypatch.setattr(timezone, "localdate", lambda: FROZEN_TODAY)
    from core.services.allocation_service import AllocationService
    from employees.models import Employee

    operator_a = SystemUser.objects.create_user(
        email="svi03-operator-a@example.com", password=PASSWORD, role=SystemUser.Role.OPERATOR
    )
    operator_b = SystemUser.objects.create_user(
        email="svi03-operator-b@example.com", password=PASSWORD, role=SystemUser.Role.OPERATOR
    )
    employee_a = Employee.objects.create(
        full_name="Operador A Vinculado",
        email=operator_a.email,
        corporate_email=operator_a.email,
        employee_id="SVI03-OP-A",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )
    employee_b = Employee.objects.create(
        full_name="Operador B Vinculado",
        email=operator_b.email,
        corporate_email=operator_b.email,
        employee_id="SVI03-OP-B",
        teams="Araquari",
        status=Employee.Status.ACTIVE,
    )
    line_a = PhoneLine.objects.create(
        phone_number="+5511999998022",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=date(2026, 8, 1),
        whatsapp_seal_expires_on=date(2026, 9, 25),
        whatsapp_seal_email="op-a@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    other_sim = SIMcard.objects.create(iccid="8900000000000088023", carrier="TIM")
    line_b = PhoneLine.objects.create(
        phone_number="+5511999998023",
        sim_card=other_sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_VERIFIED",
        whatsapp_seal_activation_status="NOT_ACTIVATED",
    )
    AllocationService.allocate_line(employee=employee_a, phone_line=line_a, allocated_by=operator_a)
    AllocationService.allocate_line(employee=employee_b, phone_line=line_b, allocated_by=operator_b)

    client.force_login(operator_a)
    response = client.get(reverse("telecom:operator_lines"))
    content = response.content.decode()

    # Controle positivo: a linha do proprio operador aparece.
    assert line_a.phone_number in content
    # RED/GREEN conjugados: o numero de B nao pode aparecer OU, se a
    # tela listar por engano (regressao de escopo, nao do indicador),
    # o rotulo do selo de B jamais pode estar presente.
    assert line_b.phone_number not in content
    assert line_b.seal_status["label"] not in content


# --- I03 — telecom:phoneline_detail --------------------------------------


@pytest.mark.parametrize(
    "seal,days",
    [
        ("META_ONE", 8),
        ("META_ONE", 7),
        ("META_ONE", 1),
        ("META_ONE", 0),
        ("META_ONE", -1),
        ("META_VERIFIED", 8),
    ],
)
def test_detail_phone_number_dd_shows_seal_indicator_at_boundary(
    admin_client, sim, monkeypatch, seal, days
):
    """I03 · apresentacao/HTTP · fronteiras +8/+7/+1/0/-1 dias, ambos os
    tipos de selo · GREEN esperado: SVI-05 (reaproveita SVI-04 para a
    distincao verde/cinza quando o tone deixar de ser so neutral)."""
    monkeypatch.setattr(timezone, "localdate", lambda: FROZEN_TODAY)
    line = PhoneLine.objects.create(
        phone_number=f"+551199999{9100 + days if days >= 0 else 9199}",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal=seal,
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=date(2026, 8, 1),
        whatsapp_seal_expires_on=FROZEN_TODAY + __import__("datetime").timedelta(days=days),
        whatsapp_seal_email="detail@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )

    response = admin_client.get(reverse("telecom:phoneline_detail", args=[line.pk]))
    content = response.content.decode()

    dd = _cell(content, line.phone_number, tag="dd")

    assert line.get_whatsapp_seal_display() in dd
    assert line.seal_status["label"] in dd


def test_detail_phone_number_dd_shows_no_circle_when_no_seal(admin_client, sim):
    """I03 · controle negativo real (nao isolado): Sem selo => nenhum
    icone. Hoje isso ja e verdade (badge nem renderiza), classificado como
    GREEN comprovado, nao RED — mantido aqui como controle da mesma
    celula usada nos testes de RED acima."""
    line = PhoneLine.objects.create(
        phone_number="+5511999998031",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
    )

    response = admin_client.get(reverse("telecom:phoneline_detail", args=[line.pk]))
    content = response.content.decode()

    dd = _cell(content, line.phone_number, tag="dd")
    assert "badge" not in dd
    assert "seal-tone" not in dd


def test_detail_inconsistent_active_without_expiry_shows_dedicated_label(admin_client, sim):
    """I03 · apresentacao/HTTP · borda aprovada #5 (fechamento SVI-02):
    ACTIVE sem vencimento deve mostrar cinza "Situação do selo
    indisponível", distinto de "Não ativado" valido. Hoje
    compute_seal_status colapsa esse caso em "Não ativado" (telecom/
    whatsapp_seal.py:299) — RED real de regra de apresentacao, nao de
    fixture: o dado abaixo e exatamente o estado legado mapeado em SVI-02
    (ACTIVE persistido sem whatsapp_seal_expires_on)."""
    line = PhoneLine.objects.create(
        phone_number="+5511999998032",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_expires_on=None,
        whatsapp_seal_email="inconsistente@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )

    response = admin_client.get(reverse("telecom:phoneline_detail", args=[line.pk]))
    content = response.content.decode()
    dd = _cell(content, line.phone_number, tag="dd")

    assert "Situação do selo indisponível" in dd
    assert line.seal_status["label"] == "Não ativado"  # confirma a causa real


def test_detail_unknown_activation_status_token_shows_dedicated_label(
    admin_client, sim, monkeypatch
):
    """I03 · apresentacao/HTTP · borda aprovada #5 (fechamento SVI-02):
    token de situacao desconhecido precisa de fallback explicito (cinza,
    "Situação do selo indisponível"), nunca tratamento silencioso como
    ACTIVE. Causa real confirmada: compute_seal_status (telecom/
    whatsapp_seal.py:299) so trata NOT_ACTIVATED e "sem vencimento" como
    caminhos especiais — qualquer OUTRO token com vencimento preenchido
    cai no calculo de dias como se fosse ACTIVE valido. whatsapp_seal_
    activation_status e CharField sem choices DB-level: ORM .create()
    aceita o valor sem passar por full_clean(), reproduzindo dado legado/
    corrompido sem inventar mecanismo novo."""
    monkeypatch.setattr(timezone, "localdate", lambda: FROZEN_TODAY)
    line = PhoneLine.objects.create(
        phone_number="+5511999998033",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="TOKEN_DESCONHECIDO",
        whatsapp_seal_expires_on=date(2026, 9, 25),
        whatsapp_seal_email="tokendesconhecido@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )

    response = admin_client.get(reverse("telecom:phoneline_detail", args=[line.pk]))
    content = response.content.decode()
    dd = _cell(content, line.phone_number, tag="dd")

    assert "Situação do selo indisponível" in dd
    # Confirma a causa real: hoje o dominio trata o token desconhecido
    # como ACTIVE valido (mesmo rotulo de uma linha verde legitima).
    assert line.seal_status["label"] == "Vence em 25/09/2026"


def test_detail_get_does_not_write_any_domain_data(admin_client, line_green):
    """I03 · somente leitura: GET de uma tela de apresentacao nao pode
    escrever PhoneLineHistory nem alterar campos do dominio. Representa
    o caminho de apresentacao mais lido deste arquivo (phoneline_detail);
    nao cobre individualmente as demais 27 superficies — citado como
    amostra representativa no Compliance Report, nao como prova
    exaustiva de todos os GETs novos."""
    history_count_before = PhoneLineHistory.objects.filter(phone_line=line_green).count()
    snapshot_before = (
        line_green.whatsapp_seal,
        line_green.whatsapp_seal_activation_status,
        line_green.whatsapp_seal_expires_on,
        line_green.status,
        line_green.updated_at,
    )

    response = admin_client.get(reverse("telecom:phoneline_detail", args=[line_green.pk]))
    assert response.status_code == 200

    line_green.refresh_from_db()
    snapshot_after = (
        line_green.whatsapp_seal,
        line_green.whatsapp_seal_activation_status,
        line_green.whatsapp_seal_expires_on,
        line_green.status,
        line_green.updated_at,
    )

    assert PhoneLineHistory.objects.filter(phone_line=line_green).count() == history_count_before
    assert snapshot_after == snapshot_before


def test_seal_status_property_costs_no_additional_query(db, line_green):
    """I01-I28 (base comum) · custo de consulta: seal_status (telecom/
    models.py:184-185 -> compute_seal_status) le apenas campos ja
    carregados na propria instancia (whatsapp_seal, whatsapp_seal_
    expires_on, whatsapp_seal_activation_status), sem atravessar FK.
    GREEN comprovado hoje: qualquer superficie que reaproveite uma
    instancia de PhoneLine ja carregada (select_related/prefetch
    existente) herda esse custo zero. Isto NAO prova que a integracao
    completa de SVI-05 (27 superficies) sera livre de N+1 — cada view
    ainda precisa buscar a PhoneLine em lote corretamente; aqui so se
    prova que a PROPRIEDADE em si, isolada, nao e a fonte de uma query
    por linha."""
    fetched = PhoneLine.objects.get(pk=line_green.pk)
    with CaptureQueriesContext(connection) as ctx:
        _ = fetched.seal_status
    assert len(ctx) == 0


# --- I04 — telecom:phoneline_update --------------------------------------


def test_edit_form_shows_indicator_adjacent_to_saved_line(admin_client, line_green):
    """I04 · apresentacao/HTTP · bordas aprovadas #3 (fechamento SVI-02):
    indicador referente ao DADO SALVO da linha, junto ao controle de
    numero existente, nao dentro de value. GREEN esperado: SVI-05."""
    response = admin_client.get(reverse("telecom:phoneline_update", args=[line_green.pk]))
    content = response.content.decode()

    window = _window(content, 'name="phone_number"', length=600)

    assert line_green.seal_status["label"] in window
    # Nunca dentro do value do proprio input.
    assert f'value="{line_green.phone_number}{line_green.seal_status["label"]}' not in content


# --- I05 — telecom:phoneline_history --------------------------------------


def test_history_shows_current_seal_labeled_as_such(admin_client, line_green):
    """I05 · apresentacao/HTTP · borda aprovada #1: historico exibe o selo
    ATUAL da linha, identificado como "Selo atual" — nao inventa estado
    passado. GREEN esperado: SVI-05."""
    response = admin_client.get(reverse("telecom:phoneline_history", args=[line_green.pk]))
    content = response.content.decode()

    window = _window(content, line_green.phone_number, length=800)

    assert "Selo atual" in window
    assert line_green.seal_status["label"] in window


# --- I06 — telecom:line_reports -------------------------------------------


def test_line_reports_exact_match_row_shows_seal_indicator(admin_client, line_green):
    """I06 · apresentacao/HTTP · busca exata por numero identificado.
    GREEN esperado: SVI-05. operational_row depende do mesmo motor de
    ciclos de I07 (build_line_reports -> build_line_operational_report):
    sem evento OPENED a linha nao produz linha operacional e a tabela nem
    renderiza, por isso o evento abaixo e necessario para um RED real."""
    from telecom.models import LineDailyActionAuditEvent

    LineDailyActionAuditEvent.objects.create(
        event_type=LineDailyActionAuditEvent.EventType.OPENED,
        source=LineDailyActionAuditEvent.Source.LINE_ALLOCATION,
        source_object_id=line_green.pk,
        occurred_at=timezone.make_aware(__import__("datetime").datetime(2026, 9, 10, 10, 0)),
        phone_line=line_green,
        before_state={},
        after_state={},
    )

    response = admin_client.get(
        reverse("telecom:line_reports"),
        {
            "phone_number": line_green.phone_number,
            "start_date": "2026-08-01",
            "end_date": "2026-09-17",
        },
    )
    content = response.content.decode()

    # A 1a ocorrencia do numero e no input do filtro (value=); a celula do
    # resultado operacional e a 2a — buscar a partir dali evita falso
    # positivo/negativo pela fronteira errada.
    first_idx = content.index(line_green.phone_number)
    table_start = first_idx + len(line_green.phone_number)
    cell = _cell(content[table_start:], line_green.phone_number, tag="td")
    assert line_green.seal_status["label"] in cell


# --- I07 — telecom:line_operational_report --------------------------------


def test_line_operational_report_row_shows_seal_indicator(admin_client, line_green):
    """I07 · apresentacao/HTTP · GREEN esperado: SVI-05. Uma linha so gera
    linha no relatorio operacional se tiver pelo menos um ciclo
    aberto/fechado (build_line_operational_report, "if not overlapping:
    continue") — evento OPENED real, mesmo padrao de criacao direta via
    ORM usado nos testes de relatorio existentes (REL-12-C)."""
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

    response = admin_client.get(reverse("telecom:line_operational_report"))
    content = response.content.decode()

    cell = _cell(content, line_green.phone_number, tag="td")
    assert line_green.seal_status["label"] in cell


# --- I23 — telecom:blip_configuration_list --------------------------------


@pytest.fixture
def line_blip(monkeypatch):
    """Linha com origem=BLIP: unico conjunto "autorizado" de candidatos
    reconhecido hoje (BlipConfigurationForm.__init__, telecom/forms.py:448-
    454 — PhoneLine.objects.filter(origem=PhoneLine.Origem.BLIP)). Usar
    uma linha SEM essa origem para provar associacao exata seria um
    defeito de fixture, nao um RED real da borda "autorizada"."""
    monkeypatch.setattr(timezone, "localdate", lambda: FROZEN_TODAY)
    blip_sim = SIMcard.objects.create(iccid="8900000000000088004", carrier="TIM")
    return PhoneLine.objects.create(
        phone_number="+5511999998040",
        sim_card=blip_sim,
        status=PhoneLine.Status.AVAILABLE,
        origem=PhoneLine.Origem.BLIP,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=date(2026, 8, 1),
        whatsapp_seal_expires_on=date(2026, 9, 25),
        whatsapp_seal_email="blip@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )


def test_blip_list_shows_indicator_for_exact_unique_authorized_match(dev_client, line_blip):
    """I23 · apresentacao/HTTP · borda aprovada #2: BLIP exige associacao
    exata, unica e autorizada (sem FK — comparacao numerica), a partir das
    MESMAS regras de opcoes autorizadas do formulario (origem=BLIP). GREEN
    esperado: SVI-05."""
    _user, client = dev_client
    BlipConfiguration.objects.create(
        blip_id="BLIP-SVI03-1",
        type=BlipConfiguration.ConfigurationType.FLOW,
        description="Fluxo SVI-03",
        phone_number=int(line_blip.phone_number),
        key=BlipConfiguration.KeyType.ACCESS,
        value="token-svi03",
    )

    response = client.get(reverse("telecom:blip_configuration_list"))
    content = response.content.decode()

    cell = _cell(content, str(int(line_blip.phone_number)), tag="td")
    assert line_blip.seal_status["label"] in cell


def test_blip_list_shows_unavailable_label_when_number_not_resolvable(dev_client):
    """I23 · apresentacao/HTTP · borda aprovada #2: numero sem PhoneLine
    correspondente => sem circulo, "Selo indisponível". GREEN esperado:
    SVI-05."""
    _user, client = dev_client
    BlipConfiguration.objects.create(
        blip_id="BLIP-SVI03-2",
        type=BlipConfiguration.ConfigurationType.ROUTER,
        description="Roteador legado sem linha",
        phone_number=5511999998099,
        key=BlipConfiguration.KeyType.HTTP,
        value="token-svi03-legacy",
    )

    response = client.get(reverse("telecom:blip_configuration_list"))
    content = response.content.decode()

    cell = _cell(content, "5511999998099", tag="td")
    assert "Selo indisponível" in cell


def test_blip_list_match_outside_authorized_origem_does_not_leak_seal(dev_client, line_green):
    """I23 · seguranca de identidade · borda aprovada #2: existe
    correspondencia numerica EXATA, mas a PhoneLine encontrada nao tem
    origem=BLIP (fora do conjunto autorizado de candidatos). Resolver
    mesmo assim seria vazar o selo de uma linha fora do escopo da tela.
    line_green (fixture padrao do arquivo) nao tem origem=BLIP — controle
    deliberado desta borda, nao reaproveitamento acidental."""
    _user, client = dev_client
    assert line_green.origem != PhoneLine.Origem.BLIP  # premissa do teste
    BlipConfiguration.objects.create(
        blip_id="BLIP-SVI03-UNAUTH",
        type=BlipConfiguration.ConfigurationType.FLOW,
        description="Numero coincide com linha fora do escopo BLIP",
        phone_number=int(line_green.phone_number),
        key=BlipConfiguration.KeyType.ACCESS,
        value="token-svi03-unauth",
    )

    response = client.get(reverse("telecom:blip_configuration_list"))
    content = response.content.decode()

    cell = _cell(content, str(int(line_green.phone_number)), tag="td")
    assert line_green.seal_status["label"] not in cell
    assert "Selo indisponível" in cell


def test_blip_list_ambiguous_match_does_not_pick_either_line(dev_client):
    """I23 · seguranca de identidade · borda aprovada #2 ("unica"): duas
    PhoneLine com origem=BLIP cujo numero normaliza para o MESMO inteiro
    (zero a esquerda vs sem zero — BlipConfiguration.phone_number e
    BigIntegerField, perde a distincao textual). Associacao ambigua nao
    pode escolher nenhuma das duas arbitrariamente."""
    _user, client = dev_client
    sim_a = SIMcard.objects.create(iccid="8900000000000088005", carrier="TIM")
    sim_b = SIMcard.objects.create(iccid="8900000000000088006", carrier="TIM")
    line_a = PhoneLine.objects.create(
        phone_number="+5511999998041",
        sim_card=sim_a,
        status=PhoneLine.Status.AVAILABLE,
        origem=PhoneLine.Origem.BLIP,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=date(2026, 8, 1),
        whatsapp_seal_expires_on=date(2026, 9, 25),
        whatsapp_seal_email="ambiguo-a@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    line_b = PhoneLine.objects.create(
        phone_number="05511999998041",
        sim_card=sim_b,
        status=PhoneLine.Status.AVAILABLE,
        origem=PhoneLine.Origem.BLIP,
        whatsapp_seal="META_VERIFIED",
        whatsapp_seal_activation_status="NOT_ACTIVATED",
    )
    assert int(line_a.phone_number) == int(line_b.phone_number)  # premissa: colisao real

    BlipConfiguration.objects.create(
        blip_id="BLIP-SVI03-AMBIGUOUS",
        type=BlipConfiguration.ConfigurationType.FLOW,
        description="Numero ambiguo entre duas linhas BLIP",
        phone_number=int(line_a.phone_number),
        key=BlipConfiguration.KeyType.ACCESS,
        value="token-svi03-ambiguous",
    )

    response = client.get(reverse("telecom:blip_configuration_list"))
    content = response.content.decode()

    cell = _cell(content, str(int(line_a.phone_number)), tag="td")
    assert line_a.seal_status["label"] not in cell
    assert line_b.seal_status["label"] not in cell
    assert "Selo indisponível" in cell


# --- I24 — telecom:blip_configuration_update ------------------------------


def test_blip_form_shows_indicator_adjacent_to_select_not_inside_option(dev_client, line_blip):
    """I24 · apresentacao/HTTP · bordas aprovadas #2/#3: indicador junto ao
    seletor nativo, referente a selecao atual — nunca HTML dentro de
    <option>. GREEN esperado: SVI-05."""
    user, client = dev_client
    config = BlipConfiguration.objects.create(
        blip_id="BLIP-SVI03-3",
        type=BlipConfiguration.ConfigurationType.FLOW,
        description="Fluxo com edicao",
        phone_number=int(line_blip.phone_number),
        key=BlipConfiguration.KeyType.ACCESS,
        value="token-svi03-edit",
    )

    response = client.get(reverse("telecom:blip_configuration_update", args=[config.pk]))
    content = response.content.decode()

    # Controle: nenhum <option> hoje carrega markup alem do numero (ja
    # correto, nao e RED) — mantido como guarda de regressao.
    for option_html in content.split("<option")[1:]:
        option_body = option_html.split(">", 1)[1].split("</option>")[0]
        assert "<" not in option_body

    window = _window(content, 'name="phone_number"', length=800)
    assert line_blip.seal_status["label"] in window
