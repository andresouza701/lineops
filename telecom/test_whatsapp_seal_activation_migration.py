"""Testes reais de migração — T10 (SEV-04).

Fonte da verdade: docs/superpowers/specs/2026-09-30-whatsapp-seal-
activation-value-design.md (contrato técnico, migração 0022, T10).

Cobre os 6 cenários aprovados: (1) legado com selo vira ACTIVE; (2) datas
preservadas; (3) categoria/plano vazios; (4) valor null; (5) registros
logicamente excluídos também contemplados; (6) reversão preserva os 5
campos antigos.

Backend: SQLite (forçado por pytest-django neste ambiente — ver
config/settings.py, bloco `if "pytest" in sys.modules`). Não executado
contra Postgres nesta rodada; ver limitação registrada na fonte da verdade.

Cada teste roda em banco de teste descartável (@pytest.mark.django_db) e
restaura o estado de migrations para o HEAD do app no `finally`, para não
contaminar outras suítes que rodem depois na mesma sessão de teste.
"""

from datetime import date

import pytest
from django.core.management import call_command
from django.db import connection

from telecom.models import PhoneLine, SIMcard

PHONELINE_TABLE = "telecom_phoneline"


def _raw_seal_row(phone_number):
    """Leitura via SQL cru dos 5 campos antigos de selo — usada depois de
    reverter a migration 0022, quando o model real (que já declara os 4
    campos novos) não pode mais fazer SELECT * sem quebrar contra o schema
    reduzido."""
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT whatsapp_seal, whatsapp_seal_activated_on, "
            f"whatsapp_seal_expires_on, whatsapp_seal_email, "
            f"whatsapp_seal_payment FROM {PHONELINE_TABLE} "
            f"WHERE phone_number = %s",
            [phone_number],
        )
        return cursor.fetchone()


@pytest.mark.django_db(transaction=True)
def test_migration_0022_backfill_classifica_legado_preserva_datas_e_exclui_sem_selo():
    sim_with_seal = SIMcard.objects.create(iccid="8900000000000080001", carrier="TIM")
    sim_without_seal = SIMcard.objects.create(iccid="8900000000000080002", carrier="TIM")
    sim_deleted = SIMcard.objects.create(iccid="8900000000000080003", carrier="TIM")
    sim_inconsistent = SIMcard.objects.create(iccid="8900000000000080004", carrier="TIM")

    with_seal = PhoneLine.objects.create(
        phone_number="+5511999998001",
        sim_card=sim_with_seal,
        status="AVAILABLE",
        whatsapp_seal="META_ONE",
        whatsapp_seal_activated_on=date(2026, 1, 10),
        whatsapp_seal_expires_on=date(2026, 12, 10),
        whatsapp_seal_email="legado@example.com",
        whatsapp_seal_payment="CREDIT_CARD",
    )
    without_seal = PhoneLine.objects.create(
        phone_number="+5511999998002",
        sim_card=sim_without_seal,
        status="AVAILABLE",
    )
    deleted_with_seal = PhoneLine.objects.create(
        phone_number="+5511999998003",
        sim_card=sim_deleted,
        status="AVAILABLE",
        whatsapp_seal="META_VERIFIED",
        whatsapp_seal_activated_on=date(2026, 2, 1),
        whatsapp_seal_expires_on=date(2026, 11, 1),
        whatsapp_seal_email="legado-deletado@example.com",
        whatsapp_seal_payment="GOOGLE_GIFT_CARD",
    )
    deleted_with_seal.is_deleted = True
    deleted_with_seal.save(update_fields=["is_deleted"])

    # Linha inconsistente proposital: selo preenchido sem e-mail/pagamento,
    # estado que não deveria existir sob a validação nova mas que pode
    # existir em dado legado real. O backfill não deve "consertar" isso.
    inconsistent = PhoneLine.objects.create(
        phone_number="+5511999998004",
        sim_card=sim_inconsistent,
        status="AVAILABLE",
        whatsapp_seal="META_ONE",
    )

    try:
        call_command("migrate", "telecom", "0021", verbosity=0)
        call_command("migrate", "telecom", "0022", verbosity=0)

        fresh = PhoneLine.all_objects.get(pk=with_seal.pk)
        assert fresh.whatsapp_seal_activation_status == "ACTIVE"
        assert fresh.whatsapp_seal_activated_on == date(2026, 1, 10)
        assert fresh.whatsapp_seal_expires_on == date(2026, 12, 10)
        assert fresh.whatsapp_seal_email == "legado@example.com"
        assert fresh.whatsapp_seal_payment == "CREDIT_CARD"
        assert fresh.whatsapp_seal_category == ""
        assert fresh.whatsapp_seal_plan == ""
        assert fresh.whatsapp_seal_monthly_value is None

        fresh_without_seal = PhoneLine.all_objects.get(pk=without_seal.pk)
        assert fresh_without_seal.whatsapp_seal_activation_status == ""
        assert fresh_without_seal.whatsapp_seal_category == ""
        assert fresh_without_seal.whatsapp_seal_plan == ""
        assert fresh_without_seal.whatsapp_seal_monthly_value is None

        fresh_deleted = PhoneLine.all_objects.get(pk=deleted_with_seal.pk)
        assert fresh_deleted.is_deleted is True
        assert fresh_deleted.whatsapp_seal_activation_status == "ACTIVE"
        assert fresh_deleted.whatsapp_seal_activated_on == date(2026, 2, 1)
        assert fresh_deleted.whatsapp_seal_expires_on == date(2026, 11, 1)
        assert fresh_deleted.whatsapp_seal_monthly_value is None

        fresh_inconsistent = PhoneLine.all_objects.get(pk=inconsistent.pk)
        assert fresh_inconsistent.whatsapp_seal_activation_status == "ACTIVE"
        assert fresh_inconsistent.whatsapp_seal_email == ""
        assert fresh_inconsistent.whatsapp_seal_payment == ""

        call_command("migrate", "telecom", "0021", verbosity=0)
        row = _raw_seal_row(with_seal.phone_number)
        assert row == (
            "META_ONE",
            date(2026, 1, 10),
            date(2026, 12, 10),
            "legado@example.com",
            "CREDIT_CARD",
        )

        deleted_row = _raw_seal_row(deleted_with_seal.phone_number)
        assert deleted_row == (
            "META_VERIFIED",
            date(2026, 2, 1),
            date(2026, 11, 1),
            "legado-deletado@example.com",
            "GOOGLE_GIFT_CARD",
        )
    finally:
        call_command("migrate", "telecom", verbosity=0)


@pytest.mark.django_db(transaction=True)
def test_migration_0022_is_reversible_sem_quebrar():
    call_command("migrate", "telecom", "0021", verbosity=0)
    call_command("migrate", "telecom", "0022", verbosity=0)
    call_command("migrate", "telecom", "0021", verbosity=0)
    call_command("migrate", "telecom", verbosity=0)
