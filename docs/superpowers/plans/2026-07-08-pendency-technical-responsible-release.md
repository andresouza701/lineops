# Pendency Technical Responsible Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an admin-only `Liberar` action in the `Status Pendencia` modal that clears `AllocationPendency.technical_responsible` without changing pendency lifecycle state.

**Architecture:** Mirror the existing admin-only `PendencyClaimView` with a small `PendencyReleaseView` and route. Keep business effect narrow: release only updates `technical_responsible` and `updated_by`; the existing modal JSON remains the frontend contract. Update the inline modal JavaScript to switch one button between `Assumir` and `Liberar`.

**Tech Stack:** Django class-based views, Django TestCase/Client, inline template JavaScript, Bootstrap modal, existing `SystemUser` role/scoping model.

---

## Specification Source

- `docs/superpowers/specs/2026-07-08-pendency-technical-responsible-release-design.md`

## File Structure

- Modify: `pendencies/tests/test_observation_notifications.py`
  - Adds endpoint contract tests before implementation.
  - Keeps test setup close to existing pendency update/detail tests and helpers.
- Modify: `pendencies/views.py`
  - Adds `PendencyReleaseView` beside `PendencyClaimView`.
  - Reuses JSON parsing, `get_object_or_404`, scope validation, and `_pendency_to_json`.
- Modify: `pendencies/urls.py`
  - Adds `api/release/` route named `release`.
- Modify: `templates/dashboard/daily_user_action_board.html`
  - Adds `RELEASE_URL`.
  - Changes responsible button state from fixed claim to claim/release mode.
- No migrations.
- No new dependencies.

## Task 1: Add Release Endpoint Tests

**Files:**
- Modify: `pendencies/tests/test_observation_notifications.py`

- [ ] **Step 1: Add release URL to test setup**

In `PendencyUpdateViewNotificationTest.setUp`, after `self.detail_url = reverse("pendencies:detail")`, add:

```python
self.claim_url = reverse("pendencies:claim")
self.release_url = reverse("pendencies:release")
```

- [ ] **Step 2: Add admin success test**

Add this method inside `PendencyUpdateViewNotificationTest`, near other technical responsible tests:

```python
def test_admin_can_release_technical_responsible_without_side_effects(self):
    allocation = self._make_allocation(
        phone_suffix="0301",
        line_status=LineAllocation.LineStatus.RESTRICTED,
    )
    resolved_at = timezone.now()
    last_changed_at = timezone.now()
    submitted_at = timezone.now()
    pendency = AllocationPendency.objects.create(
        employee=self.employee,
        allocation=allocation,
        action=AllocationPendency.ActionType.PENDING,
        observation="observacao original",
        technical_responsible=self.super_user,
        resolved_at=resolved_at,
        last_action_changed_at=last_changed_at,
        pendency_submitted_at=submitted_at,
        last_submitted_action=AllocationPendency.ActionType.PENDING,
    )

    self.client.force_login(self.admin)
    response = self.client.post(
        self.release_url,
        data=json.dumps({"pendency_id": pendency.pk}),
        content_type="application/json",
    )

    self.assertEqual(response.status_code, 200)
    payload = response.json()
    pendency.refresh_from_db()
    allocation.refresh_from_db()

    self.assertTrue(payload["ok"])
    self.assertEqual(payload["technical_responsible_name"], "")
    self.assertIsNone(pendency.technical_responsible)
    self.assertEqual(pendency.updated_by, self.admin)
    self.assertEqual(pendency.action, AllocationPendency.ActionType.PENDING)
    self.assertEqual(pendency.observation, "observacao original")
    self.assertEqual(allocation.line_status, LineAllocation.LineStatus.RESTRICTED)
    self.assertEqual(pendency.resolved_at, resolved_at)
    self.assertEqual(pendency.last_action_changed_at, last_changed_at)
    self.assertEqual(pendency.pendency_submitted_at, submitted_at)
    self.assertEqual(
        pendency.last_submitted_action,
        AllocationPendency.ActionType.PENDING,
    )
    self.assertEqual(PendencyObservationNotification.objects.count(), 0)
```

- [ ] **Step 3: Add idempotency test**

Add:

