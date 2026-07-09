# Pendency Technical Responsible Release Design

## Spec Summary

LineOps needs an admin-only action in the `Status Pendencia` modal to release the current technical responsible user from an allocation pendency.

The source of truth is `pendencies.AllocationPendency.technical_responsible`. Releasing means setting `technical_responsible = None` for the selected pendency. It must not resolve the pendency, change the action, change line status, or alter lifecycle timestamps unrelated to assignment.

Decision confirmed by user: release is admin-only. This follows the current `Assumir` behavior, where only admins can assign themselves as technical responsible through the modal.

## Objective

Allow an admin to remove the currently assigned technical responsible user from a pendency directly in the `Status Pendencia` modal.

Success means:

- admins can see and use a `Liberar` control when a pendency has a technical responsible user;
- the selected pendency is persisted with `technical_responsible = None`;
- modal JSON and the daily action board row update without page reload;
- non-admin roles cannot release a technical responsible user;
- release does not change pendency status, action, observation, line status, or resolution state.

## Current Behavior

- `PendencyClaimView` handles `POST /pendencies/api/claim/`.
- `PendencyClaimView.allowed_roles = [SystemUser.Role.ADMIN]`.
- Claim sets `pendency.technical_responsible = request.user`.
- The modal has one button, `pendencyClaimBtn`, labeled `Assumir`.
- The button appears for admins.
- The modal payload exposes `technical_responsible_name`, but not a specific release action.
- Several existing flows already clear `technical_responsible` when a pendency is resolved or reopened, but there is no explicit modal action to release only the assignee.

## Gap Analysis

Missing contract:

- no explicit API route for releasing a technical responsible user;
- no frontend state for switching the responsible-control action from `Assumir` to `Liberar`;
- no tests proving release is admin-only and assignment-only.

Resolved ambiguity:

- only admins may release the technical responsible user.

Reason:

- the existing claim flow is admin-only;
- the modal currently shows the responsible action only to admins;
- keeping release admin-only avoids changing the role model for pendency ownership.

## Django Boundary

### App

- `pendencies`

### Primary Model

- `pendencies.models.AllocationPendency`

### Entry Points Affected

- `pendencies.views._pendency_to_json`
- `pendencies.views.PendencyClaimView`
- new `pendencies.views.PendencyReleaseView`
- `pendencies.urls`
- `templates/dashboard/daily_user_action_board.html`

### Existing UI Surface

- `templates/dashboard/daily_user_action_board.html`
- modal id: `pendencyModal`
- responsible label/control area: `Responsavel Tecnico`

## API Contract

### Route

`POST /pendencies/api/release/`

Suggested URL name:

`pendencies:release`

### Request

```json
{
  "pendency_id": 123
}
```

### Success Response

The response must reuse the current modal payload shape returned by `_pendency_to_json`, with `ok = true`.

```json
{
  "ok": true,
  "id": 123,
  "employee_id": 10,
  "allocation_id": 20,
  "technical_responsible_name": "",
  "action": "pending",
  "action_display": "Pendencia",
  "line_status": "restricted",
  "line_status_display": "Restrito"
}
```

The response may include additional fields already present in `_pendency_to_json`.

### Error Responses

- invalid JSON returns HTTP 400 with `{"error": "JSON invalido."}`;
- missing or unknown `pendency_id` returns 404 through `get_object_or_404`;
- authenticated user without admin role returns existing role-protection response;
- admin outside scoped employee access raises `PermissionDenied("Sem acesso a este funcionario.")`.

## Service Behavior

The release operation must:

- load the pendency with `employee`, `allocation__phone_line`, and `technical_responsible`;
- validate employee scope using `request.user.scope_employee_queryset(Employee.objects.all())`;
- set `technical_responsible = None`;
- set `updated_by = request.user`;
- save only `technical_responsible` and `updated_by`;
- return `_pendency_to_json(pendency, pendency.allocation)`.

The release operation must not:

- call `record_action_change`;
- call `record_line_status_change`;
- change `action`;
- change `observation`;
- change `line_status`;
- change `last_action_changed_at`;
- change `pendency_submitted_at`;
- change `resolved_at`;
- create `PhoneLineHistory`;
- create observation notifications.

Idempotency:

- releasing a pendency that already has `technical_responsible = None` should return HTTP 200 and keep the field null.

