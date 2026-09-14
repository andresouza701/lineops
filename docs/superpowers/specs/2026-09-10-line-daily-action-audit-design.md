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

DAILY_USER_ACTION, ALLOCATION_PENDENCY, LINE_ALLOCATION.

LINE_ALLOCATION is used for every LINE_STATUS_CHANGED event raised from
Ações do Dia: `source_object_id` is the LineAllocation pk, not a
DailyUserAction pk. A line-status change can happen with no DailyUserAction
row at all, so DAILY_USER_ACTION must never be used with a fabricated
allocation id as source_object_id.

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

T6 (unified line timeline read screen) was originally listed here as "New
dashboard/report UI" and is now implemented — see below. It extends the
existing `telecom:phoneline_history` screen and read authorization; it does
not replace `PhoneLineHistory` as a table, and does not touch writes,
triggers, permissions, pendencies, dashboard, or CSV export.

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

## P1/P2 Audit Fixes (Core, follow-up)

Four gaps found in review of the Core implementation, fixed:

1. **LINE_STATUS_CHANGED source.** Added `Source.LINE_ALLOCATION` (migration
   0018, choices metadata only). Every line-status change from Ações do Dia
   now emits exactly one LINE_STATUS_CHANGED event with
   `source=LINE_ALLOCATION` and `source_object_id=allocation.pk`, whether or
   not a same-day DailyUserAction exists. A new action opened in the same
   POST still gets its own OPENED event (source=DAILY_USER_ACTION), sharing
   the request's `operation_id`.
2. **Real append-only.** `LineDailyActionAuditEvent` now has a custom
   manager/queryset that raises `ValidationError` on `.update()` and
   `.delete()` (instance and queryset), on top of the existing immutable
   `save()` guard. Django's own `SET_NULL` cascade (phone_line/allocation/
   employee/performed_by) bypasses the ORM queryset layer internally, so
   retention on physical deletion still works. Migration 0019 adds the same
   protection at the Postgres level (BEFORE DELETE/UPDATE triggers), no-op
   on sqlite; it explicitly allows only a filled-FK-to-NULL transition.
3. **Locking order in `daily_user_action_board`.** The view now locks the
   `LineAllocation` (or `Employee`, when there is no allocation) row with
   `select_for_update()` before reading or deciding anything, then reads
   `DailyUserAction` with `select_for_update()` too. `update_or_create()` was
   replaced with an explicit locked read + create/update to keep snapshot
   and event decisions consistent with the locked state.
4. **`scripts/resolve_old_actions.py`.** No longer bulk-updates. Delegates to
   `telecom.daily_action_audit.resolve_old_daily_user_actions()`, which
   resolves one `DailyUserAction` at a time inside `transaction.atomic()`
   with `select_for_update()`, and records a RESOLVED event per row
   (`performed_by=None`, one `operation_id` per script run). No backfill.

Test evidence:

~~~text
manage.py test telecom pendencies dashboard.tests dashboard.tests.test_daily_line_action_audit
  dashboard.tests.test_daily_line_action_audit_fixes --settings=config.settings_dev
Ran 330 tests ... OK (skipped=1)
~~~

The 1 skip is `test_postgres_trigger_blocks_raw_sql_delete_and_content_update`,
guarded to run only against a real Postgres backend (unavailable here, same
`.env`/`docker compose` blocker as above).

## T3: Service Hardening (Core, follow-up)

`record_line_daily_action_event()` in `telecom/daily_action_audit.py` now
enforces two invariants directly, instead of relying on every caller to get
them right:

1. **Active transaction required.** The service checks
   `connection.in_atomic_block` before any insert. Outside an active
   transaction it raises `RuntimeError("Auditoria exige transaction.atomic().")`
   — no event is created, no `operation_id` is generated, the error is not
   masked. **Caller opens `transaction.atomic()`; the service requires it but
   never opens its own.** The service cannot start its own transaction around
   just the append: the operational mutation that must land atomically with
   the audit event is executed by the caller (a view, a script loop) before
   the append call, so only a transaction that already encloses both can give
   the "both commit or both roll back" guarantee. This was true before T3 too;
   T3 only adds the explicit guard so a caller that forgets `atomic()` fails
   loudly instead of writing an unprotected event.
