# Allocation Pendency Null Allocation Uniqueness Bugfix PRD

## Spec Summary

LineOps must keep exactly one `AllocationPendency` per employee when the pendency is employee-level, meaning `allocation = NULL`.

The current database schema does not enforce that rule. As a result, duplicate employee-level pendencies can exist for the same employee, and the modal flow that calls `get_or_create(employee=..., allocation=None)` can fail with `MultipleObjectsReturned`.

This bugfix must add database-level protection, clean existing duplicate rows safely, and preserve the existing allocation-level pendency behavior.

## Problem Statement

`AllocationPendency` tracks pendency state for two cases:

- allocation-level pendency: tied to one `LineAllocation`;
- employee-level pendency: tied to one `Employee` with `allocation = NULL`.

The model currently uses `OneToOneField` for `allocation`, but nullable unique fields do not prevent multiple rows with `NULL` values in PostgreSQL. Therefore, multiple rows can exist with:

```text
same employee_id
allocation_id = NULL
```

This violates the business rule documented in `pendencies.models.AllocationPendency.Meta` comments and breaks read/write flows that assume one employee-level pendency.

## Evidence

### Code Evidence

- `pendencies/views.py::_get_or_create_pendency()` uses `AllocationPendency.objects.get_or_create(employee=employee, allocation=allocation)`.
- `pendencies/models.py::AllocationPendency.allocation` is nullable.
- `pendencies/models.py::AllocationPendency.Meta` has indexes, but no partial unique constraint for `allocation IS NULL`.
- `pendencies/migrations/0001_initial.py` creates only a non-unique index on `allocation`.

### Reproduction Evidence

A temporary test probe confirmed:

1. two `AllocationPendency` rows with the same `employee` and `allocation=None` can be inserted;
2. after that duplicate state exists, `get_or_create(employee=employee, allocation=None)` raises `MultipleObjectsReturned`.

## Objective

Guarantee one and only one employee-level pendency per employee.

The fix must:

- prevent future duplicates at database level;
- keep existing allocation-level uniqueness behavior unchanged;
- clean pre-existing duplicate employee-level pendencies before adding the constraint;
- preserve the most meaningful pendency data when duplicates are merged;
- keep UI, dashboard, and metrics semantics stable.

## Django Boundary

### App

- `pendencies`

### Primary Model

- `pendencies.models.AllocationPendency`

### Entry Points Affected

- `pendencies.views._get_or_create_pendency`
- `pendencies.views.PendencyDetailView`
- `pendencies.views.PendencyUpdateView`
- `pendencies.views.PendencyClaimView`
- `dashboard.views.build_daily_user_action_rows`
- `dashboard.services.query_service.get_pending_action_counts_for_user`
- `dashboard.services.metrics_service.build_pendency_metrics`

### Persistence Impact

Migration required.

Expected persistence changes:

- add partial unique constraint on `AllocationPendency.employee` where `allocation IS NULL`;
- run data migration before the constraint to deduplicate existing rows.

## Current Behavior

- Allocation-level pendencies are protected by `OneToOneField(allocation)`.
- Employee-level pendencies are not protected because `allocation_id = NULL`.
- Duplicate rows can inflate counts in dashboard and metrics.
- Duplicate rows can break `get_or_create()` with `MultipleObjectsReturned`.

## Expected Behavior

- For each employee, at most one `AllocationPendency` may exist where `allocation IS NULL`.
- Creating a second employee-level pendency for the same employee must raise `IntegrityError`.
- Opening the pendency modal for an employee without allocation must always return the single canonical pendency row.
- Existing duplicate rows must be deduplicated before applying the constraint.
- Allocation-level pendencies must still allow one pendency per allocation and must not be merged by employee.

## Data Cleanup Contract

Before adding the unique constraint, duplicate rows matching this condition must be grouped:

```text
AllocationPendency.employee_id = same value
AllocationPendency.allocation_id IS NULL
```

For each group, keep one canonical row and remove the others.

### Canonical Row Selection

Choose the canonical row using this priority order:

1. open pendency first: `action != no_action`;
2. assigned pendency next: `technical_responsible_id IS NOT NULL`;
3. most recently updated: highest `updated_at`;
4. newest row as final tie-breaker: highest `id`.

### Merge Rules

When duplicate rows exist, merge useful non-empty data into the canonical row before deleting duplicates:

- `observation`: keep canonical observation if non-empty; otherwise use the newest non-empty duplicate observation.
- `technical_responsible`: keep canonical responsible if set; otherwise use newest duplicate responsible.
- `last_submitted_action`: keep canonical value if set; otherwise use newest duplicate value.
- `pendency_submitted_at`: keep earliest non-null value among open duplicate pendencies.
- `resolved_at`: keep canonical value if set; otherwise use newest duplicate value.
- `last_action_changed_at`: keep newest non-null value.
- `updated_by`: keep canonical value if set; otherwise use newest duplicate value.

