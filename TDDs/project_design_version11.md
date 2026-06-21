Version 11 — Identity & rebrand: the Celbridge Workshop API
===========================================================

v11 is the third and final contract-alignment version derived from
`celbridge_tdd/.../workshop_server_alignment.md`. v9 reshaped how a
package version reads back; v10 reshaped ingestion. v11 closes the loop on
**identity** — the product's name, the credential's name and marker, and
the one small endpoint the client needs to confirm which workshop a key
binds to.

Four items, all about the human- and tool-facing identity surface:

7. **Rebrand: "Celbridge Hub" → "Celbridge Workshop API"** (alignment §7).
6. **Workshop Key lifecycle and format** (§6).
12. **Workshop Key naming** (§12).
11. **Connection health endpoint** (§11).

> **Scope discipline.** The alignment doc names *what* and *why* and
> leaves *how* to the server team. The body states each item as the doc
> states it, grounded in current code; my recommendations are collected
> under **"Suggested extensions"** and are not part of the v11 contract.

> **No endpoint path renames.** The alignment doc is explicit that
> `/api/packages/…` and `/api/pages/…` are namespace-correct and stay —
> v11 is identity, not URL layout.

> **Mostly contract confirmation on the client side.** Items 6 and 12 are
> "no client code change"; item 7 is one constant flip plus strings; item
> 11 is a single call-site swap.

---

## Part A — The rebrand (alignment §7)

### A.1 Current behaviour (context)

The server is branded **"Celbridge Hub" / "celbridge-hub"** (reference
client `celbridge-hub-api-client`). The API-key marker is **`kpf_`**:
`generate_key` builds `f'kpf_{prefix}_{secret}'` (`auth.py:24-29`) and
`_lookup_and_verify` rejects anything whose leading segment is not `kpf`
(`auth.py:32-40`). Module docstrings, the architecture docs, the
`README*.md` set, error text, and headers carry "Hub" / "Package Hub".
The in-app client has already converged on "Workshop" vocabulary
(`WorkshopConnection`, `WorkshopApiSender`, `IPackageApiClient`).

### A.2 What the alignment doc asks (server changes)

- **Rename the server's user-facing identity** from "Celbridge Hub" /
  "Package Hub" to **"Celbridge Workshop"** (the running instance) and
  **"Celbridge Workshop API"** (the contract).
- **Rename the reference client repo/package** from
  `celbridge-hub-api-client` to `celbridge-workshop-api-client`.
- **Change the API-key leading marker from `kpf_` to `cel_`.** The
  marker's purpose is issuer identification for humans and secret
  scanners, and `kpf_` does not say Celbridge. A survey found neither
  marker registered to an existing service's token format, so there is no
  collision (precedents: Cloudflare `cfut_`, Confluent `cflt`, Stripe
  `sk_live_`).
- **Update server-side docs** (`packages_api_server_architecture.md` and
  siblings), error messages, and any HTTP `Server:` / `User-Agent:`
  headers that name the product.
- **Endpoint paths under `/api/packages/…` and `/api/pages/…` stay
  as-is** — the rebrand is identity, not URL layout.

This is the largest-scope item by reach but a small one by code volume —
worth doing alongside whatever the server team is already touching.

### A.3 Client payoff (not v11 work, but coordinated)

- `CredentialConstants.WorkshopKeyPrefix` flips from `kpf_` to `cel_`
  (single constant change).
