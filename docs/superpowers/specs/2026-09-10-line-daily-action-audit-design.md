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

## T7: Line Operational Report (read model, follow-up)

Read-only screen + CSV export: `telecom:line_operational_report` /
`telecom:line_operational_report_csv`. One row per phone line summarizing
**cycles** derived exclusively from `LineDailyActionAuditEvent` — never from
`PhoneLineHistory` (legacy, T6-only), and never inferred from the current
state of `DailyUserAction`, `AllocationPendency`, `LineAllocation`, or any
JSON snapshot. Pure read: no `.create()`/`.update()`/`.delete()` against the
audit table or any other model.

### Cycle model

- **Cycle-opening events**: `OPENED`, `REOPENED`.
- **Cycle-closing events**: `RESOLVED`.
- **Non-cycle events**: `RESPONSIBLE_ASSIGNED`, `RESPONSIBLE_RELEASED`,
  `ACTION_CHANGED`, `NOTE_CHANGED`, `LINE_STATUS_CHANGED` — never open or
  close a cycle, but are eligible as "last action."
- **Cycle key**: `(phone_line_id, source, source_object_id)`. Sources never
  cross, even on a colliding `source_object_id` — a `DAILY_USER_ACTION` id 7
  and an `ALLOCATION_PENDENCY` id 7 are unrelated keys.
- **Sequencing**: per key, events are read `occurred_at ASC, id ASC`
  (stable order) and folded into cycles with a single pass: an
  opening event starts a cycle if none is currently open for that key;
  the next `RESOLVED` for that key closes the currently-open cycle.
- **Inconsistent legacy data is preserved, not corrected**:
  - A `RESOLVED` with no open cycle for its key is an orphan — it closes
    nothing and creates no cycle.
  - An opening event while a cycle is already open for that key does **not**
    close the previous cycle — the previous cycle stays open and a second,
    independent cycle starts. Both can be open at once for the same key.
    This mirrors historical data quality rather than papering over it.

### Temporal filter

- GET `start_date`, `end_date` (`YYYY-MM-DD`), parsed the same tolerant way
  as T6 (`LineTimelineFilters`-style): missing or unparseable is "filter
  absent," never a 500. Bounds are inclusive full-day, in the current Django
  timezone.
- **Reference instant**: `timezone.now()` when `end_date` is absent;
  otherwise the end of that day (`end_date` 23:59:59.999999 local). All
  "current state" columns (situação, duração aberta, última ação/ator) are
  computed **as of the reference instant** — events after it are never read,
  so passing `end_date` reproduces the report exactly as it stood at the end
  of that day, regardless of what happened later.
- **Cycle/period overlap**: a cycle appears when `opened_at <= fim` and
  (`resolved_at` is absent or `resolved_at >= inicio`), where `fim` is the
  reference instant and `inicio` is `start_date`'s start-of-day or absent
  (`-∞`). An open cycle started before the period still appears, since its
  "close" is unbounded.
- A phone line appears in the report only when at least one of its cycles
  overlaps the period. Lines with zero qualifying audit events (or whose
  only events are outside the period and produce no overlapping cycle) do
  not produce an all-zero row — the report is event-driven by design, not a
  listing of every visible line.

### Columns

- **Número**: `phone_line.phone_number`.
- **Entradas**: count of `OPENED`/`REOPENED` events for the line with
  `occurred_at` inside the filtered period (independent of which cycle they
  belong to).
- **Saídas**: count of `RESOLVED` events for the line inside the period
  (orphans included — an orphan `RESOLVED` is still a fact that happened).
- **Ciclos**: count of cycles (built up to the reference instant) that
  overlap the period.
- **Situação**: `Aberta` when the line has any cycle with no `RESOLVED` yet
  as of the reference instant; otherwise `Resolvida`. This falls directly
  out of the cycle fold — no separate "current status" query.
