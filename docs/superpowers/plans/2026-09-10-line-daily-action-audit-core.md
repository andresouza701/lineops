# Line Daily Action Audit Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Persist immutable, complete audit facts for daily line actions and pendencies from deployment onward.

**Architecture:** Add telecom.LineDailyActionAuditEvent as independent append-only storage. telecom.daily_action_audit owns state serialization and event creation. Existing dashboard and pendencies write paths capture before-state, mutate operational state, then append event(s) in same transaction. Existing PhoneLineHistory stays unchanged.

**Tech Stack:** Django 5.2, PostgreSQL production, Django TestCase, Django JSONField, UUIDField, transaction.atomic.

---

## Scope and Non-Goals

This plan implements core persistence, audited writes, and pendency authorization.
It does not add timeline UI, dashboard/report UI, historical backfill, or remove
PhoneLineHistory. A follow-up plan owns the read timeline and reporting.

DailyUserAction remains a legacy source. It receives audit events but keeps its
existing role policy because it has no technical_responsible ownership field.
The approved assignment restriction applies to AllocationPendency.

## File Structure

- Modify: telecom/models.py
  - Add LineDailyActionAuditEvent and its append-only model behavior.
- Create: telecom/daily_action_audit.py
  - Build source-specific full snapshots and append events.
- Create: telecom/migrations/0017_line_daily_action_audit_event.py
  - Manual isolated migration. Do not generate unrelated model drift.
- Modify: telecom/tests.py
  - Model, service, immutability, snapshot, retention, and atomicity tests.
- Modify: pendencies/views.py
  - Lock pendency writes, enforce assigned-tech ownership, emit audit events.
- Modify: pendencies/tests/test_observation_notifications.py
  - Permission and event integration tests using existing fixtures.
- Modify: dashboard/views.py
  - Emit legacy DailyUserAction and line-status audit events.
- Create: dashboard/tests/test_daily_line_action_audit.py
  - Daily action audit integration tests.

## Data Contract

LineDailyActionAuditEvent fields:

    id
    event_type
    source
    source_object_id
    operation_id
    payload_version
    occurred_at
    recorded_at
    phone_line
    allocation
    employee
    performed_by
    phone_number_snapshot
    allocation_id_snapshot
    employee_name_snapshot
    performed_by_name_snapshot
    performed_by_email_snapshot
    before_state
    after_state

Use SET_NULL for operational FKs. Snapshot fields preserve readability after
operational deletion. before_state and after_state always contain action, note,
technical_responsible, line_status, resolution, and source_state keys. Values
not applicable to a source are null, never absent.

## Task 1: Add Audit Model and Manual Migration

**Files:**
- Modify: telecom/models.py
- Create: telecom/migrations/0017_line_daily_action_audit_event.py
- Modify: telecom/tests.py

- [ ] **Step 1: Add failing model contract tests to telecom/tests.py**

Add a LineDailyActionAuditEventTest class near PhoneLineHistoryAuditTest. Create
real SystemUser, Employee, SIMcard, PhoneLine, and LineAllocation rows. Test:

~~~python
def test_event_stores_complete_identity_and_snapshot_fields(self):
    state = {
        "action": {"code": "no_action", "label": "Sem Acao"},
        "note": "",
        "technical_responsible": None,
        "line_status": {"code": "active", "label": "Ativa"},
        "resolution": {"is_resolved": False, "resolved_at": None},
        "source_state": {
            "day": None,
            "pendency_submitted_at": None,
            "last_submitted_action": None,
            "is_resolved": None,
        },
    }
    event = LineDailyActionAuditEvent.objects.create(
        phone_line=self.phone_line,
        allocation=self.allocation,
        employee=self.employee,
        performed_by=self.admin,
        event_type=LineDailyActionAuditEvent.EventType.OPENED,
        source=LineDailyActionAuditEvent.Source.ALLOCATION_PENDENCY,
        source_object_id=771,
        occurred_at=timezone.now(),
        phone_number_snapshot=self.phone_line.phone_number,
        allocation_id_snapshot=self.allocation.pk,
        employee_name_snapshot=self.employee.full_name,
        performed_by_name_snapshot=self.admin.get_full_name().strip() or self.admin.email,
        performed_by_email_snapshot=self.admin.email,
        before_state=state,
        after_state=state,
    )
    self.assertEqual(event.phone_number_snapshot, self.phone_line.phone_number)
    self.assertEqual(
        event.performed_by_name_snapshot,
        self.admin.get_full_name().strip() or self.admin.email,
    )
    self.assertIsNotNone(event.operation_id)
    self.assertIsNotNone(event.recorded_at)
