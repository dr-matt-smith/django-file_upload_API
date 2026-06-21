Version 9 — The package-version contract: delete, provenance, hashes, aliases
=============================================================================

v9 is the first of three versions that bring the **server** into line
with the client/server contract the v8 package-hub migration left
half-finished. The full backlog lives in
`celbridge_tdd/.../workshop_server_alignment.md` (13 items). This
document takes the four that all touch the **`PackageVersion` /
`PackageAlias` models and the package serializers** — the package
wire contract around a version's lifecycle, provenance, identity, and
resolution:

1. **Align the delete contract** (alignment §1).
2. **Aliases are static; `latest` is client-resolved** (§10).
3. **Version provenance: the `base` back-pointer** (§8).
4. **Content-hash format** (§9).

They are grouped because they are read or written through the **same two
models and the same serializer**
(`PackageVersionSerializer`, `PackageListItemSerializer`,
`PackageDetailSerializer`), so they share migrations, tests, and one
review pass. Publish-ingestion items are v10; rebrand/identity are v11.

> **Scope discipline.** The alignment doc states explicitly that it names
> *what* and *why*, and that "the server team owns *how* (detailed
> endpoint design)". This document therefore describes each item as the
> alignment doc states it, grounded in the current Django code for
> context. Concrete design choices I would *recommend* but that the
> alignment doc does not mandate are collected at the end under
> **"Suggested extensions"** — they are explicitly not part of the v9
> contract and can be deferred to a later version or settled in the
> implementation plan.

> **Foundation-agnostic (alignment §13).** The *what* and *why* of every
> item is independent of whether the server stays on Django or is rebuilt
> on C#; this doc describes the change against the current Django codebase
> because that is what exists today.

> **The client has already landed its side.** Every item is a server
> change the in-app client has stubbed, shimmed, or deferred. The "Client
> when shipped" notes record what the client *drops* once the server
> catches up — they are the payoff, not v9 work.

---

## Part A — The delete contract (alignment §1)

### A.1 Current behaviour (context)

The server models a deleted version as a **tombstone**:
`PackageVersion.tombstoned_at` / `tombstone_reason` (`models.py:145-146`),
`is_tombstoned` (`models.py:157-159`), serialized as a `tombstoned`
boolean + `tombstone_reason` (`serializers.py:11,24-26,38-39`).
`_tombstone_version` (`views.py:103-132`) clears the ZIP but leaves
`description` (`models.py:148`). `DELETE /api/packages/{name}`
(`views.py:190-206`) cascade-tombstones every version but **leaves the
`Package` container row**. `PackageListItemSerializer.get_latest_version`
(`serializers.py:66-70`) returns the highest version **without filtering
tombstoned ones**.

### A.2 What the alignment doc asks (server changes)

Four changes, ideally landed together:

- **Rename the version record's `tombstoned` flag to `deleted`.**
  Celbridge does not model a dead-but-retained tombstone state.
- **Strip the publisher-written `description` on delete** (return empty
  or absent). The version number and `content_hash` are retained.
- **Add a real package-removal endpoint.** `DELETE /api/packages/{name}/`
  currently cascade-deletes every version's content but leaves the
  package container listed.
- **Filter `latestVersion` against `deleted`** so `package_list` returns
  `null` when no live version remains.

### A.3 Client payoff (not v9 work)

- Drop the `[JsonPropertyName("tombstoned")]` shim on `AliasDto` /
  `VersionDetailDto`.
- Drop the `package_list` "latestVersion may be stale after delete"
  caveat.
- Drop the `package_info` "package_unpublish does not 404" gotcha.
- Walkthrough prompt steps 38–39 collapse to the long-term contract
  automatically.

---

## Part B — Aliases are static; `latest` is client-resolved (alignment §10)

### B.1 Current behaviour (context)

The server actively **manages** `latest` and mutates aliases on delete:
`process_upload` auto-upserts a `latest` alias on every publish
(`package_pipeline.py:285-288`); `_set_latest` / `_move_or_drop_latest`
(`views.py:80-100`) re-point or drop it; `GET /api/packages/{name}/latest`
(`views.py:383-400`, route `urls.py:36-40`) serves it; and
`_tombstone_version` (`views.py:122-128`) **deletes every non-`latest`
alias** pointing at a deleted version and **re-points or drops `latest`**.

### B.2 What the alignment doc asks (settled contract)

**Aliases are static pointers.** Deleting a version does not repoint or
detach an alias that points at it. The alias keeps pointing at the
now-deleted version; an install through it resolves to that version and
then fails at download with the standard "version deleted" error — the
same path an explicit version request takes. The client never relies on
the server silently moving a publisher's pointer.

**`latest` is client-resolved and reserved.** The client computes
`latest` as the newest non-deleted version from package metadata it
already fetches; it does not depend on a server-managed `latest` alias or
the `GET …/latest/` endpoint. `latest` is a reserved keyword the client
refuses to create or remove as an alias.

