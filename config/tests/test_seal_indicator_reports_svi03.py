"""SVI-03 — testes RED do indicador visual de selo junto ao número.

Fonte da verdade: docs/superpowers/specs/2026-10-05-phone-line-seal-
indicator-design.md. Cobre I18-I22 (os cinco relatorios operacionais que
exibem telefone em reports/home.html: whatsapp_seal, line_inventory,
allocations, pendencies, line_history) da matriz.

Nenhuma destas linhas de teste altera filtro, periodo, ordenacao, total
ou paginacao dos relatorios — nem CSV/XLSX (cobertura dessas exportacoes
ja existe nos arquivos config/tests/test_*_report.py e e reaproveitada,
nao duplicada aqui).

Borda critica de I22 (line_history): o dataclass LineHistoryReportRow
(core/services/line_history_report_service.py) so carrega
"phone_number: str" — SEM FK. Quando o evento vem de
LineDailyActionAuditEvent com phone_line NULL, o numero usado e
phone_number_snapshot (coluna de texto, sem vinculo). O teste
test_line_history_snapshot_without_fk_does_not_inherit_seal_from_other_line
prova a borda aprovada do fechamento SVI-02 #2: um snapshot sem FK nao
pode "herdar" o selo de outra PhoneLine que por acaso tem o mesmo
telefone.

GREEN esperado: SVI-05, reaproveitando a projecao central de SVI-04.
"""

import re
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

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


def _cell(html, marker, tag="td"):
    # Marcador aparece mais de uma vez na pagina (input do filtro "linha",
    # link de exportacao, celula de resultado) — a celula real de
    # resultado e identificada por conter o numero como TEXTO DIRETO do
    # elemento, imediatamente ANTES do fechamento da tag (nao como
    # substring de um href/value, nem como prefixo de um numero mais
    # longo).
    #
    # Ajuste aprovado 2026-10-11 (indicador a esquerda do numero): o
    # componente passou a vir ANTES do numero dentro da mesma celula
    # ("{% seal_indicator ... %}{{ row.phone_number }}"), entao o
    # lookahead abaixo exige o numero logo antes do fechamento da tag
    # (nao mais logo depois da abertura) — o conteudo anterior (o
    # indicador) pode ser qualquer coisa.
    pattern = re.compile(
        rf"<{tag}[^>]*>.*?{re.escape(marker)}(?=\s*</{tag}>).*?</{tag}>",
        re.DOTALL,
    )
    match = pattern.search(html)
    if not match:
        raise AssertionError(
            f"Nenhum <{tag}> com {marker!r} como conteudo direto foi encontrado."
        )
    return match.group(0)


def _report_url(relatorio, **extra):
    pairs = [
        ("relatorio", relatorio),
        ("data_inicial", PERIOD_START),
        ("data_final", PERIOD_END),
    ]
    pairs.extend(extra.items())
    return f"{reverse('reports_home')}?{urlencode(pairs)}"


@pytest.fixture
def admin_client(client, db, monkeypatch):
    monkeypatch.setattr(timezone, "localdate", lambda: date(2026, 9, 17))
    user = SystemUser.objects.create_user(
        email="svi03-reports-admin@example.com", password=PASSWORD, role=SystemUser.Role.ADMIN
    )
    client.force_login(user)
    return user, client


@pytest.fixture
def sim(db):
    return SIMcard.objects.create(iccid="8900000000000077060", carrier="TIM")


