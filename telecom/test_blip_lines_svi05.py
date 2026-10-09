"""SVI-05 — testes unitarios de telecom/blip_lines.py (resolucao BLIP).

Fonte da verdade: docs/superpowers/specs/2026-10-05-phone-line-seal-
indicator-design.md, borda aprovada #2 do fechamento SVI-02: associacao
exata, unica e autorizada. Estes testes cobrem a funcao pura/de banco em
isolamento (sem HTTP), complementando os testes end-to-end de I23/I24 em
telecom/test_seal_indicator_svi03.py.
"""

from datetime import date

import pytest
from django.utils import timezone

from telecom.blip_lines import (
    build_authorized_blip_line_index,
    get_authorized_blip_lines_queryset,
    resolve_blip_phone_line,
)
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser

PASSWORD = "StrongPass123"
FROZEN_TODAY = date(2026, 9, 17)


@pytest.fixture
def dev_user(db):
    return SystemUser.objects.create_user(
        email="svi05-blip-unit-dev@example.com", password=PASSWORD, role=SystemUser.Role.DEV
    )


def test_index_resolves_exact_authorized_line(dev_user, monkeypatch):
    monkeypatch.setattr(timezone, "localdate", lambda: FROZEN_TODAY)
    sim = SIMcard.objects.create(iccid="8900000000000091001", carrier="TIM")
    line = PhoneLine.objects.create(
        phone_number="+5511988887001",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        origem=PhoneLine.Origem.BLIP,
    )

    index = build_authorized_blip_line_index(dev_user)

    assert index[int(line.phone_number)] == line


def test_index_marks_colliding_numbers_as_none(dev_user):
    sim_a = SIMcard.objects.create(iccid="8900000000000091002", carrier="TIM")
    sim_b = SIMcard.objects.create(iccid="8900000000000091003", carrier="TIM")
    line_a = PhoneLine.objects.create(
        phone_number="+5511988887002",
        sim_card=sim_a,
        status=PhoneLine.Status.AVAILABLE,
        origem=PhoneLine.Origem.BLIP,
    )
    line_b = PhoneLine.objects.create(
        phone_number="05511988887002",
        sim_card=sim_b,
        status=PhoneLine.Status.AVAILABLE,
        origem=PhoneLine.Origem.BLIP,
    )
    assert int(line_a.phone_number) == int(line_b.phone_number)

    index = build_authorized_blip_line_index(dev_user)

    assert index[int(line_a.phone_number)] is None


def test_index_excludes_lines_outside_blip_origem(dev_user):
    sim = SIMcard.objects.create(iccid="8900000000000091004", carrier="TIM")
    line = PhoneLine.objects.create(
        phone_number="+5511988887004",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        origem=PhoneLine.Origem.SRVMEMU_01,
    )

    index = build_authorized_blip_line_index(dev_user)

    assert int(line.phone_number) not in index


def test_index_excludes_deleted_line_and_deleted_simcard(dev_user):
    sim_deleted = SIMcard.objects.create(
        iccid="8900000000000091005", carrier="TIM", is_deleted=True
    )
    line_with_deleted_sim = PhoneLine.all_objects.create(
        phone_number="+5511988887005",
        sim_card=sim_deleted,
        status=PhoneLine.Status.AVAILABLE,
        origem=PhoneLine.Origem.BLIP,
    )
    sim = SIMcard.objects.create(iccid="8900000000000091006", carrier="TIM")
    deleted_line = PhoneLine.all_objects.create(
        phone_number="+5511988887006",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        origem=PhoneLine.Origem.BLIP,
        is_deleted=True,
    )

    index = build_authorized_blip_line_index(dev_user)

    assert int(line_with_deleted_sim.phone_number) not in index
    assert int(deleted_line.phone_number) not in index


def test_resolve_blip_phone_line_returns_none_when_not_resolvable(dev_user):
    assert resolve_blip_phone_line(dev_user, 5511999999999) is None


def test_queryset_matches_form_candidate_rule(dev_user):
    """Mesma regra de candidatos usada por BlipConfigurationForm (telecom/
    forms.py) — fonte unica, sem segunda definicao divergente."""
    sim = SIMcard.objects.create(iccid="8900000000000091007", carrier="TIM")
    line = PhoneLine.objects.create(
        phone_number="+5511988887007",
        sim_card=sim,
        status=PhoneLine.Status.AVAILABLE,
        origem=PhoneLine.Origem.BLIP,
    )

    queryset = get_authorized_blip_lines_queryset(dev_user)

    assert line in queryset
