# Spec: Employee Email

## Objective
Add an optional email address to each negotiator (`Employee`) without changing the existing supervisor relationship stored in `corporate_email`.

## Expected Behavior
- `Employee.email` stores the negotiator's own email address.
- The field is optional.
- When present, it is normalized with the existing email normalization rule.
- When present, it is unique among active, non-deleted negotiators, case-insensitively.
- Soft-deleted negotiators do not block email reuse.
- `corporate_email` remains the supervisor email and keeps its current access-scope behavior.

## Django Boundary
- App: `employees`
- Model: `Employee`
- Forms: employee create/update and Django admin form
- Views/templates: employee list, detail, and AJAX list payload
- Upload ingestion: employee rows in CSV/XLSX
- Static templates: upload/update CSV templates

## Inputs
- Manual employee form field: `email`
- Admin field: `email`
- Upload fields: `email` or `employee_email`

## Outputs
- Employee list and detail display the negotiator email.
- AJAX list payload includes `email`.
- Employee history records email changes.

## Persistence Impact
- Add nullable/blank `EmailField` to `Employee`.
- Add a conditional unique constraint on `Lower("email")` for active, non-deleted rows with a non-null/non-empty email.
- Add an index for `email` lookup/search.

## Test Strategy
- Model tests cover optional email, normalization, active uniqueness, and reuse after soft delete.
- Form/admin tests cover duplicate email validation before database errors.
- View/template tests cover list/detail/AJAX display.
- Upload tests cover create/update from `email` and alias `employee_email`.

## Out of Scope
- Renaming `corporate_email`.
- Backfilling existing negotiator emails.
- Using negotiator email for authentication.
