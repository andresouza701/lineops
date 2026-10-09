"""SVI-07 (revisão final do diff) — achado real P1: o Admin de
Pendências (I28) quebrava com AttributeError ao renderizar uma
AllocationPendency sem alocação (`allocation=None`, caso legítimo e
admitido pelo model — pendência de funcionário sem linha).

Causa confirmada: `AllocationPendencyAdmin.allocation_display` acessava
`obj.allocation.phone_line` sem guarda de ausência.

Reprodução original desta rodada: `docs/superpowers/evidence/SVI-07/
final-diff-review-2026-10-09/review_probes.py::
test_nullable_allocation_admin` (preservado como artefato histórico da
revisão, não apagado). Este arquivo é a cobertura permanente.

RETIFICAÇÃO (rodada de correção do N+1, mesma data): a rodada anterior
classificou o N+1 da coluna "employee" como "achado alheio pré-existente,
fora do escopo de P1". Essa classificação estava ERRADA — confirmado por
`git show HEAD:pendencies/admin.py` (antes de qualquer alteração de SVI):
o Admin não declarava `list_select_related` nenhum; nesse caso, o Django
aplica `select_related()` automático (sem argumentos, 1 hop) sempre que
há FK em `list_display` e `list_select_related` não foi declarado —
`ChangeList.apply_select_related`/`has_related_field_in_list_display`
(`django/contrib/admin/views/main.py`). Isso já cobria "employee"
automaticamente: 1 query para a lista inteira. A declaração explícita de
`list_select_related = ("allocation", "allocation__phone_line",
"allocation__employee")`, introduzida por esta própria feature, DESLIGA
essa automação e passa a cobrir só os caminhos listados — "employee"
ficou de fora, virando 1 query extra por linha a partir desta feature,
não antes dela. Corrigido incluindo "employee" na mesma lista explícita
(`pendencies/admin.py`). Ver seção dedicada na fonte da verdade."""

from datetime import date

import pytest
from django.contrib import admin
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from allocations.models import LineAllocation
from core.services.allocation_service import AllocationService
from employees.models import Employee
from pendencies.admin import AllocationPendencyAdmin
from pendencies.models import AllocationPendency
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser

PASSWORD = "StrongPass123"
FROZEN_TODAY = date(2026, 9, 17)


@pytest.fixture
def superuser_client(client, db):
    user = SystemUser.objects.create_superuser(
        email="svi07-pend-nullalloc-root@example.com", password=PASSWORD, role=SystemUser.Role.ADMIN
    )
    client.force_login(user)
    return user, client


def test_allocation_display_handles_allocation_none_without_crashing():
    """P1 · unitário · chamando o método diretamente com allocation=None
    (reprodução original da revisão) — não deve levantar AttributeError,
    deve devolver o valor vazio padrão do próprio Admin (nenhum
    telefone/selo inventado)."""
    admin_instance = AllocationPendencyAdmin(AllocationPendency, admin.site)
    pendency = AllocationPendency(allocation=None)

    result = admin_instance.allocation_display(pendency)

    assert str(result) == str(admin_instance.get_empty_value_display())


@pytest.mark.django_db
def test_admin_changelist_renders_200_with_a_pendency_without_allocation(
    superuser_client, monkeypatch
):
    """P1 · GET real da changelist com uma pendência allocation=None —
    200, sem crash, mostra o valor vazio padrão na linha dessa
    pendência."""
    monkeypatch.setattr(timezone, "localdate", lambda: FROZEN_TODAY)
    _admin, client = superuser_client
    employee = Employee.objects.create(
        full_name="Funcionario Sem Linha",
        corporate_email="sem-linha-svi07@example.com",
        employee_id="SVI07-NO-ALLOC-1",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )
    pendency = AllocationPendency.objects.create(employee=employee, allocation=None)

    response = client.get(reverse("admin:pendencies_allocationpendency_changelist"))

    assert response.status_code == 200
    content = response.content.decode()
    assert employee.full_name in content
    admin_instance = admin.site._registry[AllocationPendency]
    empty_display = str(admin_instance.get_empty_value_display())
    idx = content.index(employee.full_name)
    row_start = content.rindex("<tr", 0, idx)
    row_end = content.index("</tr>", idx) + len("</tr>")
    row = content[row_start:row_end]
    assert empty_display in row
    assert pendency.pk  # garante que o objeto sem alocacao de fato existe no banco