~~~

Also test choices, default payload version 1, JSON state keys, and deleting an
isolated performed_by user sets FK null while name/email snapshots remain.

- [ ] **Step 2: Run tests and confirm RED**

Run:

~~~powershell
.\venv\Scripts\python.exe manage.py test telecom.tests.LineDailyActionAuditEventTest --settings=config.settings_dev -v 2
~~~

Expected: ImportError because LineDailyActionAuditEvent does not exist.

- [ ] **Step 3: Add LineDailyActionAuditEvent to telecom/models.py**

Place model after PhoneLineHistory. Define choice types and fields:

~~~python
class LineDailyActionAuditEvent(models.Model):
    class EventType(models.TextChoices):
        OPENED = "OPENED", "Aberta"
        ACTION_CHANGED = "ACTION_CHANGED", "Acao alterada"
        NOTE_CHANGED = "NOTE_CHANGED", "Nota alterada"
        RESPONSIBLE_ASSIGNED = "RESPONSIBLE_ASSIGNED", "Tecnico assumiu"
        RESPONSIBLE_RELEASED = "RESPONSIBLE_RELEASED", "Tecnico liberou"
        LINE_STATUS_CHANGED = "LINE_STATUS_CHANGED", "Status alterado"
        RESOLVED = "RESOLVED", "Resolvida"
        REOPENED = "REOPENED", "Reaberta"

    class Source(models.TextChoices):
        DAILY_USER_ACTION = "DAILY_USER_ACTION", "Acao diaria"
        ALLOCATION_PENDENCY = "ALLOCATION_PENDENCY", "Pendencia"

    event_type = models.CharField(max_length=30, choices=EventType.choices)
    source = models.CharField(max_length=30, choices=Source.choices)
    source_object_id = models.BigIntegerField()
    operation_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    payload_version = models.PositiveSmallIntegerField(default=1)
    occurred_at = models.DateTimeField(db_index=True)
    recorded_at = models.DateTimeField(auto_now_add=True)
    before_state = models.JSONField()
    after_state = models.JSONField()
~~~

Use nullable SET_NULL FKs to PhoneLine, LineAllocation, Employee, and
settings.AUTH_USER_MODEL. Add all five snapshot fields specified above.
Add model indexes named under backend limits for phone_line/occurred_at,
allocation/occurred_at, employee/occurred_at, event_type/occurred_at, and
source/source_object_id. Ordering is -occurred_at, -id.

Implement save guard:

~~~python
def save(self, *args, **kwargs):
    if self.pk:
        raise ValidationError("Eventos de auditoria sao imutaveis.")
    return super().save(*args, **kwargs)
~~~

Do not register model in telecom/admin.py.

- [ ] **Step 4: Write manual migration 0017**

Create telecom/migrations/0017_line_daily_action_audit_event.py with dependency
on telecom 0016_alter_phonelinehistory_action_reactivated, allocations 0008,
employees 0020, and migrations.swappable_dependency(settings.AUTH_USER_MODEL).
Use CreateModel and AddIndex operations matching model exactly.

Do not run makemigrations as a correctness gate: known unrelated drift exists in
PhoneLine.origem and dashboard DailyUserAction action_type. Run makemigrations
only to inspect generated operations, discard output, then keep manual 0017
limited to audit table.

- [ ] **Step 5: Run GREEN tests and migration checks**

Run:

~~~powershell
.\venv\Scripts\python.exe manage.py migrate telecom 0017 --settings=config.settings_dev
.\venv\Scripts\python.exe manage.py test telecom.tests.LineDailyActionAuditEventTest --settings=config.settings_dev -v 2
~~~

