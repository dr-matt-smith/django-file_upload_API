Version 11 — Implementation Plan
==================================
Identity & rebrand: Celbridge Workshop API, Workshop Key, `/api/whoami`

Covers alignment §6, §7, §11, §12. No migrations. All changes are code,
strings, and docs. Safe to deploy independently of v9/v10, but should land
last since it is the lowest-risk item.

> Suggested extensions deferred to v12: accept both `kpf_` and `cel_`
> markers during a transition window (allows existing keys to keep
> authenticating without forced re-issuance); `/api/health` as a separate
> unauthenticated liveness endpoint.

---

## Step 1 — Change the API-key marker from `kpf_` to `cel_` (auth.py)

File: `file_manager/auth.py`

### 1a — `generate_key()`

```python
def generate_key() -> tuple[str, str, str]:
    """Return (plaintext, prefix, hash). The plaintext is shown once."""
    prefix = secrets.token_hex(4)          # 8 hex chars
    secret = secrets.token_urlsafe(32)
    plaintext = f'cel_{prefix}_{secret}'   # ← was kpf_
    return plaintext, prefix, make_password(plaintext)
```

### 1b — `_lookup_and_verify()`

```python
def _lookup_and_verify(raw: str) -> ApiKey | None:
    parts = raw.split('_', 2)
    if len(parts) != 3 or parts[0] != 'cel':   # ← was kpf
        return None
    prefix = parts[1]
    for key in ApiKey.objects.filter(prefix=prefix, revoked_at__isnull=True):
        if check_password(raw, key.hash):
            return key
    return None
```

### 1c — Update module docstring (top of file)

Replace all occurrences of `kpf_` with `cel_` in the docstring and any
inline comments.

> **Important:** This is a breaking change for existing `kpf_…` keys.
> All current key holders must revoke-and-reissue to obtain a `cel_…` key
> before the server is deployed. The v12 suggested extension (dual-marker
> acceptance window) avoids forced re-issuance if that is operationally
> required.

---

## Step 2 — Add the `WhoAmIView` health/identity endpoint (views.py)

File: `file_manager/views.py`

Add a new view at the bottom of the file, before the page views or in a
logical group with the other `OrgScopedView` classes:

```python
# ---------------------------------------------------------------------------
# /api/whoami
# ---------------------------------------------------------------------------

class WhoAmIView(OrgScopedView):
    """Lightweight authenticated probe.

    Returns 200 with the caller's organisation and author identity when the
    Workshop Key is valid; DRF returns 401 automatically when it is not.
    Lets the client distinguish 'key rejected' from 'host unreachable'.
    """

    def get(self, request):
        org = self.org
        author_name = None
        if request.user and getattr(request.user, 'is_authenticated', False):
            membership = getattr(request.user, 'membership', None)
            if membership is not None:
                author_name = request.user.get_username()
        return Response({
            'organisation': org.slug,
            'organisation_name': org.name,
            'author': author_name,
        })
```

---

## Step 3 — Register `/api/whoami` in the URL configuration (urls.py)

File: `file_manager/urls.py`

Add the import and the route:

```python
from .views import (
    ...
    WhoAmIView,          # ← ADD
)

urlpatterns = [
    re_path(r'^whoami/?$', WhoAmIView.as_view(), name='whoami'),   # ← ADD (first)
    re_path(r'^packages/?$', PackagesView.as_view(), name='packages'),
    ...
]
```

---

## Step 4 — Update the `issue_api_key` management command (management/commands/issue_api_key.py)

File: `file_manager/management/commands/issue_api_key.py`

- Update any output strings that reference `kpf_` → `cel_`.
- Update any help text that says "API key" or "Application Key" →
  "Workshop Key".
- If the command prints the key format, update the example to show
  `cel_<prefix>_<secret>`.

---

## Step 5 — Rebrand user-facing strings and error messages (views.py, auth.py, permissions.py)

### views.py

