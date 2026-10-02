"""SEV-06 — interface e consumidores dos dados do selo.

Fonte da verdade: docs/superpowers/specs/2026-09-30-whatsapp-seal-
activation-value-design.md (seção "Interface e superfícies consumidoras",
Test Checklist T12/T14/T18/T19).

Cobre lacunas reais ainda não exercitadas por telecom/
test_whatsapp_seal_activation_value.py, telecom/test_phoneline_form_ui.py
ou telecom/test_seal_detail_and_listing.py após a integração de template/JS
desta task:

- Detalhe: situação Não ativado mostra datas como "Não aplicável" (nunca
  como ausência/defeito) e não gera alerta de vencimento; Ativo mostra
  valor mensal formatado em moeda brasileira e datas reais.
- Overview (render inicial, não-ajax) e listagem OPERATOR distinguem Não
  ativado de Sem selo — T12 só tinha cobertura via payload ajax.
- Catálogo é serializado ao formulário via json_script (mecanismo seguro
  do Django), sem segunda fonte de dados duplicada no JS.
- Os 4 campos novos não recebem o atributo HTML `required` incondicional
  (progressive enhancement), estendendo a verificação que
  test_phoneline_form_ui.py já fazia só para os 4 campos antigos.

Nenhum teste aqui afirma comportamento de JavaScript real (execução de
clique/alternância em navegador) — isso é aceite visual de SEV-07.
"""

import json
import re
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from telecom.models import PhoneLine, SIMcard
from telecom.whatsapp_seal import seal_catalog_entries
from users.models import SystemUser

NEW_SEAL_DETAIL_FIELD_NAMES = [
    "whatsapp_seal_activation_status",
    "whatsapp_seal_category",
    "whatsapp_seal_plan",
    "whatsapp_seal_monthly_value",
]


def field_tag(content, field_name):
    match = re.search(
        r'<(?:input|select)[^>]*name="%s"[^>]*>' % re.escape(field_name), content
    )
    assert match, f"campo {field_name} não encontrado no HTML"
    return match.group(0)


@pytest.fixture
def sim(db):
    return SIMcard.objects.create(iccid="8900000000000080001", carrier="TIM")


@pytest.fixture
def admin_client(client, db):
    user = SystemUser.objects.create_user(
        email="sev06-admin@example.com", password="test-only", role=SystemUser.Role.ADMIN
    )
    client.force_login(user)
    return client


# ---------------------------------------------------------------------------
# Formulário — os 4 campos novos nunca recebem `required` incondicional.
# ---------------------------------------------------------------------------


def test_novos_campos_do_selo_nao_recebem_required_incondicional(admin_client):
    response = admin_client.get(reverse("telecom:phoneline_create"))
    content = response.content.decode()
    for field_name in NEW_SEAL_DETAIL_FIELD_NAMES:
        assert "required" not in field_tag(content, field_name)


def test_catalogo_serializado_via_json_script_sem_segunda_fonte(admin_client):
    """O catálogo deve chegar ao JS apenas via json_script (mecanismo seguro
    do Django, escapando a saída), nunca concatenado em <script> manual."""
    response = admin_client.get(reverse("telecom:phoneline_create"))
    content = response.content.decode()

    match = re.search(
        r'<script id="seal-catalog-data" type="application/json">(.*?)</script>',
        content,
        re.S,
    )
    assert match, "bloco json_script do catálogo não encontrado"
    entries = json.loads(match.group(1))
    assert entries == seal_catalog_entries()
    assert len(entries) == 4
    assert {"META_ONE", "META_VERIFIED"} == {entry["seal"] for entry in entries}


# ---------------------------------------------------------------------------
# Detalhe — Não ativado vs Ativo.
# ---------------------------------------------------------------------------


