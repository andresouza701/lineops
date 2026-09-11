# Line Daily Action Audit Design

## Spec Summary

LineOps will add a separate append-only audit table for material changes made
through Acoes do Dia. It covers dashboard.DailyUserAction and
pendencies.AllocationPendency. Recording begins at deployment. Previously
overwritten data will not be inferred or backfilled.

## Objective

Provide complete, chronological, immutable line-action timeline. An authorized
user can identify change, before/after values, event executor, source, allocation,
employee, and occurrence time.

Success: calculate entries, exits, reopens, action changes, responsible
changes, note changes, status changes, and time open from append-only events.

## Current Gaps

DailyUserAction overwrites same-day state, loses earlier notes, has no
resolution timestamp, and only sometimes writes PhoneLineHistory.
AllocationPendency retains current/latest-cycle state only; its action,
observation, and technical-responsible changes do not create line history.
Existing PhoneLineHistory remains unchanged for compatibility and is not source
of truth for this audit.

## Confirmed Decisions

- Separate append-only table. Do not extend PhoneLineHistory.
- Capture action, note, technical responsible, line status, open, resolve,
  and reopen.
- Start at deployment. No inferred baseline or historical backfill.
- Read access follows existing visible-phone-line rules.
- Persist complete before_state and after_state; never partial deltas.
- performed_by means user who executed event. It is independent from technical
  responsible and from user who initially opened pendency.

## Django Boundary

- Primary app: telecom.
- New model: telecom.LineDailyActionAuditEvent.
- Writes: dashboard.views.daily_user_action_board,
  pendencies.views.PendencyUpdateView, PendencyClaimView, and
  PendencyReleaseView.
- Reads: later extension of telecom.views.PhoneLineHistoryView, retaining
  current authorization.

## Event Contract

### Types

OPENED, ACTION_CHANGED, NOTE_CHANGED, RESPONSIBLE_ASSIGNED,
RESPONSIBLE_RELEASED, LINE_STATUS_CHANGED, RESOLVED, REOPENED.

### Sources

DAILY_USER_ACTION, ALLOCATION_PENDENCY.

### Permission Matrix

Every technical user has admin role. technical_responsible is not a role; it is
the specific admin currently assigned to pendency.

| Role | Allowed events |
| --- | --- |
| super, backoffice, gerente | OPENED, REOPENED, NOTE_CHANGED |
| admin, pendency unassigned | RESPONSIBLE_ASSIGNED |
| admin, current technical responsible | ACTION_CHANGED, NOTE_CHANGED, RESPONSIBLE_RELEASED, LINE_STATUS_CHANGED, RESOLVED |

super, backoffice, and gerente create a pendency for a line. It becomes visible
in Acoes do Dia for every admin. Any admin may assume an unassigned pendency.
After assume, only admin whose id equals technical_responsible_id may change
action, note, line status, release, or resolve it. Other admins cannot change
or resolve an assigned pendency. Only super, backoffice, or gerente may reopen
a resolved pendency; after reopening, they may change its note only.

Examples:

- OPENED: display "Solicitado por" from performed_by.
- RESPONSIBLE_ASSIGNED: display "Tecnico que assumiu" from performed_by.
- technical_responsible is current admin responsible in after_state.
- RESOLVED: display "Tecnico que resolveu" from performed_by. It must equal
  technical_responsible in before_state.
- REOPENED: display "Reaberto por" from performed_by.
- Other events display performed_by with business label for event type.

### Fixed Fields

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

phone_line, allocation, employee, and performed_by are nullable FKs with SET_NULL.
Snapshots retain meaning after physical operational deletion. operation_id is
UUID shared by all events from one user operation. occurred_at is business
change time; recorded_at is DB write time.

### Snapshot Schema

~~~json
{
  "action": {
    "code": "reconnect_whatsapp",
    "label": "Reconectar WhatsApp"
  },
  "note": "WhatsApp desconectado; aguardando atendimento",
  "technical_responsible": {
    "id": 34,
    "name": "Ana Tecnica",
    "email": "ana@empresa.com"
  },
  "line_status": {
    "code": "active",
    "label": "Ativa"
  },
  "resolution": {
    "is_resolved": false,
    "resolved_at": null
  },
  "source_state": {
    "day": null,
    "pendency_submitted_at": "2026-09-10T14:32:18.413-03:00",
    "last_submitted_action": {
      "code": "reconnect_whatsapp",
      "label": "Reconectar WhatsApp"
    }
  }
}
~~~

technical_responsible is null when unassigned. action.code is no_action when no
pendency action is open. Non-applicable fields are null, not omitted.
source_state.day applies to DailyUserAction. pendency_submitted_at and
last_submitted_action apply to AllocationPendency. Store choice code and label
to preserve historical UI.

### Full Event Example

