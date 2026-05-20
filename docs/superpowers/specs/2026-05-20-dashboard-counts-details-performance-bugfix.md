# Dashboard Counts vs Details Performance Bugfix

## Status

Approved for implementation in this session.

## Problem

Dashboard summary paths calculate numeric indicators by materializing full detail lists:

- `dashboard/views.py::build_number_details_for_day()` builds `available_numbers`, `delivered_numbers`, and `new_numbers`;
- `dashboard/views.py::build_indicator_for_day()` then uses `len(...)` for dashboard counts;
- `dashboard/views.py::get_dashboard_indicator_for_day()` persists/recalculates the current-day snapshot on dashboard load.

At high volume, dashboard summary and live payload requests pay the cost of building details that are not rendered in those summary rows.

## Objective

Separate count calculation from detail calculation.

Dashboard summary/snapshot paths must calculate counts without building number detail lists. Detail pages must keep the full lists.

## Django Boundary

- App: `dashboard`
- Main file: `dashboard/views.py`
- Tests: `dashboard/tests/`
- Models affected: none
- Migrations: none

## Current Behavior

- `build_indicator_for_day(day, include_users=False)` builds number detail lists.
- `persist_dashboard_snapshot_for_day(day)` calls `build_indicator_for_day(day)` and stores only numeric values.
- `get_dashboard_indicator_for_day(day)` recalculates/persists current-day snapshot on each call.
- `daily_indicator_day_breakdown(..., include_users=True)` needs detail lists and must keep them.

## Expected Behavior

- Summary/snapshot path returns the same numeric values without calling detail builders.
- Detail breakdown path returns the same numeric values and the same detail lists as before.
- Scoped users keep the same scoped employee metrics.
- Global inventory metrics remain global where existing behavior already does that.
- Historical snapshot preservation behavior remains unchanged.

## Implementation Contract

Add a count-only path for number indicators:

- available numbers: count from visible available line queryset after excluding active allocated line ids;
- delivered numbers: count visible allocations for the selected day, respecting optional employee scope;
- reconnected numbers: count the same sources currently used by `build_reconnected_numbers_for_day()`, without producing detail dicts;
- new numbers: count visible phone lines created on the selected day.

`build_indicator_for_day()` must support:

- `include_users=False`: counts only; detail lists empty;
- `include_users=True`: details included for breakdown pages.

`persist_dashboard_snapshot_for_day()` must use the count-only path.

## Non-Goals

- Do not redesign dashboard views.
- Do not change templates.
- Do not change `DashboardDailySnapshot` schema.
- Do not change historical snapshot versioning.
- Do not change role-scope semantics.
- Do not solve unrelated dashboard query or N+1 issues outside this count/detail split.

## Test Checklist

- Summary indicator path does not call number detail builder.
- Current-day snapshot path does not call number detail builder.
- Summary counts match detail-list lengths on the same dataset.
- Breakdown path still returns detail lists.
- Existing dashboard pending/metrics tests still pass.

## Validation Commands

```powershell
.\venv\Scripts\python.exe manage.py check --settings=config.settings_dev
.\venv\Scripts\python.exe manage.py test dashboard.tests.test_dashboard_counts_performance --settings=config.settings_dev -v 2
.\venv\Scripts\python.exe manage.py test dashboard.tests.test_pending_cards_consistency dashboard.tests.test_pendency_metrics_service --settings=config.settings_dev -v 2
```

## Compliance Report

- Spec source: confirmed high-priority performance review gap.
- API contract impact: none.
- UI contract impact: none.
- Persistence impact: none.
- Test derivation: tests prove summary/snapshot avoid detail materialization and breakdown keeps details.
