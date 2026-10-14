"""POR-03 — testes RED do bloqueio de abertura/reabertura de pendencia por
origem da linha no caminho de Acoes do Dia (dashboard.views.
daily_user_action_board, ramo criacao/atualizacao de DailyUserAction).

Fonte da verdade: docs/superpowers/specs/2026-10-13-pendency-origin-
restriction-design.md, secao "Fechamento das quatro decisoes — 2026-10-13".
Nenhum codigo de producao e alterado aqui — so testes.

Esta view nao tem contrato JSON: a recusa deve aparecer via
messages.error + redirect (mesmo padrao das recusas existentes
"Tipo de acao invalido.", "Usuario nao encontrado...",
"Backoffice sem supervisor...").
"""

import json

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from allocations.models import LineAllocation
from dashboard.models import DailyUserAction
from employees.models import Employee
from telecom.models import LineDailyActionAuditEvent, PhoneLine, SIMcard
from users.models import SystemUser

OPEN_BLOCKED_MESSAGE = (
    "Não é permitido abrir pendência para linhas com origem Aparelho "
    "Operação ou Aparelho pessoal. Fale com o supervisor ou backoffice"
)

CONTROL_ORIGINS = (PhoneLine.Origem.APARELHO, "SRVMEMU-01", None)

_suffix_counter = [0]


def _next_suffix():
    _suffix_counter[0] += 1
    return f"{_suffix_counter[0]:04d}"


def _make_user(email, role):
    return SystemUser.objects.create_user(
        email=email, password="StrongPass123", role=role
    )


class DailyUserActionOriginRestrictionBase(TestCase):
    def setUp(self):
        self.admin = _make_user("daily.origin.admin@test.com", SystemUser.Role.ADMIN)
        self.super_user = _make_user(
            "daily.origin.super@test.com", SystemUser.Role.SUPER
        )
        self.backoffice = _make_user(
            "daily.origin.backoffice@test.com", SystemUser.Role.BACKOFFICE
        )
        self.backoffice.supervisor_email = self.super_user.email
        self.backoffice.save(update_fields=["supervisor_email"])
        self.gerente = _make_user(
            "daily.origin.gerente@test.com", SystemUser.Role.GERENTE
        )
        self.employee = Employee.objects.create(
            full_name="Daily Origin Employee",
            corporate_email=self.super_user.email,
            employee_id=f"DAILY-ORIGIN-{_next_suffix()}",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )
        self.url = reverse("daily_user_action_board")

    def _make_allocation(self, origem=None, line_status=LineAllocation.LineStatus.ACTIVE):
        suffix = _next_suffix()
        sim = SIMcard.objects.create(
            iccid=f"8955001{suffix}0000000",
            carrier="DailyOriginCarrier",
            status=SIMcard.Status.AVAILABLE,
        )
        phone_line = PhoneLine.objects.create(
            phone_number=f"+554798{suffix}",
            sim_card=sim,
            status=PhoneLine.Status.ALLOCATED,
            origem=origem,
        )
        return LineAllocation.objects.create(
            employee=self.employee,
            phone_line=phone_line,
            allocated_by=self.admin,
            is_active=True,
            line_status=line_status,
        )

    def _post(self, user, allocation, action_type="", note="", line_status="", extra=None):
        self.client.force_login(user)
        data = {
            "day": timezone.localdate().isoformat(),
            "employee_id": self.employee.pk,
            "allocation_id": str(allocation.pk) if allocation else "",
            "action_type": action_type,
            "note": note,
            "line_status": line_status,
        }
        if extra:
            data.update(extra)
        return self.client.post(self.url, data=data)

    def _messages(self, response):
        return [m.message for m in get_messages(response.wsgi_request)]

    def _events_for_action(self, action):
        return LineDailyActionAuditEvent.objects.filter(
            source=LineDailyActionAuditEvent.Source.DAILY_USER_ACTION,
            source_object_id=action.pk,
        )


