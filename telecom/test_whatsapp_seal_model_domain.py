"""Testes diretos de domínio/modelo — SEV-04.

Fonte da verdade: docs/superpowers/specs/2026-09-30-whatsapp-seal-
activation-value-design.md (contrato técnico, T01-T23).

Diferente de telecom/test_whatsapp_seal_activation_value.py (SEV-03, RED
via PhoneLineForm/PhoneLineUpdateForm — fronteira de SEV-05, ainda não
integrada), este arquivo comprova as regras de SEV-04 (campos de PhoneLine,
clean(), seal_status e telecom/whatsapp_seal.py) inteiramente pela fronteira
de domínio/model: PhoneLine.full_clean()/save() diretos e as funções de
telecom/whatsapp_seal.py. Não usa PhoneLineForm, PhoneLineUpdateForm,
create_or_reuse (fora de escopo de SEV-04) nem o client HTTP.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from telecom import whatsapp_seal
from telecom.models import PhoneLine, SIMcard

pytestmark = pytest.mark.django_db


@pytest.fixture
def sim():
    return SIMcard.objects.create(iccid="8900000000000090001", carrier="TIM")


def _make_line(sim_instance, phone_number, **field_values):
    line = PhoneLine(
        phone_number=phone_number,
        sim_card=sim_instance,
        status="AVAILABLE",
        **field_values,
    )
    return line


def _fresh(line):
    return PhoneLine.objects.get(pk=line.pk)


# ---------------------------------------------------------------------------
# T01 — Sem selo: full_clean() normaliza e limpa os 9 campos próprios do selo
# ---------------------------------------------------------------------------


def test_sem_selo_full_clean_limpa_todos_os_campos_proprios_do_selo(sim):
    line = _make_line(
        sim,
        "+5511999996001",
        whatsapp_seal="",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_category="CREATORS_BUSINESSES",
        whatsapp_seal_plan="ONE_ESSENTIAL",
        whatsapp_seal_monthly_value=Decimal("59.00"),
        whatsapp_seal_activated_on=date(2026, 1, 1),
        whatsapp_seal_expires_on=date(2026, 12, 1),
        whatsapp_seal_email="residuo@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    line.full_clean()
    line.save()

    fresh = _fresh(line)
    assert fresh.whatsapp_seal_activation_status == ""
    assert fresh.whatsapp_seal_category == ""
    assert fresh.whatsapp_seal_plan == ""
    assert fresh.whatsapp_seal_monthly_value is None
    assert fresh.whatsapp_seal_activated_on is None
    assert fresh.whatsapp_seal_expires_on is None
    assert fresh.whatsapp_seal_email == ""
    assert fresh.whatsapp_seal_payment == ""


# ---------------------------------------------------------------------------
# T17 — Catálogo: as quatro combinações aprovadas e rejeições
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "idx,seal,category,plan",
    [
        (0, "META_ONE", "CREATORS_BUSINESSES", "ONE_ESSENTIAL"),
        (1, "META_VERIFIED", "PERSONAL_CREATOR", "STANDARD"),
        (2, "META_VERIFIED", "BUSINESS_SME", "BUSINESS_BASIC"),
        (3, "META_VERIFIED", "BUSINESS", "BUSINESS_PLUS"),
    ],
)
def test_combinacao_do_catalogo_salva_e_reabre_corretamente(sim, idx, seal, category, plan):
    line = _make_line(
        sim,
        f"+551199999680{idx}",
        whatsapp_seal=seal,
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_category=category,
        whatsapp_seal_plan=plan,
        whatsapp_seal_monthly_value=Decimal("59.00"),
        whatsapp_seal_activated_on=date(2026, 1, 1),
        whatsapp_seal_expires_on=date(2026, 12, 1),
        whatsapp_seal_email="catalogo@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    line.full_clean()
    line.save()

    fresh = _fresh(line)
    assert fresh.whatsapp_seal_category == category
    assert fresh.whatsapp_seal_plan == plan


def test_combinacao_cruzada_incompativel_eh_rejeitada(sim):
    line = _make_line(
        sim,
        "+5511999996002",
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_category="CREATORS_BUSINESSES",
        whatsapp_seal_plan="BUSINESS_PLUS",
        whatsapp_seal_monthly_value=Decimal("59.00"),
        whatsapp_seal_activated_on=date(2026, 1, 1),
        whatsapp_seal_expires_on=date(2026, 12, 1),
        whatsapp_seal_email="cruzada@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    with pytest.raises(ValidationError) as exc:
        line.full_clean()
    assert "whatsapp_seal_plan" in exc.value.message_dict


def test_token_de_categoria_desconhecido_eh_rejeitado(sim):
    line = _make_line(
        sim,
        "+5511999996003",
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_category="TOKEN_QUE_NAO_EXISTE",
        whatsapp_seal_plan="ONE_ESSENTIAL",
        whatsapp_seal_monthly_value=Decimal("59.00"),
        whatsapp_seal_activated_on=date(2026, 1, 1),
        whatsapp_seal_expires_on=date(2026, 12, 1),
        whatsapp_seal_email="token@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    with pytest.raises(ValidationError) as exc:
        line.full_clean()
    assert "whatsapp_seal_category" in exc.value.message_dict


# ---------------------------------------------------------------------------
# T21/T06 — Fronteiras monetárias (Decimal, domínio puro — parsing textual
# de formulário fica para SEV-05)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [Decimal("0.00"), Decimal("150.00"), Decimal("299.00")])
def test_nao_ativado_aceita_valor_entre_zero_e_limite(sim, value):
    line = _make_line(
        sim,
        f"+551199999700{int(value)}",
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="NOT_ACTIVATED",
        whatsapp_seal_category="CREATORS_BUSINESSES",
        whatsapp_seal_plan="ONE_ESSENTIAL",
        whatsapp_seal_monthly_value=value,
        whatsapp_seal_email="limite@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    line.full_clean()
    line.save()
    fresh = _fresh(line)
    assert fresh.whatsapp_seal_monthly_value == value


def test_ativo_rejeita_valor_zero(sim):
    line = _make_line(
        sim,
        "+5511999996010",
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_category="CREATORS_BUSINESSES",
        whatsapp_seal_plan="ONE_ESSENTIAL",
        whatsapp_seal_monthly_value=Decimal("0.00"),
        whatsapp_seal_activated_on=date(2026, 1, 1),
        whatsapp_seal_expires_on=date(2026, 12, 1),
        whatsapp_seal_email="zero@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    with pytest.raises(ValidationError) as exc:
        line.full_clean()
    assert "whatsapp_seal_monthly_value" in exc.value.message_dict


def test_ativo_aceita_minimo_positivo(sim):
    line = _make_line(
        sim,
        "+5511999996011",
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_category="CREATORS_BUSINESSES",
        whatsapp_seal_plan="ONE_ESSENTIAL",
        whatsapp_seal_monthly_value=Decimal("0.01"),
        whatsapp_seal_activated_on=date(2026, 1, 1),
        whatsapp_seal_expires_on=date(2026, 12, 1),
        whatsapp_seal_email="minimo@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    line.full_clean()
    line.save()
    assert _fresh(line).whatsapp_seal_monthly_value == Decimal("0.01")


@pytest.mark.parametrize("activation_status", ["NOT_ACTIVATED", "ACTIVE"])
def test_valor_negativo_rejeitado_em_ambos_estados(sim, activation_status):
    extra_dates = (
        {}
        if activation_status == "NOT_ACTIVATED"
        else {
            "whatsapp_seal_activated_on": date(2026, 1, 1),
            "whatsapp_seal_expires_on": date(2026, 12, 1),
        }
    )
    line = _make_line(
        sim,
        f"+551199999602{0 if activation_status == 'NOT_ACTIVATED' else 1}",
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status=activation_status,
        whatsapp_seal_category="CREATORS_BUSINESSES",
        whatsapp_seal_plan="ONE_ESSENTIAL",
        whatsapp_seal_monthly_value=Decimal("-0.01"),
        whatsapp_seal_email="negativo@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
        **extra_dates,
    )
    with pytest.raises(ValidationError) as exc:
        line.full_clean()
    assert "whatsapp_seal_monthly_value" in exc.value.message_dict


def test_valor_acima_do_limite_rejeitado(sim):
    line = _make_line(
        sim,
        "+5511999996030",
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="NOT_ACTIVATED",
        whatsapp_seal_category="CREATORS_BUSINESSES",
        whatsapp_seal_plan="ONE_ESSENTIAL",
        whatsapp_seal_monthly_value=Decimal("299.01"),
        whatsapp_seal_email="acima@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    with pytest.raises(ValidationError) as exc:
        line.full_clean()
    assert "whatsapp_seal_monthly_value" in exc.value.message_dict


def test_ausencia_de_valor_eh_invalida_mesmo_nao_ativado(sim):
    line = _make_line(
        sim,
        "+5511999996031",
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="NOT_ACTIVATED",
        whatsapp_seal_category="CREATORS_BUSINESSES",
        whatsapp_seal_plan="ONE_ESSENTIAL",
        whatsapp_seal_monthly_value=None,
        whatsapp_seal_email="ausencia@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    with pytest.raises(ValidationError) as exc:
        line.full_clean()
    assert "whatsapp_seal_monthly_value" in exc.value.message_dict


def test_zero_explicito_persiste_diferente_de_ausencia(sim):
    line = _make_line(
        sim,
        "+5511999996032",
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="NOT_ACTIVATED",
        whatsapp_seal_category="CREATORS_BUSINESSES",
        whatsapp_seal_plan="ONE_ESSENTIAL",
        whatsapp_seal_monthly_value=Decimal("0.00"),
        whatsapp_seal_email="zeroexplicito@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    line.full_clean()
    line.save()
    fresh = _fresh(line)
    assert fresh.whatsapp_seal_monthly_value is not None
    assert fresh.whatsapp_seal_monthly_value == Decimal("0.00")


def test_mais_de_duas_casas_decimais_eh_rejeitado_pelo_campo(sim):
    """Node: T22 (fronteira de domínio — precisão Decimal do próprio
    DecimalField, não parsing textual de formulário, que é SEV-05)."""
    line = _make_line(
        sim,
        "+5511999996033",
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="NOT_ACTIVATED",
        whatsapp_seal_category="CREATORS_BUSINESSES",
        whatsapp_seal_plan="ONE_ESSENTIAL",
        whatsapp_seal_monthly_value=Decimal("59.123"),
        whatsapp_seal_email="casas@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    with pytest.raises(ValidationError) as exc:
        line.full_clean()
    assert "whatsapp_seal_monthly_value" in exc.value.message_dict


# ---------------------------------------------------------------------------
# T03 — Ativo exige datas; iguais aceitas, invertidas rejeitadas
# ---------------------------------------------------------------------------


def test_ativo_exige_datas_de_ativacao_e_vencimento(sim):
    line = _make_line(
        sim,
        "+5511999996040",
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_category="CREATORS_BUSINESSES",
        whatsapp_seal_plan="ONE_ESSENTIAL",
        whatsapp_seal_monthly_value=Decimal("59.00"),
        whatsapp_seal_email="semdata@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    with pytest.raises(ValidationError) as exc:
        line.full_clean()
    assert "whatsapp_seal_activated_on" in exc.value.message_dict
    assert "whatsapp_seal_expires_on" in exc.value.message_dict


def test_ativo_aceita_datas_iguais(sim):
    same_date = date(2026, 6, 1)
    line = _make_line(
        sim,
        "+5511999996041",
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_category="CREATORS_BUSINESSES",
        whatsapp_seal_plan="ONE_ESSENTIAL",
        whatsapp_seal_monthly_value=Decimal("59.00"),
        whatsapp_seal_activated_on=same_date,
        whatsapp_seal_expires_on=same_date,
        whatsapp_seal_email="igual@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    line.full_clean()
    line.save()
    assert _fresh(line).whatsapp_seal_expires_on == same_date


def test_ativo_rejeita_vencimento_anterior_a_ativacao(sim):
    line = _make_line(
        sim,
        "+5511999996042",
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_category="CREATORS_BUSINESSES",
        whatsapp_seal_plan="ONE_ESSENTIAL",
        whatsapp_seal_monthly_value=Decimal("59.00"),
        whatsapp_seal_activated_on=date(2026, 10, 17),
        whatsapp_seal_expires_on=date(2026, 9, 1),
        whatsapp_seal_email="invertido@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    with pytest.raises(ValidationError) as exc:
        line.full_clean()
    assert "whatsapp_seal_expires_on" in exc.value.message_dict


# ---------------------------------------------------------------------------
# T02/T16 — Não ativado: datas nulas obrigatórias; normalize limpa resíduo
# ---------------------------------------------------------------------------


def test_nao_ativado_com_datas_residuais_eh_normalizado_antes_de_validar(sim):
    """normalize_seal_fields limpa as datas residuais de Não ativado ANTES
    de validate_seal_fields rodar — por isso full_clean() não rejeita datas
    residuais aqui; ele as limpa. Ver T16 (transição Ativo -> Não ativado)
    coberto abaixo com duas etapas reais de save()."""
    line = _make_line(
        sim,
        "+5511999996050",
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="NOT_ACTIVATED",
        whatsapp_seal_category="CREATORS_BUSINESSES",
        whatsapp_seal_plan="ONE_ESSENTIAL",
        whatsapp_seal_monthly_value=Decimal("59.00"),
        whatsapp_seal_activated_on=date(2026, 1, 1),
        whatsapp_seal_expires_on=date(2026, 12, 1),
        whatsapp_seal_email="residual@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    line.full_clean()
    line.save()
    fresh = _fresh(line)
    assert fresh.whatsapp_seal_activated_on is None
    assert fresh.whatsapp_seal_expires_on is None
    assert fresh.whatsapp_seal_category == "CREATORS_BUSINESSES"
    assert fresh.whatsapp_seal_monthly_value == Decimal("59.00")


def test_ativo_para_nao_ativado_limpa_datas_preserva_demais_dados_do_selo(sim):
    """Node: T16. Duas gravações reais e sequenciais via model (sem forms):
    primeiro Ativo completo, depois a mesma linha editada para Não ativado —
    deve limpar as datas e preservar tipo/categoria/plano/valor/e-mail/
    pagamento."""
    line = _make_line(
        sim,
        "+5511999996051",
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_category="CREATORS_BUSINESSES",
        whatsapp_seal_plan="ONE_ESSENTIAL",
        whatsapp_seal_monthly_value=Decimal("59.00"),
        whatsapp_seal_activated_on=date(2026, 9, 1),
        whatsapp_seal_expires_on=date(2026, 10, 17),
        whatsapp_seal_email="transicao@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    line.full_clean()
    line.save()

    line.whatsapp_seal_activation_status = "NOT_ACTIVATED"
    line.full_clean()
    line.save()

    fresh = _fresh(line)
    assert fresh.whatsapp_seal_activation_status == "NOT_ACTIVATED"
    assert fresh.whatsapp_seal_activated_on is None
    assert fresh.whatsapp_seal_expires_on is None
    assert fresh.whatsapp_seal_category == "CREATORS_BUSINESSES"
    assert fresh.whatsapp_seal_plan == "ONE_ESSENTIAL"
    assert fresh.whatsapp_seal_monthly_value == Decimal("59.00")
    assert fresh.whatsapp_seal_email == "transicao@example.com"
    assert fresh.whatsapp_seal_payment == "CREDIT_CARD"


# ---------------------------------------------------------------------------
# E-mail/pagamento obrigatórios com selo
# ---------------------------------------------------------------------------


def test_email_e_pagamento_obrigatorios_com_selo(sim):
    line = _make_line(
        sim,
        "+5511999996060",
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="NOT_ACTIVATED",
        whatsapp_seal_category="CREATORS_BUSINESSES",
        whatsapp_seal_plan="ONE_ESSENTIAL",
        whatsapp_seal_monthly_value=Decimal("59.00"),
    )
    with pytest.raises(ValidationError) as exc:
        line.full_clean()
    assert "whatsapp_seal_email" in exc.value.message_dict
    assert "whatsapp_seal_payment" in exc.value.message_dict


def test_situacao_ausente_com_selo_eh_rejeitada(sim):
    line = _make_line(
        sim,
        "+5511999996061",
        whatsapp_seal="META_ONE",
        whatsapp_seal_category="CREATORS_BUSINESSES",
        whatsapp_seal_plan="ONE_ESSENTIAL",
        whatsapp_seal_monthly_value=Decimal("59.00"),
        whatsapp_seal_email="semsituacao@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    with pytest.raises(ValidationError) as exc:
        line.full_clean()
    assert "whatsapp_seal_activation_status" in exc.value.message_dict


# ---------------------------------------------------------------------------
# T20 — Legado via ORM direta (save() comum, sem full_clean): nenhum campo
# novo é inferido — nem situação, nem categoria/plano.
#
# Retificação de SEV-04 (01/10/2026): esta asserção originalmente exigia
# whatsapp_seal_activation_status == "ACTIVE", codificando o fallback de
# PhoneLine.save() que foi removido por inferir situação ausente em save()
# comum (achado B da retificação — ver fonte da verdade). O backfill
# histórico (ACTIVE para legado real) é responsabilidade exclusiva da
# migration 0022 (RunPython), nunca do model/save(). Ver
# telecom/test_whatsapp_seal_sev04_correction.py e
# telecom/test_whatsapp_seal_activation_migration.py.
# ---------------------------------------------------------------------------


def test_save_comum_nao_infere_situacao_nem_categoria_plano(sim):
    line = PhoneLine.objects.create(
        phone_number="+5511999996070",
        sim_card=sim,
        status="AVAILABLE",
        whatsapp_seal="META_ONE",
        whatsapp_seal_activated_on=date(2026, 1, 10),
        whatsapp_seal_expires_on=date(2026, 12, 10),
        whatsapp_seal_email="legado-orm@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    fresh = _fresh(line)
    assert fresh.whatsapp_seal_activation_status == ""
    assert fresh.whatsapp_seal_category == ""
    assert fresh.whatsapp_seal_plan == ""
    assert fresh.whatsapp_seal_monthly_value is None
    assert fresh.whatsapp_seal_activated_on == date(2026, 1, 10)


def test_linha_sem_selo_nao_recebe_situacao_automatica(sim):
    line = PhoneLine.objects.create(
        phone_number="+5511999996071", sim_card=sim, status="AVAILABLE"
    )
    fresh = _fresh(line)
    assert fresh.whatsapp_seal_activation_status == ""


# ---------------------------------------------------------------------------
# seal_status / compute_seal_status — alertas preservados, Não ativado nunca
# alerta mesmo com data residual, Sem selo distinto de Não ativado
# ---------------------------------------------------------------------------


def test_sem_selo_label_distinto_de_nao_ativado():
    line = PhoneLine(whatsapp_seal="")
    assert line.seal_status == {"tone": "neutral", "label": "Sem selo"}


def test_nao_ativado_sem_vencimento_mostra_nao_ativado():
    line = PhoneLine(whatsapp_seal="META_ONE", whatsapp_seal_expires_on=None)
    status = line.seal_status
    assert status == {"tone": "neutral", "label": "Não ativado"}


def test_nao_ativado_explicito_ignora_data_residual_vencida(monkeypatch):
    monkeypatch.setattr(timezone, "localdate", lambda: date(2026, 9, 17))
    line = PhoneLine(
        whatsapp_seal="META_ONE",
        whatsapp_seal_expires_on=date(2026, 1, 1),
        whatsapp_seal_activation_status="NOT_ACTIVATED",
    )
    assert line.seal_status == {"tone": "neutral", "label": "Não ativado"}


@pytest.mark.parametrize(
    "delta_days,expected_tone",
    [(8, "neutral"), (7, "warning"), (1, "warning"), (0, "today"), (-1, "expired")],
)
def test_ativo_mantem_alertas_8_7_1_0_menos1_dias(monkeypatch, delta_days, expected_tone):
    from datetime import timedelta

    today = date(2026, 9, 17)
    monkeypatch.setattr(timezone, "localdate", lambda: today)
    expires_on = today + timedelta(days=delta_days)
    line = PhoneLine(
        whatsapp_seal="META_ONE",
        whatsapp_seal_expires_on=expires_on,
        whatsapp_seal_activation_status="ACTIVE",
    )
    assert line.seal_status["tone"] == expected_tone


def test_selo_ativo_vencido_continua_active_quanto_a_ativacao(sim):
    """Vencimento não rebaixa whatsapp_seal_activation_status — apenas o
    rótulo do indicador muda (tone='expired'); a ativação persistida
    continua ACTIVE, nunca é sobrescrita por compute_seal_status (que não
    persiste nada)."""
    line = PhoneLine.objects.create(
        phone_number="+5511999996072",
        sim_card=sim,
        status="AVAILABLE",
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_category="CREATORS_BUSINESSES",
        whatsapp_seal_plan="ONE_ESSENTIAL",
        whatsapp_seal_monthly_value=Decimal("59.00"),
        whatsapp_seal_activated_on=date(2020, 1, 1),
        whatsapp_seal_expires_on=date(2020, 2, 1),
        whatsapp_seal_email="vencido@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    fresh = _fresh(line)
    assert fresh.whatsapp_seal_activation_status == "ACTIVE"
    assert fresh.seal_status["tone"] == "expired"


# ---------------------------------------------------------------------------
# Catálogo centralizado — smoke test de que as referências vivem só no
# domínio (telecom/whatsapp_seal.py), sem duplicação de tabela de preços
# ---------------------------------------------------------------------------


def test_catalogo_centralizado_tem_as_quatro_combinacoes_aprovadas():
    assert len(whatsapp_seal.SEAL_CATALOG_COMBINATIONS) == 4
    assert (
        whatsapp_seal.WhatsAppSeal.META_ONE,
        whatsapp_seal.WhatsAppSealCategory.CREATORS_BUSINESSES,
        whatsapp_seal.WhatsAppSealPlan.ONE_ESSENTIAL,
    ) in whatsapp_seal.SEAL_CATALOG_COMBINATIONS


def test_referencia_de_preco_nao_eh_usada_para_validar_valor_efetivo(sim):
    """Node: T18 (parte de domínio). Plano com referência fixa (R$ 59,00)
    aceita valor efetivo diferente — a referência é só exibição (SEV-06),
    nunca restrição de domínio."""
    line = _make_line(
        sim,
        "+5511999996080",
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_category="CREATORS_BUSINESSES",
        whatsapp_seal_plan="ONE_ESSENTIAL",
        whatsapp_seal_monthly_value=Decimal("45.00"),
        whatsapp_seal_activated_on=date(2026, 1, 1),
        whatsapp_seal_expires_on=date(2026, 12, 1),
        whatsapp_seal_email="referencia@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    line.full_clean()
    line.save()
    assert _fresh(line).whatsapp_seal_monthly_value == Decimal("45.00")
