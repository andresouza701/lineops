"""
T8: retencao de LineDailyActionAuditEvent sob exclusao fisica operacional.

Prova que exclusao fisica de PhoneLine, LineAllocation, Employee, SystemUser,
DailyUserAction ou AllocationPendency nunca apaga o evento de auditoria:
apenas nulifica a FK correspondente (quando o modelo excluido e alvo de uma
FK do evento) ou nao afeta o evento (quando o modelo excluido e apenas
"fonte", referenciado por source/source_object_id).

Nao muda regra de negocio nenhuma: cada exclusao fisica abaixo usa o mesmo
caminho fisico ja usado pelo projeto (queryset/manager bruto ou instance
delete real) quando o delete() de negocio bloqueia ou faz soft-delete —
nunca SQL bruto, nunca desabilita trigger/guard.

Cobertura ja existente (nao duplicada aqui), em telecom/tests.py:
- LineDailyActionAuditEventTest.test_deleting_performed_by_sets_fk_null_and_keeps_snapshot
  (SystemUser fisico via instance.delete() — AbstractUser nao tem soft-delete)
- LineDailyActionAuditEventTest.test_django_set_null_cascade_still_works_despite_update_guard
  (LineAllocation fisico via queryset bruto)
- LineDailyActionAuditIntegrityTest.test_deleting_allocation_sets_fk_null_and_keeps_snapshot
- LineDailyActionAuditIntegrityTest.test_deleting_employee_sets_fk_null_and_keeps_snapshot
  (Employee fisico via all_objects manager bruto, bypassando soft-delete)
- LineDailyActionAuditEventTest.test_postgres_trigger_blocks_raw_sql_delete_and_content_update
  (guard de banco Postgres, skip fora de Postgres)

Este modulo cobre o que falta: fontes sem FK (DailyUserAction,
AllocationPendency), PhoneLine como alvo de FK, cascata indireta
(LineAllocation -> DailyUserAction/AllocationPendency) e um checklist de
integridade de campo completo apos cada tipo de exclusao.
"""

import uuid

from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from allocations.models import LineAllocation
from dashboard.models import DailyUserAction
from employees.models import Employee
from pendencies.models import AllocationPendency
from telecom.daily_action_audit import record_line_daily_action_event
from telecom.models import LineDailyActionAuditEvent, PhoneLine, SIMcard
from users.models import SystemUser