## UI Contract

The responsible technical control in the modal must behave as:

- non-admin: no claim/release button visible;
- admin and no responsible: show `Assumir`;
- admin and responsible exists: show `Liberar`;
- after successful claim: modal shows responsible name and button changes to `Liberar`;
- after successful release: modal shows `-` and button changes to `Assumir`;
- the board row `.js-tech-responsible` updates from the returned payload;
- no full page reload required.

The frontend may implement this with one existing button or two separate buttons. Preferred minimal change:

- keep one button element;
- add a current action mode derived from `data.technical_responsible_name`;
- call `CLAIM_URL` when mode is `claim`;
- call `RELEASE_URL` when mode is `release`;
- update button text, title, and visual class in `renderModal`.

## Persistence Impact

No migration required.

Only existing nullable FK is updated:

- table: `pendencies_allocationpendency`
- column: `technical_responsible_id`

## Security and Permission Rules

- release is admin-only;
- CSRF protection follows existing modal POST pattern;
- scope validation must match `PendencyClaimView`;
- no user may release a pendency for an employee outside their scoped queryset;
- no secrets or credentials are involved.

## Test Checklist

- Admin releases a pendency assigned to another admin/user and DB stores `technical_responsible = None`.
- Admin release response has `technical_responsible_name == ""`.
- Admin release response preserves `action`.
- Admin release response preserves `line_status`.
- Admin release response preserves `resolved_at`.
- Admin release response preserves `last_action_changed_at`.
- Admin release updates `updated_by` to the acting admin.
- Admin release on already unassigned pendency returns 200 and remains null.
- Non-admin cannot call release endpoint.
- Admin outside employee scope cannot release endpoint.
- Existing claim endpoint still assigns current admin.
- Modal row update uses returned `technical_responsible_name` and renders `-` after release.

## Test Strategy

Use Django database-backed tests.

Targeted backend tests:

```powershell
.\venv\Scripts\python.exe manage.py test pendencies.tests.test_observation_notifications --settings=config.settings_dev -v 2
```

Recommended new tests in `pendencies/tests/test_observation_notifications.py` or a focused `pendencies/tests/test_pendency_technical_responsible.py`.

Frontend behavior is mostly inline-template JavaScript. Prefer backend coverage for the contract and one template/view smoke assertion if practical. Manual browser verification can confirm button mode changes after backend tests pass.

Avoid mocking core business logic. Create real users, employees, allocations, and pendencies.

## Implementation Plan

1. Add failing tests for release endpoint:
   - admin success;
   - non-admin forbidden;
   - idempotent unassigned release.
2. Add `PendencyReleaseView` beside `PendencyClaimView`.
3. Add `path("api/release/", views.PendencyReleaseView.as_view(), name="release")`.
4. Add `RELEASE_URL` in `daily_user_action_board.html`.
5. Update modal responsible button rendering to switch between `Assumir` and `Liberar`.
6. Add frontend submit function or generic responsible-action function.
7. Run targeted pendency tests.
8. Run `manage.py check --settings=config.settings_dev`.

## Acceptance Criteria

- Admin can release the technical responsible user from the `Status Pendencia` modal.
- Released pendency persists with `technical_responsible_id IS NULL`.
- Modal and board row update immediately from API response.
- Non-admin roles cannot release.
- No lifecycle/status/action side effects occur.
- Targeted pendency tests pass.
- Django check passes.

## Non-Goals

- Do not add historical assignment audit events.
- Do not allow non-admin self-release in this version.
- Do not redesign pendency ownership rules.
- Do not change metrics semantics.
- Do not change claim behavior beyond what is needed for button state.
- Do not add database migrations.

## Compliance Report

- Specification source: user-approved requirement to add `Liberar` for current `responsavel tecnico` in the `Status Pendencia` modal.
- Gap resolved: release is explicitly admin-only.
- API contract impact: one new internal JSON POST endpoint.
- Service behavior impact: one assignment-only operation on `AllocationPendency.technical_responsible`.
- Persistence impact: no schema change; nullable FK updated.
- Test derivation: tests derive from admin-only permission, scoped access, idempotency, and no side effects.
- Architecture compliance: view remains thin and mirrors existing claim boundary; core pendency state remains in the model; UI consumes existing modal JSON payload.