class CreationBlockedByOriginTests(DailyUserActionOriginRestrictionBase):
    """T4: criacao (sem DailyUserAction do dia) recusada para APARELHO OP
    e PESSOAL."""

    def test_creation_blocked_for_aparelho_op(self):
        allocation = self._make_allocation(origem=PhoneLine.Origem.APARELHO_OP)

        response = self._post(
            self.admin, allocation, action_type=DailyUserAction.ActionType.NEW_NUMBER
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(OPEN_BLOCKED_MESSAGE, self._messages(response))
        self.assertFalse(
            DailyUserAction.objects.filter(employee=self.employee).exists()
        )
        self.assertFalse(
            LineDailyActionAuditEvent.objects.filter(
                source=LineDailyActionAuditEvent.Source.DAILY_USER_ACTION,
                employee=self.employee,
            ).exists()
        )

    def test_creation_blocked_for_pessoal(self):
        allocation = self._make_allocation(origem=PhoneLine.Origem.PESSOAL)

        response = self._post(
            self.admin, allocation, action_type=DailyUserAction.ActionType.PENDING
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(OPEN_BLOCKED_MESSAGE, self._messages(response))
        self.assertFalse(
            DailyUserAction.objects.filter(employee=self.employee).exists()
        )


class ReopeningBlockedByOriginTests(DailyUserActionOriginRestrictionBase):
    """T5: DailyUserAction do dia ja resolvida (is_resolved=True); nova
    tentativa de reabertura e recusada quando a origem esta bloqueada."""

    def test_reopening_blocked_keeps_resolved_true(self):
        allocation = self._make_allocation(origem=PhoneLine.Origem.APARELHO_OP)
        existing = DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=self.employee,
            allocation=allocation,
            supervisor=self.super_user,
            action_type=DailyUserAction.ActionType.PENDING,
            note="resolvida anteriormente",
            updated_by=self.admin,
            created_by=self.admin,
            is_resolved=True,
        )
        marker = LineDailyActionAuditEvent.objects.order_by("-id").first()
        marker_id = marker.pk if marker else 0

        response = self._post(
            self.admin, allocation, action_type=DailyUserAction.ActionType.PENDING
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(OPEN_BLOCKED_MESSAGE, self._messages(response))
        existing.refresh_from_db()
        self.assertTrue(existing.is_resolved)
        self.assertFalse(
            LineDailyActionAuditEvent.objects.filter(pk__gt=marker_id).exists()
        )


class ControlOriginsPreservedTests(DailyUserActionOriginRestrictionBase):
    """T6: APARELHO, origem custom e vazia continuam criando normalmente."""

    def test_creation_allowed_for_each_control_origin(self):
        for origem in CONTROL_ORIGINS:
            with self.subTest(origem=origem):
                allocation = self._make_allocation(origem=origem)

                response = self._post(
                    self.admin,
                    allocation,
                    action_type=DailyUserAction.ActionType.PENDING,
                )

                self.assertEqual(response.status_code, 302)
                self.assertTrue(
                    DailyUserAction.objects.filter(
                        employee=self.employee, allocation=allocation
                    ).exists()
                )


class CreationWithoutAllocationPreservedTests(DailyUserActionOriginRestrictionBase):
    """T7: acao em nivel de funcionario (sem allocation_id) nao tem
    origem a checar; continua criando normalmente."""

    def test_creation_allowed_without_allocation(self):
        response = self._post(
            self.admin, None, action_type=DailyUserAction.ActionType.PENDING
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            DailyUserAction.objects.filter(
                employee=self.employee, allocation=None
            ).exists()
        )


class AllRolesBlockedIdenticallyTests(DailyUserActionOriginRestrictionBase):
    """T9: ADMIN/SUPER/BACKOFFICE/GERENTE recebem o mesmo tratamento ao
    tentar abrir numa origem bloqueada — sem exceçao nova por role."""

    def test_each_allowed_role_is_blocked_the_same_way(self):
        for role_user in (
            self.admin,
            self.super_user,
            self.backoffice,
            self.gerente,
        ):
            with self.subTest(role=role_user.role):
                allocation = self._make_allocation(origem=PhoneLine.Origem.PESSOAL)

                response = self._post(
                    role_user,
                    allocation,
                    action_type=DailyUserAction.ActionType.NEW_NUMBER,
                )

                self.assertEqual(response.status_code, 302)
                self.assertIn(OPEN_BLOCKED_MESSAGE, self._messages(response))
                self.assertFalse(
                    DailyUserAction.objects.filter(allocation=allocation).exists()
                )


class ForgedOriginInPayloadTests(DailyUserActionOriginRestrictionBase):
    """Variacao de T4/T11: o form nao expoe campo de origem, mas um POST
    direto pode tentar enviar um campo extra 'origem'. A view nunca le
    origem do corpo — so de allocation_obj.phone_line.origem."""

    def test_extra_origin_field_in_post_is_ignored(self):
        allocation = self._make_allocation(origem=PhoneLine.Origem.APARELHO_OP)

        response = self._post(
            self.admin,
            allocation,
            action_type=DailyUserAction.ActionType.PENDING,
            extra={"origem": PhoneLine.Origem.APARELHO},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(OPEN_BLOCKED_MESSAGE, self._messages(response))
        self.assertFalse(
            DailyUserAction.objects.filter(allocation=allocation).exists()
        )


class CompositePayloadNoPartialEffectsTests(DailyUserActionOriginRestrictionBase):
    """Fechamento 2026-10-13, retificacao: o contrato original de ausencia
    de efeitos parciais no mesmo pedido PREVALECE. Hoje o ramo de
    line_status (so ADMIN) roda ANTES e de forma independente do ramo de
    abertura, entao persiste mesmo quando a abertura e recusada — isso
    contraria o contrato e deve ser corrigido em POR-04. Usa ADMIN
    (unico role autorizado a mudar line_status nesta view) para nao gerar
    falso GREEN por falta de autorizacao sobre o efeito colateral."""

    def test_refused_opening_does_not_persist_line_status_change(self):
        allocation = self._make_allocation(
            origem=PhoneLine.Origem.APARELHO_OP,
            line_status=LineAllocation.LineStatus.ACTIVE,
        )

        response = self._post(
            self.admin,
            allocation,
            action_type=DailyUserAction.ActionType.NEW_NUMBER,
            line_status=LineAllocation.LineStatus.RESTRICTED,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(OPEN_BLOCKED_MESSAGE, self._messages(response))
        allocation.refresh_from_db()
        self.assertEqual(
            allocation.line_status, LineAllocation.LineStatus.ACTIVE
        )
        self.assertFalse(
            DailyUserAction.objects.filter(allocation=allocation).exists()
        )
        self.assertFalse(
            LineDailyActionAuditEvent.objects.filter(
                source=LineDailyActionAuditEvent.Source.LINE_ALLOCATION,
                allocation=allocation,
            ).exists()
        )


class ExistingOpenActionTreatmentPreservedTests(DailyUserActionOriginRestrictionBase):
    """Controle: alteracao de uma acao JA aberta no mesmo dia
    (previous_is_resolved=False) e resolucao (action_type vazio) nao sao
    bloqueadas por origem — so abertura/reabertura o sao."""

    def test_changing_already_open_action_is_not_blocked(self):
        allocation = self._make_allocation(origem=PhoneLine.Origem.APARELHO_OP)
        existing = DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=self.employee,
            allocation=allocation,
            supervisor=self.super_user,
            action_type=DailyUserAction.ActionType.PENDING,
            note="nota original",
            updated_by=self.admin,
            created_by=self.admin,
            is_resolved=False,
        )

        response = self._post(
            self.admin,
            allocation,
            action_type=DailyUserAction.ActionType.RECONNECT_WHATSAPP,
            note="nota atualizada",
        )

        self.assertEqual(response.status_code, 302)
        self.assertNotIn(OPEN_BLOCKED_MESSAGE, self._messages(response))
        existing.refresh_from_db()
        self.assertEqual(
            existing.action_type, DailyUserAction.ActionType.RECONNECT_WHATSAPP
        )
        self.assertEqual(existing.note, "nota atualizada")

    def test_resolving_open_action_is_not_blocked(self):
        allocation = self._make_allocation(origem=PhoneLine.Origem.PESSOAL)
        existing = DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=self.employee,
            allocation=allocation,
            supervisor=self.super_user,
            action_type=DailyUserAction.ActionType.PENDING,
            note="",
            updated_by=self.admin,
            created_by=self.admin,
            is_resolved=False,
        )

        response = self._post(self.admin, allocation, action_type="")

        self.assertEqual(response.status_code, 302)
        self.assertNotIn(OPEN_BLOCKED_MESSAGE, self._messages(response))
        existing.refresh_from_db()
        self.assertTrue(existing.is_resolved)
