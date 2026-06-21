Version 10 — The publish & pages ingestion contract
====================================================

v10 is the second of the three contract-alignment versions derived from
`celbridge_tdd/.../workshop_server_alignment.md`. Where v9 reshaped how a
package version is *read back*, v10 reshapes how packages and pages are
*taken in and served* — the ingestion contract: what the server reads
from the multipart form versus the bundled manifest, what it injects into
served bytes, and what URL shape it returns.

Four items, all on the upload/serve path:

2. **Absolute page URL** (alignment §2).
3. **Manifest schema convergence** (§3).
4. **Publisher author persistence** (§4).
5. **Page manifest** (§5).

They share one seam: the client now sends `author` and `path` as
**multipart fields** (settled in the v8 migration's Phase E), and the
server should treat those form fields — not values baked into the ZIP —
as the source of truth.

> **Scope discipline.** The alignment doc names *what* and *why* and
> leaves *how* (detailed endpoint design) to the server team. The body
> below states each item as the alignment doc states it, grounded in
> current code. My own recommendations are collected under **"Suggested
> extensions"** and are not part of the v10 contract.

> **Depends on v9 only loosely** — different files (ingestion vs.
> read-back). When v10 touches the pages hash it should respect the v9
> content-hash decision (alignment §9).

> **The client has already landed its side.** Each "Client when shipped"
> note is the payoff, not v10 work.

---

## Part A — Absolute page URL (alignment §2)

### A.1 Current behaviour (context)

The page endpoints return a **host-relative** URL: `_page_body`
(`views.py:541-547`, used by publish + detail) and `PageSerializer.get_url`
(`serializers.py:104-105`, used by the list) both build
`/pages/<org-slug>/<path>/`. The client absolutises it itself via
`PageApiClient.ToPage` + `WorkshopApiSender.GetBaseUriAsync`.

### A.2 What the alignment doc asks (server change)

- **Return an absolute `url`** (`https://host/pages/<org>/<path>/`) in
  publish, list, and detail responses. **Only the server knows its
  canonical public host.** Already-absolute URLs pass through unchanged.

### A.3 Client payoff (not v10 work)

Delete `PageApiClient.ToPage`'s host-relative absolutisation pass and the
`WorkshopApiSender.GetBaseUriAsync` call it uses.

---

## Part B — Manifest schema convergence (alignment §3)

The manifest's `[package].name`, optional `title`, and conservative
naming rule are settled. Three remaining gaps.

### B.1 Current behaviour (context)

`process_upload` calls `_stamp_version_into_toml`
(`package_pipeline.py:79-114`, invoked at `:272`) to write `version = N`
into the served `package.toml` before repackaging (`_repackage_zip`,
`:117-155`). `parse_package_zip` **400s** when `[package].author` is
absent (`package_parsing.py:77-81`). `summary` is read from the form
(`views.py:241`) into a `TextField` (`models.py:136`) with no explicit
length check.

### B.2 What the alignment doc asks (server changes)

- **Stop injecting `version = N` into the served package zip's
  `package.toml`.** The schema is "no version field (server-assigned)",
  but installs come out 102 bytes vs the 90-byte authored source — a
  phantom diff in three-way merges between an authored copy and an
  installed one.
- **Stop requiring `[package].author` in the uploaded manifest.** The
  client now sends `author` as a multipart field from Workshop settings
  (Phase E) and no longer writes it into the bundle, but the server still
  400s when the key is absent.
- **Confirm the server's `summary` length limit meets or exceeds the
  client's 512-character cap (R10).**

### B.3 Client payoff (not v10 work)

- No code change for the `version` injection — the C# loader already
  ignores stray manifest keys. Installed and authored manifests become
  byte-identical.
- The Phase F test fixture drops its temporary `author = "…"` line.

---

## Part C — Publisher author persistence (alignment §4)

### C.1 Current behaviour (context)

The version author is derived from the **manifest**: `process_upload`
`get_or_create`s an `Author` from `parsed.author`
(`package_pipeline.py:231-233`). Pages capture no author from the form —
`Page.published_by` is set from the authenticated principal only
(`pages.py:128-136`), so an org **service** key leaves `published_by`
`None` and the list reports `'service'` (`serializers.py:110-111`). The
client flagged this empty `publishedBy` in Phase E and already sends
`author` as a multipart field on every publish.

### C.2 What the alignment doc asks (server change)

- **Read the multipart `author` field on `package_publish` and
  `page_publish`, persist it as the version author / page `publishedBy`,
  and stop relying on the (no-longer-sent) manifest `author`.** Confirm
  the field name (`author`) and that it surfaces in version metadata and
  page detail.

### C.3 Client payoff (not v10 work)

The empty `publishedBy` that Phase E flagged is populated automatically —
no client change.

---

## Part D — Page manifest (alignment §5)

### D.1 Current behaviour (context)

`pages_parsing.py` requires a top-level **plural `pages.toml`**
(`_read_toml_at_root`, `:67-74`; `_MANIFEST` in `pages.py:38`) and reads
the served `path` from `[publish].path` inside it
(`parse_pages_zip`, `:99-102`) — even though the client already sends
`path` as a multipart field on every publish.

### D.2 What the alignment doc asks (server changes)

Two related items:

- **Either accept singular `page.toml`** instead of (or alongside) plural
  `pages.toml` — the plural breaks the project's otherwise-singular config
  convention (`package.toml`, `.celbridge`) and tripped both a user and an
  agent during dogfooding. **Or keep `pages.toml`** and the client retains
  its near-miss detector.
- **Read the multipart `path` field on `page_publish`** instead of from
  the bundled manifest, so the bundle can stop carrying `pages.toml`. The
  client already sends `path` on every publish.

### D.3 Client payoff (not v10 work)

- One-line change: `PageConstants.ManifestFileName` flips to `page.toml`
  if the server accepts the singular.
- One-line change: `BuildPageArchiveAsync` excludes the manifest from the
  ZIP once the server reads `path` from the form field. Only web content
  leaves the machine.

---

## Data model — v10 changes implied by the alignment doc

| Model | Change the alignment doc implies |
|---|---|
| `PackageVersion` | no field change; the **served ZIP** stops carrying an injected `version`; author sourced from the form |
| `Page` / `PagePublication` | a page must persist its publisher from the form `author` and surface it in page detail (the alignment doc says "persist as page `publishedBy`"); the storage shape is the server's call — see Suggested extensions |
| `Author` | unchanged; name now comes from the form rather than the manifest |
| `Package` / `PackageAlias` / `Organisation` / `Membership` / `ApiKey` | unchanged |

---

## API / wire-contract surface (v10)

```
# packages
POST /api/packages/{name}/versions
     reads multipart `author` (and existing summary/description/parent_version/base);
     manifest `author` no longer required;
     served package.toml byte-identical to the authored source (no `version=` injection)

# pages
POST /api/pages
     reads multipart `path` (and `author`); bundle need not carry pages.toml;
     singular `page.toml` accepted (per §5 choice)
GET    /api/pages            list — absolute `url`, author surfaced
GET    /api/pages/{path}     detail — absolute `url`, author surfaced
DELETE /api/pages/{path}     unchanged
GET    /pages/{org-slug}/{path}/...   served output — unchanged
```

No URL layout change; bodies and ingestion inputs change.

---

## Decisions the alignment doc settles (v10)

1. **Page URLs are absolute** (publish/list/detail); the host is the
   server's canonical public host. (§2.)
2. **The server stops injecting `version = N`** into the served
   `package.toml`. (§3.)
3. **`[package].author` is no longer required** in the uploaded manifest.
   (§3.)
4. **The server `summary` limit meets or exceeds 512 chars.** (§3.)
5. **`author` is read from the multipart form** and persisted as the
   version author / page publisher, for both packages and pages; it
   surfaces in metadata and page detail. (§4.)
6. **`path` is read from the multipart form** for page publish, so the
   bundle can stop carrying a manifest. (§5.)
7. **Singular vs plural manifest is settled one way** — accept `page.toml`
   (and the client drops its detector) *or* keep `pages.toml` (and the
   client keeps it). (§5; the alignment doc offers both — see Suggested
   extensions for which I'd pick.)

---

## Suggested extensions (NOT in the alignment doc — candidates for a later version or the implementation plan)

- **Singular/plural — accept `page.toml` and, since `path` now comes from
  the form, make the manifest optional entirely.** The alignment doc
  presents singular-vs-plural as an open choice. I'd pick **singular
  `page.toml`** (matches `package.toml`; removes the dogfooding trap) and
  go further: once `path` is form-driven the bundle is just web content,
  so the cleanest end state is **no required manifest at all** (a `400`
  when the `path` form field is missing). *(The alignment doc only asks to
  read `path` from the form "so the bundle *can* stop carrying
  `pages.toml`"; making it mandatory-absent is my extension.)*
- **Pages author storage.** The alignment doc says "persist as page
  `publishedBy`", but `Page.published_by` is a *user* FK
  (`models.py:209-215`) and a form `author` is free text that an org
  service key has no user for. I'd add a `Page.author` (and
  `PagePublication.author`) `CharField` for the displayed name, keeping
  `published_by` for the authenticated-user case. *(Storage shape is the
  server's call.)*
- **Absolute-URL host source — configured, not request-derived.** I'd
  build the absolute page URL from a configured canonical origin (a
  setting, or Django `Sites`/`ALLOWED_HOSTS`-derived host) rather than the
  inbound `Host` header, so the same page always advertises the same
  public URL regardless of proxy/hostname. *(The alignment doc only says
  "only the server knows its canonical public host".)*
- **`summary` cap made explicit.** §3 only asks to *confirm* the limit is
  ≥512. A `TextField` already accepts that, so no change is strictly
  required; I'd optionally add an explicit `400` above an agreed maximum so
  the contract is a stated number rather than "whatever TextField allows".
- **Author-source precedence.** With the manifest author optional (§3) and
  the form author authoritative (§4), I'd treat a lingering manifest
  `author` as a fallback only, and `400` when neither is present — so
  there is always exactly one conceptual source.

---

## Out of scope for v10

- The v9 read-back items and the v11 identity/rebrand items.
- More than `path`/`author` on the page side (redirects, headers, display
  name) — still a later extension, ignored if present (inherited v8
  stance).
- Versioned page bundles / rollback; common-prefix auto-stripping of page
  ZIPs (inherited v8 out-of-scope).

---

## Cutover

v10 changes ingestion inputs and served bytes but not URL layout.

1. Any pages-side schema change (to store the form `author`) is migrated;
   no backfill needed (existing rows have an empty author until
   republished).
2. Deploy the v10 server. It reads `author` and `path` from the form,
   which the modern client already sends, so a current client keeps
   working unchanged; the payoff is the client dropping its
   manifest-author line, its manifest-build step, and its URL
   absolutisation pass.
3. Because the manifest `author` is no longer required and the served
   `version=` injection is gone, re-publishing produces a
   byte-identical-to-source `package.toml`; old already-installed bundles
   are not rewritten in place.