2. **Material no-op returns `None`.** When `before_state == after_state`
   (deep equality of the full JSON), the service does not insert a row and
   returns `None` instead of a `LineDailyActionAuditEvent`. The service still
   does not decide `event_type` — callers keep deciding semantics — this only
   suppresses the write when the snapshot truly did not change.

No schema, migration, PostgreSQL trigger, or pendency-rule change. Every
production caller (`dashboard.views`, `pendencies.views`,
`scripts/resolve_old_actions.py` via `resolve_old_daily_user_actions()`) was
already calling the service from inside `transaction.atomic()` and already
computing before/after snapshots that materially differ before calling it, so
no caller behavior changed.

### Test evidence

~~~text
manage.py test telecom pendencies dashboard.tests dashboard.tests.test_daily_line_action_audit
  dashboard.tests.test_daily_line_action_audit_fixes --settings=config.settings_dev -v 2
Ran 334 tests ... OK (skipped=1)

manage.py check --settings=config.settings_dev
System check identified no issues (0 silenced).
~~~

New coverage in `telecom/tests.py`:

- `LineDailyActionAuditGuardTest` (`TestCase`): identical before/after states
  return `None` and create zero events; a material difference returns the
  event with snapshots, actor, references, `occurred_at`, and `operation_id`
  preserved.
- `LineDailyActionAuditAtomicRequiredTest` (`TransactionTestCase`, not
  `TestCase` — `TestCase` already wraps each test in an implicit transaction,
  which would mask the guard): calling the service with no active transaction
  raises `RuntimeError` and creates zero events.
- Existing `LineDailyActionAuditIntegrityTest` rollback test
  (`test_exception_after_mutation_rolls_back_operational_change_and_event`)
  still covers mutation+event rollback together; it needed no change since it
  already used a materially-different before/after pair.

Five pre-existing tests passed identical `before_state`/`after_state` objects
to the service to check unrelated behavior (`operation_id` sharing, snapshot
fields, null-phone_line handling, FK-deletion retention). Under the new no-op
guard those calls would have returned `None` where the test expected an
event, so their `after_state` was changed to a materially different value
(same intent, real event returned) without touching what each test actually
asserts.

## T6: Unified Line Timeline (Core, follow-up)

Read-only screen: `telecom:phoneline_history` now shows a single timeline
mixing `PhoneLineHistory` (legacy) and `LineDailyActionAuditEvent` (new),
without deduplicating — the same business change can legitimately produce
one row in each table, and both are shown as distinct facts from distinct
sources.

### Query contract

- **Sources and identity**: legacy rows get a fixed `source` of
  `PHONE_LINE_HISTORY` (not a `LineDailyActionAuditEvent.Source` choice, just
  a literal used for timeline identity); new rows keep their real `source`
  (`DAILY_USER_ACTION`, `ALLOCATION_PENDENCY`, `LINE_ALLOCATION`).
- **Ordering**: `occurred_at DESC, source ASC, source-row-id DESC`, stable.
  Legacy `occurred_at` is `PhoneLineHistory.changed_at`; new is
  `LineDailyActionAuditEvent.occurred_at`.
- **Filters** (GET `start_date`, `end_date`, `event_type`, `actor_id`,
  `allocation_id`, `page`): all parsed tolerantly — an invalid value (bad
  date, non-numeric id) becomes "filter absent," never a 500. `start_date`/
  `end_date` are inclusive full-day bounds in the current timezone.
  `event_type` filters `PhoneLineHistory.action` and
  `LineDailyActionAuditEvent.event_type` independently (the two choice sets
  never overlap). `actor_id` filters `changed_by_id` / `performed_by_id`.
  `allocation_id` excludes the legacy source entirely (no historical
  allocation on `PhoneLineHistory` to filter or infer) and filters
  `LineDailyActionAuditEvent.allocation_id` on the new source; combined with
  the existing `phone_line` scope, an allocation id from another line simply
  matches nothing — it cannot leak another line's rows.
- **Scope**: unchanged — `get_visible_phone_lines_queryset(request.user)`,
  404 outside it. Events with `phone_line=None` never appear in any line's
  timeline (existing Read Contract, unchanged).