def test_detalhe_nao_ativado_mostra_datas_nao_aplicavel_sem_alerta(admin_client, sim):
    line = PhoneLine.objects.create(
        phone_number="+5511999998001",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="NOT_ACTIVATED",
        whatsapp_seal_category="CREATORS_BUSINESSES",
        whatsapp_seal_plan="ONE_ESSENTIAL",
        whatsapp_seal_monthly_value=Decimal("59.00"),
        whatsapp_seal_email="seal@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    response = admin_client.get(reverse("telecom:phoneline_detail", args=[line.pk]))
    content = response.content.decode()

    assert "Não ativado" in content
    assert "Não aplicável" in content
    assert "Vencido" not in content
    assert "Vence em" not in content
    assert "R$ 59,00" in content


def test_detalhe_ativo_mostra_valor_formatado_e_datas_reais(admin_client, sim):
    line = PhoneLine.objects.create(
        phone_number="+5511999998002",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_VERIFIED",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_category="PERSONAL_CREATOR",
        whatsapp_seal_plan="STANDARD",
        whatsapp_seal_monthly_value=Decimal("53.90"),
        whatsapp_seal_activated_on=date(2026, 9, 1),
        whatsapp_seal_expires_on=date(2026, 12, 1),
        whatsapp_seal_email="seal@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    response = admin_client.get(reverse("telecom:phoneline_detail", args=[line.pk]))
    content = response.content.decode()

    assert "R$ 53,90" in content
    assert "01/09/2026" in content
    assert "01/12/2026" in content
    assert "Pessoa Física (Uso Pessoal / Criador)" in content
    assert "Standard" in content
    assert "Não aplicável" not in content


def test_detalhe_legado_valor_ausente_nunca_mostra_r_zero(admin_client, sim):
    line = PhoneLine.objects.create(
        phone_number="+5511999998003",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activated_on=date(2026, 1, 10),
        whatsapp_seal_expires_on=date(2026, 12, 10),
        whatsapp_seal_email="legado@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    response = admin_client.get(reverse("telecom:phoneline_detail", args=[line.pk]))
    content = response.content.decode()
    assert "R$ 0,00" not in content
    assert "Não informado" in content


def _monthly_value_dd(content):
    """Recorta só o <dd> do campo "Valor mensal (R$)" no detalhe — uma
    ocorrência genérica de "R$ ..." na página não comprova o requisito
    (ex.: poderia vir de outro valor, se algum dia existir)."""
    match = re.search(
        r'<dt class="col-sm-3">Valor mensal \(R\$\)</dt>\s*'
        r'<dd class="col-sm-9">([^<]*)</dd>',
        content,
    )
    assert match, "campo Valor mensal (R$) não encontrado no detalhe"
    return match.group(1).strip()


# ---------------------------------------------------------------------------
# Contrato monetário na fronteira real (template) — ausência vs zero
# explícito. Decimal("0.00") é valor válido para Não ativado (nunca
# ausência); None nunca é convertido em "R$ 0,00".
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "index,monthly_value,expected",
    [
        (0, None, "Não informado"),
        (1, Decimal("0.00"), "R$ 0,00"),
        (2, Decimal("59.00"), "R$ 59,00"),
        (3, Decimal("53.90"), "R$ 53,90"),
        (4, Decimal("299.00"), "R$ 299,00"),
    ],
)
def test_detalhe_campo_valor_distingue_ausencia_de_zero_explicito(
    admin_client, index, monthly_value, expected
):
    line = PhoneLine.objects.create(
        phone_number=f"+551199999810{index}",
        sim_card=SIMcard.objects.create(
            iccid=f"8900000000000081{index:03d}", carrier="TIM"
        ),
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="NOT_ACTIVATED",
        whatsapp_seal_category="CREATORS_BUSINESSES",
        whatsapp_seal_plan="ONE_ESSENTIAL",
        whatsapp_seal_monthly_value=monthly_value,
        whatsapp_seal_email="seal@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    response = admin_client.get(reverse("telecom:phoneline_detail", args=[line.pk]))
    content = response.content.decode()
    assert _monthly_value_dd(content) == expected


def test_property_whatsapp_seal_monthly_value_display_distingue_ausencia_de_zero(sim):
    """Fronteira de domínio (property), sem HTTP/template: None permanece
    None (não é convertido para string); Decimal("0.00") é formatado como
    "R$ 0,00", nunca omitido nem tratado como ausência."""
    line = PhoneLine.objects.create(
        phone_number="+5511999998010",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
    )
    assert line.whatsapp_seal_monthly_value_display is None

    line.whatsapp_seal_monthly_value = Decimal("0.00")
    assert line.whatsapp_seal_monthly_value_display == "R$ 0,00"

    line.whatsapp_seal_monthly_value = Decimal("299.00")
    assert line.whatsapp_seal_monthly_value_display == "R$ 299,00"


# ---------------------------------------------------------------------------
# Overview (render inicial, não-ajax) e OPERATOR distinguem Não ativado.
# ---------------------------------------------------------------------------


def test_overview_render_inicial_distingue_nao_ativado_de_sem_selo(admin_client, sim):
    sim2 = SIMcard.objects.create(iccid="8900000000000080002", carrier="TIM")
    not_activated = PhoneLine.objects.create(
        phone_number="+5511999998004",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="NOT_ACTIVATED",
        whatsapp_seal_category="CREATORS_BUSINESSES",
        whatsapp_seal_plan="ONE_ESSENTIAL",
        whatsapp_seal_monthly_value=Decimal("59.00"),
        whatsapp_seal_email="seal@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    without_seal = PhoneLine.objects.create(
        phone_number="+5511999998005", sim_card=sim2, status=PhoneLine.Status.AVAILABLE
    )

    response = admin_client.get(reverse("telecom:overview"))
    content = response.content.decode()
    assert response.status_code == 200
    assert not_activated.phone_number in content
    assert without_seal.phone_number in content
    assert "Não ativado" in content
    assert "Sem selo" in content


def test_operator_lines_distingue_nao_ativado_de_sem_selo(client, db, sim):
    from core.services.allocation_service import AllocationService
    from employees.models import Employee

    admin = SystemUser.objects.create_user(
        email="sev06-admin-op@example.com", password="test-only", role=SystemUser.Role.ADMIN
    )
    operator = SystemUser.objects.create_user(
        email="sev06-operator@example.com", password="test-only", role=SystemUser.Role.OPERATOR
    )
    employee = Employee.objects.create(
        full_name="SEV06 Operator",
        corporate_email="sev06-manager@example.com",
        email="sev06-operator@example.com",
        employee_id="SEV06-1",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )
    sim2 = SIMcard.objects.create(iccid="8900000000000080003", carrier="TIM")
    not_activated = PhoneLine.objects.create(
        phone_number="+5511999998006",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="NOT_ACTIVATED",
        whatsapp_seal_category="CREATORS_BUSINESSES",
        whatsapp_seal_plan="ONE_ESSENTIAL",
        whatsapp_seal_monthly_value=Decimal("59.00"),
        whatsapp_seal_email="seal@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    without_seal = PhoneLine.objects.create(
        phone_number="+5511999998007", sim_card=sim2, status=PhoneLine.Status.AVAILABLE
    )
    AllocationService.allocate_line(employee=employee, phone_line=not_activated, allocated_by=admin)
    AllocationService.allocate_line(employee=employee, phone_line=without_seal, allocated_by=admin)

    client.force_login(operator)
    response = client.get(reverse("telecom:operator_lines"))
    content = response.content.decode()
    assert response.status_code == 200
    assert "Não ativado" in content
    assert "Sem selo" in content
