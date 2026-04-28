# Pendency Metrics Page Design

## Spec Summary

LineOps needs a dashboard page that shows which technical users are assuming and handling the most allocation pendencies. The metric source of truth for the first version is `AllocationPendency.technical_responsible`, because the desired business question is "quem tratou/assumiu as pendencias", not "quem alterou o status da linha".

The first implementation version must report the current operational state of pendencies. It must not claim historical resolution metrics unless an audit event model is added later.

## Objective

Provide a management view for admins, supervisors, backoffice users, and managers to understand:

- how many pendencies are open;
- how many are assigned to a technical responsible user;
- how many are unassigned;
- which technical users have the largest assigned backlog;
- how that backlog splits by line status and pendency action.

## Django Boundary

- App: `dashboard`
- Existing data sources:
  - `pendencies.AllocationPendency`
  - `allocations.LineAllocation`
  - `employees.Employee`
  - `users.SystemUser`
- Entry point:
  - HTML page rendered by a Django view in `dashboard.views`
- New service boundary:
  - `dashboard.services.metrics_service`
- New template:
  - `templates/dashboard/metrics.html`

## Contract

### Route

`GET /dashboard/metricas/`

Suggested URL name:

`dashboard_metrics`

### Allowed Roles

Use the same broad dashboard role pattern already used by daily actions:

- `admin`
- `super`
- `backoffice`
- `gerente`

### Scope Rules

The metrics must respect the current employee scoping model:

- `admin`: sees all active, non-deleted employees and their pendencies.
- `super`: sees employees where `corporate_email` matches the supervisor effective email.
- `backoffice`: sees employees for the linked supervisor effective email.
- `gerente`: sees employees under managed supervisors or direct manager scope.

The service must derive this via the existing `SystemUser.scope_employee_queryset()` behavior instead of duplicating role logic.

### Filters

V1 filters:

- `line_status`: optional status filter. Includes `active`, `under_analysis`, `restricted`, `permanently_banned`, and `waiting_operator`.
- `action`: optional pendency action filter. Includes `new_number`, `reconnect_whatsapp`, and `pending`.
- `technical_responsible`: optional responsible user id filter.
- `supervisor`: optional text/email filter for admin only, matching existing dashboard behavior where useful.

No date range filter is included in V1 because `technical_responsible` reflects the current assignee and is cleared on resolution. A date filter would imply historical behavior that the current model cannot guarantee.

### Output Context

The view must pass a context shaped like:

```python
{
    "title": "Metricas de Pendencias",
    "filters": {
        "line_status": "...",
        "action": "...",
        "technical_responsible": "...",
        "supervisor": "...",
    },
    "summary": {
        "open_total": 0,
        "assigned_total": 0,
        "unassigned_total": 0,
        "restricted_assigned_total": 0,
        "banned_assigned_total": 0,
    },
    "responsible_rankings": [
        {
            "responsible_id": 1,
            "responsible_name": "Admin User",
            "total": 0,
            "restricted": 0,
            "permanently_banned": 0,
            "under_analysis": 0,
            "waiting_operator": 0,
            "new_number": 0,
            "reconnect_whatsapp": 0,
            "pending": 0,
            "oldest_submitted_at": None,
        }
    ],
    "unassigned_breakdown": {
        "total": 0,
        "restricted": 0,
        "permanently_banned": 0,
    },
    "technical_responsible_choices": [],
}
```

## Behavior

- Count only open pendencies where `AllocationPendency.action != no_action`.
- Treat a pendency as assigned when `technical_responsible_id` is not null.
- Treat a pendency as unassigned when `technical_responsible_id` is null.
- For pendencies attached to an active allocation, use `LineAllocation.line_status`.
- For pendencies without an allocation, use `Employee.line_status`.
- Rank technical responsible users by total assigned open pendencies descending.
- Use `oldest_submitted_at` to show the oldest active assigned pendency for each responsible user.
- Display unknown or deleted responsible users only if reachable through the nullable FK. In normal current-state reports, unassigned pendencies should be grouped separately instead.
- Do not count resolved pendencies in V1.
- Do not infer historical handling from `updated_by`, `resolved_at`, or `last_submitted_action`.