```python
def test_admin_release_unassigned_pendency_is_idempotent(self):
    allocation = self._make_allocation(phone_suffix="0302")
    pendency = AllocationPendency.objects.create(
        employee=self.employee,
        allocation=allocation,
        action=AllocationPendency.ActionType.PENDING,
        technical_responsible=None,
    )

    self.client.force_login(self.admin)
    response = self.client.post(
        self.release_url,
        data=json.dumps({"pendency_id": pendency.pk}),
        content_type="application/json",
    )

    self.assertEqual(response.status_code, 200)
    payload = response.json()
    pendency.refresh_from_db()

    self.assertTrue(payload["ok"])
    self.assertEqual(payload["technical_responsible_name"], "")
    self.assertIsNone(pendency.technical_responsible)
    self.assertEqual(pendency.updated_by, self.admin)
```

- [ ] **Step 4: Add non-admin forbidden test**

Add:

```python
def test_non_admin_cannot_release_technical_responsible(self):
    allocation = self._make_allocation(phone_suffix="0303")
    pendency = AllocationPendency.objects.create(
        employee=self.employee,
        allocation=allocation,
        action=AllocationPendency.ActionType.PENDING,
        technical_responsible=self.admin,
    )

    self.client.force_login(self.super_user)
    response = self.client.post(
        self.release_url,
        data=json.dumps({"pendency_id": pendency.pk}),
        content_type="application/json",
    )

    self.assertEqual(response.status_code, 403)
    pendency.refresh_from_db()
    self.assertEqual(pendency.technical_responsible, self.admin)
```

- [ ] **Step 5: Add claim regression test**

Add:

```python
def test_existing_claim_endpoint_still_assigns_current_admin(self):
    allocation = self._make_allocation(phone_suffix="0304")
    pendency = AllocationPendency.objects.create(
        employee=self.employee,
        allocation=allocation,
        action=AllocationPendency.ActionType.PENDING,
        technical_responsible=None,
    )

    self.client.force_login(self.admin)
    response = self.client.post(
        self.claim_url,
        data=json.dumps({"pendency_id": pendency.pk}),
        content_type="application/json",
    )

    self.assertEqual(response.status_code, 200)
    payload = response.json()
    pendency.refresh_from_db()

    self.assertTrue(payload["ok"])
    self.assertEqual(pendency.technical_responsible, self.admin)
    self.assertEqual(pendency.updated_by, self.admin)
    self.assertNotEqual(payload["technical_responsible_name"], "")
```

- [ ] **Step 6: Run tests to verify expected red state**

Run:

```powershell
.\venv\Scripts\python.exe manage.py test pendencies.tests.test_observation_notifications.PendencyUpdateViewNotificationTest --settings=config.settings_dev -v 2
```

Expected:

```text
django.urls.exceptions.NoReverseMatch: Reverse for 'release' not found.
```

If local venv is missing dependencies, record blocker output and use the repo-supported Python environment before editing implementation.

## Task 2: Add Release View and URL

**Files:**
- Modify: `pendencies/views.py`
- Modify: `pendencies/urls.py`
- Test: `pendencies/tests/test_observation_notifications.py`

- [ ] **Step 1: Add `PendencyReleaseView`**

In `pendencies/views.py`, after `PendencyClaimView`, add:

```python
class PendencyReleaseView(RoleRequiredMixin, View):
    """POST: admin remove o Responsavel Tecnico atual."""

    allowed_roles = [SystemUser.Role.ADMIN]

    def post(self, request):
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "JSON invalido."}, status=400)

        pendency_id = body.get("pendency_id")
        pendency = get_object_or_404(
            AllocationPendency.objects.select_related(
                "employee", "allocation__phone_line", "technical_responsible"
            ),
            pk=pendency_id,
        )

        scoped_qs = request.user.scope_employee_queryset(Employee.objects.all())
        if not scoped_qs.filter(pk=pendency.employee_id).exists():
            raise PermissionDenied("Sem acesso a este funcionario.")

        pendency.technical_responsible = None
        pendency.updated_by = request.user
        pendency.save(update_fields=["technical_responsible", "updated_by"])

        allocation = pendency.allocation
        return JsonResponse(
            {"ok": True, **_pendency_to_json(pendency, allocation)}
        )
```