~~~json
{
  "id": 1842,
  "event_type": "OPENED",
  "source": "ALLOCATION_PENDENCY",
  "source_object_id": 771,
  "operation_id": "93b7ba42-8e55-4e2d-a152-25e0e20e4c13",
  "payload_version": 1,
  "occurred_at": "2026-09-10T14:32:18.413-03:00",
  "recorded_at": "2026-09-10T14:32:18.419-03:00",
  "phone_line_id": 102,
  "allocation_id": 455,
  "employee_id": 88,
  "performed_by_id": 12,
  "phone_number_snapshot": "+5511999999999",
  "allocation_id_snapshot": 455,
  "employee_name_snapshot": "Maria Silva",
  "performed_by_name_snapshot": "Joao Admin",
  "performed_by_email_snapshot": "joao@empresa.com",
  "before_state": {
    "action": {"code": "no_action", "label": "Sem Acao"},
    "note": "",
    "technical_responsible": null,
    "line_status": {"code": "active", "label": "Ativa"},
    "resolution": {"is_resolved": false, "resolved_at": null},
    "source_state": {
      "day": null,
      "pendency_submitted_at": null,
      "last_submitted_action": null
    }
  },
  "after_state": {
    "action": {
      "code": "reconnect_whatsapp",
      "label": "Reconectar WhatsApp"
    },
    "note": "WhatsApp desconectado; aguardando atendimento",
    "technical_responsible": null,
    "line_status": {"code": "active", "label": "Ativa"},
    "resolution": {"is_resolved": false, "resolved_at": null},
    "source_state": {
      "day": null,
      "pendency_submitted_at": "2026-09-10T14:32:18.413-03:00",
      "last_submitted_action": {
        "code": "reconnect_whatsapp",
        "label": "Reconectar WhatsApp"
      }
    }
  }
}
~~~

## Persistence and Immutability

Only central audit service creates events. It writes operational mutation and
event in one transaction. Application workflows and admin have no update or
delete path for audit events.

Required indexes:

- phone_line, occurred_at DESC
- allocation, occurred_at DESC
- employee, occurred_at DESC
- event_type, occurred_at DESC
- source, source_object_id
- operation_id

## Read Contract

Timeline reads use existing visible-phone-line queryset. Events without a phone
line are excluded from line timeline and remain for future employee reporting.

## Migration and Rollback

New table and indexes only. No data migration. Rollback stops new code but does
not delete recorded audit facts.

## Test Strategy

- Unit: event type and complete snapshot serialization.
- Integration: every DailyUserAction and AllocationPendency write path.
- Transaction: mutation and event commit/roll back together.
- Retention: FK deletion retains readable snapshots.
- Permission: query obeys existing line visibility.
- Reporting: entries, resolutions, reopens, durations.

~~~powershell
.\venv\Scripts\python.exe manage.py test telecom dashboard pendencies --settings=config.settings_dev -v 2
~~~

## Boundaries

Always: central service, atomic write, append-only facts, preserve current
PhoneLineHistory behavior.

Ask first: new event type, payload-version change, retention/purge, backfill.

Never: infer lost transitions, overwrite/delete events through application
code, expand read access.

## Success Criteria

- Every approved type has full before/after states.
- Every event identifies source, event executor, time, line, allocation, employee when available.
- Operational deletion cannot make retained event unreadable.
- Timeline reconstructs lifecycle from deployment onward.
- Existing workflows remain compatible outside new audit writes.

## Out of Scope

- Historical reconstruction before deployment.
- Replacing PhoneLineHistory.
- New dashboard/report UI.

## Implementation Status (Core, 2026-09-10)

Core plan (docs/superpowers/plans/2026-09-10-line-daily-action-audit-core.md)
Tasks 1-5 implemented on `main`:

- `telecom.LineDailyActionAuditEvent` (append-only, immutable `save()` guard)
  plus manual migration `telecom/migrations/0017_line_daily_action_audit_event.py`.
- `telecom/daily_action_audit.py`: central snapshot builders
  (`build_pendency_state`, `build_daily_user_action_state`) and
  `record_line_daily_action_event`.
- `pendencies/views.py`: ownership-gated PendencyUpdateView/ClaimView/ReleaseView,
  one `operation_id` per request, mutation + event(s) in one `transaction.atomic`.
- `dashboard/views.py`: `daily_user_action_board` POST wrapped in
  `transaction.atomic`, emits OPENED/REOPENED/ACTION_CHANGED/NOTE_CHANGED/
  RESOLVED/LINE_STATUS_CHANGED for the legacy DailyUserAction source.

Clarification resolved during implementation: the "unassigned pendency: admin
may only assume" rule applies only while the pendency has an open action
(`action != no_action`). With no open action, admin behavior is unchanged
(free edit of note/line status), preserving pre-existing tests.

### Test evidence

~~~text
manage.py test telecom pendencies dashboard.tests dashboard.tests.test_daily_line_action_audit
  dashboard.tests.test_blocked_lines_card dashboard.tests.test_daily_action_criticality
  dashboard.tests.test_dashboard_counts_performance dashboard.tests.test_dashboard_query_service
  dashboard.tests.test_manager_dashboard_removed_supervisor dashboard.tests.test_pendency_metrics_service
  dashboard.tests.test_pendency_metrics_view dashboard.tests.test_reconnect_counter
  dashboard.tests.test_daily_action_total_card dashboard.tests.test_pending_cards_consistency
  --settings=config.settings_dev
Ran 314 tests ... OK

manage.py check --settings=config.settings_dev
System check identified no issues (0 silenced).
~~~

`manage.py test dashboard` (bare app label) cannot run in this repo: it
pre-dates this work — `dashboard/tests.py` and `dashboard/tests/` coexist,
which breaks unittest discovery on the app label. Verified on a clean stash
of this branch's changes; worked around by testing `dashboard.tests` (the
file) and each `dashboard/tests/test_*` module explicitly, as shown above.

`manage.py migrate telecom 0017 --plan` / `showmigrations telecom` against
the real Postgres service could not be run in this sandbox: `docker compose`
needs a local `.env` with `DB_PASSWORD` that does not exist here, and the
`db` hostname only resolves inside that compose network. Equivalent
verification was done instead: migration 0017 applies cleanly against the
sqlite backend `manage.py test` always uses (see the 314-test run above,
which creates the schema from migrations on every run), and it is the only
new/pending operation added to the `telecom` app.