- **Duração aberta**: for a line with one open cycle, `referência -
  opened_at` of that cycle. With more than one simultaneously open cycle
  (see inconsistent-data case above), shows the count and the duration of
  the **oldest** open cycle. `-` when there is no open cycle.
- **Última ação** / **Último ator**: the single most recent audit event for
  the line with `occurred_at <= referência`, tie-broken
  `occurred_at DESC, id DESC` — any event type qualifies, including
  non-cycle ones. Actor resolution: live `performed_by` FK, else
  `performed_by_name_snapshot`, else `performed_by_email_snapshot`, else
  `"Sistema"` — same fallback chain as T6. `PhoneLineHistory` is never a
  candidate.

### Scope, routes, CSV

- Scope: `get_visible_phone_lines_queryset(request.user)`, identical to T6 —
  no new permission surface. No `phone_line_id` GET/POST parameter is
  accepted anywhere in this feature; scope comes only from the visible
  queryset, so it cannot be widened from outside.
- Routes, both under `telecom/`, added to `telecom/urls.py` without touching
  the T6 route: `telecom:line_operational_report` (HTML) and
  `telecom:line_operational_report_csv` (CSV). View lives in
  `telecom/views.py`; the read model lives in
  `telecom/line_operational_report.py`; template in
  `templates/telecom/line_operational_report.html`.
- HTML paginates 50 rows/page (Django `Paginator`), preserving `start_date`/
  `end_date` in pagination links, same pattern as T6's querystring
  preservation. CSV always exports the **full** filtered+scoped result set,
  UTF-8 with a BOM (`﻿`, matching `dashboard`'s existing CSV export
  convention) so Excel opens accented characters correctly — independent of
  whatever HTML page the user was on.

### Read model and query cost

- `telecom/line_operational_report.py` exposes: `LineOperationalReportFilters`
  (GET parsing, mirroring `LineTimelineFilters`), `_Cycle` (internal
  fold result), `LineOperationalReportRow` (render DTO — plain values only,
  no lazy FK access from the template), and
  `build_line_operational_report(phone_lines_queryset, filters)` returning
  all matching rows (unpaginated) for both the HTML view (which paginates in
  Python/`Paginator`) and the CSV view (which streams all of them).
- **Query cost**: one query loads the scoped, non-deleted phone lines
  (`values("id", "phone_number")` — no full `PhoneLine` objects). One query
  loads every `LineDailyActionAuditEvent` for those line ids with
  `occurred_at <= referência`, ordered `phone_line_id, occurred_at, id`,
  projected with `.values(...)` to the handful of fields the fold needs
  (including snapshot columns, so no second trip is needed to resolve an
  actor). A third, small query resolves the still-live `performed_by` users
  for the page's "last actor" column in one batch
  (`SystemUser.objects.filter(pk__in=...)`) — never per-row. Total query
  count is constant with respect to the number of qualifying lines or
  events (verified via `assertNumQueries` with a small and a large fixture).
  The event fold itself is a single Python pass over the ordered event list,
  grouped by `(phone_line_id, source, source_object_id)` in memory — no
  per-key queries.
- No migration: no schema change, purely additive read-side module.

### Limitations (explicit, matching the closed contract)

- Reports lines with at least one overlapping cycle only — a line with only
  non-cycle events, or with zero audit history, never appears, even inside
  its own visible scope.
- Simultaneous open cycles on the same key show only the oldest one's
  duration (with a count) — the UI does not enumerate every open cycle
  inline; the full detail remains available via the T6 timeline.
- `PhoneLineHistory` never contributes to any column — this is intentional
  per the closed contract, not an oversight; it remains T6-only.

## T8: Retention Under Physical Deletion (proof, no code change)

Proves physical deletion of operational objects never deletes
`LineDailyActionAuditEvent`; it only nullifies FKs that point to rows
physically deleted by that operation. Snapshots and the append-only fact
stay readable.
Current behavior already satisfied this contract — delivery is test
coverage only, **no migration, no schema change, no production code
change**.

### FK map found (SET_NULL on the event, unchanged)

