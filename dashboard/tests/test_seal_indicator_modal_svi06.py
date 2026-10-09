"""SVI-06 — aceite em navegador: fecha a lacuna registrada em SVI-03/05
("modal JS-only de detalhe da linha ... registrado como lacuna reservada
para SVI-06") sobre o modal de detalhe da linha (I11) em
daily_user_action_board nao carregar nenhum dado de selo.

Fonte da verdade: docs/superpowers/specs/2026-10-05-phone-line-seal-
indicator-design.md, I11 ("Célula da tabela e modal de detalhes alimentado
por data-line-number; adicionar projeção estruturada também ao modal").

Smoke real em navegador (docs/superpowers/evidence/SVI-06/svi06_smoke.mjs)
provou que, antes desta correção, o modal abria sem nenhum indicador. Este
teste prova o contrato de dados/markup server-side (o que o Django test
client consegue provar); a renderizacao do DOM pelo JS continua provada
pelo smoke real, nao por este teste.
"""

import json
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from core.services.allocation_service import AllocationService
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser

PASSWORD = "StrongPass123"


def test_daily_user_action_board_line_button_carries_seal_json_for_modal(
    client, db
):
    """I11 · apresentacao/HTTP · botao server-rendered deve carregar
    data-line-seal com o mesmo SealIndicator.as_dict() usado pelo
    SealIndicator.createNode (JS) em outras telas — sem isso, o JS do modal
    (inalterado desde antes de SVI-04) nao tem nenhum dado para desenhar o
    indicador, mesmo a celula da tabela ja mostrando o circulo correto."""
    admin = SystemUser.objects.create_user(
        email="svi06-dash-super@example.com", password=PASSWORD, role=SystemUser.Role.SUPER
    )
    client.force_login(admin)
    employee = Employee.objects.create(
        full_name="Funcionario Modal SVI06",
        corporate_email=admin.email,
        employee_id="SVI06-MODAL-1",
        teams="Joinville",
        status=Employee.Status.ACTIVE,
    )
    sim = SIMcard.objects.create(iccid="8900000000000077060", carrier="TIM")
    line = PhoneLine.objects.create(
        phone_number="+5511999997760",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_activated_on=timezone.localdate() - timedelta(days=30),
        whatsapp_seal_expires_on=timezone.localdate() + timedelta(days=8),
    )
    AllocationService.allocate_line(employee=employee, phone_line=line, allocated_by=admin)

    response = client.get(reverse("daily_user_action_board"))
    content = response.content.decode()

    marker = f'data-line-number="{line.phone_number}"'
    idx = content.index(marker)
    button_start = content.rindex("<button", 0, idx)
    button_end = content.index("</button>", idx) + len("</button>")
    button_html = content[button_start:button_end]

    assert "data-line-seal=" in button_html, (
        "botao do modal de detalhe (I11) sem data-line-seal: modal nao tem "
        "como desenhar o indicador"
    )

    attr_marker = "data-line-seal=\""
    attr_start = button_html.index(attr_marker) + len(attr_marker)
    attr_end = button_html.index('"', attr_start)
    raw_json = button_html[attr_start:attr_end]
    unescaped = (
        raw_json.replace("&quot;", '"')
        .replace("&amp;", "&")
        .replace("&#x27;", "'")
        .replace("&#39;", "'")
    )
    payload = json.loads(unescaped)

    assert payload["css_class"] == "seal-indicator--green"
    assert payload["show_circle"] is True
    assert line.seal_status["label"] in payload["accessible_text"]


def test_daily_user_action_board_modal_has_seal_target_slot(client, db):
    """I11 · apresentacao/HTTP · o modal de detalhes precisa de um elemento
    dedicado (data-line-detail="seal") para o JS anexar o no do indicador —
    sem repetir o numero como texto decorativo e sem reescrever os demais
    campos ja existentes do modal."""
    admin = SystemUser.objects.create_user(
        email="svi06-dash-super2@example.com", password=PASSWORD, role=SystemUser.Role.SUPER
    )
    client.force_login(admin)

    response = client.get(reverse("daily_user_action_board"))
    content = response.content.decode()

    assert 'data-line-detail="seal"' in content