Expected: migration applies and every model contract test passes.

- [ ] **Step 6: Commit foundation**

~~~powershell
git add telecom/models.py telecom/migrations/0017_line_daily_action_audit_event.py telecom/tests.py
git commit -m "feat(telecom): add line action audit events"
~~~

## Task 2: Add Central Snapshot and Append Service

**Files:**
- Create: telecom/daily_action_audit.py
- Modify: telecom/tests.py

- [ ] **Step 1: Add failing service tests**

Test snapshots for pendency and DailyUserAction. Assert every state has exactly
these top-level keys:

~~~python
STATE_KEYS = {
    "action", "note", "technical_responsible",
    "line_status", "resolution", "source_state",
}

def test_record_event_uses_one_operation_id_for_related_events(self):
    operation_id = uuid.uuid4()
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
    first = record_line_daily_action_event(
        event_type=LineDailyActionAuditEvent.EventType.OPENED,
        source=LineDailyActionAuditEvent.Source.ALLOCATION_PENDENCY,
        source_object_id=771,
        phone_line=self.phone_line,
        allocation=self.allocation,
        employee=self.employee,
        performed_by=self.admin,
        before_state=state,
        after_state=state,
        occurred_at=timezone.now(),
        operation_id=operation_id,
    )
    second = record_line_daily_action_event(
        event_type=LineDailyActionAuditEvent.EventType.NOTE_CHANGED,
        source=LineDailyActionAuditEvent.Source.ALLOCATION_PENDENCY,
        source_object_id=771,
        phone_line=self.phone_line,
        allocation=self.allocation,
        employee=self.employee,
        performed_by=self.admin,
        before_state=state,
        after_state={**state, "note": "Nova nota"},
        occurred_at=timezone.now(),
        operation_id=operation_id,
    )
    self.assertEqual(first.operation_id, second.operation_id)
~~~

Test state snapshots have code and display label for choices. Test append helper
uses supplied occurred_at, copies executor identity into performed_by snapshots,
and accepts nullable phone_line for allocation-less DailyUserAction events.

- [ ] **Step 2: Run RED**

Run:

~~~powershell
.\venv\Scripts\python.exe manage.py test telecom.tests.LineDailyActionAuditServiceTest --settings=config.settings_dev -v 2
~~~

Expected: ImportError for telecom.daily_action_audit.

- [ ] **Step 3: Implement telecom/daily_action_audit.py**

Expose only these functions:

~~~python
def build_pendency_state(pendency, allocation) -> dict:
    return {
        "action": _choice_state(pendency.action, pendency.get_action_display()),
        "note": pendency.observation,
        "technical_responsible": _user_state(pendency.technical_responsible),
        "line_status": _allocation_line_status_state(allocation),
        "resolution": _pendency_resolution_state(pendency),
        "source_state": _pendency_source_state(pendency),
    }

def build_daily_user_action_state(action, allocation) -> dict:
    return {
        "action": _choice_state(action.action_type, action.get_action_type_display()),
        "note": action.note,
        "technical_responsible": None,
        "line_status": _allocation_line_status_state(allocation),
        "resolution": {"is_resolved": action.is_resolved, "resolved_at": None},
        "source_state": {
            "day": action.day.isoformat(),
            "pendency_submitted_at": None,
            "last_submitted_action": None,
            "is_resolved": action.is_resolved,
        },
    }

def _choice_state(code, label):
    return {"code": code, "label": label}

def _user_state(user):
    if user is None:
        return None
    return {
        "id": user.pk,
        "name": user.get_full_name().strip() or user.email,
        "email": user.email,
    }

def _allocation_line_status_state(allocation):
    if allocation is None:
        return {"code": None, "label": None}
    return {
        "code": allocation.line_status,
        "label": allocation.get_line_status_display(),
    }

def _pendency_resolution_state(pendency):
    return {
        "is_resolved": pendency.resolved_at is not None,
        "resolved_at": pendency.resolved_at.isoformat() if pendency.resolved_at else None,
    }

