"""POR-03 — testes RED do bloqueio de abertura/reabertura de pendencia por
origem da linha (PendencyUpdateView, PendencyDetailView e Django Admin).

Fonte da verdade: docs/superpowers/specs/2026-10-13-pendency-origin-
restriction-design.md, secao "Fechamento das quatro decisoes — 2026-10-13"
(prevalece sobre o historico de POR-02). Nenhum codigo de producao e
alterado aqui — so testes. Node IDs e resultado real: ver atualizacao da
spec apos a execucao desta suite.

Origens bloqueadas (duas, nao tres): PhoneLine.Origem.APARELHO_OP
("APARELHO OP") e PhoneLine.Origem.PESSOAL ("PESSOAL"). APARELHO e as
demais origens, inclusive vazia/None, preservam o comportamento anterior.

Mensagem exata aprovada (contrato, linha 14 da spec):
"Nao e permitido abrir pendencia para linhas com origem Aparelho Operacao
ou Aparelho pessoal. Fale com o supervisor ou backoffice"
"""

import json

from django.test import TestCase
from django.urls import reverse

from allocations.models import LineAllocation
from employees.models import Employee
from pendencies.models import AllocationPendency, PendencyObservationNotification
from telecom.models import LineDailyActionAuditEvent, PhoneLine, SIMcard
from users.models import SystemUser

OPEN_BLOCKED_MESSAGE = (
    "Não é permitido abrir pendência para linhas com origem Aparelho "
    "Operação ou Aparelho pessoal. Fale com o supervisor ou backoffice"
)

BLOCKED_ORIGINS = (PhoneLine.Origem.APARELHO_OP, PhoneLine.Origem.PESSOAL)
CONTROL_ORIGINS = (PhoneLine.Origem.APARELHO, "SRVMEMU-01", None)

_suffix_counter = [0]


def _next_suffix():
    _suffix_counter[0] += 1
    return f"{_suffix_counter[0]:04d}"


def _make_user(email, role):
    return SystemUser.objects.create_user(
        email=email, password="StrongPass123", role=role
    )


def _make_employee(corporate_email, full_name="Origin Restriction Employee"):
    suffix = _next_suffix()
    return Employee.objects.create(
        full_name=full_name,
        corporate_email=corporate_email,
        employee_id=f"ORIGIN-{suffix}",
        teams=Employee.UnitChoices.JOINVILLE,
        status=Employee.Status.ACTIVE,
    )


def _make_allocation(employee, admin, origem=None, line_status=LineAllocation.LineStatus.ACTIVE):
    suffix = _next_suffix()
    sim = SIMcard.objects.create(
        iccid=f"8955000{suffix}0000000",
        carrier="OriginRestrictionCarrier",
        status=SIMcard.Status.AVAILABLE,
    )
    phone_line = PhoneLine.objects.create(
        phone_number=f"+554799{suffix}",
        sim_card=sim,
        status=PhoneLine.Status.ALLOCATED,
        origem=origem,
    )
    return LineAllocation.objects.create(
        employee=employee,
        phone_line=phone_line,
        allocated_by=admin,
        is_active=True,
        line_status=line_status,
    )


class PendencyOriginRestrictionBase(TestCase):
    """Fixtures compartilhadas: admin, super (dono do escopo do employee),
    backoffice, gerente, operator e um employee no escopo do super."""

    def setUp(self):
        self.admin = _make_user("origin.admin@test.com", SystemUser.Role.ADMIN)
        self.super_user = _make_user("origin.super@test.com", SystemUser.Role.SUPER)
        self.backoffice = _make_user(
            "origin.backoffice@test.com", SystemUser.Role.BACKOFFICE
        )
        self.backoffice.supervisor_email = self.super_user.email
        self.backoffice.save(update_fields=["supervisor_email"])
        self.gerente = _make_user("origin.gerente@test.com", SystemUser.Role.GERENTE)
        self.operator = _make_user("origin.operator@test.com", SystemUser.Role.OPERATOR)
        self.employee = _make_employee(self.super_user.email)
        self.update_url = reverse("pendencies:update")
        self.detail_url = reverse("pendencies:detail")
        self.claim_url = reverse("pendencies:claim")
        self.release_url = reverse("pendencies:release")

    def _allocation(self, origem=None, line_status=LineAllocation.LineStatus.ACTIVE):
        return _make_allocation(self.employee, self.admin, origem=origem, line_status=line_status)

    def _pendency_audit_count(self, pendency):
        return LineDailyActionAuditEvent.objects.filter(
            source=LineDailyActionAuditEvent.Source.ALLOCATION_PENDENCY,
            source_object_id=pendency.pk,
        ).count()

    def _post_update(self, user, pendency, action="", observation="", line_status="", extra=None):
        self.client.force_login(user)
        body = {
            "pendency_id": pendency.pk,
            "action": action,
            "observation": observation,
            "line_status": line_status,
        }
        if extra:
            body.update(extra)
        return self.client.post(
            self.update_url,
            data=json.dumps(body),
            content_type="application/json",
        )


