"""SVI-07 (checagem final, rodada 3) — dois achados reais sobre o CSS do
indicador de selo no Django Admin (I25-I28), nesta ordem:

1. Django Admin nunca carregava static/css/styles.css, entao o indicador
   de selo aparecia no DOM (estrutura/atributos corretos, confirmado
   desde SVI-05) mas SEM NENHUM estilo aplicado — ponto transparente,
   width:auto, border-radius:0px (nao e um circulo), foco sem efeito.
   Corrigido (rodada anterior) adicionando `class Media` com
   static/css/styles.css aos 4 ModelAdmin.

2. Retificacao dessa correcao: carregar o arquivo INTEIRO introduzia
   regras GLOBAIS (seletores de elemento puro: body, h1-h6, input,
   select, table/td/th) que vazavam para os controles NATIVOS do Admin —
   confirmado em Chrome real, comparando a MESMA pagina com/sem o
   stylesheet via interceptacao de rede (nao harness, nao suposicao):
   body.background mudava de branco (Admin) para o gradiente escuro do
   LineOps; o pior caso concreto — campos de texto (<input>) ficavam com
   fundo claro (#f8f8f8, herdado do proprio Admin) e COR DE TEXTO quase
   branca (var(--text-strong), pensada para fundo escuro) — texto
   efetivamente ilegivel no campo de busca/formularios do Admin.

Correcao final (menor escopo, sem duplicar regras divergentes): as
regras do componente (.seal-indicator*) foram extraidas para
static/css/seal_indicator.css, um arquivo PROPRIO, pequeno, sem nenhum
seletor de elemento global — cada var() de cor ganhou um fallback
explicito (mesmo valor do :root de styles.css, mesma tecnica ja usada
para --border-focus/--text-strong antes desta correcao), entao o arquivo
funciona sozinho, sem depender do :root de styles.css estar presente.
static/css/styles.css passa a importar esse mesmo arquivo (@import, uma
unica fonte, sem copia) para o app principal continuar identico; os 4
ModelAdmin passam a referenciar SO static/css/seal_indicator.css (nao
mais o arquivo inteiro) — nenhuma regra global do projeto chega ao
Admin.

Evidencia completa (comparacao com/sem stylesheet, screenshots, cores
computadas): docs/superpowers/evidence/SVI-07/admin_css_check/.
"""

import pytest
from django.urls import reverse

from telecom.models import BlipConfiguration, PhoneLine, SIMcard
from users.models import SystemUser

PASSWORD = "StrongPass123"
SCOPED_STYLESHEET = "css/seal_indicator.css"
FULL_PROJECT_STYLESHEET = "css/styles.css"


@pytest.fixture
def superuser_client(client, db):
    user = SystemUser.objects.create_superuser(
        email="svi07-admin-styles@example.com", password=PASSWORD, role=SystemUser.Role.ADMIN
    )
    client.force_login(user)
    return client


@pytest.mark.parametrize(
    "url_name",
    [
        "admin:telecom_simcard_changelist",
        "admin:telecom_blipconfiguration_changelist",
        "admin:allocations_lineallocation_changelist",
        "admin:pendencies_allocationpendency_changelist",
    ],
)
def test_admin_changelist_loads_scoped_seal_indicator_stylesheet(
    superuser_client, url_name
):
    """I25-I28 · o Admin precisa carregar o CSS do indicador para ter
    cor/forma e a regra de foco (SVI-07) funcionar — sem isso, o
    componente existe no DOM mas e invisivel/inerte."""
    response = superuser_client.get(reverse(url_name))
    content = response.content.decode()

    assert SCOPED_STYLESHEET in content, (
        f"{url_name}: changelist nao referencia {SCOPED_STYLESHEET} — "
        "indicador de selo fica sem estilo (ponto transparente, sem "
        "forma) nesta pagina de Admin"
    )


@pytest.mark.parametrize(
    "url_name",
    [
        "admin:telecom_simcard_changelist",
        "admin:telecom_blipconfiguration_changelist",
        "admin:allocations_lineallocation_changelist",
        "admin:pendencies_allocationpendency_changelist",
    ],
)
def test_admin_changelist_does_not_load_full_project_stylesheet(
    superuser_client, url_name
):
    """I25-I28 · retificacao: o arquivo INTEIRO (static/css/styles.css)
    nao pode ser carregado no Admin — ele contem regras globais (body,
    h1-h6, input, select, table) que vazam para os controles nativos do
    Admin (confirmado em Chrome real: texto quase branco sobre fundo
    claro em <input>, ilegivel). So o CSS escopado do componente
    (css/seal_indicator.css) pode ser carregado."""
    response = superuser_client.get(reverse(url_name))
    content = response.content.decode()

    assert FULL_PROJECT_STYLESHEET not in content, (
        f"{url_name}: changelist referencia {FULL_PROJECT_STYLESHEET} "
        "inteiro — regras globais (body/input/select/h1/table) vazam "
        "para os controles nativos do Admin"
    )