def _pendency_source_state(pendency):
    return {
        "day": None,
        "pendency_submitted_at": (
            pendency.pendency_submitted_at.isoformat()
            if pendency.pendency_submitted_at else None
        ),
        "last_submitted_action": _choice_state(
            pendency.last_submitted_action,
            dict(AllocationPendency.ActionType.choices).get(
                pendency.last_submitted_action
            ),
        ) if pendency.last_submitted_action else None,
        "is_resolved": None,
    }
def record_line_daily_action_event(
    *,
    event_type,
    source,
    source_object_id,
    phone_line,
    allocation,
    employee,
    performed_by,
    before_state,
    after_state,
    occurred_at,
    operation_id,
) -> LineDailyActionAuditEvent:
    return LineDailyActionAuditEvent.objects.create(
        event_type=event_type,
        source=source,
        source_object_id=source_object_id,
        phone_line=phone_line,
        allocation=allocation,
        employee=employee,
        performed_by=performed_by,
        phone_number_snapshot=phone_line.phone_number if phone_line else "",
        allocation_id_snapshot=allocation.pk if allocation else None,
        employee_name_snapshot=employee.full_name if employee else "",
        performed_by_name_snapshot=(
            performed_by.get_full_name().strip() or performed_by.email
        ) if performed_by else "",
        performed_by_email_snapshot=performed_by.email if performed_by else "",
        before_state=before_state,
        after_state=after_state,
        occurred_at=occurred_at,
        operation_id=operation_id,
    )
~~~

Use get_action_display and get_line_status_display at snapshot time. Represent
technical_responsible as null or id/name/email. For DailyUserAction set
technical_responsible, pendency_submitted_at, and last_submitted_action to null;
set source_state.day and source_state.is_resolved. For AllocationPendency set
source_state.day and source_state.is_resolved to null; retain pendency timestamps
and last_submitted_action.

record_line_daily_action_event creates one row only. It must not decide event
type, mutate business rows, query unrelated data, or open its own transaction.
Callers provide a request-scoped uuid.uuid4 operation id inside transaction.

- [ ] **Step 4: Run GREEN and regression tests**

Run:

~~~powershell
.\venv\Scripts\python.exe manage.py test telecom.tests.LineDailyActionAuditServiceTest telecom.tests.PhoneLineHistoryAuditTest --settings=config.settings_dev -v 2
~~~

Expected: PASS. Existing PhoneLineHistory behavior remains unchanged.

- [ ] **Step 5: Commit service**

~~~powershell
git add telecom/daily_action_audit.py telecom/tests.py
git commit -m "feat(telecom): centralize line action audit writes"
~~~

## Task 3: Enforce Pendency Ownership and Audit Pendency Writes

**Files:**
- Modify: pendencies/views.py
- Modify: pendencies/tests/test_observation_notifications.py
- Modify: telecom/tests.py

- [ ] **Step 1: Add failing authorization and audit tests**

Extend existing PendencyUpdateViewNotificationTest with second_admin. Cover:

Add these exact methods:

- test_unassigned_pendency_can_be_claimed_by_admin
- test_assigned_pendency_cannot_be_claimed_by_second_admin
- test_only_current_technical_responsible_can_update_action_status_or_resolve
- test_super_can_open_and_reopen_but_cannot_change_open_action
- test_super_can_change_note_without_becoming_responsible
- test_explicit_release_creates_responsible_released_event
- test_resolve_creates_resolved_event_with_responsible_cleared
- test_reopen_creates_reopened_event_with_responsible_cleared

For each success test assert one event, event_type, performed_by, before_state,
after_state, and same operation_id for action plus note/status changes in one
request. For denied requests assert HTTP 403, zero audit events, and unchanged
pendency/allocation.

- [ ] **Step 2: Run RED**

Run:

~~~powershell
.\venv\Scripts\python.exe manage.py test pendencies.tests.test_observation_notifications.PendencyUpdateViewNotificationTest --settings=config.settings_dev -v 2
~~~

