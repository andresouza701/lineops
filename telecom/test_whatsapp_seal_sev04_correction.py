"""Testes de retificação de SEV-04 — removem o portão de compatibilidade
de PhoneLine.clean() e o fallback legado->ACTIVE de PhoneLine.save().

Fonte da verdade: docs/superpowers/specs/2026-09-30-whatsapp-seal-
activation-value-design.md (Registro de execução, retificação de SEV-04).

Dois achados confirmados por inspeção direta do código antes deste arquivo
(não por relato):

A. PhoneLine.clean() tinha um portão (`_seal_extended_fields_in_use`) que
   pulava a validação obrigatória de situação/categoria/plano/valor sempre
   que os três campos (categoria, plano, valor) estavam todos ausentes —
   exatamente o caso que o contrato exige rejeitar. Removido: a validação
   completa (telecom.whatsapp_seal.validate_seal_fields) agora roda sempre
   que há selo, sem exceção.
B. PhoneLine.save() tinha um fallback que classificava qualquer linha com
   selo e situação vazia como ACTIVE automaticamente, em qualquer save()
   comum — não só no backfill de migração. Isso inferia situação ausente
   em entrada nova, o que o contrato proíbe. Removido: save() não toca mais
   nenhum campo do selo; o backfill histórico é responsabilidade exclusiva
   da migration 0022 (RunPython bulk update, sem passar pelo model).

Este arquivo prova, pela fronteira de domínio/model (full_clean/save
diretos, sem PhoneLineForm), que os dois mecanismos foram removidos e que
o contrato completo é aplicado sempre que full_clean() roda.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from telecom.models import PhoneLine, SIMcard

pytestmark = pytest.mark.django_db


@pytest.fixture
def sim():
    return SIMcard.objects.create(iccid="8900000000000095001", carrier="TIM")


def _line(sim_instance, phone_number, **field_values):
    return PhoneLine(
        phone_number=phone_number,
        sim_card=sim_instance,
        status="AVAILABLE",
        **field_values,
    )


def _fresh(line):
    return PhoneLine.objects.get(pk=line.pk)


# ---------------------------------------------------------------------------
# 1. Selo com os 4 campos novos ausentes: full_clean rejeita (achado A)
# ---------------------------------------------------------------------------


def test_selo_com_quatro_campos_novos_ausentes_eh_rejeitado_por_full_clean(sim):
    line = _line(
        sim,
        "+5511999995101",
        whatsapp_seal="META_ONE",
        whatsapp_seal_activated_on=date(2026, 1, 1),
        whatsapp_seal_expires_on=date(2026, 12, 1),
        whatsapp_seal_email="semcampos@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    with pytest.raises(ValidationError) as exc:
        line.full_clean()
    errors = exc.value.message_dict
    assert "whatsapp_seal_activation_status" in errors
    assert "whatsapp_seal_category" in errors
    assert "whatsapp_seal_plan" in errors
    assert "whatsapp_seal_monthly_value" in errors


# ---------------------------------------------------------------------------
# 2. NOT_ACTIVATED sem categoria/plano/valor: full_clean rejeita obrigatórios
# ---------------------------------------------------------------------------


def test_nao_ativado_sem_categoria_plano_valor_eh_rejeitado(sim):
    line = _line(
        sim,
        "+5511999995102",
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="NOT_ACTIVATED",
        whatsapp_seal_email="semextras@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    with pytest.raises(ValidationError) as exc:
        line.full_clean()
    errors = exc.value.message_dict
    assert "whatsapp_seal_category" in errors
    assert "whatsapp_seal_plan" in errors
    assert "whatsapp_seal_monthly_value" in errors
    assert "whatsapp_seal_activation_status" not in errors


# ---------------------------------------------------------------------------
# 3. Situação ausente, demais dados completos: full_clean rejeita situação
# ---------------------------------------------------------------------------


def test_situacao_ausente_com_demais_dados_completos_eh_rejeitada(sim):
    line = _line(
        sim,
        "+5511999995103",
        whatsapp_seal="META_ONE",
        whatsapp_seal_category="CREATORS_BUSINESSES",
        whatsapp_seal_plan="ONE_ESSENTIAL",
        whatsapp_seal_monthly_value=Decimal("59.00"),
        whatsapp_seal_activated_on=date(2026, 1, 1),
        whatsapp_seal_expires_on=date(2026, 12, 1),
        whatsapp_seal_email="situacaoausente@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    with pytest.raises(ValidationError) as exc:
        line.full_clean()
    errors = exc.value.message_dict
    assert "whatsapp_seal_activation_status" in errors
    assert "whatsapp_seal_category" not in errors
    assert "whatsapp_seal_plan" not in errors
    assert "whatsapp_seal_monthly_value" not in errors


# ---------------------------------------------------------------------------
# 4. ACTIVE com campos completos: valida
# ---------------------------------------------------------------------------


def test_ativo_com_campos_completos_valida(sim):
    line = _line(
        sim,
        "+5511999995104",
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_category="CREATORS_BUSINESSES",
        whatsapp_seal_plan="ONE_ESSENTIAL",
        whatsapp_seal_monthly_value=Decimal("59.00"),
        whatsapp_seal_activated_on=date(2026, 1, 1),
        whatsapp_seal_expires_on=date(2026, 12, 1),
        whatsapp_seal_email="ativo@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    line.full_clean()
    line.save()
    fresh = _fresh(line)
    assert fresh.whatsapp_seal_activation_status == "ACTIVE"
    assert fresh.whatsapp_seal_monthly_value == Decimal("59.00")


# ---------------------------------------------------------------------------
# 5. NOT_ACTIVATED com campos completos e valor zero: valida
# ---------------------------------------------------------------------------


def test_nao_ativado_com_campos_completos_e_valor_zero_valida(sim):
    line = _line(
        sim,
        "+5511999995105",
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="NOT_ACTIVATED",
        whatsapp_seal_category="CREATORS_BUSINESSES",
        whatsapp_seal_plan="ONE_ESSENTIAL",
        whatsapp_seal_monthly_value=Decimal("0.00"),
        whatsapp_seal_email="naoativadozero@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    line.full_clean()
    line.save()
    fresh = _fresh(line)
    assert fresh.whatsapp_seal_activation_status == "NOT_ACTIVATED"
    assert fresh.whatsapp_seal_monthly_value == Decimal("0.00")
    assert fresh.whatsapp_seal_activated_on is None
    assert fresh.whatsapp_seal_expires_on is None


# ---------------------------------------------------------------------------
# 6. ACTIVE com valor zero: rejeita
# ---------------------------------------------------------------------------


def test_ativo_com_valor_zero_eh_rejeitado(sim):
    line = _line(
        sim,
        "+5511999995106",
        whatsapp_seal="META_ONE",
        whatsapp_seal_activation_status="ACTIVE",
        whatsapp_seal_category="CREATORS_BUSINESSES",
        whatsapp_seal_plan="ONE_ESSENTIAL",
        whatsapp_seal_monthly_value=Decimal("0.00"),
        whatsapp_seal_activated_on=date(2026, 1, 1),
        whatsapp_seal_expires_on=date(2026, 12, 1),
        whatsapp_seal_email="ativozero@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    with pytest.raises(ValidationError) as exc:
        line.full_clean()
    assert "whatsapp_seal_monthly_value" in exc.value.message_dict


# ---------------------------------------------------------------------------
# 7. Registro histórico migrado: ACTIVE vem da migration, não do model/save
# ---------------------------------------------------------------------------


def test_backfill_historico_classifica_ative_sem_depender_de_save_ou_model(sim):
    """A migration 0022 usa apps.get_model (histórico) + .update() em massa
    — nunca PhoneLine.save()/full_clean(). Com o fallback de save() e o
    portão de clean() removidos, confirma-se aqui que o próprio
    PhoneLine.objects.create() (model real, sem full_clean) NÃO classifica
    nada sozinho: quem classifica é exclusivamente o RunPython da migration
    (ver telecom/test_whatsapp_seal_activation_migration.py para os 6
    cenários completos de T10, executados em banco isolado)."""
    line = PhoneLine.objects.create(
        phone_number="+5511999995107",
        sim_card=sim,
        status="AVAILABLE",
        whatsapp_seal="META_ONE",
        whatsapp_seal_activated_on=date(2026, 1, 10),
        whatsapp_seal_expires_on=date(2026, 12, 10),
        whatsapp_seal_email="legado-real@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    fresh = _fresh(line)
    assert fresh.whatsapp_seal_activation_status == ""
    assert fresh.whatsapp_seal_category == ""
    assert fresh.whatsapp_seal_plan == ""
    assert fresh.whatsapp_seal_monthly_value is None
    assert fresh.whatsapp_seal_activated_on == date(2026, 1, 10)
    assert fresh.whatsapp_seal_expires_on == date(2026, 12, 10)


# ---------------------------------------------------------------------------
# 8. Operação independente em legado via save(update_fields=...) não exige
# nem preenche situação/categoria/plano/valor
# ---------------------------------------------------------------------------


def test_operacao_independente_em_legado_nao_exige_nem_preenche_campos_novos(sim):
    line = PhoneLine.objects.create(
        phone_number="+5511999995108",
        sim_card=sim,
        status="ALLOCATED",
        whatsapp_seal="META_ONE",
        whatsapp_seal_activated_on=date(2026, 1, 10),
        whatsapp_seal_expires_on=date(2026, 12, 10),
        whatsapp_seal_email="legado-liberar@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    assert line.whatsapp_seal_activation_status == ""

    line.status = "AVAILABLE"
    line.save(update_fields=["status"])

    fresh = _fresh(line)
    assert fresh.status == "AVAILABLE"
    assert fresh.whatsapp_seal_activation_status == ""
    assert fresh.whatsapp_seal_category == ""
    assert fresh.whatsapp_seal_plan == ""
    assert fresh.whatsapp_seal_monthly_value is None


# ---------------------------------------------------------------------------
# 9. save() comum não inventa ACTIVE quando situação está ausente
# ---------------------------------------------------------------------------


def test_save_comum_nao_inventa_active_quando_situacao_ausente(sim):
    line = PhoneLine(
        phone_number="+5511999995109",
        sim_card=sim,
        status="AVAILABLE",
        whatsapp_seal="META_ONE",
        whatsapp_seal_activated_on=date(2026, 1, 1),
        whatsapp_seal_expires_on=date(2026, 12, 1),
        whatsapp_seal_email="savecomum@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    line.save()
    fresh = _fresh(line)
    assert fresh.whatsapp_seal_activation_status == ""