- **Pagination (DB-side, 50/page)**: both sources are projected to the same
  three columns (`row_source`, `row_id`, `sort_at`) via `.values()`, filtered
  *before* combining, then joined with `QuerySet.union(..., all=True)` (or
  used alone when `allocation_id` drops the legacy branch) and finally
  `.order_by(...)`. Django's `Paginator` runs against that combined
  queryset, so `count()` and the page slice are both single SQL queries with
  `LIMIT`/`OFFSET` — the full history is never materialized in Python.
  A backend restriction (`ORDER BY not allowed in subqueries of compound
  statements`) meant each branch first needed `.order_by()` (clearing the
  model's `Meta.ordering`) before `.values()` — only the final combined
  queryset carries an `ORDER BY`.
- **Hydration**: only the current page's ids are split by source, then
  loaded in at most two queries — `PhoneLineHistory.objects.filter(pk__in=...)
  .select_related("changed_by")` and `LineDailyActionAuditEvent.objects
  .filter(pk__in=...).select_related("performed_by", "allocation",
  "employee")` — and assembled in memory into plain `LineTimelineItem` DTOs
  in page order. The template only reads DTO attributes (strings/datetimes),
  never model instances, so it cannot trigger lazy queries.

### Read model

- New module `telecom/line_timeline.py`: `LineTimelineFilters` (parsing/
  validation), `LineTimelineItem` (render DTO), `get_line_timeline_page`
  (union + paginate + hydrate), `get_line_timeline_filter_options` (dropdown
  choices), `has_line_activity` (distinguishes "no activity at all" from "no
  match for current filters" in the empty state).
- `telecom.views.PhoneLineHistoryView` (the view actually wired to
  `telecom:phoneline_history` — `telecom/views_history.py` holds an
  unrelated, unused/orphaned `PhoneLineHistoryView` that nothing imports;
  left untouched) changed from `DetailView` (whose `paginate_by = 50` never
  actually paginated `context["history"]`, per the confirmed gap) to a plain
  `View` that resolves scope, parses filters, calls the service, and renders.
- Actor label: current FK name/email, else `performed_by_name_snapshot`,
  else `performed_by_email_snapshot`, else "Sistema" (legacy: FK or
  "Sistema" — it has no snapshot). Allocation label: `#<allocation_id>` when
  the FK is live, `#<allocation_id_snapshot> (removida)` when only the
  snapshot survives, `-` for legacy rows (no allocation concept there).
  Before/after: legacy uses `old_value`/`new_value` plain text; new events
  render `json.dumps(..., ensure_ascii=False, indent=2, sort_keys=True)` —
  never `|safe`, so Django's autoescaping keeps the JSON safe in the
  template.

### Test evidence

New module `telecom/tests_line_timeline.py` (not `telecom/tests.py`, which
already has 5000+ lines; not a `telecom/tests/` package either, since
`telecom` — unlike `dashboard` — has only `tests.py` today, and adding a
package alongside it would reproduce the exact discovery break already
documented above for `dashboard`). 19 tests, covering: source mixing +
global ordering, DB-driven pagination across pages (`assertNumQueries`
proves the query count from a page request does not depend on total row
count), scope (200/404/cross-line isolation), all four filters including
inclusive date bounds and the allocation/legacy exclusion and cross-line
non-leak, phone_line-less events never appearing, legacy/new compatibility
(original `PhoneLineHistory` rows unmodified), N+1 absence, and the UI
(sources, filters, both tables, paginated querystring preservation, the two
distinct empty states).

~~~text
manage.py test telecom.tests_line_timeline --settings=config.settings_dev -v 2
Ran 19 tests ... OK

manage.py test telecom --settings=config.settings_dev -v 1
manage.py test dashboard.tests pendencies --settings=config.settings_dev -v 1
manage.py check --settings=config.settings_dev
~~~

(Full-suite and `check` output recorded at delivery time in the task report,
not duplicated here.)

No migration, no schema change, no change to writes, the PostgreSQL
immutability triggers, permissions, pendencies, the dashboard, or the legacy
CSV export.