## Architecture Map

### Entry Points

- `dashboard.urls`: add the route for `dashboard_metrics`.
- `dashboard.views`: add a thin function-based view or class-based view that:
  - validates filter values;
  - calls the metrics service;
  - renders the template.

### Business Logic

- `dashboard.services.metrics_service` owns:
  - base queryset construction;
  - role scope application through `scope_employee_queryset`;
  - line status resolution for allocation and employee-level pendencies;
  - aggregation;
  - ranking preparation.

### Persistence

- V1 uses existing tables only.
- No migration is required.

### Presentation

- `templates/dashboard/metrics.html` renders:
  - filter form;
  - summary cards;
  - ranking table;
  - unassigned breakdown.
- The sidebar should include a metrics navigation item for allowed roles.

## Responsibility Review

Well-placed responsibilities:

- Access scope already belongs to `SystemUser.scope_employee_queryset`.
- Current pendency state already belongs to `AllocationPendency`.
- Presentation belongs to `dashboard` because the feature is a dashboard/reporting view.

Misplaced responsibility to avoid:

- Do not put aggregation logic inside the template.
- Do not put ORM-heavy ranking logic directly in the view.
- Do not use `PhoneLineHistory.changed_by` for this metric, because it answers a different business question.

## Persistence Impact

V1 has no persistence change.

Known limitation:

- `technical_responsible` is cleared when a pendency is resolved or reopened in some flows. Therefore the current schema cannot reliably answer "how many pendencies each technical user resolved in a historical period".

Future V2 persistence option:

- Add a `PendencyAssignmentEvent` or `PendencyLifecycleEvent` model with:
  - `pendency`
  - `event_type`
  - `actor`
  - `technical_responsible`
  - `old_action`
  - `new_action`
  - `old_line_status`
  - `new_line_status`
  - `created_at`

This would enable period metrics, historical resolved counts, reassignment analysis, and average handling time.

## Test Checklist

- Admin sees assigned pendencies across all employees.
- Supervisor sees only assigned pendencies for employees in their scope.
- Backoffice sees only assigned pendencies for the linked supervisor.
- Manager sees only assigned pendencies in manager scope.
- Pendencies with `action=no_action` are excluded.
- Pendencies with `technical_responsible=None` are counted as unassigned.
- Pendencies with allocation use `LineAllocation.line_status`.
- Pendencies without allocation use `Employee.line_status`.
- Ranking sorts by total assigned open pendencies descending.
- Restricted and permanently banned totals are counted separately.
- Filters by line status and action affect summary and ranking consistently.
- The view requires authentication and one of the allowed roles.

## Test Strategy

- Add unit tests for `dashboard.services.metrics_service`.
- Add view tests for route access, role permission, and expected context keys.
- Prefer database-backed tests because the feature is ORM aggregation and role scoping.
- Avoid mocking core business logic. Create representative users, employees, allocations, and pendencies instead.
- Include both allocation-level and employee-level pendencies.

## Implementation Plan

1. Add service tests that define the expected aggregation and scope behavior.
2. Implement `dashboard.services.metrics_service`.
3. Add view tests for permissions and context.
4. Add the dashboard route and view.
5. Add the metrics template.
6. Add the sidebar navigation link for allowed roles.
7. Run targeted dashboard tests.
8. Run broader regression tests if the targeted suite passes.

## Compliance Report

- Specification source: user-approved requirement that metrics must show who handled or assumed pendencies.
- API contract impact: one new HTML endpoint, no external API.
- Service behavior impact: new read-only dashboard service.
- Persistence impact: no V1 migration.
- Test derivation: tests derive from role scoping, open-pendency filtering, assignment state, and line-status aggregation.
- Architecture compliance: view remains thin, business logic is isolated in service layer, persistence concerns are kept out of the template.
- Known ambiguity resolved: the metric uses `technical_responsible`, not status-change history.