`LineDailyActionAuditEvent.phone_line`, `.allocation`, `.employee`,
`.performed_by` are the only four FKs the event itself carries, all
`on_delete=SET_NULL`, all nullable — set in the original core design (see
above) and re-verified here, not changed:

- `phone_line` → `telecom.PhoneLine`
- `allocation` → `allocations.LineAllocation`
- `employee` → `employees.Employee`
- `performed_by` → `settings.AUTH_USER_MODEL` (`users.SystemUser`)

Each has a matching `*_snapshot` field (`phone_number_snapshot`,
`allocation_id_snapshot`, `employee_name_snapshot`,
`performed_by_name_snapshot`/`performed_by_email_snapshot`) that keeps
identity readable once the FK goes `NULL`.

### Sources without an audit FK

`DailyUserAction` and `AllocationPendency` are never a FK target of the
event — the event references them only through `source` +
`source_object_id`. Physically deleting either row leaves the event
completely untouched (including `source_object_id`, JSON states, and every
snapshot); neither model has a custom `delete()`, so instance
`.delete()` is already the real physical path for both.

### Domain rules left untouched (explicitly out of scope)

T8 changed no `on_delete` value, no `CASCADE`/`PROTECT`, no soft-delete, and
no business `delete()` override:

- `PhoneLine.delete()` / `SIMcard.delete()` / `Employee.delete()`: unchanged
  soft-delete.
- `LineAllocation.delete()`: still raises `BusinessRuleException` (deletion
  by design is not allowed through the business path).
- `LineAllocation.employee` / `.phone_line`: still `PROTECT`.
- `DailyUserAction.allocation` / `.employee`, `AllocationPendency.allocation`
  / `.employee`, `PhoneLineHistory.phone_line`,
  `WhatsappReconnectHistory.phone_line`: still `CASCADE`.
- `LineDailyActionAuditEvent` save/delete guards and the Postgres
  immutability trigger (migration 0019): unchanged.

Where a business `delete()` blocks or soft-deletes, retention is proven
through the same physical path already used elsewhere in this codebase for
the same reason: a raw manager/queryset bypass that skips the custom
instance method — `LineAllocation.objects.filter(pk=...).delete()`,
`Employee.all_objects.filter(pk=...).delete()`,
`PhoneLine.all_objects.filter(pk=...).delete()` (the `all_objects` manager
has no queryset-level override, unlike `objects`) — never raw SQL, never a
disabled trigger/guard.

### Snapshot preservation and full-field integrity

For every one of the four FK deletions, a full-field comparison (id,
source, source_object_id, event_type, occurred_at, operation_id,
payload_version, before_state, after_state, all four FK ids, all
snapshots) proves only FK columns whose referenced rows were deleted by the
operation change — nothing else drifts.

### Indirect cascade covered

Deleting a `LineAllocation` physically (via the same raw-queryset path,
since its business `delete()` blocks) cascades to any `DailyUserAction` and
`AllocationPendency` rows still pointing at it (`on_delete=CASCADE`,
unchanged) — both operational sources disappear, both audit events for them
survive with `allocation_id=NULL` and `allocation_id_snapshot` intact.

### Migration

None. No schema or model change was required — the existing `SET_NULL` FKs,
the append-only guards, and the Postgres trigger from migrations 0017/0019
already implement this contract in full.

### Test evidence

New module `telecom/tests_line_daily_action_audit_retention.py` — adds only
what was not already covered in `telecom/tests.py`
(`LineDailyActionAuditEventTest`, `LineDailyActionAuditIntegrityTest`):
`DailyUserAction`/`AllocationPendency` physical deletion (source without
FK), `PhoneLine` FK deletion, the `LineAllocation` → `DailyUserAction`/
`AllocationPendency` indirect cascade, and one full-field-integrity check
across all four FK types. `SystemUser` (`performed_by`), `LineAllocation`
(`allocation`), and `Employee` retention were already proven in
`telecom/tests.py` and are not duplicated.