Expected: authorization assertions fail and audit event rows are absent.

- [ ] **Step 3: Add locked load and ownership helpers in pendencies/views.py**

Use transaction.atomic and select_for_update for every mutation. Define:

~~~python
def _is_current_technical_responsible(pendency, user):
    return (
        user.role == SystemUser.Role.ADMIN
        and pendency.technical_responsible_id == user.id
    )

def _load_locked_pendency_for_scope(request, pendency_id):
    pendency = get_object_or_404(
        AllocationPendency.objects.select_for_update().select_related(
            "employee", "allocation__phone_line", "technical_responsible"
        ),
        pk=pendency_id,
    )
    if not request.user.scope_employee_queryset(Employee.objects.all()).filter(
        pk=pendency.employee_id
    ).exists():
        raise PermissionDenied("Sem acesso a este funcionario.")
    return pendency
~~~

Claim requires admin, pending action not no_action, and
technical_responsible_id is null. Otherwise return 403 and do not replace owner.
Release requires _is_current_technical_responsible. Replace current idempotent
release test: release on unassigned or another technician's pendency is 403.

PendencyUpdateView policy:

- super/backoffice/gerente: may set non-no_action only from no_action
  (OPENED if resolved_at null, REOPENED otherwise), and may edit observation.
- Those roles may not change active action, set no_action, set line status, or
  alter technical_responsible.
- Current technical responsible may change action, observation, line status,
  explicitly release, or resolve.
- Other admins cannot mutate assigned pendency.

Capture before_state before record_action_change or field mutation. Generate one
operation_id per POST. Append event after each material mutation with same
operation_id. An explicit release creates RESPONSIBLE_RELEASED. Resolution and
reopen clear technical responsible inside their semantic RESOLVED or REOPENED
event; do not create duplicate release event.

- [ ] **Step 4: Preserve existing side effects**

Keep PhoneLineHistory STATUS_CHANGED, PendencyObservationNotification behavior,
last_action_changed_at, pendency_submitted_at, resolved_at, and updated_by.
Place notification dispatch after successful pendency save inside successful
transaction path. Do not notify on denied/no-op requests.

- [ ] **Step 5: Run GREEN tests**

Run:

~~~powershell
.\venv\Scripts\python.exe manage.py test pendencies.tests.test_observation_notifications pendencies.tests.test_line_status_web_restriction --settings=config.settings_dev -v 2
~~~

Expected: PASS, including existing notification and line-status behavior.

- [ ] **Step 6: Commit pendency slice**

~~~powershell
git add pendencies/views.py pendencies/tests/test_observation_notifications.py telecom/tests.py
git commit -m "feat(pendencies): audit assigned technician actions"
~~~

## Task 4: Audit Legacy DailyUserAction Writes

**Files:**
- Modify: dashboard/views.py
- Create: dashboard/tests/test_daily_line_action_audit.py

- [ ] **Step 1: Add failing daily action tests**

Use real admin, employee, allocation, line, and DailyUserAction rows. Cover:

Add these exact methods:

- test_create_action_records_opened_event
- test_change_action_and_note_records_two_events_with_one_operation_id
- test_resolve_action_records_note_changed_then_resolved_event
- test_reactivate_resolved_same_day_action_records_reopened_event
- test_line_status_change_records_line_status_changed_event
- test_action_without_allocation_has_null_phone_line_event

Assert existing PhoneLineHistory DAILY_ACTION_CHANGED and STATUS_CHANGED rows
still occur for allocation-backed legacy actions. Null-line event must preserve
employee, performed_by, source object id, and full state but not appear in a
future line timeline.

- [ ] **Step 2: Run RED**

Run:

~~~powershell
.\venv\Scripts\python.exe manage.py test dashboard.tests.test_daily_line_action_audit --settings=config.settings_dev -v 2
~~~

Expected: LineDailyActionAuditEvent count is zero.

- [ ] **Step 3: Make daily_user_action_board atomic per POST**

Wrap operational write(s), existing PhoneLineHistory write(s), and new audit
event write(s) in transaction.atomic. Create operation_id once after form
validation. Build before_state from existing action before mutating it.