class LineDailyActionAuditRetentionTest(TestCase):
    """T8: retencao sob exclusao fisica, sqlite (`manage.py test` padrao)."""

    def setUp(self):
        self.maxDiff = None
        self.admin = SystemUser.objects.create_user(
            email="audit.retention.admin@test.com",
            password="123456",
            role=SystemUser.Role.ADMIN,
        )
        self.employee = Employee.objects.create(
            full_name="Employee Retention",
            corporate_email="audit.retention.super@corp.com",
            employee_id="EMPRET1",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        self.sim_card = SIMcard.objects.create(
            iccid="8900000000000000601",
            carrier="CarrierRetention",
            status=SIMcard.Status.AVAILABLE,
        )
        self.phone_line = PhoneLine.objects.create(
            phone_number="+551199999601",
            sim_card=self.sim_card,
            status=PhoneLine.Status.ALLOCATED,
        )
        self.allocation = LineAllocation.objects.create(
            employee=self.employee,
            phone_line=self.phone_line,
            allocated_by=self.admin,
            is_active=True,
        )

    def _state(self, **overrides):
        state = {
            "action": {"code": "pending", "label": "Pendencia"},
            "note": "",
            "technical_responsible": None,
            "line_status": {"code": "active", "label": "Ativa"},
            "resolution": {"is_resolved": False, "resolved_at": None},
            "source_state": {
                "day": None,
                "pendency_submitted_at": None,
                "last_submitted_action": None,
            },
        }
        state.update(overrides)
        return state

    def _record_event(self, **overrides):
        kwargs = dict(
            event_type=LineDailyActionAuditEvent.EventType.OPENED,
            source=LineDailyActionAuditEvent.Source.ALLOCATION_PENDENCY,
            source_object_id=1,
            phone_line=self.phone_line,
            allocation=self.allocation,
            employee=self.employee,
            performed_by=self.admin,
            before_state=self._state(),
            after_state=self._state(note="Pendencia aberta"),
            occurred_at=timezone.now(),
            operation_id=uuid.uuid4(),
        )
        kwargs.update(overrides)
        with transaction.atomic():
            return record_line_daily_action_event(**kwargs)

    def _snapshot_all_fields(self, event):
        """Todos os campos auditaveis fixos do contrato T8, para comparar
        antes/depois de uma exclusao fisica e provar que nada mais mudou."""
        return {
            "id": event.id,
            "source": event.source,
            "source_object_id": event.source_object_id,
            "event_type": event.event_type,
            "occurred_at": event.occurred_at,
            "operation_id": event.operation_id,
            "payload_version": event.payload_version,
            "before_state": event.before_state,
            "after_state": event.after_state,
            "phone_line_id": event.phone_line_id,
            "allocation_id": event.allocation_id,
            "employee_id": event.employee_id,
            "performed_by_id": event.performed_by_id,
            "phone_number_snapshot": event.phone_number_snapshot,
            "allocation_id_snapshot": event.allocation_id_snapshot,
            "employee_name_snapshot": event.employee_name_snapshot,
            "performed_by_name_snapshot": event.performed_by_name_snapshot,
            "performed_by_email_snapshot": event.performed_by_email_snapshot,
        }

    # -- 1. DailyUserAction: fonte sem FK -----------------------------------

    def test_deleting_daily_user_action_source_row_preserves_event(self):
        """DailyUserAction e fonte (source_object_id), nao FK do evento.
        Exclusao fisica direta: DailyUserAction nao tem delete() customizado
        nem manager que sobrescreva queryset.delete(), logo `.delete()` na
        instancia ja e o caminho fisico real (sem soft-delete no meio)."""
        with transaction.atomic():
            action = DailyUserAction.objects.create(
                employee=self.employee,
                allocation=self.allocation,
                action_type=DailyUserAction.ActionType.RECONNECT_WHATSAPP,
                note="Aguardando",
            )
            before = self._state()
            after = self._state(note="Aguardando")
            event = record_line_daily_action_event(
                event_type=LineDailyActionAuditEvent.EventType.OPENED,
                source=LineDailyActionAuditEvent.Source.DAILY_USER_ACTION,
                source_object_id=action.pk,
                phone_line=self.phone_line,
                allocation=self.allocation,
                employee=self.employee,
                performed_by=self.admin,
                before_state=before,
                after_state=after,
                occurred_at=timezone.now(),
                operation_id=uuid.uuid4(),
            )
        self.assertIsNotNone(event)
        before_snapshot = self._snapshot_all_fields(event)
        action_pk = action.pk

        action.delete()

        self.assertFalse(DailyUserAction.objects.filter(pk=action_pk).exists())
        event.refresh_from_db()
        after_snapshot = self._snapshot_all_fields(event)
        self.assertEqual(before_snapshot, after_snapshot)
        self.assertEqual(event.source_object_id, action_pk)

    # -- 2. AllocationPendency: fonte sem FK --------------------------------

    def test_deleting_allocation_pendency_source_row_preserves_event(self):
        """AllocationPendency e fonte (source_object_id), nao FK do evento.
        Sem delete() customizado: `.delete()` na instancia e exclusao
        fisica real."""
        with transaction.atomic():
            pendency = AllocationPendency.objects.create(
                employee=self.employee,
                allocation=self.allocation,
                action=AllocationPendency.ActionType.PENDING,
                observation="Observacao original",
            )
            before = self._state()
            after = self._state(note="Observacao original")
            event = record_line_daily_action_event(
                event_type=LineDailyActionAuditEvent.EventType.OPENED,
                source=LineDailyActionAuditEvent.Source.ALLOCATION_PENDENCY,
                source_object_id=pendency.pk,
                phone_line=self.phone_line,
                allocation=self.allocation,
                employee=self.employee,
                performed_by=self.admin,
                before_state=before,
                after_state=after,
                occurred_at=timezone.now(),
                operation_id=uuid.uuid4(),
            )
        self.assertIsNotNone(event)
        before_snapshot = self._snapshot_all_fields(event)
        pendency_pk = pendency.pk

        pendency.delete()

        self.assertFalse(
            AllocationPendency.objects.filter(pk=pendency_pk).exists()
        )
        event.refresh_from_db()
        after_snapshot = self._snapshot_all_fields(event)
        self.assertEqual(before_snapshot, after_snapshot)
        self.assertEqual(event.source_object_id, pendency_pk)

    # -- 6. PhoneLine: alvo de FK SET_NULL ----------------------------------

    def test_deleting_phone_line_sets_fk_null_and_keeps_snapshot(self):
        """PhoneLine.delete() de negocio faz soft-delete e libera alocacao
        ativa (regra atual, preservada). Para provar exclusao fisica real
        sem tocar essa regra: remove a LineAllocation que ainda a referencia
        (PROTECT) pelo mesmo caminho de queryset bruto ja usado no projeto,
        depois exclui a PhoneLine fisicamente via `all_objects` (manager sem
        override de queryset.delete(), ao contrario do manager `objects`
        default que faz soft-delete).

        Evento gravado sem `allocation` (None): remover a LineAllocation
        para desbloquear o PROTECT da linha e' um efeito colateral necessario
        deste caminho de exclusao, e nulificaria `allocation_id` do proprio
        evento se ele apontasse pra ela — o que testaria a FK errada aqui.
        Retencao de `allocation_id` sob exclusao de LineAllocation ja e'
        coberta por outro teste deste modulo e por
        telecom/tests.py::LineDailyActionAuditIntegrityTest."""
        event = self._record_event(source_object_id=601, allocation=None)
        before_snapshot = self._snapshot_all_fields(event)
        phone_number_snapshot = event.phone_number_snapshot
        line_pk = self.phone_line.pk

        LineAllocation.objects.filter(pk=self.allocation.pk).delete()
        PhoneLine.all_objects.filter(pk=line_pk).delete()

        self.assertFalse(PhoneLine.all_objects.filter(pk=line_pk).exists())
        event.refresh_from_db()
        self.assertIsNone(event.phone_line_id)
        self.assertEqual(event.phone_number_snapshot, phone_number_snapshot)
        after_snapshot = self._snapshot_all_fields(event)
        before_snapshot["phone_line_id"] = None
        self.assertEqual(before_snapshot, after_snapshot)

    # -- 7. Cascata indireta: LineAllocation -> DailyUserAction/Pendency ----

    def test_deleting_allocation_cascades_daily_action_and_pendency_sources(self):
        """DailyUserAction.allocation e AllocationPendency.allocation sao
        CASCADE (modelo de dominio, T8 nao altera). Exclusao fisica da
        LineAllocation (via queryset bruto, mesmo caminho ja usado no
        projeto porque LineAllocation.delete() de negocio bloqueia) remove
        as duas fontes operacionais por cascata; os eventos de auditoria
        permanecem, apenas com allocation_id nulificado."""
        with transaction.atomic():
            action = DailyUserAction.objects.create(
                employee=self.employee,
                allocation=self.allocation,
                action_type=DailyUserAction.ActionType.RECONNECT_WHATSAPP,
            )
            pendency = AllocationPendency.objects.create(
                employee=self.employee,
                allocation=self.allocation,
                action=AllocationPendency.ActionType.PENDING,
            )
            action_event = record_line_daily_action_event(
                event_type=LineDailyActionAuditEvent.EventType.OPENED,
                source=LineDailyActionAuditEvent.Source.DAILY_USER_ACTION,
                source_object_id=action.pk,
                phone_line=self.phone_line,
                allocation=self.allocation,
                employee=self.employee,
                performed_by=self.admin,
                before_state=self._state(),
                after_state=self._state(note="a"),
                occurred_at=timezone.now(),
                operation_id=uuid.uuid4(),
            )
            pendency_event = record_line_daily_action_event(
                event_type=LineDailyActionAuditEvent.EventType.OPENED,
                source=LineDailyActionAuditEvent.Source.ALLOCATION_PENDENCY,
                source_object_id=pendency.pk,
                phone_line=self.phone_line,
                allocation=self.allocation,
                employee=self.employee,
                performed_by=self.admin,
                before_state=self._state(),
                after_state=self._state(note="b"),
                occurred_at=timezone.now(),
                operation_id=uuid.uuid4(),
            )

        action_pk, pendency_pk = action.pk, pendency.pk
        allocation_id_snapshot_action = action_event.allocation_id_snapshot
        allocation_id_snapshot_pendency = pendency_event.allocation_id_snapshot

        LineAllocation.objects.filter(pk=self.allocation.pk).delete()

        self.assertFalse(DailyUserAction.objects.filter(pk=action_pk).exists())
        self.assertFalse(
            AllocationPendency.objects.filter(pk=pendency_pk).exists()
        )

        action_event.refresh_from_db()
        pendency_event.refresh_from_db()
        self.assertIsNone(action_event.allocation_id)
        self.assertIsNone(pendency_event.allocation_id)
        self.assertEqual(
            action_event.allocation_id_snapshot, allocation_id_snapshot_action
        )
        self.assertEqual(
            pendency_event.allocation_id_snapshot, allocation_id_snapshot_pendency
        )
        self.assertEqual(action_event.source_object_id, action_pk)
        self.assertEqual(pendency_event.source_object_id, pendency_pk)

    # -- 8. Integridade completa de campo, por tipo de FK -------------------

    def test_field_integrity_preserved_across_every_fk_deletion_type(self):
        """Para cada FK nulificavel (phone_line, allocation, employee,
        performed_by), cria evento isolado e confere que a exclusao fisica
        do alvo nulifica so aquela FK — todos os outros campos auditaveis
        (id, source, source_object_id, event_type, occurred_at, before/after
        JSON, operation_id, payload_version, snapshots, e as outras 3 FKs
        ainda existentes) permanecem bit-a-bit identicos."""
        # performed_by isolado (nao usado por outro teste/objeto)
        isolated_admin = SystemUser.objects.create_user(
            email="audit.retention.isolated@test.com",
            password="123456",
            role=SystemUser.Role.ADMIN,
        )
        event = self._record_event(
            source_object_id=602, performed_by=isolated_admin
        )
        before_snapshot = self._snapshot_all_fields(event)

        isolated_admin.delete()

        event.refresh_from_db()
        after_snapshot = self._snapshot_all_fields(event)
        expected = dict(before_snapshot, performed_by_id=None)
        self.assertEqual(expected, after_snapshot)
        # snapshots textuais sobrevivem, mesmo com a FK nula
        self.assertTrue(event.performed_by_name_snapshot)
        self.assertTrue(event.performed_by_email_snapshot)

        # employee isolado, com sua propria alocacao/linha para nao colidir
        # com o employee/allocation/phone_line compartilhados do setUp.
        isolated_sim = SIMcard.objects.create(
            iccid="8900000000000000602",
            carrier="CarrierRetention2",
            status=SIMcard.Status.AVAILABLE,
        )
        isolated_line = PhoneLine.objects.create(
            phone_number="+551199999602",
            sim_card=isolated_sim,
            status=PhoneLine.Status.ALLOCATED,
        )
        isolated_employee = Employee.objects.create(
            full_name="Employee Retention Isolated",
            corporate_email="audit.retention.isolated.super@corp.com",
            employee_id="EMPRET2",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        isolated_allocation = LineAllocation.objects.create(
            employee=isolated_employee,
            phone_line=isolated_line,
            allocated_by=self.admin,
            is_active=True,
        )
        employee_event = self._record_event(
            source_object_id=603,
            phone_line=isolated_line,
            allocation=isolated_allocation,
            employee=isolated_employee,
        )
        before_employee_snapshot = self._snapshot_all_fields(employee_event)

        # Employee.delete() de negocio e soft-delete: remove primeiro a
        # LineAllocation que ainda referencia (PROTECT) pelo caminho de
        # queryset bruto ja usado no projeto, depois exclui fisicamente via
        # all_objects (sem override de soft-delete no queryset).
        LineAllocation.objects.filter(pk=isolated_allocation.pk).delete()
        Employee.all_objects.filter(pk=isolated_employee.pk).delete()

        employee_event.refresh_from_db()
        after_employee_snapshot = self._snapshot_all_fields(employee_event)
        expected_employee = dict(
            before_employee_snapshot,
            employee_id=None,
            allocation_id=None,
        )
        self.assertEqual(expected_employee, after_employee_snapshot)
        self.assertTrue(employee_event.employee_name_snapshot)

        # allocation isolada, ligada ao employee/phone_line compartilhados
        # do setUp (ainda vivos nesta altura do teste).
        allocation_event = self._record_event(source_object_id=604)
        before_allocation_snapshot = self._snapshot_all_fields(allocation_event)

        LineAllocation.objects.filter(pk=self.allocation.pk).delete()

        allocation_event.refresh_from_db()
        after_allocation_snapshot = self._snapshot_all_fields(allocation_event)
        expected_allocation = dict(before_allocation_snapshot, allocation_id=None)
        self.assertEqual(expected_allocation, after_allocation_snapshot)
        self.assertIsNotNone(allocation_event.allocation_id_snapshot)

        # phone_line: ultima FK viva do setUp (allocation ja removida acima).
        phone_line_event_source_id = 605
        with transaction.atomic():
            phone_line_event = record_line_daily_action_event(
                event_type=LineDailyActionAuditEvent.EventType.OPENED,
                source=LineDailyActionAuditEvent.Source.ALLOCATION_PENDENCY,
                source_object_id=phone_line_event_source_id,
                phone_line=self.phone_line,
                allocation=None,
                employee=self.employee,
                performed_by=self.admin,
                before_state=self._state(),
                after_state=self._state(note="linha"),
                occurred_at=timezone.now(),
                operation_id=uuid.uuid4(),
            )
        before_line_snapshot = self._snapshot_all_fields(phone_line_event)

        PhoneLine.all_objects.filter(pk=self.phone_line.pk).delete()

        phone_line_event.refresh_from_db()
        after_line_snapshot = self._snapshot_all_fields(phone_line_event)
        expected_line = dict(before_line_snapshot, phone_line_id=None)
        self.assertEqual(expected_line, after_line_snapshot)
        self.assertTrue(phone_line_event.phone_number_snapshot)