~~~text
manage.py test telecom.tests_line_daily_action_audit_retention --settings=config.settings_dev -v 2
Ran 5 tests ... OK

manage.py test telecom --settings=config.settings_dev -v 1
Ran 254 tests ... OK (skipped=1)

manage.py test dashboard.tests pendencies --settings=config.settings_dev -v 1
Ran 126 tests ... OK

manage.py check --settings=config.settings_dev
System check identified no issues (0 silenced).
~~~

One RED was hit while writing the new tests — a test-authoring bug, not a
production one: an early draft of the `PhoneLine` retention test recorded
its event against the shared `LineAllocation` from `setUp`, then deleted
that same `LineAllocation` first (a required step to clear the `PROTECT` on
`phone_line` before deleting it). That correctly nulled the event's own
`allocation_id` too — an assertion the test hadn't accounted for. Fixed by
recording that event with `allocation=None`, isolating the test to the one
FK it means to prove. No production file changed to reach GREEN.

## T9: Existing Data and Rollout (no backfill, deploy/rollback runbook)

Documentation-only. No model, migration, or event code touched. No commit/push
performed as part of this task.

### 1. No-backfill decision (confirmed, impact)

- No script, data migration, SQL, or job will ever create
  `LineDailyActionAuditEvent` rows for anything that happened before this
  feature deploys. No `BASELINE_IMPORTED` event type exists or will be added.
- `PhoneLineHistory` (legacy) is unchanged and stays queryable — T6 already
  reads it side by side with the new table (see T6 above) — but it is never
  converted into `LineDailyActionAuditEvent` rows. There is no reconstruction
  of prior versions, entries, exits, or cycles.
- Consequence for T6: a line's timeline shows two independent fact sources.
  Anything before deploy only ever appears as `PHONE_LINE_HISTORY` rows (if
  legacy code wrote one); anything after deploy also gets the new, richer
  audit rows. This is the existing, already-implemented behavior — no code
  change is required for T9.
- Consequence for T7: `build_line_operational_report()` derives cycles
  exclusively from `LineDailyActionAuditEvent` (see T7 above). A line with
  zero audit events — because all its activity predates deploy — produces no
  row at all; this is the existing "event-driven, not a listing of every
  line" contract, not an error state. No line will show a false "never
  touched" cycle count of zero; it simply will not appear until its first
  post-deploy event. This already matches the approved contract with no
  further change needed.
- Practical impact for operators: on deploy day, the T6 timeline and T7
  report will look "empty" or sparse for lines with no activity yet under
  the new code, even though `PhoneLineHistory` may show years of legacy
  rows for the same line. That gap is intentional, not a bug: it closes
  itself as real post-deploy events accumulate.

### 2. Migrations and dependencies

The initial additive rollout uses `0017`-`0019`. A corrective `0020` follows
them: it aligns the audit event primary-key type with the project's
`DEFAULT_AUTO_FIELD` and must be applied before treating the migration drift
check as clean.

| Migration | Effect | Depends on |
| --- | --- | --- |
| `telecom.0017_line_daily_action_audit_event` | Creates `LineDailyActionAuditEvent` table + indexes | `AUTH_USER_MODEL` swappable dep, `allocations.0008_alter_lineallocation_line_status`, `employees.0020_rename_heineki_portfolio`, `telecom.0016_alter_phonelinehistory_action_reactivated` |
| `telecom.0018_linedailyactionauditevent_source_line_allocation` | Adds `LINE_ALLOCATION` to `source` choices (metadata only, no column/constraint change) | `telecom.0017` |
| `telecom.0019_linedailyactionauditevent_db_immutability` | Postgres `BEFORE DELETE`/`BEFORE UPDATE` triggers blocking mutation of any field except the four FKs transitioning to `NULL`; no-op on sqlite | `telecom.0018` |
| `telecom.0020_alter_linedailyactionauditevent_id` | Changes only the audit event PK from `AutoField` to the project-standard `BigAutoField`; does not write or delete audit events and does not alter trigger behavior | `telecom.0019` |