@pytest.fixture
def line_green(sim):
    line = PhoneLine.objects.create(
        phone_number="+5511999997760",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=date(2026, 8, 1),
        whatsapp_seal_expires_on=date(2026, 9, 25),
        whatsapp_seal_email="report@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    # created_at usa auto_now_add (timezone.now() real, nao afetado pelo
    # monkeypatch de localdate) — ajustado para dentro do periodo do
    # relatorio (REL-12-C/REL-08-C: mesmo padrao ORM direto ja usado nos
    # arquivos de teste de relatorio existentes), senao line_inventory
    # (filtro por created_at) nunca encontraria a linha.
    PhoneLine.objects.filter(pk=line.pk).update(
        created_at=timezone.make_aware(datetime(2026, 9, 10, 10, 0))
    )
    return line


# --- I18 — reports_home, whatsapp_seal -------------------------------------


def test_whatsapp_seal_report_row_shows_seal_indicator(admin_client, line_green):
    """I18 · apresentacao/HTTP · GREEN esperado: SVI-05."""
    _admin, client = admin_client
    response = client.get(
        _report_url("whatsapp_seal", linha=line_green.phone_number)
    )
    content = response.content.decode()

    cell = _cell(content, line_green.phone_number, tag="td")
    assert line_green.seal_status["label"] in cell


# --- I19 — reports_home, line_inventory ------------------------------------


def test_line_inventory_report_row_shows_seal_indicator(admin_client, line_green):
    """I19 · apresentacao/HTTP · GREEN esperado: SVI-05."""
    _admin, client = admin_client
    response = client.get(
        _report_url("line_inventory", linha=line_green.phone_number)
    )
    content = response.content.decode()

    cell = _cell(content, line_green.phone_number, tag="td")
    assert line_green.seal_status["label"] in cell


# --- I20 — reports_home, allocations ----------------------------------------


def test_allocations_report_row_shows_seal_indicator(admin_client, line_green):
    """I20 · apresentacao/HTTP · GREEN esperado: SVI-05."""
    admin, client = admin_client
    employee = Employee.objects.create(
        full_name="Funcionario Relatorio Alocacoes",
        corporate_email="rel-alocacoes@example.com",
        employee_id="SVI03-REL-ALLOC-1",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )
    AllocationService.allocate_line(employee=employee, phone_line=line_green, allocated_by=admin)
    LineAllocation.objects.filter(employee=employee, phone_line=line_green, is_active=True).update(
        allocated_at=timezone.make_aware(datetime(2026, 9, 10, 10, 0))
    )

    response = client.get(_report_url("allocations", linha=line_green.phone_number))
    content = response.content.decode()

    cell = _cell(content, line_green.phone_number, tag="td")
    assert line_green.seal_status["label"] in cell


# --- I21 — reports_home, pendencies ------------------------------------------


def test_pendencies_report_row_shows_seal_indicator(admin_client, line_green):
    """I21 · apresentacao/HTTP · GREEN esperado: SVI-05."""
    admin, client = admin_client
    employee = Employee.objects.create(
        full_name="Funcionario Relatorio Pendencias",
        corporate_email="rel-pendencias@example.com",
        employee_id="SVI03-REL-PEND-1",
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
    # pendency_submitted_at so e preenchido quando action != NO_ACTION
    # (pendencies/models.py); valor real de save() ainda cai fora do
    # periodo fixo abaixo, mesmo ajuste ORM direto do restante do arquivo.
    AllocationPendency.objects.filter(pk=pendency.pk).update(
        pendency_submitted_at=timezone.make_aware(datetime(2026, 9, 10, 10, 0))
    )

    response = client.get(_report_url("pendencies", linha=line_green.phone_number))
    content = response.content.decode()

    cell = _cell(content, line_green.phone_number, tag="td")
    assert line_green.seal_status["label"] in cell


# --- I22 — reports_home, line_history ---------------------------------------


def test_line_history_report_row_shows_seal_indicator_for_fk_event(admin_client, line_green):
    """I22 · apresentacao/HTTP · evento com phone_line FK presente.
    GREEN esperado: SVI-05."""
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

    cell = _cell(content, line_green.phone_number, tag="td")
    assert line_green.seal_status["label"] in cell


def test_line_history_snapshot_without_fk_does_not_inherit_seal_from_other_line(
    admin_client, line_green
):
    """I22 · seguranca de identidade · borda aprovada (fechamento SVI-02
    #2): snapshot sem FK (phone_line NULL, phone_number_snapshot apenas
    texto) NAO pode herdar o selo de outra PhoneLine com o mesmo numero.
    GREEN esperado: SVI-05 — o snapshot deve mostrar "Selo indisponível",
    nunca o rotulo real da linha identificada que coincide no texto."""
    _admin, client = admin_client
    LineDailyActionAuditEvent.objects.create(
        event_type=LineDailyActionAuditEvent.EventType.OPENED,
        source=LineDailyActionAuditEvent.Source.DAILY_USER_ACTION,
        source_object_id=999001,
        occurred_at=timezone.make_aware(datetime(2026, 9, 11, 10, 0)),
        phone_line=None,
        phone_number_snapshot=line_green.phone_number,
        before_state={},
        after_state={},
    )

    # incluir_excluidos=1: por padrao o motor exclui phone_line__isnull
    # (linha nao resolvida por FK) do resultado — precisa ser pedido
    # explicitamente para o snapshot aparecer (core/services/
    # line_history_report_service.py::_audit_base_queryset).
    response = client.get(
        _report_url("line_history", linha=line_green.phone_number, incluir_excluidos="1")
    )
    content = response.content.decode()

    cell = _cell(content, line_green.phone_number, tag="td")
    # RED esperado por dois motivos possiveis e distintos, registrados
    # ambos: hoje a celula nao tem indicador algum (nem "indisponivel");
    # a regra de nao-heranca so sera validada de fato quando a celula
    # existir e ainda assim nao expuser line_green.seal_status["label"].
    assert "Selo indisponível" in cell
    assert line_green.seal_status["label"] not in cell