Note: use project file encoding/style as-is. If nearby strings are encoded with accents, keep message text consistent with the file. The behavior matters more than accent form in JSON error text.

- [ ] **Step 2: Add URL route**

In `pendencies/urls.py`, add route after claim:

```python
path("api/release/", views.PendencyReleaseView.as_view(), name="release"),
```

Expected block:

```python
urlpatterns = [
    path("api/detail/", views.PendencyDetailView.as_view(), name="detail"),
    path("api/update/", views.PendencyUpdateView.as_view(), name="update"),
    path("api/claim/", views.PendencyClaimView.as_view(), name="claim"),
    path("api/release/", views.PendencyReleaseView.as_view(), name="release"),
    path(
        "api/notifications/",
        views.PendencyNotificationsView.as_view(),
        name="notifications",
    ),
]
```

- [ ] **Step 3: Run targeted backend tests**

Run:

```powershell
.\venv\Scripts\python.exe manage.py test pendencies.tests.test_observation_notifications.PendencyUpdateViewNotificationTest --settings=config.settings_dev -v 2
```

Expected:

```text
OK
```

- [ ] **Step 4: Commit backend contract**

Run:

```powershell
git add pendencies/tests/test_observation_notifications.py pendencies/views.py pendencies/urls.py docs/superpowers/specs/2026-07-08-pendency-technical-responsible-release-design.md
git commit -m "feat(pendencies): add responsible release endpoint"
```

Commit only if tests pass and user wants commits in this workflow. If not committing yet, leave files unstaged.

## Task 3: Update Modal Responsible Button

**Files:**
- Modify: `templates/dashboard/daily_user_action_board.html`
- Test manually through rendered template or browser after backend tests.

- [ ] **Step 1: Add release URL constant**

Near existing URL constants:

```javascript
const DETAIL_URL = "{% url 'pendencies:detail' %}";
const UPDATE_URL = "{% url 'pendencies:update' %}";
const CLAIM_URL  = "{% url 'pendencies:claim' %}";
const RELEASE_URL = "{% url 'pendencies:release' %}";
const CSRF_TOKEN = "{{ csrf_token }}";
```

- [ ] **Step 2: Add action mode state**

Near current modal state variables:

```javascript
let currentPendencyId   = null;
let currentEmployeeId   = null;
let currentAllocationId = null;
let currentResponsibleAction = 'claim';
```

- [ ] **Step 3: Update responsible button rendering**

Replace current responsible block inside `renderModal(data)`:

```javascript
// Responsavel tecnico
const techNameEl = document.getElementById('pendencyTechName');
const hasTechnicalResponsible = Boolean(data.technical_responsible_name);
techNameEl.textContent = data.technical_responsible_name || '-';
techNameEl.classList.toggle('text-muted', !hasTechnicalResponsible);
techNameEl.classList.remove('fst-italic');

currentResponsibleAction = hasTechnicalResponsible ? 'release' : 'claim';
if (IS_ADMIN) {
    claimBtn.style.display = '';
    claimBtn.textContent = hasTechnicalResponsible ? 'Liberar' : 'Assumir';
    claimBtn.title = hasTechnicalResponsible
        ? 'Liberar responsavel tecnico'
        : 'Assumir como responsavel tecnico';
    claimBtn.classList.toggle('btn-outline-primary', !hasTechnicalResponsible);
    claimBtn.classList.toggle('btn-outline-danger', hasTechnicalResponsible);
} else {
    claimBtn.style.display = 'none';
}
```

Keep `id="pendencyClaimBtn"` unchanged to minimize template changes.

- [ ] **Step 4: Replace claim-only function with generic responsible action**

Replace `async function claimPendency()` with:

```javascript
async function submitResponsibleAction() {
    claimBtn.disabled = true;
    const isRelease = currentResponsibleAction === 'release';
    try {
        const resp = await fetch(isRelease ? RELEASE_URL : CLAIM_URL, {
            method: 'POST',
            headers: {
                'Content-Type':     'application/json',
                'X-CSRFToken':      CSRF_TOKEN,
                'X-Requested-With': 'XMLHttpRequest',
            },
            body: JSON.stringify({ pendency_id: currentPendencyId }),
        });
        const data = await resp.json();
        if (resp.ok && data.ok) {
            renderModal(data);
            updateTableRow(currentEmployeeId, currentAllocationId, data);
            saveStatusEl.textContent = isRelease
                ? 'Responsavel tecnico liberado.'
                : 'Responsavel tecnico atribuido.';
            saveStatusEl.className = 'text-success small me-auto';
        } else {
            saveStatusEl.textContent = data.error || (
                isRelease
                    ? 'Erro ao liberar responsavel tecnico.'
                    : 'Erro ao assumir responsabilidade.'
            );
            saveStatusEl.className = 'text-danger small me-auto';
        }
    } catch (err) {
        saveStatusEl.textContent = err.message;
        saveStatusEl.className = 'text-danger small me-auto';
    } finally {
        claimBtn.disabled = false;
    }
}
```

- [ ] **Step 5: Update event listener**

Replace:

```javascript
claimBtn.addEventListener('click', claimPendency);
```

With:

```javascript
claimBtn.addEventListener('click', submitResponsibleAction);
```

- [ ] **Step 6: Run Django check**

Run:

```powershell
.\venv\Scripts\python.exe manage.py check --settings=config.settings_dev
```

Expected:

```text
System check identified no issues (0 silenced).
```

## Task 4: Regression Tests and Manual Verification

**Files:**
- No required code changes unless verification finds a defect.

- [ ] **Step 1: Run targeted pendency suite**

Run:

```powershell
.\venv\Scripts\python.exe manage.py test pendencies.tests.test_observation_notifications --settings=config.settings_dev -v 2
```

Expected:

```text
OK
```

- [ ] **Step 2: Run dashboard smoke tests that cover modal rendering**

Run:

```powershell
.\venv\Scripts\python.exe manage.py test dashboard.tests.DailyUserActionBoardTest --settings=config.settings_dev -v 2
```

Expected:

```text
OK
```

If class name differs in this checkout, find exact dashboard test class with:

```powershell
rg -n "class .*Daily.*Action|test_daily_user_action_board|line_detail_modal|Status Pend" dashboard\tests.py
```

Then run the matching class or module.

- [ ] **Step 3: Browser/manual check**

Start dev server:

```powershell
.\venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --settings=config.settings_dev
```

Manual expected behavior:

```text
Admin opens Acoes do Dia.
Admin opens Status Pendencia modal for pendency with no responsible.
Button shows Assumir.
Click Assumir.
Responsible name appears; row Resp. Tecnico updates; button becomes Liberar.
Click Liberar.
Responsible becomes "-"; row Resp. Tecnico becomes "-"; button becomes Assumir.
Action/status/observation remain unchanged.
```

- [ ] **Step 4: Final status check**

Run:

```powershell
git status --short
```

Expected changed files:

```text
M pendencies/tests/test_observation_notifications.py
M pendencies/views.py
M pendencies/urls.py
M templates/dashboard/daily_user_action_board.html
?? docs/superpowers/specs/2026-07-08-pendency-technical-responsible-release-design.md
?? docs/superpowers/plans/2026-07-08-pendency-technical-responsible-release.md
```

If commits were made during previous tasks, status may be clean or only show uncommitted verification artifacts.

## Self-Review

Spec coverage:

- Admin-only release: Task 1 non-admin test, Task 2 `allowed_roles`, Task 3 hides button for non-admin.
- API route and payload: Task 2 route/view.
- No side effects: Task 1 success test preserves action, observation, status, timestamps, notifications.
- Idempotency: Task 1 idempotency test, Task 2 simple null assignment.
- UI switch: Task 3 render/action-mode changes.
- Validation: Task 4 targeted tests, dashboard smoke, manual check.

Placeholder scan:

- No `TBD`.
- No undefined helper names in snippets.
- Commands include expected outputs.

Type consistency:

- `currentResponsibleAction` uses string values `claim` and `release`.
- Backend endpoint uses `pendency_id`, matching existing claim endpoint.
- Response uses `_pendency_to_json`, matching existing modal/table update code.