Event mapping:

- new update_or_create row: OPENED;
- existing resolved row made unresolved: REOPENED;
- action type changed: ACTION_CHANGED;
- note changed: NOTE_CHANGED;
- resolved action: RESOLVED;
- allocation line status changed: LINE_STATUS_CHANGED.

When one POST changes action and note, append two rows with same operation_id.
When resolution overwrites note, append NOTE_CHANGED first, then RESOLVED.
Keep all current redirects, messages, DailyUserAction update_or_create behavior,
and PhoneLineHistory entries unchanged.

- [ ] **Step 4: Run GREEN and dashboard regression tests**

Run:

~~~powershell
.\venv\Scripts\python.exe manage.py test dashboard.tests.test_daily_line_action_audit dashboard.tests.test_daily_action_total_card dashboard.tests.test_pending_cards_consistency --settings=config.settings_dev -v 2
~~~

Expected: PASS.

- [ ] **Step 5: Commit legacy slice**

~~~powershell
git add dashboard/views.py dashboard/tests/test_daily_line_action_audit.py
git commit -m "feat(dashboard): audit legacy daily line actions"
~~~

## Task 5: End-to-End Integrity and Deployment Validation

**Files:**
- Modify: telecom/tests.py
- Modify: docs/superpowers/specs/2026-09-10-line-daily-action-audit-design.md

- [ ] **Step 1: Add rollback and retention tests**

Test that exception after operational mutation but before transaction completion
rolls back both mutation and audit rows. Test physical deletion of isolated
performed_by and allocation references sets FK null while snapshots remain.
Test model save after creation raises ValidationError.

- [ ] **Step 2: Run full affected suite**

Run:

~~~powershell
.\venv\Scripts\python.exe manage.py test telecom dashboard pendencies --settings=config.settings_dev -v 2
.\venv\Scripts\python.exe manage.py check --settings=config.settings_dev
~~~

Expected: all tests PASS and check reports no new errors.

- [ ] **Step 3: Inspect migration plan**

Run:

~~~powershell
.\venv\Scripts\python.exe manage.py showmigrations telecom --settings=config.settings_dev
.\venv\Scripts\python.exe manage.py migrate telecom 0017 --plan --settings=config.settings_dev
~~~

Expected: only telecom 0017 audit-table operations are pending. Do not treat
makemigrations --check failure as this feature failure because unrelated drift
is already known and intentionally excluded.

- [ ] **Step 4: Update spec implementation status and commit**

Add implementation evidence and test command results to spec after tests pass.

~~~powershell
git add telecom/tests.py docs/superpowers/specs/2026-09-10-line-daily-action-audit-design.md
git commit -m "test: verify line daily action audit integrity"
~~~

## Checkpoints

After Task 2:

- Audit model migration applies.
- Service serializes full states.
- No existing PhoneLineHistory test regresses.

After Task 4:

- Pendency lifecycle records approved events.
- Only assigned technician can manage assigned pendency.
- Legacy DailyUserAction writes preserve each material change.

After Task 5:

- Affected suite passes.
- Migration plan is isolated.
- Review event samples against approved contract before deployment.

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Existing views are not atomic | Add transaction.atomic and write audit within same boundary. |
| Two admins claim same pendency | select_for_update plus null-owner check. |
| Existing unrestricted admin behavior changes | Explicit permission tests before code. |
| Existing model drift creates noisy migration | Hand-write 0017 and inspect migration plan. |
| Snapshot format evolves | payload_version; new shape needs approved version bump. |
| Operational deletes remove references | SET_NULL plus immutable snapshots. |

## Spec Coverage Review

- Append-only table, snapshots, event types, sources, and indexes: Tasks 1-2.
- Atomic writes: Tasks 3-4.
- Super/backoffice/gerente and assigned technician policy: Task 3.
- Legacy DailyUserAction audit coverage: Task 4.
- Retention, immutability, test evidence, migration isolation: Task 5.
- Timeline UI, dashboard/report, and historical backfill: intentionally out of scope.