@pytest.mark.django_db
def test_admin_changelist_still_shows_indicator_for_pendency_with_allocation(
    superuser_client, monkeypatch
):
    """P1 · regressão: uma pendência COM alocação e selo continua
    renderizando o indicador normalmente, na MESMA changelist que também
    contém uma pendência sem alocação (garante que a guarda não afeta o
    caminho com dado presente)."""
    monkeypatch.setattr(timezone, "localdate", lambda: FROZEN_TODAY)
    admin_user, client = superuser_client

    employee_without_line = Employee.objects.create(
        full_name="Funcionario Sem Linha Dois",
        corporate_email="sem-linha-svi07-2@example.com",
        employee_id="SVI07-NO-ALLOC-2",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )
    AllocationPendency.objects.create(employee=employee_without_line, allocation=None)

    employee_with_line = Employee.objects.create(
        full_name="Funcionario Com Linha Selo",
        corporate_email="com-linha-svi07@example.com",
        employee_id="SVI07-WITH-ALLOC-1",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )
    sim = SIMcard.objects.create(iccid="8900000000000077051", carrier="TIM")
    line = PhoneLine.objects.create(
        phone_number="+5511999997751",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=date(2026, 8, 1),
        whatsapp_seal_expires_on=date(2026, 9, 25),
    )
    AllocationService.allocate_line(employee=employee_with_line, phone_line=line, allocated_by=admin_user)
    allocation = LineAllocation.objects.get(employee=employee_with_line, phone_line=line, is_active=True)
    AllocationPendency.objects.create(employee=employee_with_line, allocation=allocation)

    response = client.get(reverse("admin:pendencies_allocationpendency_changelist"))
    assert response.status_code == 200
    content = response.content.decode()

    idx = content.index(line.phone_number)
    row_start = content.rindex("<tr", 0, idx)
    row_end = content.index("</tr>", idx) + len("</tr>")
    row = content[row_start:row_end]
    assert line.seal_status["label"] in row


def _make_pendencies(admin_user, count, prefix, with_allocation):
    """Cria `count` pendencias de funcionarios DISTINTOS (nomes/ids
    unicos por prefixo+indice) — distinto e essencial para a prova de
    ausencia de N+1: reaproveitar o mesmo funcionario nao exercitaria a
    consulta por linha que o bug original causava."""
    employees = []
    for i in range(count):
        employee = Employee.objects.create(
            full_name=f"Funcionario Custo {prefix}-{i}",
            corporate_email=f"custo-{prefix}-{i}@example.com",
            employee_id=f"SVI07-COST-{prefix}-{i}",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        employees.append(employee)
        if not with_allocation:
            AllocationPendency.objects.create(employee=employee, allocation=None)
            continue
        sim = SIMcard.objects.create(iccid=f"890000000000096{prefix}{i:03d}", carrier="TIM")
        line = PhoneLine.objects.create(
            phone_number=f"+551155555{prefix}{i:03d}",
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
            whatsapp_seal="META_ONE",
            whatsapp_seal_activation_status="ACTIVE",
            whatsapp_seal_activated_on=date(2026, 8, 1),
            whatsapp_seal_expires_on=date(2026, 9, 25),
        )
        AllocationService.allocate_line(employee=employee, phone_line=line, allocated_by=admin_user)
        allocation = LineAllocation.objects.get(employee=employee, phone_line=line, is_active=True)
        AllocationPendency.objects.create(employee=employee, allocation=allocation)
    return employees


@pytest.mark.django_db
def test_admin_changelist_query_count_does_not_grow_with_distinct_employees(
    superuser_client, monkeypatch
):
    """P1/N+1 · prova real de ausência de N+1: poucas (2) vs muitas (22)
    pendências, funcionários DISTINTOS em cada rodada, misturando
    `allocation=None` e `allocation` preenchida. Exige conteúdo
    REALMENTE renderizado (nomes dos funcionários esperados presentes no
    HTML — não apenas status 200) e que a contagem de consultas NÃO
    cresça com o número de linhas. Substitui o comparativo anterior
    (5 sem alocação vs 5 com alocação, mesmo tamanho), que não
    demonstrava ausência de N+1 — só que os dois caminhos tinham custo
    parecido entre si, sem provar que nenhum dos dois crescia por linha."""
    monkeypatch.setattr(timezone, "localdate", lambda: FROZEN_TODAY)
    admin_user, client = superuser_client
    url = reverse("admin:pendencies_allocationpendency_changelist")

    small_employees = _make_pendencies(admin_user, 1, "smallA", with_allocation=False) + _make_pendencies(
        admin_user, 1, "smallB", with_allocation=True
    )
    with CaptureQueriesContext(connection) as small_ctx:
        small_response = client.get(url)
    assert small_response.status_code == 200
    small_content = small_response.content.decode()
    for employee in small_employees:
        assert employee.full_name in small_content

    large_employees = _make_pendencies(admin_user, 10, "largeA", with_allocation=False) + _make_pendencies(
        admin_user, 10, "largeB", with_allocation=True
    )
    with CaptureQueriesContext(connection) as large_ctx:
        large_response = client.get(url)
    assert large_response.status_code == 200
    large_content = large_response.content.decode()
    # Conteudo real: os funcionarios da rodada pequena (ainda no banco) E
    # os da rodada grande precisam aparecer — nao so um subconjunto.
    for employee in small_employees + large_employees:
        assert employee.full_name in large_content

    assert len(large_ctx) == len(small_ctx), (
        "Consultas do Admin de AllocationPendency cresceram com o numero "
        f"de pendencias/funcionarios distintos: {len(small_ctx)} (2 "
        f"pendencias) vs {len(large_ctx)} (22 pendencias) — N+1 real, "
        "nao tolerado."
    )