The first three are purely additive (new table, new trigger functions scoped to
that one table, a choices-metadata change with no DB constraint). None
alters an existing column, index, or table that old code reads or writes.
This is what makes "apply 0017-0019 while the previous release is still
serving traffic" safe: the old code never queries
`telecom_linedailyactionauditevent` and is not affected by triggers scoped
to it. `0020` is a narrow schema correction: it is required only because
`0017` was handwritten with `AutoField` while the project default is
`BigAutoField`; it preserves every audit fact and the immutability trigger.

`allocations.0008` and `employees.0020` must already be applied for `0017`
to apply — both predate this feature branch by several commits and are
already on `main`'s migration graph; not re-verified individually here
since `0017` itself was already exercised end-to-end by the 254-test
`telecom` run (§6).

### 3. Deploy order (real mechanism, mapped from this repo)

Mapped from `docker-compose.prod.yml`, `docker-entrypoint.sh`, and
`README.md` (§"Produção com Docker Compose") — no host, container, or
command below is invented.

Confirmed real facts:

- Prod stack: `docker-compose.prod.yml`, three services — `db`
  (`lineops-db-prod`, Postgres 15.8), `web` (`lineops-app-prod`, built from
  this repo's `Dockerfile`), `nginx` (`lineops-nginx-prod`, TLS
  termination). Deploy root on the box: `/opt/app/src/lineops` (confirmed by
  reading `scripts/backup_db.sh`, and by `ls`-ing that exact path over SSH —
  see §6, it exists and contains this repo's layout, owned by `appuser`).
  `.env.prod` exists at that path (confirmed present, not read).
- `docker-entrypoint.sh` (the `web` image's entrypoint) always runs, in
  order, on every container start: `wait_for_db` → `manage.py migrate
  --noinput` (if `RUN_MIGRATIONS=1`, the prod default) → `manage.py
  collectstatic --noinput` (if `COLLECT_STATIC=1`, the prod default) →
  `exec "$@"` (starts the app server). **Migration and new code are coupled
  by default**: a plain `docker compose -f docker-compose.prod.yml up -d
  --build` rebuilds the image with the new code *and* migrates in the same
  container start, with no window where 0017-0019 are applied while the
  previous release's container is still the one serving traffic.
- To honor the approved order (migrate first, old code still serving, code
  deploy second) inside this real tooling, the migration step must run in a
  *separate, disposable* container built from the new image, before the
  running `web` container is replaced:

Pre-deploy (once per release, read-only/backup steps first):

```bash
ssh lineops-prod
cd /opt/app/src/lineops

# 1. Backup current DB state (existing cron script, run manually here;
#    requires docker access — see §6 for who currently has it)
./scripts/backup_db.sh
# or, equivalently, ad hoc:
docker exec lineops-db-prod pg_dump -U "$DB_USER" "$DB_NAME" \
  | gzip > /opt/backups/lineops/lineops_pre_t9_$(date +%Y%m%d_%H%M%S).sql.gz

# 2. Pull/checkout the release commit
git fetch --all
git checkout <release-tag-or-commit>

# 3. Confirm exact pending plan before touching anything
docker compose -f docker-compose.prod.yml exec web \
  python manage.py showmigrations telecom
docker compose -f docker-compose.prod.yml exec web \
  python manage.py migrate telecom --plan
```

Deploy (migrate on new code image, old container still serving, then swap):

```bash
# 4. Build the new image without starting it
docker compose -f docker-compose.prod.yml build web

# 5. Apply 0017-0019 from the NEW image, in a disposable container, while
#    lineops-app-prod (OLD code) is still up and serving via nginx.
#    COLLECT_STATIC=0 here: no need to touch static files before the swap.
docker compose -f docker-compose.prod.yml run --rm \
  -e RUN_MIGRATIONS=1 -e COLLECT_STATIC=0 -e WAIT_FOR_DB=1 \
  web python manage.py migrate --noinput

# 6. Confirm applied
docker compose -f docker-compose.prod.yml exec web \
  python manage.py showmigrations telecom

# 7. Swap old container for new code (entrypoint re-runs migrate — no-op,
#    already applied in step 5 — then collectstatic, then starts gunicorn)
docker compose -f docker-compose.prod.yml up -d --build

# 8. Restart nginx only if its own config changed (it did not for T9)
```

Post-deploy:

```bash
# 9. Health check
curl -k https://localhost/health/
curl -I https://lineops.somosglobal.com.br

# 10. Django system check inside the running container
docker compose -f docker-compose.prod.yml exec web \
  python manage.py check
```

If step 5 is skipped as unnecessary overhead, the simpler single-command
flow already documented in `README.md`
(`docker compose -f docker-compose.prod.yml up -d --build`) is equally
correct given the migrations are additive/backward-compatible (§2) — it
just collapses the "old code still running" window to zero, which the
approved order treats as the safer default rather than a strict
requirement.

**Checklist:**

- [ ] Pre: DB backup taken and verified non-empty (`gzip -t` or size check)
- [ ] Pre: on release commit/tag, working tree clean
- [ ] Pre: `showmigrations telecom` shows `0017`, `0018`, `0019` unapplied
      (`[ ]`), everything before `0016` applied (`[X]`)
- [ ] Pre: `migrate telecom --plan` output reviewed, matches §2's table
- [ ] Deploy: new image built (step 4)
- [ ] Deploy: `migrate --noinput` run from new image, exit code 0 (step 5)
- [ ] Deploy: `showmigrations telecom` now shows `0017`-`0019` applied
      (step 6)
- [ ] Deploy: `up -d --build` completed, `lineops-app-prod` healthy
      (`docker compose ps`, healthcheck `healthy`)
- [ ] Post: `/health/` returns `{"status": "ok"}`
- [ ] Post: `manage.py check` clean in the running container
- [ ] Post: PRD validation cycle executed or explicitly marked blocked (§4)

### 4. PRD validation procedure

**Status: BLOCKED — not executed.** Objective reasons, both confirmed this
session (see §6 for the actual commands run):

1. **No approved test line.** The contract requires an explicitly approved
   test line (masked id/number, no real user/customer, no active pendency)
   before any mutation. No such line was named or approved in this
   conversation. Per the contract, this is not something to improvise —
   delivering the procedure below, unexecuted, is the correct outcome.
2. **No privileged access to run/inspect containers in PRD from this
   session.** SSH to `lineops-prod` (`global@10.103.4.184`, per existing
   [[lineops-prod-ssh]] memory) works and was used read-only (§6). The
   `global` user is in group `wheel` but not `docker`, and `sudo -n docker
   ...` returned `sudo: a password is required` — no non-interactive
   privileged path exists to run `docker compose exec/run` for migration or
   validation commands. This blocks not just PRD validation but also steps
   5-7 of the deploy sequence in §3 until someone with docker/sudo access on
   that box executes them.

Procedure to run once both blockers are cleared (unexecuted; documented for
whoever has access and an approved line):

1. **Before mutating**, record: line id/number (masked, e.g. `+55119***9999`),
   current line status, current allocation, current pendency/action (or
   "none"), the executing user, and current timestamp. Keep this note to
   compare against the audit event afterward.
2. **Generate the event only through the real UI/API flow** — Ações do Dia
   board or the pendency endpoints (`PendencyUpdateView` /
   `PendencyClaimView` / `PendencyReleaseView`). Never insert a row via
   shell or SQL.
3. **Minimal reversible cycle** (preferred): open an allowed pendency
   action on the approved line, then resolve it through the authorized flow
   for the assigned technical responsible. The resulting events are
   permanent by design — do not attempt to delete them afterward; that is
   the append-only contract working as intended, not cleanup debt.
4. **Validate, in DB and app**:
   - `showmigrations telecom` shows `0017`-`0019` applied.
   - Exactly the expected event(s) exist in
     `telecom_linedailyactionauditevent` for that line/allocation.
   - `source`, `source_object_id`, `event_type`, `occurred_at`,
     `performed_by`, `before_state`, `after_state`, and all snapshot fields
     match what was recorded in step 1 / observed in the UI action.
   - The event appears on `telecom:phoneline_history` for that line (T6).
   - `telecom:line_operational_report` reflects the new cycle/state (T7) —
     entradas/saídas/ciclos/situação move as expected for that one line.
   - If the cycle was resolved (step 3), a separate `RESOLVED` event exists
     with its own `operation_id` distinct from the opening event's, both
     sharing the same `(phone_line, source, source_object_id)` cycle key.

### 5. Rollback

- **Code rollback is allowed**: redeploy a previous commit/release
  (`git checkout <previous-tag>` + repeat the build/up steps in §3). The
  entrypoint's `manage.py migrate --noinput` on the old code is a no-op for
  `0017`-`0019` since Django's migration state doesn't move backward on its
  own — the old code simply never queries the new table.
- **Never reverse `0017`-`0019` in PRD once any event exists.** No
  `migrate telecom 0016` in production after go-live. The table, its
  indexes, and the Postgres triggers stay in place regardless of which code
  version is running.
- **Events and the table are permanent** even if code rolls back. Rolling
  back code does not, and must not, delete recorded audit facts — there is
  no operational reason to "clean up" a rollback by removing append-only
  data, and doing so would violate the core design decision (Persistence
  and Immutability, above) and is blocked at the DB level for `DELETE`/
  content-`UPDATE` anyway (migration 0019 trigger).
- **Backward compatibility of the schema itself**: the new table, its
  indexes, and its triggers are scoped entirely to
  `telecom_linedailyactionauditevent`. Old code issues no queries against
  that table and no writes that the triggers would intercept, so old code
  runs identically whether `0017`-`0019` are applied or not. This is why
  §3's order (migrate first, code second) is safe rather than merely
  convenient.
- **If deploy fails before traffic/writes reach the new code** (e.g., step
  7 in §3 fails health check and `docker compose` is rolled back to the
  previous image): the migrations applied in step 5 stay applied — they are
  harmless to old code per the point above. Default is **no automatic
  reverse migration**. Record the operational decision (what failed, who
  decided, whether a reverse migration was chosen anyway) before running
  any `migrate telecom <earlier>` command; this is a deliberate manual
  gate, not an automated step.

### 6. Local validation actually run (this session)

Environment note: this machine's `manage.py test` forces the `sqlite3`
backend regardless of `--settings` (see `config/settings.py`,
`sys.argv[1] == "test"`) — that is what all test runs below used. Direct
`manage.py showmigrations` / `migrate --plan` (no `test` subcommand) use the
real configured backend, Postgres, via `DB_HOST=db` — resolvable only
inside the project's own `docker compose` network, which was not running
locally in this session (`docker compose ps` returned no services; a
same-machine standalone `postgres`/pgvector container on port 5432 is
unrelated to this project). This exact blocker was already documented
earlier in this file (Implementation Status, Core) and reproduces
identically now:

```text
$ .\venv\Scripts\python.exe manage.py showmigrations telecom --settings=config.settings_dev
django.db.utils.OperationalError: could not translate host name "db" to address: Name or service not known

$ .\venv\Scripts\python.exe manage.py migrate telecom --plan --settings=config.settings_dev
django.db.utils.OperationalError: could not translate host name "db" to address: Name or service not known
```

This is a local/sandbox limitation, not a statement about PRD's actual
migration state — PRD's Postgres is reachable from `lineops-app-prod`
itself (its `DB_HOST=db` resolves inside that compose network), just not
from this session without the docker/sudo access described in §4.

Real command output, this session, local sqlite backend:

```text
$ .\venv\Scripts\python.exe manage.py test telecom --settings=config.settings_dev -v 1
Ran 254 tests in 166.969s
OK (skipped=1)

$ .\venv\Scripts\python.exe manage.py test dashboard.tests pendencies --settings=config.settings_dev -v 1
Ran 126 tests in 85.790s
OK

$ .\venv\Scripts\python.exe manage.py check --settings=config.settings_dev
System check identified no issues (0 silenced).

$ git diff --check
(no output — only a benign LF/CRLF line-ending warning on this file, not a
whitespace-error exit)
```

`telecom/tests_line_daily_action_audit_retention.py` (untracked, T8's new
module) is included in the 254 `telecom` count above — `manage.py test
telecom` discovers it as part of the app, no separate invocation needed.

SSH to PRD (`ssh lineops-prod`), read-only, no mutation, to map real deploy
config for §3 and confirm the §4 blocker:

```text
$ ssh lineops-prod "whoami && hostname"
global
SRVQA-01

$ ssh lineops-prod "docker ps ..."
permission denied while trying to connect to the docker API at unix:///var/run/docker.sock

$ ssh lineops-prod "sudo -n docker ps ..."
sudo: a password is required

$ ssh lineops-prod "ls -la /opt/app/src/lineops; test -f /opt/app/src/lineops/.env.prod && echo yes; groups"
(confirms repo layout at that path, owned by appuser, .env.prod present, global's groups: global wheel)
```

No production data was read, no container was started/stopped, no
migration was applied, no line was touched.

### 7. Success / failure criteria

Success (per release):

- `showmigrations telecom` shows `0017`, `0018`, `0019` applied in PRD.
- `lineops-app-prod` healthy (`docker compose ps`, container healthcheck)
  and `/health/` returns `{"status": "ok"}`.
- `manage.py check` clean against PRD settings.
- Either the PRD validation cycle in §4 ran clean end-to-end, or it is
  explicitly recorded as skipped with the operational reason (no approved
  line yet) — never silently omitted.
- No `PhoneLineHistory` row, `DailyUserAction` row, or `AllocationPendency`
  row was created, altered, or backfilled to simulate pre-deploy audit
  history.

Failure (stop and record a decision before proceeding, per §5):

- Any `0017`-`0019` migration fails to apply, or `showmigrations` disagrees
  with §2's table.
- `web` container fails its healthcheck after step 7 in §3.
- Any script, shell command, or manual DB write creates a
  `LineDailyActionAuditEvent` row outside the audited UI/API flow.
- A `DELETE` or content-`UPDATE` against `telecom_linedailyactionauditevent`
  is attempted and blocked by the migration 0019 trigger in PRD — this is
  the trigger working correctly, but it means something upstream tried to
  mutate audit history and needs investigation, not a retry.

### Files changed (T9)

- `docs/superpowers/specs/2026-09-10-line-daily-action-audit-design.md`
  (this section).

No model, migration, view, or test file was created or modified for T9. No
commit or push was made.

### Residual risks

- **Docker/sudo access gap.** No one accessible in this session can run
  `docker compose exec/run` in PRD. Steps 4-7 in §3 and all of §4 are
  blocked on this until someone with that access (root, or `appuser`, or a
  `global` grant into the `docker` group / passworded `sudo`) executes them
  or hands over interactive access.
- **No test line named yet.** §4's procedure is ready but unexecuted; first
  real validation still needs someone to approve a specific, safe line.
- **PRD's current `telecom` migration head is unconfirmed.** §6 shows the
  read-only `showmigrations`/`migrate --plan` check could not run from this
  session (Postgres unreachable locally) or against PRD itself (docker
  access blocked). §3 step 3/6 close this gap at actual deploy time,
  before/after applying `0017`-`0019` — but as of this document, no
  session has captured PRD's real current state.
- **`scripts/backup_db.sh` also needs docker access.** It calls
  `docker exec lineops-db-prod pg_dump ...` — it is affected by the same
  gap as steps 5/6, not a separate concern.