**Server changes:**

- On version delete, **leave every alias pointing where the publisher put
  it.** Do not auto-repoint or auto-detach.
- **No need to manage a `latest` alias or guarantee `GET …/latest/`** —
  `latest` is a client concept. The endpoint **may remain** for other
  consumers, but the in-app client does not use it for resolution.

### B.3 Client payoff (not v9 work)

- `PackageVersionResolver` resolves an alias to its target without a
  liveness check; download is the single authority on existence.
- The unused `DownloadLatestAsync` / `GET …/latest/` path can be dropped
  from the client.
- The delete confirmation states the aliases are left pointing at the
  deleted version, rather than hedging "dangling or repointed".

---

## Part C — Version provenance: the `base` back-pointer (alignment §8)

### C.1 Current behaviour (context)

The only persisted provenance pointer is `forked_from`
(`models.py:138-144`), a **same-table self-FK** serialized as
`{package, version}` (`serializers.py:41-47`), set only on a brand-new
package name via `_detect_fork` (`package_pipeline.py:158-186`). The
publish view also accepts a `parent_version` form field used solely for a
head-mismatch check (`views.py:243-252`, `package_pipeline.py:252-253`).
The client-side rendering has already landed (`# name@version` headers, a
compact metadata line, the stale-base advisory on publish); only the wire
round-trip is missing.

### C.2 What the alignment doc asks (server changes)

- **Accept and persist a name-qualified `{name, version}` `base` field on
  publish.** (The existing `parent_version` marker is version-only and
  same-package, so it needs generalising to cover renames and forks.)
- **Return `base` per version** in version metadata / `package_info`.
- **Settle naming: `base` end to end** (matching the rendered
  `HISTORY.md` field), not the proposal's earlier `basedOn`. The shorter
  form keeps one vocabulary.

### C.3 Client payoff (not v9 work)

- `package_publish` sends `base` from the local install record (already
  read for the stale-base check).
- `PackageHistoryFile.Format` adds the `base` field to the metadata
  line — **always emitted** (`base: name@version`, or `base: none` for
  roots/hand-authored). Today the client deliberately omits the field.
- `base_hash` is added **only** for cross-package bases (a fork/rename
  ancestor whose entry may be unavailable, especially if deleted), where
  it makes the pointer self-verifying.
- `package_info` result exposes `base` per version.
- Optional later: a configurable "refuse" mode on the stale-base check.

---

## Part D — Content-hash format (alignment §9)

### D.1 Current behaviour (context)

`content_hash` flows from version metadata into `package_info`,
`HISTORY.md`, and (for pages) page detail, and an agent compares it
against a locally computed hash. Today the server is **inconsistent**:
packages emit `'sha256:' + hexdigest()` (`package_pipeline.py:292`) —
lowercase hex **with** an `sha256:` prefix — while pages emit a bare
`hexdigest()` (`pages.py:117`) — lowercase hex, **no** prefix. The client
strips a possible `algo:` prefix defensively
(`PackageHistoryFile.TruncateHash`).

### D.2 What the alignment doc asks (server changes)

- **Emit `content_hash`** (version metadata and page `content_hash`) **as
  lowercase-hex SHA-256**, so it compares directly with a client-computed
  `file_get_info` hash. (The client settled on lowercase hex — what git,
  `sha256sum`, and Docker digests emit.)
- **Settle whether the value carries an algorithm prefix (`sha256:…`) or
  is bare hex, and keep it consistent across packages and pages.** *(The
  alignment doc leaves this choice to the server; see Suggested
  extensions for a recommendation.)*

### D.3 Client payoff (not v9 work)

No code change if the server already emits lowercase. `TruncateHash`'s
defensive `algo:` strip can be simplified once the prefix question is
settled.

---

## Data model — v9 changes implied by the alignment doc

| Model | Change the alignment doc implies |
|---|---|
| `PackageVersion` | rename the deleted-state field(s) from `tombstoned`→`deleted`; clear `description` on delete (retain version number + `content_hash`); persist a name-qualified `base` (`{name, version}`); emit `content_hash` as lowercase hex |
| `Package` | gains *some* way to be removed as a container (the alignment doc requires the container stop being listed; it does not specify the mechanism) |
| `PackageAlias` | **no schema change**; behaviour change only — no auto-detach / auto-repoint on version delete; `latest` no longer server-managed |
| `Author` / `Organisation` / `Membership` / `ApiKey` / `Page` / `PagePublication` | unchanged |

> The alignment doc names the *fields and behaviours*; the exact storage
> shape (e.g. how `base` is stored, how the container is removed, the
> on-disk migration) is the server team's call — see Suggested extensions
> and the implementation plan.

---

## API / wire-contract surface (v9)