class OpeningBlockedByOriginTests(PendencyOriginRestrictionBase):
    """T1, T2: abertura via PendencyUpdateView recusada para APARELHO OP e
    PESSOAL, por role autorizado a abrir (super)."""

    def test_opening_blocked_for_aparelho_op(self):
        allocation = self._allocation(origem=PhoneLine.Origem.APARELHO_OP)
        pendency = AllocationPendency.objects.create(employee=self.employee, allocation=allocation)
        before_count = self._pendency_audit_count(pendency)

        response = self._post_update(
            self.super_user, pendency, action=AllocationPendency.ActionType.PENDING
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["errors"], [OPEN_BLOCKED_MESSAGE])
        pendency.refresh_from_db()
        self.assertEqual(pendency.action, AllocationPendency.ActionType.NO_ACTION)
        self.assertEqual(self._pendency_audit_count(pendency), before_count)

    def test_opening_blocked_for_pessoal(self):
        allocation = self._allocation(origem=PhoneLine.Origem.PESSOAL)
        pendency = AllocationPendency.objects.create(employee=self.employee, allocation=allocation)
        before_count = self._pendency_audit_count(pendency)

        response = self._post_update(
            self.super_user, pendency, action=AllocationPendency.ActionType.NEW_NUMBER
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["errors"], [OPEN_BLOCKED_MESSAGE])
        pendency.refresh_from_db()
        self.assertEqual(pendency.action, AllocationPendency.ActionType.NO_ACTION)
        self.assertEqual(self._pendency_audit_count(pendency), before_count)


class ReopeningBlockedByOriginTests(PendencyOriginRestrictionBase):
    """T3: reabertura (resolved_at preenchido) tambem recusada para as
    mesmas origens."""

    def _resolved_pendency(self, origem):
        allocation = self._allocation(origem=origem)
        return AllocationPendency.objects.create(
            employee=self.employee,
            allocation=allocation,
            action=AllocationPendency.ActionType.NO_ACTION,
            last_submitted_action=AllocationPendency.ActionType.PENDING,
            resolved_at=self.admin.date_joined,
        )

    def test_reopening_blocked_for_aparelho_op(self):
        pendency = self._resolved_pendency(PhoneLine.Origem.APARELHO_OP)
        resolved_at_before = pendency.resolved_at

        response = self._post_update(
            self.super_user, pendency, action=AllocationPendency.ActionType.PENDING
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["errors"], [OPEN_BLOCKED_MESSAGE])
        pendency.refresh_from_db()
        self.assertEqual(pendency.action, AllocationPendency.ActionType.NO_ACTION)
        self.assertEqual(pendency.resolved_at, resolved_at_before)

    def test_reopening_blocked_for_pessoal(self):
        pendency = self._resolved_pendency(PhoneLine.Origem.PESSOAL)
        resolved_at_before = pendency.resolved_at

        response = self._post_update(
            self.super_user, pendency, action=AllocationPendency.ActionType.RECONNECT_WHATSAPP
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["errors"], [OPEN_BLOCKED_MESSAGE])
        pendency.refresh_from_db()
        self.assertEqual(pendency.action, AllocationPendency.ActionType.NO_ACTION)
        self.assertEqual(pendency.resolved_at, resolved_at_before)