- `_tombstone_version` docstring and any inline comments: replace "Package Hub" → "Workshop".
- Module docstring (line 1–12): update "v7 package API" context, "Package Hub" references → "Celbridge Workshop API".

### auth.py

- Module docstring (line 1–11): update "v7 package API" → "Celbridge Workshop API",
  `kpf_` → `cel_`.

### permissions.py

- Module docstring: update "v7 package API" → "Celbridge Workshop API".

### package_pipeline.py

- Module docstring (line 1–11): update "v7 packages" → "Workshop packages",
  remove or update "Package Hub" references.

### pages.py

- Module docstring: update any "v8" / "Package Hub" references.

---

## Step 6 — Rename credential label "Workshop Key" in admin and issuance flow

File: `file_manager/admin.py`

Check for any `ApiKey`-related list display, verbose names, or help texts
that say "Application Key", "API key", or "Package Hub key". Rename to
"Workshop Key".

File: `file_manager/models.py`

In `ApiKey.__str__`, the label field comes from the caller. If any hardcoded
label strings appear elsewhere, update them. The `label` field stores
whatever the issuer provides — update the management command and admin
forms to suggest/default to "Workshop Key" as the label convention.

---

## Step 7 — Update README and architecture docs (docs sweep)

Files: `README.md`, `README_deploy.md`, `README_Matt_pythonanwyhere_setup_notes.md`,
`README_local_testing.md`, `README_list_users.md`

Search and replace:
- `"Celbridge Hub"` → `"Celbridge Workshop"`
- `"celbridge-hub"` → `"celbridge-workshop"` (repo/package references)
- `"celbridge-hub-api-client"` → `"celbridge-workshop-api-client"`
- `"Package Hub"` → `"Workshop"` or `"Celbridge Workshop API"` (context-dependent)
- `"Application Key"` or `"API key"` (as a credential name) → `"Workshop Key"`
- `kpf_` → `cel_` in all key-format examples

Note: endpoint paths (`/api/packages/…`, `/api/pages/…`) are correct and
do not change. Only identity strings change.

---

## Step 8 — Update `_prompt.md` and any internal workflow docs

File: `_prompt.md` (project root)

Apply the same rebrand sweep: Hub → Workshop, kpf → cel, Application Key →
Workshop Key.

---

## Step 9 — Update tests

Files: `file_manager/tests_v4.py`, `file_manager/tests_v6.py`,
`file_manager/tests_pages.py`, `file_manager/tests_org_isolation.py`

- Update any test fixture or assertion that creates/checks a key with
  `kpf_` prefix → `cel_`.
- Add a test for `GET /api/whoami`:
  - Valid key → 200 with `organisation`, `organisation_name`, `author`.
  - No key / invalid key → 401.
  - Confirm the response body does not leak cross-org data.
- Add a test that `kpf_…` keys are now rejected (401) by `_lookup_and_verify`.

---

## Step 10 — Deploy checklist

1. **Pre-deploy:** notify all key holders — existing `kpf_…` keys will
   stop working on deploy. Revoke-and-reissue to obtain `cel_…` keys.
   *(If zero-downtime key rollover is required, implement the v12
   dual-marker suggestion before deploying.)*
2. Deploy server — no migration needed.
3. The `/api/whoami` endpoint is live. Update the client Settings page to
   call `/api/whoami` instead of `GET /api/packages/` for the connection check.
4. Release the coordinated client change:
   - Flip `CredentialConstants.WorkshopKeyPrefix` constant from `kpf_` to `cel_`.
   - Update the advisory typo-guard string (`"Workshop Keys start with cel_…"`).
   - Update Settings connection check to call `/api/whoami`.
   - Sweep "Hub" → "Workshop" in any remaining user-facing strings.
5. Rename the reference client repo/package from `celbridge-hub-api-client`
   to `celbridge-workshop-api-client` (GitHub repo rename + package.json / NuGet
   package ID update — coordinate with consumers of that package).