Do not merge rows across different employees.

Do not merge rows where `allocation_id IS NOT NULL`.

## API / UI Contract

No route, template, or payload shape should change.

The modal JSON returned by `PendencyDetailView` must remain compatible with current frontend behavior.

Expected visible effect:

- duplicate employee-level pendencies stop appearing in metrics/counts;
- modal open no longer risks `MultipleObjectsReturned` for duplicate employee-level rows.

## Service / ORM Contract

The fix must keep `get_or_create()` usable for employee-level pendencies.

Recommended model constraint:

```python
models.UniqueConstraint(
    fields=["employee"],
    condition=models.Q(allocation__isnull=True),
    name="uq_pendency_employee_without_allocation",
)
```

The implementation may keep `_get_or_create_pendency()` unchanged after the database constraint is added, unless tests show a race still needs explicit transaction handling.

## Gap Analysis

Known gap:

- current model comment says uniqueness exists for employee-level pendencies, but database schema does not enforce it.

Risk:

- adding the constraint without cleanup can fail migration on environments that already have duplicate rows.

Required mitigation:

- data migration must run before constraint migration.

## Test Checklist

- Creating the first employee-level pendency succeeds.
- Creating a second employee-level pendency for the same employee with `allocation=None` raises `IntegrityError`.
- Creating allocation-level pendencies for different allocations under the same employee still succeeds.
- Creating a second pendency for the same non-null allocation still fails.
- `_get_or_create_pendency(employee, None)` returns the existing row when only one row exists.
- Data migration deduplicates duplicate employee-level pendencies.
- Data migration preserves the open row when duplicate group has one open and one `no_action` row.
- Data migration preserves or merges `technical_responsible`.
- Dashboard pending-card counts do not double-count duplicate employee-level pendencies after migration.
- Pendency metrics do not double-count duplicate employee-level pendencies after migration.

## Test Strategy

Use Django database-backed tests.

Preferred targeted suites:

```powershell
.\venv\Scripts\python.exe manage.py test pendencies.tests.test_observation_notifications --settings=config.settings_dev -v 2
.\venv\Scripts\python.exe manage.py test dashboard.tests.test_pending_cards_consistency dashboard.tests.test_pendency_metrics_service --settings=config.settings_dev -v 2
```

Add focused migration/model tests in the existing pendency test module or a new `pendencies/tests/test_pendency_uniqueness.py`.

Tests must be derived from the persistence contract above, not from the implementation details of a specific migration function.

## Acceptance Criteria

- The database has a partial unique constraint preventing duplicate `employee + allocation=NULL` rows.
- Migration applies successfully on a database that already contains duplicate employee-level pendencies.
- No existing allocation-level pendency behavior changes.
- Targeted pendency and dashboard tests pass.
- `manage.py check --settings=config.settings_dev` passes.

## Non-Goals

- Do not redesign the pendency workflow.
- Do not add a historical audit model.
- Do not change dashboard metric semantics.
- Do not change modal payload shape.
- Do not change role-scope behavior.
- Do not solve the separate dashboard performance gap in this bugfix.

## Rollout Notes

Before production deploy:

1. create or verify a fresh production backup;
2. count duplicate employee-level pendency groups before migration:

```sql
SELECT employee_id, COUNT(*) AS duplicate_count
FROM pendencies_allocationpendency
WHERE allocation_id IS NULL
GROUP BY employee_id
HAVING COUNT(*) > 1;
```

3. restore the backup into a real staging database and run the migrations normally up to `pendencies.0006`;
4. do not use `--fake-initial`; it is only for initial migrations and does not validate this `0005`/`0006` rollout;
5. inspect how many duplicate groups were deduplicated and how long the migration took in staging;
6. after production migration, verify pendency modal opens for employees without active allocation;
7. verify dashboard pending cards and pendency metrics load.

Rollback note:

- Removing the constraint restores old risk and should be avoided unless migration blocks deployment.
- If rollback is needed, keep the deduplication already applied; do not recreate duplicate rows.

## Compliance Report

- Specification source: confirmed bug analysis from current `AllocationPendency` model, migration, and `get_or_create()` flow.
- API contract impact: none.
- Service behavior impact: employee-level pendency uniqueness becomes enforced.
- Persistence impact: migration required.
- Test derivation: tests derive from one employee-level pendency per employee, allocation-level uniqueness preservation, and deduplication safety.
- Architecture compliance: business behavior remains in existing views/services; database owns invariant enforcement.