class OpeningControlOriginsPreservedTests(PendencyOriginRestrictionBase):
    """T6: APARELHO, origem custom e origem vazia continuam abrindo
    normalmente (controle positivo contra falso GREEN por quebra geral)."""

    def test_opening_allowed_for_each_control_origin(self):
        for origem in CONTROL_ORIGINS:
            with self.subTest(origem=origem):
                allocation = self._allocation(origem=origem)
                pendency = AllocationPendency.objects.create(
                    employee=self.employee, allocation=allocation
                )

                response = self._post_update(
                    self.super_user, pendency, action=AllocationPendency.ActionType.PENDING
                )

                self.assertEqual(response.status_code, 200)
                pendency.refresh_from_db()
                self.assertEqual(pendency.action, AllocationPendency.ActionType.PENDING)
                event = LineDailyActionAuditEvent.objects.get(
                    source=LineDailyActionAuditEvent.Source.ALLOCATION_PENDENCY,
                    source_object_id=pendency.pk,
                )
                self.assertEqual(
                    event.event_type, LineDailyActionAuditEvent.EventType.OPENED
                )


class OpeningWithoutAllocationPreservedTests(PendencyOriginRestrictionBase):
    """T7: pendencia sem allocation (employee sem linha) nao tem origem a
    checar; abre normalmente mesmo apos a politica existir."""

    def test_opening_allowed_without_allocation(self):
        pendency = AllocationPendency.objects.create(employee=self.employee, allocation=None)

        response = self._post_update(
            self.super_user, pendency, action=AllocationPendency.ActionType.PENDING
        )

        self.assertEqual(response.status_code, 200)
        pendency.refresh_from_db()
        self.assertEqual(pendency.action, AllocationPendency.ActionType.PENDING)


class AdminNoNewExceptionTests(PendencyOriginRestrictionBase):
    """T8: ADMIN tentando abrir via PendencyUpdateView recebe a mensagem de
    PERMISSAO pre-existente, nunca a mensagem de origem — tanto para origem
    bloqueada quanto para origem permitida, porque ADMIN nunca chega a
    avaliar a origem (gate de role vem primeiro)."""

    PRE_EXISTING_PERMISSION_MESSAGE = (
        "Somente super/backoffice/gerente pode abrir uma pendência."
    )

    def test_admin_blocked_by_permission_regardless_of_origin(self):
        for origem in (PhoneLine.Origem.APARELHO_OP, PhoneLine.Origem.PESSOAL, None):
            with self.subTest(origem=origem):
                allocation = self._allocation(origem=origem)
                pendency = AllocationPendency.objects.create(
                    employee=self.employee, allocation=allocation
                )

                response = self._post_update(
                    self.admin, pendency, action=AllocationPendency.ActionType.PENDING
                )

                self.assertEqual(response.status_code, 403)
                self.assertEqual(
                    response.json()["errors"], [self.PRE_EXISTING_PERMISSION_MESSAGE]
                )
                self.assertNotEqual(
                    response.json()["errors"], [OPEN_BLOCKED_MESSAGE]
                )


class ForgedOriginInPayloadTests(PendencyOriginRestrictionBase):
    """T11: cliente tenta mascarar a origem enviando um campo extra no
    corpo do POST. A view nunca le origem do corpo — so de
    pendency.allocation.phone_line.origem persistido."""

    def test_extra_origin_field_in_body_is_ignored(self):
        allocation = self._allocation(origem=PhoneLine.Origem.PESSOAL)
        pendency = AllocationPendency.objects.create(employee=self.employee, allocation=allocation)

        response = self._post_update(
            self.super_user,
            pendency,
            action=AllocationPendency.ActionType.PENDING,
            extra={"origem": PhoneLine.Origem.APARELHO},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["errors"], [OPEN_BLOCKED_MESSAGE])
        pendency.refresh_from_db()
        self.assertEqual(pendency.action, AllocationPendency.ActionType.NO_ACTION)


class OriginChangedBetweenRenderAndPostTests(PendencyOriginRestrictionBase):
    """T17: origem permitida no GET; origem alterada para bloqueada antes
    do POST. Decisao usa a origem persistida no momento do POST."""

    def test_post_uses_origin_at_evaluation_time_not_at_render_time(self):
        allocation = self._allocation(origem=PhoneLine.Origem.APARELHO)
        pendency = AllocationPendency.objects.create(employee=self.employee, allocation=allocation)

        self.client.force_login(self.super_user)
        get_response = self.client.get(
            self.detail_url,
            {"employee_id": self.employee.pk, "allocation_id": allocation.pk},
        )
        self.assertEqual(get_response.status_code, 200)

        allocation.phone_line.origem = PhoneLine.Origem.PESSOAL
        allocation.phone_line.save(update_fields=["origem"])

        response = self._post_update(
            self.super_user, pendency, action=AllocationPendency.ActionType.PENDING
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["errors"], [OPEN_BLOCKED_MESSAGE])
        pendency.refresh_from_db()
        self.assertEqual(pendency.action, AllocationPendency.ActionType.NO_ACTION)


