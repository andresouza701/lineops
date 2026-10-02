"""Testes RED de SEV-03 — ativação, categoria, plano e valor mensal do
selo WHATS LINEOPS.

Fonte da verdade: docs/superpowers/specs/2026-09-30-whatsapp-seal-activation-
value-design.md (contrato técnico, matriz T01–T23, fechamento SEV-02).

Nenhum dos quatro campos novos (whatsapp_seal_activation_status,
whatsapp_seal_category, whatsapp_seal_plan, whatsapp_seal_monthly_value)
existe ainda em telecom/models.py nem em telecom/forms.py; nenhum token de
catálogo ou função de parsing monetário existe em telecom/whatsapp_seal.py.
Por isso nenhuma constante/classe futura é importada no topo deste arquivo
— isso quebraria a coleta do pytest para o arquivo inteiro. Em vez disso:

- Campos de model/form futuros são referenciados por *nome* (string) nos
  payloads de POST/kwargs e lidos via fetch fresco após salvar — gera
  AttributeError/TypeError real e legível quando o campo não existe.
- Nenhum teste afirma a ausência de um símbolo interno (classe/função) que
  a própria spec não exige por nome — isso seria um requisito de API
  inventado pelo teste, não pela spec. A cobertura de catálogo (T17) é
  inteiramente comportamental: as quatro combinações aprovadas e as
  rejeições (token desconhecido, combinação cruzada) são exercitadas pela
  fronteira real (PhoneLineForm), não por inspeção de telecom/whatsapp_seal.py.
- Após qualquer save(), busca-se a linha por PhoneLine.objects.get(pk=...)
  (instância nova, não o mesmo objeto Python) antes de ler um campo
  hipotético — refresh_from_db() no mesmo objeto não apagaria um atributo
  Python que o teste tenha setado manualmente, o que mascararia RED real
  como falso GREEN.

Nenhum código de aplicação é alterado por este arquivo.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from allocations.models import LineAllocation
from core.services.allocation_service import AllocationService
from core.services.line_inventory_report_service import build_line_inventory_report
from core.services.whatsapp_seal_report_service import build_whatsapp_seal_report
from employees.models import Employee
from telecom import whatsapp_seal
from telecom.forms import PhoneLineForm, PhoneLineUpdateForm
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser

PASSWORD = "test-only"


# ---------------------------------------------------------------------------
# Fixtures — coerentes com os padrões já usados em test_whatsapp_seal.py e
# test_phoneline_form_ui.py (mesmos apps, mesma forma de criar SIM/linha).
# ---------------------------------------------------------------------------


@pytest.fixture
def sim(db):
    return SIMcard.objects.create(iccid="8900000000000070001", carrier="TIM")


@pytest.fixture
def admin_client(client, db):
    user = SystemUser.objects.create_user(
        email="sev03-admin@example.com", password=PASSWORD, role=SystemUser.Role.ADMIN
    )
    client.force_login(user)
    return client


def _fresh(line):
    """Busca uma instância nova do banco — nunca o mesmo objeto Python —
    para que um atributo hipotético setado manualmente no teste não
    sobreviva e mascare um RED real como GREEN."""
    return PhoneLine.objects.get(pk=line.pk)


def base_payload(sim_instance, **overrides):
    payload = {
        "phone_number": "+5511999997001",
        "sim_card": sim_instance.pk,
        "whatsapp_seal": "META_ONE",
        "whatsapp_seal_activation_status": "ACTIVE",
        "whatsapp_seal_category": "CREATORS_BUSINESSES",
        "whatsapp_seal_plan": "ONE_ESSENTIAL",
        "whatsapp_seal_monthly_value": "59,00",
        "whatsapp_seal_activated_on": "2026-09-01",
        "whatsapp_seal_expires_on": "2026-10-17",
        "whatsapp_seal_email": "seal@example.com",
        "whatsapp_seal_payment": "CREDIT_CARD",
    }
    payload.update(overrides)
    return payload


# ===========================================================================
# T01 — Sem selo limpa situação/categoria/plano/valor residuais
# Camada: domínio/model (clear_seal_fields) · Task futura: SEV-04/05
# ===========================================================================


class TestT01SemSeloLimpaDadosProprios:
    def test_sem_selo_limpa_situacao_categoria_plano_valor(self, sim):
        """Node: T01. Hoje clear_seal_fields() (telecom/whatsapp_seal.py)
        só limpa 5 campos antigos; os 4 novos não existem. RED esperado:
        AttributeError na instância recém-buscada ao ler
        whatsapp_seal_activation_status/category/plan/monthly_value."""
        line = PhoneLine.objects.create(
            phone_number="+5511999997002", sim_card=sim, status="AVAILABLE"
        )
        line.whatsapp_seal = ""
        line.save()

        fresh = _fresh(line)
        assert fresh.whatsapp_seal == ""
        assert fresh.whatsapp_seal_activation_status == ""
        assert fresh.whatsapp_seal_category == ""
        assert fresh.whatsapp_seal_plan == ""
        assert fresh.whatsapp_seal_monthly_value is None

    def test_form_sem_selo_limpa_campos_novos_mesmo_com_residuo_no_post(self, sim):
        """Node: T01 (form). PhoneLineForm.full_clean() hoje só limpa os 4
        campos de SEAL_DETAIL_FIELDS; os novos tokens residuais enviados no
        POST não são zerados porque não existem como campo do form. RED
        esperado: AttributeError ao ler os campos novos após salvar."""
        payload = base_payload(sim, whatsapp_seal="")
        form = PhoneLineForm(data=payload)
        assert form.is_valid(), form.errors
        line = form.save()

        fresh = _fresh(line)
        assert fresh.whatsapp_seal_activation_status == ""
        assert fresh.whatsapp_seal_category == ""
        assert fresh.whatsapp_seal_plan == ""
        assert fresh.whatsapp_seal_monthly_value is None


# ===========================================================================
# T02 — Não ativado: datas nulas, sem alerta, valor 0,00–299,00
# Camada: domínio/model · Task futura: SEV-04/05
# ===========================================================================


class TestT02NaoAtivado:
    # Correção de fixture (SEV-05): a parametrização original só variava
    # `seal`, mantendo category/plan fixos em "CREATORS_BUSINESSES"/
    # "ONE_ESSENTIAL" (default de base_payload) — válido apenas para
    # META_ONE. Isso não dava erro em SEV-03/04 porque a validação cruzada
    # de catálogo (SEV-04) ainda não existia; com ela ativa, META_VERIFIED
    # com essa dupla é uma combinação cruzada inválida, não o cenário que
    # este teste pretende provar (Não ativado aceita valor R$ 0,00 para
    # qualquer tipo de selo). Corrigido para parametrizar a combinação
    # completa e válida de cada tipo; intenção e asserções inalteradas.
    @pytest.mark.parametrize(
        "seal,category,plan",
        [
            ("META_ONE", "CREATORS_BUSINESSES", "ONE_ESSENTIAL"),
            ("META_VERIFIED", "PERSONAL_CREATOR", "STANDARD"),
        ],
    )
    def test_nao_ativado_salva_datas_nulas_e_valor_zero(self, sim, seal, category, plan):
        """Node: T02. Não ativado aceita valor R$ 0,00. Sem o campo
        whatsapp_seal_activation_status no model/form, o form hoje ainda
        exige whatsapp_seal_activated_on/expires_on (campos antigos
        continuam no Meta.fields) — RED esperado por form.is_valid() falso
        ou, se corrigido o payload com datas vazias, por AttributeError ao
        ler whatsapp_seal_activation_status na instância fresca."""
        payload = base_payload(
            sim,
            whatsapp_seal=seal,
            whatsapp_seal_category=category,
            whatsapp_seal_plan=plan,
            whatsapp_seal_activation_status="NOT_ACTIVATED",
            whatsapp_seal_monthly_value="0,00",
            whatsapp_seal_activated_on="",
            whatsapp_seal_expires_on="",
        )
        form = PhoneLineForm(data=payload)
        assert form.is_valid(), form.errors
        line = form.save()

        fresh = _fresh(line)
        assert fresh.whatsapp_seal_activation_status == "NOT_ACTIVATED"
        assert fresh.whatsapp_seal_activated_on is None
        assert fresh.whatsapp_seal_expires_on is None
        assert fresh.whatsapp_seal_monthly_value == Decimal("0.00")

    def test_nao_ativado_nao_gera_alerta(self):
        """Node: T02/T11. compute_seal_status(seal, expires_on) hoje
        retorna {"tone": "neutral", "label": "Sem selo"} quando expires_on
        é None — rótulo errado para Não ativado (deveria distinguir de Sem
        selo, conforme matriz de estados). RED esperado: mismatch de label,
        gap de domínio real para SEV-04/06, não falha de fixture."""
        line = PhoneLine(whatsapp_seal="META_ONE", whatsapp_seal_expires_on=None)
        status = line.seal_status
        assert status["tone"] == "neutral"
        assert status["label"] == "Não ativado"


# ===========================================================================
# T03 — Ativo exige datas e valor; vencimento manual >= ativação
# Camada: domínio/model · Task futura: SEV-04/05
# ===========================================================================


class TestT03Ativo:
    def test_ativo_exige_cada_data_e_valor(self, sim):
        """Node: T03. Ativo deve exigir whatsapp_seal_monthly_value além das
        datas atuais. RED esperado: form válido sem erro no campo de valor
        porque o campo ainda não existe (assert falha mostrando ausência de
        validação, não bug de fixture)."""
        payload = base_payload(
            sim,
            whatsapp_seal_activation_status="ACTIVE",
            whatsapp_seal_monthly_value="",
        )
        form = PhoneLineForm(data=payload)
        assert not form.is_valid()
        assert "whatsapp_seal_monthly_value" in form.errors

    def test_vencimento_anterior_a_ativacao_rejeitado(self, sim):
        """Node: T03. Já coberto por validate_seal_fields hoje (datas
        invertidas). Mantido aqui apenas como controle de regressão dentro
        do novo arquivo — deve ficar GREEN já nesta rodada."""
        payload = base_payload(
            sim,
            whatsapp_seal_activated_on="2026-10-17",
            whatsapp_seal_expires_on="2026-09-01",
        )
        form = PhoneLineForm(data=payload)
        assert not form.is_valid()
        assert "whatsapp_seal_expires_on" in form.errors


# ===========================================================================
# T04 — Ativação de Não ativado preserva tipo/valor e não altera
# status/activated_at/vínculo/histórico. Camada: form/HTTP · SEV-04/05
# ===========================================================================


class TestT04AtivacaoNaoAlteraOperacional:
    def test_editar_apenas_selo_nao_altera_status_activated_at_ou_historico(
        self, admin_client, sim
    ):
        """Node: T04/T16. Transição Não ativado -> Ativo editando somente o
        bloco do selo não deve tocar status/activated_at/histórico. RED
        esperado: AttributeError ao gravar/ler whatsapp_seal_activation_status
        (campo ainda inexistente no form/model).

        Correção de fixture (SEV-05): a chamada original informava apenas
        `whatsapp_seal="META_ONE"`, sem os 4 campos novos — válido quando
        create_or_reuse não validava nada além dos 5 campos antigos (SEV-03).
        Agora que create_or_reuse exige dados completos quando há selo (ver
        docstring da própria função), a mesma chamada levantaria
        ValidationError antes mesmo do cenário sob teste (a edição). Corrigido
        com uma combinação completa e válida em Não ativado — exatamente o
        estado de partida que o nome da classe (AtivacaoNaoAlteraOperacional)
        já pressupõe; intenção e asserções abaixo inalteradas."""
        line = PhoneLine.create_or_reuse(
            phone_number="+5511999997003",
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
            whatsapp_seal="META_ONE",
            whatsapp_seal_activation_status="NOT_ACTIVATED",
            whatsapp_seal_category="CREATORS_BUSINESSES",
            whatsapp_seal_plan="ONE_ESSENTIAL",
            whatsapp_seal_monthly_value=Decimal("0.00"),
            whatsapp_seal_email="seal@example.com",
            whatsapp_seal_payment="CREDIT_CARD",
        )
        fixed_activated_at = timezone.now() - timedelta(days=10)
        line.activated_at = fixed_activated_at
        line.save(update_fields=["activated_at"])
        history_count_before = line.history.count()

        payload = base_payload(
            sim,
            whatsapp_seal_activation_status="ACTIVE",
            status="AVAILABLE",
        )
        edit = PhoneLineUpdateForm(data=payload, instance=line, can_edit_origem=True)
        assert edit.is_valid(), edit.errors
        edit.save()

        fresh = _fresh(line)
        assert fresh.whatsapp_seal_activation_status == "ACTIVE"
        assert fresh.activated_at == fixed_activated_at
        assert fresh.status == "AVAILABLE"
        assert fresh.history.count() == history_count_before


# ===========================================================================
# T05 — Legado: ativo, datas preservadas, valor null; exige preenchimento
# na próxima edição. Camada: migração/model/form · SEV-04/05
# ===========================================================================


class TestT05Legado:
    def test_criacao_direta_via_orm_nao_classifica_nem_infere_campos_novos(self, sim):
        """Node: T05/T20. Retificado em 01/10/2026 (retificação de SEV-04,
        achado B): a asserção original exigia whatsapp_seal_activation_status
        == "ACTIVE" para uma linha criada via ORM direto (.objects.create()),
        presumindo que isso "simulava o estado pós-migração". Isso só era
        verdade por causa de um fallback em PhoneLine.save() que classificava
        qualquer save() comum com selo e situação vazia como ACTIVE — não só
        o backfill histórico. Esse fallback inferia situação ausente em
        entrada nova (violação do contrato) e foi removido. A classificação
        ACTIVE de legado é responsabilidade exclusiva da migration 0022
        (RunPython sobre modelo histórico), nunca do model/save() — ver
        telecom/test_whatsapp_seal_activation_migration.py para os 6
        cenários reais de T10. Este node agora prova o oposto do que a
        versão original (incorreta) presumia: .objects.create() comum NÃO
        infere nem classifica nada."""
        line = PhoneLine.objects.create(
            phone_number="+5511999997004",
            sim_card=sim,
            status="AVAILABLE",
            whatsapp_seal="META_ONE",
            whatsapp_seal_activated_on=date(2026, 1, 10),
            whatsapp_seal_expires_on=date(2026, 12, 10),
            whatsapp_seal_email="legado@example.com",
            whatsapp_seal_payment="CREDIT_CARD",
        )
        fresh = _fresh(line)
        assert fresh.whatsapp_seal_activation_status == ""
        assert fresh.whatsapp_seal_category == ""
        assert fresh.whatsapp_seal_plan == ""
        assert fresh.whatsapp_seal_monthly_value is None
        assert fresh.whatsapp_seal_activated_on == date(2026, 1, 10)

    def test_get_legado_funciona_sem_valor(self, admin_client, sim):
        """Node: T05. GET no detalhe de linha legada sem valor não pode
        quebrar. Controle de regressão — espera-se GREEN já nesta rodada,
        pois a view atual não referencia os campos novos."""
        line = PhoneLine.objects.create(
            phone_number="+5511999997005",
            sim_card=sim,
            status="AVAILABLE",
            whatsapp_seal="META_ONE",
            whatsapp_seal_activated_on=date(2026, 1, 10),
            whatsapp_seal_expires_on=date(2026, 12, 10),
            whatsapp_seal_email="legado2@example.com",
            whatsapp_seal_payment="CREDIT_CARD",
        )
        response = admin_client.get(reverse("telecom:phoneline_detail", args=[line.pk]))
        assert response.status_code == 200

    def test_edicao_legado_sem_valor_eh_rejeitada(self, admin_client, sim):
        """Node: T05. Próxima edição de legado sem valor deve exigir
        preenchimento. RED esperado: form válido (sem erro no campo de
        valor) porque o campo ainda não existe no form."""
        line = PhoneLine.objects.create(
            phone_number="+5511999997006",
            sim_card=sim,
            status="AVAILABLE",
            whatsapp_seal="META_ONE",
            whatsapp_seal_activated_on=date(2026, 1, 10),
            whatsapp_seal_expires_on=date(2026, 12, 10),
            whatsapp_seal_email="legado3@example.com",
            whatsapp_seal_payment="CREDIT_CARD",
        )
        payload = base_payload(
            sim,
            status="AVAILABLE",
            whatsapp_seal_activated_on="2026-01-10",
            whatsapp_seal_expires_on="2026-12-10",
            whatsapp_seal_email="legado3@example.com",
            whatsapp_seal_monthly_value="",
        )
        edit = PhoneLineUpdateForm(data=payload, instance=line, can_edit_origem=True)
        assert not edit.is_valid()
        assert "whatsapp_seal_monthly_value" in edit.errors


# ===========================================================================
# T06 — Valor válido persiste exato; ausente/inválido/negativo/zero/limite
# Camada: domínio/form · SEV-04/05
# ===========================================================================


class TestT06ValorMonetario:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("59,00", Decimal("59.00")),
            ("0,01", Decimal("0.01")),
            ("299,00", Decimal("299.00")),
        ],
    )
    def test_valor_valido_persiste_exato(self, sim, raw, expected):
        """Node: T06. RED esperado: AttributeError na instância fresca
        (campo whatsapp_seal_monthly_value ainda não existe)."""
        payload = base_payload(sim, whatsapp_seal_monthly_value=raw)
        form = PhoneLineForm(data=payload)
        assert form.is_valid(), form.errors
        line = form.save()
        fresh = _fresh(line)
        assert fresh.whatsapp_seal_monthly_value == expected

    @pytest.mark.parametrize(
        "raw",
        ["", "-0,01", "-59,00", "299,01", "300,00", "0", "0,00"],
    )
    def test_valor_invalido_ou_fora_de_faixa_para_ativo_rejeitado(self, sim, raw):
        """Node: T06/T21. Ativo exige 0,01–299,00; os valores acima violam
        esse contrato (0 e negativos inclusive). RED esperado: form válido
        sem erro no campo (validação ainda não existe)."""
        payload = base_payload(
            sim, whatsapp_seal_activation_status="ACTIVE", whatsapp_seal_monthly_value=raw
        )
        form = PhoneLineForm(data=payload)
        assert not form.is_valid()
        assert "whatsapp_seal_monthly_value" in form.errors


# ===========================================================================
# T07 — Erro de valor/e-mail não gera obrigatório contraditório nem
# gravação parcial. Camada: form · SEV-05
# ===========================================================================


class TestT07SemMensagemContraditoria:
    def test_valor_invalido_nao_duplica_obrigatorio_e_nao_grava_parcial(
        self, admin_client, sim
    ):
        """Node: T07. Mesma classe de bug de SEL-10/SEL-11 (ver
        test_whatsapp_seal.py) mas para o campo de valor. RED esperado:
        campo ausente — não há form.errors["whatsapp_seal_monthly_value"]
        para inspecionar ainda."""
        payload = base_payload(sim, whatsapp_seal_monthly_value="1.000,00")
        response = admin_client.post(reverse("telecom:phoneline_create"), payload)
        assert response.status_code == 200
        errors = response.context["form"].errors["whatsapp_seal_monthly_value"]
        assert len(errors) == 1
        assert not PhoneLine.objects.filter(phone_number=payload["phone_number"]).exists()


# ===========================================================================
# T08 — create_or_reuse / save(commit=False) não perdem campos novos nem
# recuperam selo antigo. Camada: domínio/model · SEV-05
# ===========================================================================


class TestT08CreateOrReuseECommitFalse:
    def test_create_or_reuse_aceita_kwargs_novos(self, sim):
        """Node: T08/T23. create_or_reuse hoje só aceita os 5 kwargs
        antigos de selo. RED esperado: TypeError (unexpected keyword
        argument) ao chamar com os 4 kwargs novos."""
        line = PhoneLine.create_or_reuse(
            phone_number="+5511999997007",
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
            whatsapp_seal="META_ONE",
            whatsapp_seal_activation_status="ACTIVE",
            whatsapp_seal_category="CREATORS_BUSINESSES",
            whatsapp_seal_plan="ONE_ESSENTIAL",
            whatsapp_seal_monthly_value=Decimal("59.00"),
            whatsapp_seal_activated_on=date(2026, 9, 1),
            whatsapp_seal_expires_on=date(2026, 10, 17),
            whatsapp_seal_email="seal@example.com",
            whatsapp_seal_payment="CREDIT_CARD",
        )
        fresh = _fresh(line)
        assert fresh.whatsapp_seal_monthly_value == Decimal("59.00")

    def test_save_commit_false_nao_grava_e_preserva_valor_normalizado(self, sim):
        """Node: T08. save(commit=False) não deve gravar no banco e deve
        devolver a instância com os campos normalizados. RED esperado:
        AttributeError ao ler whatsapp_seal_monthly_value na instância."""
        payload = base_payload(sim)
        form = PhoneLineForm(data=payload)
        assert form.is_valid(), form.errors
        instance = form.save(commit=False)

        assert not PhoneLine.objects.filter(
            phone_number=payload["phone_number"]
        ).exists()
        assert instance.whatsapp_seal_monthly_value == Decimal("59.00")

    def test_reactivation_nao_recupera_categoria_plano_valor_antigos(self, sim):
        """Node: T08. Reativação (linha excluída reaproveitada) não deve
        trazer de volta categoria/plano/valor antigos quando o novo
        create_or_reuse não os informa. RED esperado: TypeError nos kwargs
        novos (mesmo gap de test_create_or_reuse_aceita_kwargs_novos) ou,
        se corrigido, AttributeError na leitura.

        Correção de fixture (SEV-05): a chamada original informava
        category/plan/value sem activation_status/datas/e-mail/pagamento —
        válido só enquanto create_or_reuse não validava nada (SEV-03). Com a
        validação completa exigida pelo contrato, essa chamada agora
        levantaria ValidationError antes do delete/reativação sob teste.
        Corrigido com uma combinação ACTIVE completa e válida; intenção
        (provar que a reativação não resgata dados antigos) e asserções
        abaixo inalteradas."""
        line = PhoneLine.create_or_reuse(
            phone_number="+5511999997008",
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
            whatsapp_seal="META_ONE",
            whatsapp_seal_activation_status="ACTIVE",
            whatsapp_seal_category="CREATORS_BUSINESSES",
            whatsapp_seal_plan="ONE_ESSENTIAL",
            whatsapp_seal_monthly_value=Decimal("59.00"),
            whatsapp_seal_activated_on=date(2026, 9, 1),
            whatsapp_seal_expires_on=date(2026, 10, 17),
            whatsapp_seal_email="seal@example.com",
            whatsapp_seal_payment="CREDIT_CARD",
        )
        line.delete()
        restored = PhoneLine.create_or_reuse(
            phone_number=line.phone_number, sim_card=sim, status="AVAILABLE"
        )
        fresh = _fresh(restored)
        assert fresh.whatsapp_seal_category == ""
        assert fresh.whatsapp_seal_plan == ""
        assert fresh.whatsapp_seal_monthly_value is None


# ===========================================================================
# T09 — Liberar/alocar/cancelar não exigem completar dados legados do selo.
# Camada: HTTP/views · SEV-05
# ===========================================================================


class TestT09AcoesIndependentesComLegadoIncompleto:
    def test_liberar_linha_nao_exige_completar_selo_legado(self, admin_client, sim):
        """Node: T09. Ação Liberar (PhoneLineUpdateView.post, action=
        release_line) não valida o form — deve continuar funcionando com
        legado sem categoria/plano/valor. Controle de regressão: espera-se
        GREEN já nesta rodada, prova que a ação independente não quebra.

        Correção de fixture (SEV-05): o legado era simulado com
        create_or_reuse(whatsapp_seal=..., sem os 4 campos novos) — válido
        só enquanto create_or_reuse não validava nada (SEV-03). Dados
        legados reais são produzidos pela migration 0022 (RunPython sobre
        modelo histórico), nunca por create_or_reuse, que agora exige dados
        completos quando há selo. Trocado para `.objects.create()` direto
        (mesmo padrão já usado em TestT05Legado/TestT20), que continua
        simulando fielmente uma linha pré-existente sem os campos novos,
        sem acionar a validação nova. Intenção e asserções inalteradas."""
        line = PhoneLine.objects.create(
            phone_number="+5511999997009",
            sim_card=sim,
            status="AVAILABLE",
            whatsapp_seal="META_ONE",
            whatsapp_seal_activated_on=date(2026, 1, 10),
            whatsapp_seal_expires_on=date(2026, 12, 10),
            whatsapp_seal_email="legado-liberar@example.com",
            whatsapp_seal_payment="CREDIT_CARD",
        )
        employee = Employee.objects.create(
            full_name="Legado Liberar",
            corporate_email="legado-liberar-emp@example.com",
            employee_id="SEV03-LIB-1",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        allocator = SystemUser.objects.create_user(
            email="sev03-allocator@example.com", password=PASSWORD, role=SystemUser.Role.ADMIN
        )
        AllocationService.allocate_line(employee=employee, phone_line=line, allocated_by=allocator)
        line.refresh_from_db()

        response = admin_client.post(
            reverse("telecom:phoneline_update", args=[line.pk]),
            {"action": "release_line"},
        )
        assert response.status_code == 302
        line.refresh_from_db()
        assert line.status == "AVAILABLE"
        assert not LineAllocation.objects.filter(phone_line=line, is_active=True).exists()

    def test_editar_linha_alocada_sem_completar_legado_eh_rejeitado_mas_nao_pela_alocacao(
        self, admin_client, sim
    ):
        """Node: T09. Editar uma linha alocada com legado incompleto deve
        ser bloqueada pela exigência NOVA de valor (quando implementada),
        não por regra de alocação. RED esperado: form válido hoje (campo
        de valor ainda não existe) — comprova que a exigência de SEV-05
        ainda não está wired, sem ser mascarada por erro de alocação.

        Correção de fixture (SEV-05): mesma causa e mesma correção do node
        anterior (test_liberar_linha_nao_exige_completar_selo_legado) —
        trocado create_or_reuse por `.objects.create()` para simular legado
        real sem acionar a validação nova de create_or_reuse."""
        line = PhoneLine.objects.create(
            phone_number="+5511999997010",
            sim_card=sim,
            status="AVAILABLE",
            whatsapp_seal="META_ONE",
            whatsapp_seal_activated_on=date(2026, 1, 10),
            whatsapp_seal_expires_on=date(2026, 12, 10),
            whatsapp_seal_email="legado-edit@example.com",
            whatsapp_seal_payment="CREDIT_CARD",
        )
        employee = Employee.objects.create(
            full_name="Legado Editar",
            corporate_email="legado-edit-emp@example.com",
            employee_id="SEV03-EDIT-1",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        allocator = SystemUser.objects.create_user(
            email="sev03-allocator2@example.com", password=PASSWORD, role=SystemUser.Role.ADMIN
        )
        AllocationService.allocate_line(employee=employee, phone_line=line, allocated_by=allocator)
        line.refresh_from_db()

        payload = {
            "phone_number": line.phone_number,
            "sim_card": sim.pk,
            "status": "ALLOCATED",
            "employee": employee.pk,
            "whatsapp_seal": "META_ONE",
            "whatsapp_seal_activated_on": "2026-01-10",
            "whatsapp_seal_expires_on": "2026-12-10",
            "whatsapp_seal_email": "legado-edit@example.com",
            "whatsapp_seal_payment": "CREDIT_CARD",
        }
        response = admin_client.post(
            reverse("telecom:phoneline_update", args=[line.pk]), payload
        )
        assert response.status_code == 200
        assert "whatsapp_seal_monthly_value" in response.context["form"].errors


# ===========================================================================
# T10 — Migração inclui excluídos; forward/reverse preservam campos antigos.
# Camada: migração · Task futura: SEV-04.
#
# SEM teste executável nesta task: a migration sucessora de
# telecom/migrations/0021_phoneline_whatsapp_seal_and_more.py ainda não
# existe (grafo de migrations do app `telecom` não tem sucessora para este
# adendo), e a instrução desta task proíbe criar migration fictícia,
# placeholder que sempre falha (pytest.fail incondicional), skip ou xfail.
# Um placeholder executável não seria RED funcional válido: falharia
# independente de qualquer código, não comprova nem refuta comportamento
# nenhum. A pendência fica registrada apenas em texto, aqui e na fonte da
# verdade (Registro de execução), para SEV-04 escrever o teste real quando
# o grafo existir — mesmo formato de
# telecom/test_whatsapp_seal.py::test_migration_preserves_existing_lines_
# as_no_seal / test_migration_0021_is_reversible, cobrindo:
#
# 1. Legado com selo (whatsapp_seal preenchido) é classificado ACTIVE pela
#    migration forward.
# 2. Datas (whatsapp_seal_activated_on/expires_on) preservadas sem alteração.
# 3. whatsapp_seal_category e whatsapp_seal_plan ficam vazios ("").
# 4. whatsapp_seal_monthly_value fica null, sem valor inventado.
# 5. Registros com is_deleted=True (linha excluída logicamente) e SIMcard
#    excluído também são classificados, usando all_objects/modelos
#    históricos — não apenas o manager padrão.
# 6. Reversão (migrate para a migration anterior) não quebra e preserva os
#    5 campos antigos de selo; perder os 4 campos novos no rollback é
#    esperado e deve ser documentado, não testado como sucesso silencioso.
# ===========================================================================


# ===========================================================================
# T11 — Ativo mantém alertas 8/7/1/0/-1; Não ativado jamais alerta mesmo
# com resíduo de data. Camada: domínio · SEV-04/06
# ===========================================================================


class TestT11AlertasEComputeSealStatus:
    def test_ativo_mantem_alertas_atuais(self, monkeypatch):
        """Node: T11. Controle de regressão dos limites já existentes —
        espera-se GREEN, já que compute_seal_status não muda para o estado
        Ativo (equivalente ao comportamento atual com selo+vencimento)."""
        monkeypatch.setattr(timezone, "localdate", lambda: date(2026, 9, 17))
        line = PhoneLine(whatsapp_seal="META_ONE", whatsapp_seal_expires_on=date(2026, 9, 25))
        assert line.seal_status == {"tone": "neutral", "label": "Vence em 25/09/2026"}

    def test_nao_ativado_jamais_alerta_mesmo_com_data_residual(self, monkeypatch):
        """Node: T11. Caso real de risco: um registro Não ativado que, por
        resíduo de edição anterior, ainda tenha whatsapp_seal_expires_on
        preenchido não pode gerar alerta — a situação deve ser decidida
        pela ativação, não pela data residual. RED esperado: hoje
        compute_seal_status não recebe nem considera o estado de ativação,
        então uma data residual vencida geraria alerta "Vencido" incorreto
        para uma linha Não ativado."""
        monkeypatch.setattr(timezone, "localdate", lambda: date(2026, 9, 17))
        line = PhoneLine(whatsapp_seal="META_ONE", whatsapp_seal_expires_on=date(2026, 1, 1))
        line.whatsapp_seal_activation_status = "NOT_ACTIVATED"
        status = whatsapp_seal.compute_seal_status(
            line.whatsapp_seal,
            line.whatsapp_seal_expires_on,
            activation_status=line.whatsapp_seal_activation_status,
        )
        assert status == {"tone": "neutral", "label": "Não ativado"}


# ===========================================================================
# T12 — Detalhe/overview/Carregar mais/OPERATOR distinguem Não ativado de
# Sem selo. Camada: interface/consumidores · SEV-06
# ===========================================================================


class TestT12InterfaceDistingueNaoAtivadoDeSemSelo:
    def test_overview_ajax_distingue_nao_ativado_de_sem_selo(self, admin_client, sim):
        """Node: T12. Payload main/Carregar mais hoje expõe apenas
        seal_status calculado a partir de (seal, expires_on) — indistinto
        de Não ativado vs Sem selo quando expires_on é nulo em ambos. RED
        esperado: AttributeError ao tentar gravar whatsapp_seal_activation_
        status na linha de fixture (campo ainda inexistente)."""
        line = PhoneLine.objects.create(
            phone_number="+5511999997011", sim_card=sim, status="AVAILABLE", whatsapp_seal="META_ONE"
        )
        line.whatsapp_seal_activation_status = "NOT_ACTIVATED"
        line.save()
        fresh = _fresh(line)
        assert fresh.whatsapp_seal_activation_status == "NOT_ACTIVATED"

        response = admin_client.get(
            reverse("telecom:overview"), {"table": "main", "offset": 0},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        row = next(r for r in response.json()["data"] if r["id"] == line.pk)
        assert row["seal_status"]["label"] == "Não ativado"

    def test_detalhe_mostra_situacao_e_valor_nao_informado_para_legado(
        self, admin_client, sim
    ):
        """Node: T12. Detalhe deve mostrar "Não informado" (nunca R$ 0,00)
        para valor ausente de legado. RED esperado: template atual não
        renderiza nenhum campo de valor — o texto nunca aparece."""
        line = PhoneLine.objects.create(
            phone_number="+5511999997012",
            sim_card=sim,
            status="AVAILABLE",
            whatsapp_seal="META_ONE",
            whatsapp_seal_activated_on=date(2026, 1, 10),
            whatsapp_seal_expires_on=date(2026, 12, 10),
            whatsapp_seal_email="legado-detalhe@example.com",
            whatsapp_seal_payment="CREDIT_CARD",
        )
        response = admin_client.get(reverse("telecom:phoneline_detail", args=[line.pk]))
        content = response.content.decode()
        assert "Não informado" in content


# ===========================================================================
# T13 — Relatório de Selos exclui Não ativado; Inventário conta posse de
# selo independente de ativação. Camada: relatórios · SEV-06
# ===========================================================================


class TestT13Relatorios:
    def test_relatorio_selos_exclui_linha_sem_data_de_ativacao(self, sim):
        """Node: T13. Controle de regressão + prova positiva: o filtro
        atual (whatsapp_seal_activated_on entre datas) já exclui
        naturalmente qualquer linha sem essa data — inclusive uma futura
        Não ativado (datas nulas por contrato). Inclui uma linha ativa
        elegível como controle, para não passar por ausência do motor.
        Espera-se GREEN já nesta rodada: é comportamento já correto,
        documentado aqui para não regressar quando SEV-04/06 adicionarem
        o novo campo de situação."""
        eligible = PhoneLine.objects.create(
            phone_number="+5511999997013",
            sim_card=sim,
            status="AVAILABLE",
            whatsapp_seal="META_ONE",
            whatsapp_seal_activated_on=date(2026, 9, 10),
            whatsapp_seal_expires_on=date(2026, 12, 10),
            whatsapp_seal_email="relatorio-ativo@example.com",
            whatsapp_seal_payment="CREDIT_CARD",
        )
        sim2 = SIMcard.objects.create(iccid="8900000000000070002", carrier="TIM")
        not_activated_like = PhoneLine.objects.create(
            phone_number="+5511999997014",
            sim_card=sim2,
            status="AVAILABLE",
            whatsapp_seal="META_ONE",
            whatsapp_seal_activated_on=None,
            whatsapp_seal_expires_on=None,
        )

        result = build_whatsapp_seal_report(
            data_inicial=date(2026, 9, 1),
            data_final=date(2026, 9, 30),
            reference_date=date(2026, 9, 17),
        )
        phone_numbers = {row.phone_number for row in result.rows}
        assert eligible.phone_number in phone_numbers
        assert not_activated_like.phone_number not in phone_numbers

    def test_inventario_conta_selo_independente_de_ativacao(self, sim):
        """Node: T13. Inventário conta posse de selo por whatsapp_seal !=
        "" (core/services/line_inventory_report_service.py::_selo_label),
        sem depender de data de ativação — já correto hoje. Controle de
        regressão, espera-se GREEN."""
        sim2 = SIMcard.objects.create(iccid="8900000000000070003", carrier="TIM")
        with_seal_not_activated_like = PhoneLine.objects.create(
            phone_number="+5511999997015",
            sim_card=sim,
            status="AVAILABLE",
            whatsapp_seal="META_ONE",
            whatsapp_seal_activated_on=None,
            whatsapp_seal_expires_on=None,
        )
        without_seal = PhoneLine.objects.create(
            phone_number="+5511999997016", sim_card=sim2, status="AVAILABLE"
        )

        today = timezone.localdate()
        result = build_line_inventory_report(
            data_inicial=today - timedelta(days=1), data_final=today + timedelta(days=1)
        )
        rows_by_phone = {row.phone_number: row for row in result.rows}
        assert rows_by_phone[with_seal_not_activated_like.phone_number].selo_display.startswith(
            "Com selo"
        )
        assert rows_by_phone[without_seal.phone_number].selo_display == "Sem selo"


# ===========================================================================
# T14 — JS/sem JS: required/visibilidade, vírgula monetária. Estrutural
# apenas — aceite visual fica em SEV-07. Camada: interface · SEV-06/07
# ===========================================================================


class TestT14EstruturaDeFormularioParaNovosCampos:
    def test_formulario_novo_nao_renderiza_campo_de_valor_ainda(self, admin_client):
        """Node: T14 (estrutural). Hoje não existe nenhum input de nome
        whatsapp_seal_monthly_value no HTML. RED esperado: assert falha
        confirmando a ausência (prova negativa explícita para SEV-06, não
        aceite visual — isso é SEV-07)."""
        response = admin_client.get(reverse("telecom:phoneline_create"))
        content = response.content.decode()
        assert 'name="whatsapp_seal_monthly_value"' in content
        assert 'name="whatsapp_seal_category"' in content
        assert 'name="whatsapp_seal_plan"' in content


# ===========================================================================
# T15 — Permissões/escopo e POST inválido permanecem; valor só nas
# superfícies definidas. Camada: HTTP · SEV-05/06
# ===========================================================================


class TestT15PermissoesInalteradas:
    def test_operator_continua_sem_poder_criar_selo_com_novos_campos(self, sim):
        """Node: T15. Controle de regressão de permissão — espera-se GREEN
        já nesta rodada (RoleRequiredMixin não muda com os novos campos)."""
        user = SystemUser.objects.create_user(
            email="sev03-operator@example.com", password=PASSWORD, role=SystemUser.Role.OPERATOR
        )
        from django.test import Client

        client = Client()
        client.force_login(user)
        payload = base_payload(sim)
        response = client.post(reverse("telecom:phoneline_create"), payload)
        assert response.status_code == 403
        assert not PhoneLine.objects.exists()


# ===========================================================================
# T16 — Regra final Ativo -> Não ativado e default de novos selos.
# Camada: domínio/form/HTTP · SEV-04/05/07
# ===========================================================================


class TestT16AtivoParaNaoAtivadoEDefault:
    def test_ativo_para_nao_ativado_limpa_datas_preserva_demais_dados(self, sim):
        """Node: T16. Transição aprovada: limpar datas ao salvar,
        preservando tipo/categoria/plano/valor/e-mail/pagamento. RED
        esperado: AttributeError/TypeError pelos campos novos ainda
        inexistentes em create_or_reuse."""
        line = PhoneLine.create_or_reuse(
            phone_number="+5511999997017",
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
            whatsapp_seal="META_ONE",
            whatsapp_seal_activation_status="ACTIVE",
            whatsapp_seal_category="CREATORS_BUSINESSES",
            whatsapp_seal_plan="ONE_ESSENTIAL",
            whatsapp_seal_monthly_value=Decimal("59.00"),
            whatsapp_seal_activated_on=date(2026, 9, 1),
            whatsapp_seal_expires_on=date(2026, 10, 17),
            whatsapp_seal_email="seal@example.com",
            whatsapp_seal_payment="CREDIT_CARD",
        )
        payload = base_payload(
            line.sim_card,
            status="AVAILABLE",
            whatsapp_seal_activation_status="NOT_ACTIVATED",
            whatsapp_seal_activated_on="",
            whatsapp_seal_expires_on="",
        )
        edit = PhoneLineUpdateForm(data=payload, instance=line, can_edit_origem=True)
        assert edit.is_valid(), edit.errors
        edit.save()

        fresh = _fresh(line)
        assert fresh.whatsapp_seal_activation_status == "NOT_ACTIVATED"
        assert fresh.whatsapp_seal_activated_on is None
        assert fresh.whatsapp_seal_expires_on is None
        assert fresh.whatsapp_seal_category == "CREATORS_BUSINESSES"
        assert fresh.whatsapp_seal_plan == "ONE_ESSENTIAL"
        assert fresh.whatsapp_seal_monthly_value == Decimal("59.00")
        assert fresh.whatsapp_seal_email == "seal@example.com"
        assert fresh.whatsapp_seal_payment == "CREDIT_CARD"

    def test_novo_formulario_apresenta_nao_ativado_por_default(self, admin_client):
        """Node: T16/T23. GET de cadastro novo deve pré-selecionar Não
        ativado quando um selo é escolhido. RED esperado: não há nenhum
        campo/valor inicial de situação no HTML hoje."""
        response = admin_client.get(reverse("telecom:phoneline_create"))
        content = response.content.decode()
        assert 'name="whatsapp_seal_activation_status"' in content
        assert 'value="NOT_ACTIVATED" selected' in content

    def test_post_com_selo_sem_situacao_explicita_eh_invalido(self, sim):
        """Node: T16/T23. POST com selo mas sem
        whatsapp_seal_activation_status deve ser inválido. RED esperado:
        form válido hoje (campo inexistente, ninguém o exige)."""
        payload = base_payload(sim)
        del payload["whatsapp_seal_activation_status"]
        form = PhoneLineForm(data=payload)
        assert not form.is_valid()
        assert "whatsapp_seal_activation_status" in form.errors


# ===========================================================================
# T17 — Quatro combinações do catálogo; token desconhecido e combinação
# cruzada rejeitados no servidor. Camada: domínio/form/interface · SEV-04/05/06
# ===========================================================================

CATALOG_COMBINATIONS = [
    ("META_ONE", "CREATORS_BUSINESSES", "ONE_ESSENTIAL"),
    ("META_VERIFIED", "PERSONAL_CREATOR", "STANDARD"),
    ("META_VERIFIED", "BUSINESS_SME", "BUSINESS_BASIC"),
    ("META_VERIFIED", "BUSINESS", "BUSINESS_PLUS"),
]


class TestT17CatalogoCategoriaPlano:
    @pytest.mark.parametrize("seal,category,plan", CATALOG_COMBINATIONS)
    def test_combinacao_do_catalogo_salva_e_reabre_corretamente(
        self, sim, seal, category, plan
    ):
        """Node: T17. As quatro combinações aprovadas devem persistir e
        reabrir com categoria/plano corretos. RED esperado: AttributeError
        na instância fresca (campos ainda inexistentes)."""
        payload = base_payload(
            sim, whatsapp_seal=seal, whatsapp_seal_category=category, whatsapp_seal_plan=plan
        )
        form = PhoneLineForm(data=payload)
        assert form.is_valid(), form.errors
        line = form.save()
        fresh = _fresh(line)
        assert fresh.whatsapp_seal_category == category
        assert fresh.whatsapp_seal_plan == plan

    def test_token_de_categoria_desconhecido_rejeitado(self, sim):
        """Node: T17. RED esperado: form válido hoje (campo inexistente,
        nenhuma validação de token para rejeitar)."""
        payload = base_payload(sim, whatsapp_seal_category="TOKEN_QUE_NAO_EXISTE")
        form = PhoneLineForm(data=payload)
        assert not form.is_valid()
        assert "whatsapp_seal_category" in form.errors

    def test_combinacao_cruzada_incompativel_rejeitada(self, sim):
        """Node: T17. META_ONE com plano BUSINESS_PLUS (pertence a
        META_VERIFIED) é combinação cruzada incompatível. RED esperado:
        form válido hoje, sem validação cruzada de catálogo."""
        payload = base_payload(
            sim,
            whatsapp_seal="META_ONE",
            whatsapp_seal_category="CREATORS_BUSINESSES",
            whatsapp_seal_plan="BUSINESS_PLUS",
        )
        form = PhoneLineForm(data=payload)
        assert not form.is_valid()
        assert "whatsapp_seal_plan" in form.errors

    # As quatro combinações aprovadas e as duas rejeições (token
    # desconhecido, combinação cruzada) acima já cobrem T17 pela fronteira
    # real do formulário. Nenhum teste adicional afirma a existência de
    # WhatsAppSealCategory/WhatsAppSealPlan/um validador por nome: a spec
    # não exige esses símbolos especificamente — exige o comportamento, já
    # comprovado pelos três testes anteriores.


# ===========================================================================
# T18 — Referência de preço separada do valor efetivo; valor editado
# preservado. Camada: form/interface · SEV-05/06/07
# ===========================================================================


class TestT18ReferenciaNaoSobrescreveValor:
    def test_referencia_de_preco_nao_preenche_nem_sobrescreve_valor_editado(self, sim):
        """Node: T18. Escolher um plano com preço fixo de referência (ex.:
        META_ONE/ONE_ESSENTIAL = R$ 59,00) não deve preencher nem
        sobrescrever um valor digitado manualmente diferente (ex.: R$
        45,00). RED esperado: AttributeError ao ler whatsapp_seal_monthly_
        value na instância fresca."""
        payload = base_payload(
            sim,
            whatsapp_seal="META_ONE",
            whatsapp_seal_category="CREATORS_BUSINESSES",
            whatsapp_seal_plan="ONE_ESSENTIAL",
            whatsapp_seal_monthly_value="45,00",
        )
        form = PhoneLineForm(data=payload)
        assert form.is_valid(), form.errors
        line = form.save()
        fresh = _fresh(line)
        assert fresh.whatsapp_seal_monthly_value == Decimal("45.00")


# ===========================================================================
# T19 — Remoção/troca de selo/categoria/plano com/sem JS, POST inválido
# sem gravação parcial. Camada: form/interface · SEV-05/06/07
# ===========================================================================


class TestT19RemocaoETrocaDeSeloCategoriaPlano:
    def test_remover_selo_remove_categoria_plano_e_valor(self, sim):
        """Node: T19. Já coberto estruturalmente por T01; mantido aqui
        como ponto de verificação explícito do requisito de remoção.
        RED esperado: AttributeError na instância fresca."""
        payload = base_payload(sim)
        form = PhoneLineForm(data=payload)
        assert form.is_valid(), form.errors
        line = form.save()

        edit_payload = dict(payload)
        edit_payload.update(whatsapp_seal="", status="AVAILABLE")
        edit = PhoneLineUpdateForm(data=edit_payload, instance=line, can_edit_origem=True)
        assert edit.is_valid(), edit.errors
        edit.save()

        fresh = _fresh(line)
        assert fresh.whatsapp_seal_category == ""
        assert fresh.whatsapp_seal_plan == ""
        assert fresh.whatsapp_seal_monthly_value is None

    def test_troca_de_categoria_sem_js_post_invalido_nao_grava_parcial(
        self, admin_client, sim
    ):
        """Node: T19. POST com combinação incompatível sem JS deve
        retornar erro sem gravação parcial (nem phone_number novo
        persistido). RED esperado: hoje não há erro de combinação cruzada
        (ver T17), então a linha seria criada — assert de ausência falha."""
        payload = base_payload(
            sim,
            whatsapp_seal="META_ONE",
            whatsapp_seal_category="CREATORS_BUSINESSES",
            whatsapp_seal_plan="BUSINESS_PLUS",
        )
        response = admin_client.post(reverse("telecom:phoneline_create"), payload)
        assert response.status_code == 200
        assert not PhoneLine.objects.filter(phone_number=payload["phone_number"]).exists()


# ===========================================================================
# T20 — Legados não recebem categoria/plano/valor inferidos.
# Camada: migração/form · SEV-04/05
# ===========================================================================


class TestT20LegadoSemInferencia:
    def test_legado_nao_recebe_categoria_plano_inferidos_pelo_tipo(self, sim):
        """Node: T20. Mesmo quando só existe uma combinação de
        categoria/plano compatível com o tipo (ex.: META_ONE só tem
        CREATORS_BUSINESSES/ONE_ESSENTIAL no catálogo), a migração NÃO
        deve inferir isso para legados — devem ficar vazios. RED esperado:
        AttributeError na instância fresca (campo ainda inexistente;
        quando existir, deve ficar "" e não um valor inferido)."""
        line = PhoneLine.objects.create(
            phone_number="+5511999997018",
            sim_card=sim,
            status="AVAILABLE",
            whatsapp_seal="META_ONE",
            whatsapp_seal_activated_on=date(2026, 1, 10),
            whatsapp_seal_expires_on=date(2026, 12, 10),
            whatsapp_seal_email="legado-sem-inferencia@example.com",
            whatsapp_seal_payment="CREDIT_CARD",
        )
        fresh = _fresh(line)
        assert fresh.whatsapp_seal_category == ""
        assert fresh.whatsapp_seal_plan == ""


# ===========================================================================
# T21 — Fronteiras monetárias explícitas (0,00/0,01/-0,01/299,00/299,01).
# Camada: domínio/form · SEV-04/05/07
# ===========================================================================


class TestT21FronteirasMonetarias:
    def test_nao_ativado_aceita_zero_exato(self, sim):
        """Node: T21. RED esperado: AttributeError na instância fresca."""
        payload = base_payload(
            sim,
            whatsapp_seal_activation_status="NOT_ACTIVATED",
            whatsapp_seal_monthly_value="0,00",
            whatsapp_seal_activated_on="",
            whatsapp_seal_expires_on="",
        )
        form = PhoneLineForm(data=payload)
        assert form.is_valid(), form.errors
        line = form.save()
        fresh = _fresh(line)
        assert fresh.whatsapp_seal_monthly_value == Decimal("0.00")

    def test_ativo_rejeita_zero_exato(self, sim):
        """Node: T21. RED esperado: form válido hoje (campo ausente)."""
        payload = base_payload(
            sim, whatsapp_seal_activation_status="ACTIVE", whatsapp_seal_monthly_value="0,00"
        )
        form = PhoneLineForm(data=payload)
        assert not form.is_valid()
        assert "whatsapp_seal_monthly_value" in form.errors

    def test_ativo_aceita_minimo_positivo(self, sim):
        """Node: T21. RED esperado: AttributeError na instância fresca."""
        payload = base_payload(sim, whatsapp_seal_monthly_value="0,01")
        form = PhoneLineForm(data=payload)
        assert form.is_valid(), form.errors
        line = form.save()
        fresh = _fresh(line)
        assert fresh.whatsapp_seal_monthly_value == Decimal("0.01")

    @pytest.mark.parametrize("activation_status", ["NOT_ACTIVATED", "ACTIVE"])
    def test_negativo_minimo_rejeitado_em_ambos_estados(self, sim, activation_status):
        """Node: T21. -0,01 rejeitado tanto em Não ativado quanto em Ativo.
        RED esperado: form válido hoje (campo ausente)."""
        dates = (
            {"whatsapp_seal_activated_on": "", "whatsapp_seal_expires_on": ""}
            if activation_status == "NOT_ACTIVATED"
            else {}
        )
        payload = base_payload(
            sim,
            whatsapp_seal_activation_status=activation_status,
            whatsapp_seal_monthly_value="-0,01",
            **dates,
        )
        form = PhoneLineForm(data=payload)
        assert not form.is_valid()
        assert "whatsapp_seal_monthly_value" in form.errors

    def test_excesso_do_limite_rejeitado(self, sim):
        """Node: T21. 299,01 rejeitado. RED esperado: form válido hoje."""
        payload = base_payload(sim, whatsapp_seal_monthly_value="299,01")
        form = PhoneLineForm(data=payload)
        assert not form.is_valid()
        assert "whatsapp_seal_monthly_value" in form.errors

    def test_limite_maximo_exato_aceito(self, sim):
        """Node: T21. 299,00 aceito. RED esperado: AttributeError na
        instância fresca."""
        payload = base_payload(sim, whatsapp_seal_monthly_value="299,00")
        form = PhoneLineForm(data=payload)
        assert form.is_valid(), form.errors
        line = form.save()
        fresh = _fresh(line)
        assert fresh.whatsapp_seal_monthly_value == Decimal("299.00")

    def test_ativar_com_zero_exige_correcao_sem_gravar_parcial(self, admin_client, sim):
        """Node: T21. Ativar selo com valor zero deve exigir correção
        antes de salvar, sem gravação parcial. RED esperado: form válido
        hoje (campo ausente) e linha seria criada — assert de ausência
        falha."""
        payload = base_payload(
            sim, whatsapp_seal_activation_status="ACTIVE", whatsapp_seal_monthly_value="0,00"
        )
        response = admin_client.post(reverse("telecom:phoneline_create"), payload)
        assert response.status_code == 200
        assert not PhoneLine.objects.filter(phone_number=payload["phone_number"]).exists()


# ===========================================================================
# T22 — Parsing monetário: aceitos/rejeitados exatos de SEV-02.
# Camada: domínio/form · SEV-04/05
# ===========================================================================


class TestT22ParsingMonetario:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("59", Decimal("59.00")),
            ("59,0", Decimal("59.00")),
            ("59,00", Decimal("59.00")),
            ("59.00", Decimal("59.00")),
            (" 59,00 ", Decimal("59.00")),
        ],
    )
    def test_entradas_aceitas_pelo_parsing(self, sim, raw, expected):
        """Node: T22. RED esperado: AttributeError na instância fresca."""
        payload = base_payload(sim, whatsapp_seal_monthly_value=raw)
        form = PhoneLineForm(data=payload)
        assert form.is_valid(), form.errors
        line = form.save()
        fresh = _fresh(line)
        assert fresh.whatsapp_seal_monthly_value == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "1,000",
            "1.000",
            "1.000,00",
            "R$ 59,00",
            "1e2",
            "1E2",
            "NaN",
            "Infinity",
            "-0,00",
            "59,000",
            "59.00,00",
        ],
    )
    def test_entradas_rejeitadas_pelo_parsing(self, sim, raw):
        """Node: T22. RED esperado: form válido hoje (campo ausente, nada
        rejeita essas entradas)."""
        payload = base_payload(sim, whatsapp_seal_monthly_value=raw)
        form = PhoneLineForm(data=payload)
        assert not form.is_valid()
        assert "whatsapp_seal_monthly_value" in form.errors

    def test_zero_explicito_diferente_de_ausencia(self, sim):
        """Node: T22. "0,00" (zero explícito, válido para Não ativado) não
        pode ser tratado como ausência de valor. RED esperado:
        AttributeError na instância fresca ao comparar com Decimal("0.00")
        versus None."""
        payload = base_payload(
            sim,
            whatsapp_seal_activation_status="NOT_ACTIVATED",
            whatsapp_seal_monthly_value="0,00",
            whatsapp_seal_activated_on="",
            whatsapp_seal_expires_on="",
        )
        form = PhoneLineForm(data=payload)
        assert form.is_valid(), form.errors
        line = form.save()
        fresh = _fresh(line)
        assert fresh.whatsapp_seal_monthly_value is not None
        assert fresh.whatsapp_seal_monthly_value == Decimal("0.00")


# ===========================================================================
# T23 — Form novo apresenta Não ativado; POST com selo sem situação
# inválido; serviço com selo e args novos ausentes rejeitado; chamadores
# Sem selo continuam válidos. Camada: form/domínio · SEV-04/05
# ===========================================================================


class TestT23DefaultsEChamadoresCompatíveis:
    def test_chamador_sem_selo_continua_compativel(self, sim):
        """Node: T23. create_or_reuse sem nenhum kwarg de selo continua
        funcionando como hoje. Controle de regressão — espera-se GREEN já
        nesta rodada."""
        line = PhoneLine.create_or_reuse(
            phone_number="+5511999997019",
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
        )
        assert line.whatsapp_seal == ""

    def test_create_or_reuse_com_selo_exige_novos_dados(self, sim):
        """Node: T23. Quando o chamador informa selo, deve exigir
        situação/categoria/plano/valor válidos via domínio — não presumir
        ACTIVE nem usar default para mascarar ausência. RED esperado:
        create_or_reuse hoje aceita selo sem nenhum desses quatro dados
        sem levantar erro (nenhuma validação de domínio nova existe)."""
        with pytest.raises(ValidationError):
            PhoneLine.create_or_reuse(
                phone_number="+5511999997020",
                sim_card=sim,
                status=PhoneLine.Status.AVAILABLE,
                whatsapp_seal="META_ONE",
            )