- One localized warning string updates ("Workshop Keys start with
  `cel_`…"). The typo guard is advisory, so already-stored keys keep
  working across the change either way.
- Internal user-facing strings that say "Hub" become "Workshop"; already-
  converged names ("Workshop URL", "Workshop Author") need no change.
- The walkthrough prompt and tool guides update terminology in one pass.

---

## Part B — Workshop Key lifecycle and format (alignment §6)

This item is mostly **contract confirmation** — pinning behaviours the
server already has, plus stating the key format as a stable contract.

### B.1 Current behaviour (context)

`ApiKey` carries `revoked_at` (`models.py:71`); `_lookup_and_verify`
filters `revoked_at__isnull=True` (`auth.py:37`), so revocation is
immediate. Only the lookup `prefix` and a salted hash of the full key are
stored (`models.py:67-69`); the plaintext is shown once. The format is
`kpf_<prefix>_<secret>` (`prefix = token_hex(4)` → 8 hex chars; `secret =
token_urlsafe(32)`).

### B.2 What the alignment doc asks (server confirmations)

- **Confirm revoke-and-reissue is fast and workable** (it is the only
  response to a leak).
- **Confirm backups exist behind delete** (owner-side disaster recovery; a
  leaked key can destroy package content directly via the delete
  endpoints, regardless of the client's confirmation gating).
- **Confirm the issued key format as a stable contract:**
  `kpf_<prefix>_<secret>` (after the rebrand, `cel_<prefix>_<secret>`),
  with the middle segment identifying the individual key (the credential
  store's Settings page displays everything up to the second underscore).
  Per-user or scoped keys (publish-only vs admin) are a longer-term
  upgrade, **not part of this migration**.

### B.3 Client payoff (not v11 work)

No code change; this is contract confirmation. The store and UI degrade
safely if the shape ever changes (an unrecognised key gets no display
hint).

---

## Part C — Workshop Key naming (alignment §12)

### C.1 Current behaviour (context)

The client has standardised on one name — the **Workshop Key** (the
Settings label, the `SettingsPage_WorkshopKey*` strings, the
`WorkshopKey`-scoped `ICredentialService` API,
`CredentialConstants.WorkshopKeyPrefix`). The server and docs use a
scatter: "Application Key", "API key", "Package Hub key".

### C.2 What the alignment doc asks (server changes)

- **Name the issued credential the Workshop Key** in the issuance flow,
  account docs, and any error or help text. Retire "Application Key",
  "API key", and "Package Hub key" as user-facing labels.
- **The HTTP auth scheme stays wire-level** (`Authorization: Api-Key
  <key>`, `auth.py:44`); this item is the human-facing name, not the
  transport token.
- **Name it once and keep it:** do not introduce "Workshop API Key" or
  other variants. One concept, one name.

### C.3 Client payoff (not v11 work)

No code change; the client already uses "Workshop Key" throughout.

---

## Part D — Connection health endpoint (alignment §11)

### D.1 Current behaviour (context)

The Settings page verifies a saved connection by calling
`ListPackagesAsync` (`GET /api/packages/`, `views.py:142-144`) purely for
its status code. It works, but it is heavier than a connectivity probe
needs, and a list failure cannot cleanly tell "key rejected" from "host
unreachable".

### D.2 What the alignment doc asks (server change)

- **Provide a lightweight authenticated endpoint** (e.g. `GET
  /api/whoami` or `/api/health`) that returns `200` with a minimal body
  when the Workshop Key is valid and `401` when it is not. **Ideally it
  echoes the resolved org / author**, so the client can confirm *which*
  workshop the key binds to (and surface it beside the connection — see
  §4 / v10).

### D.3 Client payoff (not v11 work)

The Settings connection check calls the dedicated endpoint instead of
`ListPackagesAsync`, letting the InfoBar distinguish `401` (key rejected)
from a network / host error.

---

## Data model — v11 changes

| Model | Change |
|---|---|
| `ApiKey` | **no schema change.** The marker change (`kpf_`→`cel_`) is in `auth.py` (plaintext generation), not the stored fields. |
| everything else | unchanged |

v11 adds **no migrations**. The work is `auth.py` (marker), a small new
health-endpoint view + route, and a docs/strings/branding sweep.

---

## API / wire-contract surface (v11)

```
# new — connection health probe
GET /api/whoami  (or /api/health)   200 + minimal body (ideally echoing org/author) when key valid;
                                    401 when missing/invalid

# unchanged paths; identity strings/branding updated in responses & docs
#   /api/packages/…    (names/paths unchanged — rebrand is identity, not routing)
#   /api/pages/…

# auth — scheme keyword unchanged; marker changes
Authorization: Api-Key <key>
new keys issued as  cel_<prefix>_<secret>
```

---

## Decisions the alignment doc settles (v11)

1. **The product is "Celbridge Workshop" / "Celbridge Workshop API"** —
   identity rebrand across docs, branding, error text, headers; endpoint
   paths unchanged. (§7.)
2. **The API-key marker is `cel_`.** (§7.)
3. **The reference client repo is `celbridge-workshop-api-client`.** (§7.)
4. **Key format is a stable contract:** `cel_<prefix>_<secret>`, prefix
   the human-distinguishable segment shown up to the second underscore;
   scoped/per-user keys remain a later upgrade. (§6.)
5. **Revoke-and-reissue and backups-behind-delete are confirmed and
   documented.** (§6.)
6. **The credential has one human-facing name — the Workshop Key** — end
   to end; the `Api-Key` wire scheme keyword is unchanged. (§12.)
7. **A lightweight authenticated health endpoint exists** (`/api/whoami`
   or `/api/health`): `200` valid / `401` invalid, ideally echoing
   org/author. (§11.)

---

## Suggested extensions (NOT in the alignment doc — candidates for a later version or the implementation plan)

- **Key-marker compatibility window.** The alignment doc says to change
  the marker but does not address existing `kpf_` keys. Because the stored
  record is a salted hash of the full plaintext plus the lookup `prefix`
  (the marker is part of the hashed plaintext), I'd have
  `_lookup_and_verify` accept a leading segment of **either `cel` or
  `kpf`** during a transition — old keys keep authenticating, no forced
  re-issuance — and retire `kpf_` naturally as users revoke-and-reissue.
  *(Not specified by the alignment doc; a safe-rollout suggestion.)*
- **Health-endpoint shape — pick `/api/whoami` with an identity body.**
  The alignment doc offers `/api/whoami` *or* `/api/health` and says it
  should "ideally echo org/author". I'd pick **`/api/whoami`** (the name
  fits an authenticated, identity-echoing probe; `/api/health` connotes an
  unauthenticated liveness check) with a body like
  `{organisation, organisation_name, author, key_kind}`, org-scoped from
  the key so there is no cross-org leak. A separate unauthenticated
  `/api/health` could be added later for uptime monitoring without
  conflict. *(Endpoint shape is the server's call.)*
- **Scoped / per-user role keys** (publish-only vs admin) — the alignment
  doc explicitly defers these; a natural later-version feature now that
  `ApiKey.user` already distinguishes per-user from org-service keys.

---

## Out of scope for v11

- The v9 read-back contract and the v10 ingestion contract.
- Scoped / per-user role keys (alignment §6 defers them).
- Any endpoint **path** rename — paths are namespace-correct and stay.
- Forced re-issuance of `kpf_` keys.

---

## Cutover

v11 adds no migrations; it is a code + docs change with one coordinated
client constant.

1. Deploy the v11 server. New keys issue as `cel_…`; the health endpoint
   goes live. (If the compatibility-window suggestion is adopted, existing
   `kpf_…` keys keep authenticating.)
2. Release the coordinated client change: flip
   `CredentialConstants.WorkshopKeyPrefix` to `cel_`, update the advisory
   typo string, point the Settings connection check at the health
   endpoint, and sweep "Hub"→"Workshop" in user-facing strings.
3. Docs/branding sweep across `packages_api_server_architecture.md`, the
   `README*.md` set, module docstrings, admin labels, and any
   `Server:`/`User-Agent:` headers; rename the reference client repo.
4. No data migration; no forced key rotation.

---

## The three-version arc (for reference)

v9–v11 together discharge the twelve actionable items of
`workshop_server_alignment.md` (item 13, the server-foundation choice, is
a meta-note; the per-version file-manifest is a follow-up):

| Version | Theme | Alignment items |
|---|---|---|
| **v9** | Package-version read-back contract | 1, 10, 8, 9 |
| **v10** | Publish & pages ingestion contract | 2, 3, 4, 5 |
| **v11** | Identity & rebrand | 7, 6, 12, 11 |

Each version is independently shippable. They are ordered so the most
operationally pressing change (the delete contract, which blocks a clean
integration-test reset) lands first and the broad-reach-but-low-risk
rebrand last.