class EmptyRecordIsNotOpeningTests(PendencyOriginRestrictionBase):
    """T16: GET em PendencyDetailView cria registro NO_ACTION (get_or_
    create) quando nao existe. Isso NAO e abertura: sem evento de
    auditoria, sem mensagem de bloqueio, mesmo com origem bloqueada."""

    def test_get_detail_creates_empty_record_without_opening(self):
        allocation = self._allocation(origem=PhoneLine.Origem.APARELHO_OP)
        self.assertFalse(
            AllocationPendency.objects.filter(allocation=allocation).exists()
        )

        self.client.force_login(self.admin)
        response = self.client.get(
            self.detail_url,
            {"employee_id": self.employee.pk, "allocation_id": allocation.pk},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertNotIn("errors", payload)
        pendency = AllocationPendency.objects.get(allocation=allocation)
        self.assertEqual(pendency.action, AllocationPendency.ActionType.NO_ACTION)
        self.assertEqual(self._pendency_audit_count(pendency), 0)


class OutOfScopeUserDoesNotLeakOriginTests(PendencyOriginRestrictionBase):
    """T14: usuario de outro escopo recebe 403 de autorizacao/escopo
    pre-existente, sem chegar na checagem de origem e sem revelar a
    mensagem de bloqueio por origem."""

    def test_out_of_scope_super_is_denied_before_origin_check(self):
        other_super = _make_user("origin.other.super@test.com", SystemUser.Role.SUPER)
        allocation = self._allocation(origem=PhoneLine.Origem.PESSOAL)
        pendency = AllocationPendency.objects.create(employee=self.employee, allocation=allocation)

        response = self._post_update(
            other_super, pendency, action=AllocationPendency.ActionType.PENDING
        )

        self.assertEqual(response.status_code, 403)
        content = response.content.decode()
        self.assertNotIn(OPEN_BLOCKED_MESSAGE, content)
        self.assertNotIn("origin_open_blocked", content)
        pendency.refresh_from_db()
        self.assertEqual(pendency.action, AllocationPendency.ActionType.NO_ACTION)


class RoleAccessControlPrecedesOriginCheckTests(PendencyOriginRestrictionBase):
    """T10: controle de acesso por role (RoleRequiredMixin) continua
    negando OPERATOR antes de qualquer avaliacao de origem. Comportamento
    pre-existente — reaproveitado como controle para esta feature, nao
    duplicado em outro arquivo."""

    def test_operator_denied_access_regardless_of_origin(self):
        allocation = self._allocation(origem=PhoneLine.Origem.PESSOAL)
        pendency = AllocationPendency.objects.create(employee=self.employee, allocation=allocation)

        response = self._post_update(
            self.operator, pendency, action=AllocationPendency.ActionType.PENDING
        )

        self.assertEqual(response.status_code, 403)
        pendency.refresh_from_db()
        self.assertEqual(pendency.action, AllocationPendency.ActionType.NO_ACTION)


class CompositePayloadNoPartialEffectsTests(PendencyOriginRestrictionBase):
    """T13: abertura recusada (origem bloqueada) com observation no mesmo
    POST nao persiste observation nem dispara notificacao. Usa SUPER, que
    e autorizado a alterar observation numa pendencia NO_ACTION — evita
    falso GREEN por falta de autorizacao para o efeito colateral."""

    def test_refused_opening_does_not_persist_observation_or_notify(self):
        allocation = self._allocation(origem=PhoneLine.Origem.APARELHO_OP)
        pendency = AllocationPendency.objects.create(employee=self.employee, allocation=allocation)
        before_count = self._pendency_audit_count(pendency)

        response = self._post_update(
            self.super_user,
            pendency,
            action=AllocationPendency.ActionType.PENDING,
            observation="observacao enviada junto com abertura recusada",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["errors"], [OPEN_BLOCKED_MESSAGE])
        pendency.refresh_from_db()
        self.assertEqual(pendency.action, AllocationPendency.ActionType.NO_ACTION)
        self.assertEqual(pendency.observation, "")
        self.assertEqual(PendencyObservationNotification.objects.count(), 0)
        self.assertEqual(self._pendency_audit_count(pendency), before_count)


class OpenPendencyTreatmentPreservedTests(PendencyOriginRestrictionBase):
    """T12: pendencia JA aberta numa linha com origem agora bloqueada
    continua permitindo claim, observacao, release e resolucao — a
    restricao e so sobre abrir/reabrir, nunca sobre tratar o que ja esta
    aberto."""

    def setUp(self):
        super().setUp()
        self.allocation = self._allocation(origem=PhoneLine.Origem.APARELHO_OP)
        self.open_pendency = AllocationPendency.objects.create(
            employee=self.employee,
            allocation=self.allocation,
            action=AllocationPendency.ActionType.PENDING,
        )

    def test_admin_can_claim_already_open_pendency_on_blocked_origin(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            self.claim_url,
            data=json.dumps({"pendency_id": self.open_pendency.pk}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.open_pendency.refresh_from_db()
        self.assertEqual(self.open_pendency.technical_responsible, self.admin)

    def test_responsible_admin_can_change_observation_on_blocked_origin(self):
        self.client.force_login(self.admin)
        self.client.post(
            self.claim_url,
            data=json.dumps({"pendency_id": self.open_pendency.pk}),
            content_type="application/json",
        )

        response = self._post_update(
            self.admin,
            self.open_pendency,
            action=self.open_pendency.action,
            observation="observacao de tratamento legitimo",
        )

        self.assertEqual(response.status_code, 200)
        self.open_pendency.refresh_from_db()
        self.assertEqual(
            self.open_pendency.observation, "observacao de tratamento legitimo"
        )

    def test_admin_can_release_already_open_pendency_on_blocked_origin(self):
        self.open_pendency.technical_responsible = self.admin
        self.open_pendency.save(update_fields=["technical_responsible"])

        self.client.force_login(self.admin)
        response = self.client.post(
            self.release_url,
            data=json.dumps({"pendency_id": self.open_pendency.pk}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.open_pendency.refresh_from_db()
        self.assertIsNone(self.open_pendency.technical_responsible)

    def test_responsible_admin_can_resolve_already_open_pendency_on_blocked_origin(self):
        self.open_pendency.technical_responsible = self.admin
        self.open_pendency.save(update_fields=["technical_responsible"])

        response = self._post_update(
            self.admin,
            self.open_pendency,
            action=AllocationPendency.ActionType.NO_ACTION,
        )

        self.assertEqual(response.status_code, 200)
        self.open_pendency.refresh_from_db()
        self.assertEqual(
            self.open_pendency.action, AllocationPendency.ActionType.NO_ACTION
        )
        self.assertIsNotNone(self.open_pendency.resolved_at)


class AdminChangeFormOpeningRestrictionTests(PendencyOriginRestrictionBase):
    """Decisao 1A (Fechamento 2026-10-13): o Django Admin NAO e exceçao a
    regra de origem. Abertura/reabertura direta pelo Admin
    (AllocationPendencyAdmin, campo `action` editavel) deve ser recusada
    com a mensagem aprovada como erro de formulario — sem tornar `action`
    globalmente readonly, sem remover o campo."""

    def setUp(self):
        super().setUp()
        self.superuser = SystemUser.objects.create_superuser(
            email="origin.admin.root@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.client.force_login(self.superuser)

    def _admin_change_url(self, pendency):
        return reverse("admin:pendencies_allocationpendency_change", args=[pendency.pk])

    def _admin_post(self, pendency, new_action, observation=None, allocation_id=None):
        data = {
            "employee": pendency.employee_id,
            "allocation": (
                pendency.allocation_id or ""
                if allocation_id is None
                else (allocation_id or "")
            ),
            "action": new_action,
            "observation": (
                observation if observation is not None else pendency.observation
            ),
            "technical_responsible": pendency.technical_responsible_id or "",
            "last_submitted_action": pendency.last_submitted_action or "",
            "updated_by": "",
            "_save": "Salvar",
        }
        return self.client.post(self._admin_change_url(pendency), data=data)

    def test_admin_change_form_blocks_opening_for_aparelho_op(self):
        allocation = self._allocation(origem=PhoneLine.Origem.APARELHO_OP)
        pendency = AllocationPendency.objects.create(employee=self.employee, allocation=allocation)

        response = self._admin_post(pendency, AllocationPendency.ActionType.PENDING)

        self.assertEqual(response.status_code, 200)
        self.assertIn(OPEN_BLOCKED_MESSAGE, response.content.decode())
        pendency.refresh_from_db()
        self.assertEqual(pendency.action, AllocationPendency.ActionType.NO_ACTION)

    def test_admin_change_form_blocks_opening_for_pessoal(self):
        allocation = self._allocation(origem=PhoneLine.Origem.PESSOAL)
        pendency = AllocationPendency.objects.create(employee=self.employee, allocation=allocation)

        response = self._admin_post(pendency, AllocationPendency.ActionType.NEW_NUMBER)

        self.assertEqual(response.status_code, 200)
        self.assertIn(OPEN_BLOCKED_MESSAGE, response.content.decode())
        pendency.refresh_from_db()
        self.assertEqual(pendency.action, AllocationPendency.ActionType.NO_ACTION)

    def test_admin_change_form_blocks_reopening_for_blocked_origin(self):
        allocation = self._allocation(origem=PhoneLine.Origem.PESSOAL)
        pendency = AllocationPendency.objects.create(
            employee=self.employee,
            allocation=allocation,
            action=AllocationPendency.ActionType.NO_ACTION,
            last_submitted_action=AllocationPendency.ActionType.PENDING,
            resolved_at=self.admin.date_joined,
        )
        resolved_at_before = pendency.resolved_at

        response = self._admin_post(pendency, AllocationPendency.ActionType.PENDING)

        self.assertEqual(response.status_code, 200)
        self.assertIn(OPEN_BLOCKED_MESSAGE, response.content.decode())
        pendency.refresh_from_db()
        self.assertEqual(pendency.action, AllocationPendency.ActionType.NO_ACTION)
        self.assertEqual(pendency.resolved_at, resolved_at_before)

    def test_admin_change_form_allows_opening_for_permitted_origin(self):
        """Controle: origem permitida continua funcionando pelo Admin,
        sem mudanca de comportamento."""
        allocation = self._allocation(origem=PhoneLine.Origem.APARELHO)
        pendency = AllocationPendency.objects.create(employee=self.employee, allocation=allocation)

        response = self._admin_post(pendency, AllocationPendency.ActionType.PENDING)

        self.assertEqual(response.status_code, 302)
        pendency.refresh_from_db()
        self.assertEqual(pendency.action, AllocationPendency.ActionType.PENDING)

    def test_admin_change_form_allows_resolution_on_blocked_origin(self):
        """Controle: resolucao (acao -> NO_ACTION) nao e abertura; deve
        continuar funcionando mesmo numa linha com origem bloqueada."""
        allocation = self._allocation(origem=PhoneLine.Origem.APARELHO_OP)
        pendency = AllocationPendency.objects.create(
            employee=self.employee,
            allocation=allocation,
            action=AllocationPendency.ActionType.PENDING,
        )

        response = self._admin_post(pendency, AllocationPendency.ActionType.NO_ACTION)

        self.assertEqual(response.status_code, 302)
        pendency.refresh_from_db()
        self.assertEqual(pendency.action, AllocationPendency.ActionType.NO_ACTION)

    def test_admin_change_form_allows_opening_without_allocation(self):
        """Controle: pendencia sem allocation (funcionario sem linha) nao
        tem origem a checar; abre normalmente pelo Admin."""
        pendency = AllocationPendency.objects.create(employee=self.employee, allocation=None)

        response = self._admin_post(pendency, AllocationPendency.ActionType.PENDING)

        self.assertEqual(response.status_code, 302)
        pendency.refresh_from_db()
        self.assertEqual(pendency.action, AllocationPendency.ActionType.PENDING)

    def test_admin_change_form_blocks_opening_when_allocation_swapped_to_blocked_origin(self):
        """A decisao deve usar a alocacao PROPOSTA no mesmo POST, nao a
        alocacao antiga de self.instance: abrir trocando simultaneamente
        para uma linha de origem bloqueada deve ser recusado."""
        old_allocation = self._allocation(origem=PhoneLine.Origem.APARELHO)
        new_allocation = self._allocation(origem=PhoneLine.Origem.PESSOAL)
        pendency = AllocationPendency.objects.create(
            employee=self.employee, allocation=old_allocation
        )

        response = self._admin_post(
            pendency,
            AllocationPendency.ActionType.PENDING,
            allocation_id=new_allocation.pk,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(OPEN_BLOCKED_MESSAGE, response.content.decode())
        pendency.refresh_from_db()
        self.assertEqual(pendency.action, AllocationPendency.ActionType.NO_ACTION)
        self.assertEqual(pendency.allocation_id, old_allocation.pk)

    def test_admin_change_form_allows_opening_when_allocation_swapped_to_permitted_origin(self):
        """Simetrico ao teste acima: a alocacao antiga tinha origem
        bloqueada, mas a alocacao PROPOSTA no mesmo POST tem origem
        permitida — a abertura deve usar a origem proposta, nao a antiga,
        e ser permitida."""
        old_allocation = self._allocation(origem=PhoneLine.Origem.PESSOAL)
        new_allocation = self._allocation(origem=PhoneLine.Origem.APARELHO)
        pendency = AllocationPendency.objects.create(
            employee=self.employee, allocation=old_allocation
        )

        response = self._admin_post(
            pendency,
            AllocationPendency.ActionType.PENDING,
            allocation_id=new_allocation.pk,
        )

        self.assertEqual(response.status_code, 302)
        pendency.refresh_from_db()
        self.assertEqual(pendency.action, AllocationPendency.ActionType.PENDING)
        self.assertEqual(pendency.allocation_id, new_allocation.pk)

    def test_admin_change_form_allocation_swap_on_already_open_pendency_not_blocked(self):
        """Trocar a allocation de uma pendencia JA aberta nao e uma
        transicao de abertura (was_no_action e False) — nao deve ser
        reclassificada como abertura nem bloqueada por origem, mesmo que
        a nova linha tenha origem bloqueada."""
        old_allocation = self._allocation(origem=PhoneLine.Origem.APARELHO)
        new_allocation = self._allocation(origem=PhoneLine.Origem.PESSOAL)
        pendency = AllocationPendency.objects.create(
            employee=self.employee,
            allocation=old_allocation,
            action=AllocationPendency.ActionType.PENDING,
        )

        response = self._admin_post(
            pendency,
            AllocationPendency.ActionType.PENDING,
            allocation_id=new_allocation.pk,
        )

        self.assertEqual(response.status_code, 302)
        pendency.refresh_from_db()
        self.assertEqual(pendency.action, AllocationPendency.ActionType.PENDING)
        self.assertEqual(pendency.allocation_id, new_allocation.pk)

    def test_admin_add_form_blocks_creation_with_open_action_on_blocked_origin(self):
        """Criacao direta (sem instancia previa) com acao ja aberta deve
        usar a origem da allocation escolhida NA CRIACAO — nao pode
        ignorar a checagem so porque self.instance.pk ainda e None."""
        blocked_allocation = self._allocation(origem=PhoneLine.Origem.APARELHO_OP)
        new_employee = _make_employee(
            self.super_user.email, full_name="Admin Create Employee"
        )

        response = self.client.post(
            reverse("admin:pendencies_allocationpendency_add"),
            data={
                "employee": new_employee.pk,
                "allocation": blocked_allocation.pk,
                "action": AllocationPendency.ActionType.PENDING,
                "observation": "",
                "technical_responsible": "",
                "last_submitted_action": "",
                "updated_by": "",
                "_save": "Salvar",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(OPEN_BLOCKED_MESSAGE, response.content.decode())
        self.assertFalse(
            AllocationPendency.objects.filter(allocation=blocked_allocation).exists()
        )


class OriginBlockedPayloadFlagTests(PendencyOriginRestrictionBase):
    """Decisao 2A (Fechamento 2026-10-13) + contrato técnico fixado na
    conferência corretiva de POR-03: `_pendency_to_json` deve expor
    `origin_open_blocked` (bool) e `origin_open_blocked_reason` (str),
    calculados pelo backend a partir da origem persistida da linha —
    nunca do payload do cliente, nunca da permissao do usuario atual.

    Estes campos nao existem ainda em `_pendency_to_json`; todo teste
    abaixo que afirma presenca/valor correto da flag e RED ate POR-04."""

    def test_detail_payload_flags_blocked_origin_with_exact_reason(self):
        for origem in BLOCKED_ORIGINS:
            with self.subTest(origem=origem):
                allocation = self._allocation(origem=origem)
                AllocationPendency.objects.create(
                    employee=self.employee, allocation=allocation
                )

                self.client.force_login(self.super_user)
                response = self.client.get(
                    self.detail_url,
                    {"employee_id": self.employee.pk, "allocation_id": allocation.pk},
                )

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertIn("origin_open_blocked", payload)
                self.assertTrue(payload["origin_open_blocked"])
                self.assertEqual(
                    payload["origin_open_blocked_reason"], OPEN_BLOCKED_MESSAGE
                )

    def test_detail_payload_flags_permitted_origin_as_false(self):
        for origem in CONTROL_ORIGINS:
            with self.subTest(origem=origem):
                allocation = self._allocation(origem=origem)
                AllocationPendency.objects.create(
                    employee=self.employee, allocation=allocation
                )

                self.client.force_login(self.super_user)
                response = self.client.get(
                    self.detail_url,
                    {"employee_id": self.employee.pk, "allocation_id": allocation.pk},
                )

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertIn("origin_open_blocked", payload)
                self.assertFalse(payload["origin_open_blocked"])
                self.assertEqual(payload["origin_open_blocked_reason"], "")

    def test_detail_payload_flag_is_false_without_allocation(self):
        AllocationPendency.objects.create(employee=self.employee, allocation=None)

        self.client.force_login(self.super_user)
        response = self.client.get(
            self.detail_url, {"employee_id": self.employee.pk}
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("origin_open_blocked", payload)
        self.assertFalse(payload["origin_open_blocked"])
        self.assertEqual(payload["origin_open_blocked_reason"], "")

    def test_detail_payload_flag_reflects_origin_not_viewers_permission(self):
        """ADMIN nao pode abrir (bloqueado por permissao, T8) — mas a
        flag deve refletir a ORIGEM da linha, nao se o ADMIN poderia
        abrir. Diferencia bloqueio por origem de autorizacao geral."""
        allocation = self._allocation(origem=PhoneLine.Origem.PESSOAL)
        AllocationPendency.objects.create(employee=self.employee, allocation=allocation)

        self.client.force_login(self.admin)
        response = self.client.get(
            self.detail_url,
            {"employee_id": self.employee.pk, "allocation_id": allocation.pk},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("origin_open_blocked", payload)
        self.assertTrue(payload["origin_open_blocked"])
        self.assertEqual(
            payload["origin_open_blocked_reason"], OPEN_BLOCKED_MESSAGE
        )

    def test_flag_does_not_restrict_treatment_fields_or_actions_on_open_pendency(self):
        """Pendencia JA aberta numa linha com origem agora bloqueada:
        a flag informa o estado da origem, mas nao reduz action_choices
        nem impede claim/observacao — tratamento continua liberado."""
        allocation = self._allocation(origem=PhoneLine.Origem.APARELHO_OP)
        pendency = AllocationPendency.objects.create(
            employee=self.employee,
            allocation=allocation,
            action=AllocationPendency.ActionType.PENDING,
        )

        self.client.force_login(self.admin)
        detail_response = self.client.get(
            self.detail_url,
            {"employee_id": self.employee.pk, "allocation_id": allocation.pk},
        )
        payload = detail_response.json()
        self.assertIn("origin_open_blocked", payload)
        self.assertTrue(payload["origin_open_blocked"])
        self.assertEqual(
            len(payload["action_choices"]),
            len(AllocationPendency.ActionType.choices),
        )

        claim_response = self.client.post(
            self.claim_url,
            data=json.dumps({"pendency_id": pendency.pk}),
            content_type="application/json",
        )
        self.assertEqual(claim_response.status_code, 200)
        pendency.refresh_from_db()
        self.assertEqual(pendency.technical_responsible, self.admin)

        update_response = self._post_update(
            self.admin,
            pendency,
            action=pendency.action,
            observation="tratamento legitimo com origem bloqueada",
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(
            update_response.json()["origin_open_blocked_reason"], OPEN_BLOCKED_MESSAGE
        )

    def test_update_success_response_includes_false_flag_for_permitted_origin(self):
        allocation = self._allocation(origem=PhoneLine.Origem.APARELHO)
        pendency = AllocationPendency.objects.create(employee=self.employee, allocation=allocation)

        response = self._post_update(
            self.super_user, pendency, action=AllocationPendency.ActionType.PENDING
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("origin_open_blocked", payload)
        self.assertFalse(payload["origin_open_blocked"])
        self.assertEqual(payload["origin_open_blocked_reason"], "")