```
GET    /api/packages                 latest_version excludes deleted (null if none live)
GET    /api/packages/{name}          version objects use `deleted`/`delete_reason`/`base`
POST   /api/packages/{name}/versions accepts `base={name,version}`; persists it
GET    /api/packages/{name}/versions/{n}        `deleted`/`delete_reason`/`base`; lowercase content_hash
DELETE /api/packages/{name}/versions/{n}        sets the deleted state + clears description; does NOT touch aliases
DELETE /api/packages/{name}                     cascade-delete versions; plus a way to remove the container
GET    /api/packages/{name}/latest              MAY remain (not used by the in-app client for resolution)

# alias routes unchanged in shape; server no longer auto-mutates aliases on delete
PUT    /api/packages/{name}/aliases/{alias}
DELETE /api/packages/{name}/aliases/{alias}
```

No URL layout change is required by the alignment doc; pages routes are
untouched.

---

## Decisions the alignment doc settles (v9)

1. **A deleted version is `deleted`, not tombstoned** — field rename end
   to end; `description` cleared on delete; version number and
   `content_hash` retained. (§1.)
2. **The package container can be removed** so it stops being listed
   (§1) — *mechanism left to the server*.
3. **`latestVersion` excludes deleted versions** — `null` when none live.
   (§1.)
4. **Aliases are static** — deleting a version never detaches or repoints
   an alias; download is the single authority on existence. (§10.)
5. **`latest` is not server-managed** — the in-app client resolves it;
   the `/latest` endpoint may remain for other consumers. (§10.)
6. **Provenance is one name-qualified `base` field** (`{name, version}`),
   generalising the same-package marker; named `base` end to end. (§8.)
7. **`content_hash` is lowercase-hex SHA-256**, consistent for packages
   and pages; the prefix-vs-bare question is to be settled. (§9.)

---

## Suggested extensions (NOT in the alignment doc — candidates for a later version or the implementation plan)

These are my recommendations where the alignment doc deliberately leaves
the *how* open. They are **not** part of the v9 contract; flagged here so
they are not mistaken for it.

- **Package-removal shape — soft-delete the container.** The alignment
  doc only requires the container stop being listed. I'd suggest adding a
  `Package.deleted_at` and filtering it out of `package_list` /
  `package_info` (preserving history) rather than hard-deleting the row,
  and exposing it as `DELETE /api/packages/{name}?purge=true` so the
  existing cascade verb is unchanged. *(Deferrable; settle in the v9
  implementation plan.)*
- **`base` storage as plain fields.** Since a `base` can name another
  package (rename/fork) and that package may be renamed or deleted, I'd
  store it as `base_name` + `base_version` columns rather than an FK, and
  retire the `forked_from` self-FK (fork-at-creation just populates
  `base`). This avoids two overlapping provenance fields. *(Implementation
  detail; the contract only needs the `{name, version}` round-trip.)*
- **`content_hash` prefix — pick bare hex.** I'd settle §9 on **bare
  lowercase hex (no `sha256:` prefix)** because the client's
  `file_get_info` returns bare hex, so it compares directly; this also
  needs a one-off data migration to strip the prefix from existing rows
  so the client's defensive strip can eventually be retired. *(The
  alignment doc explicitly leaves the prefix choice to the server.)*
- **Re-implement `/latest` as "highest non-deleted, computed live"** if
  the endpoint is kept — so it agrees with the client's definition rather
  than reading a stored `latest` row that no longer exists. *(Optional;
  the alignment doc only says the endpoint "may remain".)*
- **`summary` on delete.** The alignment doc names only `description` as
  stripped; I'd confirm `summary` is *retained* (it is the short line the
  rendered `HISTORY.md` shows for every version). *(Clarification, not a
  change.)*
- **`base_hash` server echo** (future): the alignment doc keeps
  `base_hash` client-side only; a later version could have the server
  store/return it, which folds into the per-version file-manifest
  follow-up.

---

## Out of scope for v9

- Absolute page URLs, manifest convergence, author persistence, the
  `page.toml` rename — **v10**.
- Rebrand, `kpf_`→`cel_`, the health endpoint, "Workshop Key" naming —
  **v11**.
- Per-version file manifest (alignment follow-up) and scoped/per-user keys
  (alignment §6) — later.

---

## Cutover

v9 changes response/request **bodies** but not URL layout.

1. Migrate the schema (rename the deleted-state field; persist `base`;
   provide the container-removal mechanism; align `content_hash` casing).
   The exact migration steps depend on the storage choices above and are
   detailed in the implementation plan.
2. Deploy the v9 server. Old clients still reading `tombstoned` /
   `forked_from` break on the rename — coordinate with the client release
   that drops the shims (this is the payoff; the two land together).
3. The Part B behaviour change (no auto-detach on delete) means publisher
   aliases now persist across a target delete — the intended static
   contract; no data migration, but operators should know previously
   auto-cleaned aliases will now linger.
4. Pages data and routes are untouched by v9.
