Version 9 — Implementation Plan
=================================
Package-version read-back contract: delete, provenance, hashes, aliases

Covers alignment §1, §8, §9, §10. All changes are in `file_manager/`.
Coordinate the server deploy with the client release that drops its
`tombstoned`/`forked_from` shims — they land together.

> Suggested extensions deferred to v12: soft-delete the Package container
> (`Package.deleted_at`); retire `forked_from` FK in favour of `base_name`/
> `base_version` as the sole provenance field; bare-hex data migration for
> existing `PackageVersion.content_hash` rows.

---

## Step 1 — Rename deleted-state fields on `PackageVersion` (models.py)

File: `file_manager/models.py`

- Rename field `tombstoned_at` → `deleted_at` (DateTimeField, null/blank).
- Rename field `tombstone_reason` → `delete_reason` (TextField, blank=True).
- Rename property `is_tombstoned` → `is_deleted` (returns `deleted_at is not None`).
- Leave `forked_from` FK, `base_name`, `base_version` for the next step.

```python
# models.py — PackageVersion
deleted_at = models.DateTimeField(null=True, blank=True)
delete_reason = models.TextField(blank=True)

@property
def is_deleted(self):
    return self.deleted_at is not None
```

---

## Step 2 — Add `base` provenance fields to `PackageVersion` (models.py)

File: `file_manager/models.py`

Add two plain fields to `PackageVersion` (no FK — the named package may
be renamed or deleted):

```python
base_name = models.CharField(max_length=255, blank=True)
base_version = models.PositiveIntegerField(null=True, blank=True)
```

Keep the existing `forked_from` self-FK intact for now (retiring it is a
v12 suggested extension). New publishes will populate `base_name`/
`base_version` instead; existing rows keep their `forked_from` link and
the history renderer reads both.

---

## Step 3 — Create and run the Django migration

Generate the migration that covers Steps 1 and 2:

```
python manage.py makemigrations file_manager \
    --name v9_deleted_state_and_base_fields
```

The migration must include:
- `RenameField('PackageVersion', 'tombstoned_at', 'deleted_at')`
- `RenameField('PackageVersion', 'tombstone_reason', 'delete_reason')`
- `AddField('PackageVersion', 'base_name', ...)`
- `AddField('PackageVersion', 'base_version', ...)`

Then add a **data migration** step (RunPython) inside the same migration
to strip the `sha256:` prefix from every existing `PackageVersion.content_hash`
that starts with `sha256:`:

```python
def strip_hash_prefix(apps, schema_editor):
    PV = apps.get_model('file_manager', 'PackageVersion')
    rows = PV.objects.filter(content_hash__startswith='sha256:')
    for pv in rows:
        pv.content_hash = pv.content_hash[len('sha256:'):]
        pv.save(update_fields=['content_hash'])

class Migration(migrations.Migration):
    ...
    operations = [
        # RenameField ops above …
        migrations.RunPython(strip_hash_prefix, migrations.RunPython.noop),
    ]
```

Run: `python manage.py migrate`

---

## Step 4 — Fix content_hash emission in the pipeline (package_pipeline.py)

File: `file_manager/package_pipeline.py`, line 292

Change the hash emission from prefixed to bare lowercase hex:

```python
# before
version.content_hash = 'sha256:' + hashlib.sha256(repacked).hexdigest()

# after
version.content_hash = hashlib.sha256(repacked).hexdigest()
```

Pages (`pages.py:117`) already emit bare hex — no change there.

---

## Step 5 — Stop auto-managing the `latest` alias on publish (package_pipeline.py)

File: `file_manager/package_pipeline.py`, lines 285–288

Remove the `PackageAlias.objects.update_or_create` call that upserts the
`latest` alias on every publish. `latest` is now a client-computed concept;
the server no longer manages it.

```python
# Delete these four lines entirely:
PackageAlias.objects.update_or_create(
    package=package, name=_RESERVED_ALIAS,
    defaults={'version': version},
)
```

---

## Step 6 — Accept and persist `base` on publish (package_pipeline.py + views.py)

### package_pipeline.py

Add `base_name: str = ''` and `base_version: int | None = None` params to
`process_upload`:

```python
def process_upload(
    django_file,
    *,
    organisation,
    expected_name: str | None = None,
    summary: str = '',
    description: str = '',
    parent_version: int | None = None,
    base_name: str = '',
    base_version: int | None = None,
) -> PackageVersion:
```

In the `PackageVersion.objects.create(...)` call, pass the new fields:

```python
version = PackageVersion.objects.create(
    ...
    base_name=base_name or '',
    base_version=base_version,
)
```

When `_detect_fork` returns an ancestor and no explicit `base` was passed,
auto-populate from the fork detection result (this preserves existing fork
semantics via the new `base` fields):

```python
forked_from = _detect_fork(parsed, organisation)
if forked_from is not None and not base_name:
    base_name = forked_from.package.name
    base_version = forked_from.version
```

### views.py — PackageVersionsView.post

Parse `base` from the multipart form (the client sends it as two separate
fields):

```python
base_name = (request.data.get('base_name') or '').strip()
base_version_raw = request.data.get('base_version')
base_version = None
if base_version_raw not in (None, ''):
    try:
        base_version = int(base_version_raw)
    except (TypeError, ValueError):
        return Response(
            {'detail': '`base_version` must be an integer'},
            status=status.HTTP_400_BAD_REQUEST,
        )
```

Pass to `process_upload`:

```python
version = process_upload(
    upload,
    organisation=self.org,
    expected_name=name,
    summary=summary,
    description=description,
    parent_version=parent_version,
    base_name=base_name,
    base_version=base_version,
)
```

---

## Step 7 — Update `_tombstone_version` in views.py

File: `file_manager/views.py`, lines 103–132

1. Rename field references throughout:
   - `version_obj.is_tombstoned` → `version_obj.is_deleted`
   - `version_obj.tombstoned_at = timezone.now()` → `version_obj.deleted_at = timezone.now()`
   - `version_obj.tombstone_reason = reason` → `version_obj.delete_reason = reason`
   - `save(update_fields=['tombstoned_at', 'tombstone_reason', 'zip_file'])`
     → `save(update_fields=['deleted_at', 'delete_reason', 'description', 'zip_file'])`

2. Add description-clearing before the save:
   ```python
   version_obj.description = ''
   ```

3. Remove the alias cascade logic entirely (lines 122–128) — deleting a
   version no longer touches any alias:
   ```python
   # DELETE these lines:
   PackageAlias.objects.filter(version=version_obj).exclude(name=_RESERVED_ALIAS).delete()
   if PackageAlias.objects.filter(
       package=package, name=_RESERVED_ALIAS, version=version_obj,
   ).exists():
       _move_or_drop_latest(package)
   ```

---

## Step 8 — Remove `_set_latest` and `_move_or_drop_latest` (views.py)

File: `file_manager/views.py`, lines 80–100

Delete both helper functions entirely — they are no longer called after
Steps 5 and 7.

---

## Step 9 — Update all `is_tombstoned` call sites (views.py)

File: `file_manager/views.py`

Rename every remaining reference:

| Location | Old | New |
|---|---|---|
| `PackageVersionView.delete` (line 310) | `version_obj.is_tombstoned` | `version_obj.is_deleted` |
| `PackageVersionView.delete` error message | `'version already tombstoned'` | `'version already deleted'` |
| `PackageVersionDownloadView.get` (line 347) | `version_obj.is_tombstoned` | `version_obj.is_deleted` |
| `PackageVersionDownloadView.get` 410 body `'detail'` | `'tombstoned'` | `'deleted'` |
| `PackageVersionDownloadView.get` 410 body key | `'tombstone_reason'` | `'delete_reason'` |
| `PackageVersionDownloadView.get` 410 body key | `'tombstoned_at'` | `'deleted_at'` |
| `PackageAliasView.put` (line 507) | `target.is_tombstoned` | `target.is_deleted` |
| `PackageAliasView.put` error message | `'version {n} is tombstoned'` | `'version {n} is deleted'` |

Also update the filter in `PackageView.delete` (line 201):
```python
# before
PackageVersion.objects.filter(package=package, tombstoned_at__isnull=True)
# after
PackageVersion.objects.filter(package=package, deleted_at__isnull=True)
```

---

## Step 10 — Hard-delete the Package container (views.py)

File: `file_manager/views.py`, `PackageView.delete` (lines 190–206)

After the existing cascade-delete of all live versions and aliases, add a
hard-delete of the Package row itself so it stops appearing in `package_list`:

```python
with transaction.atomic():
    for version in PackageVersion.objects.filter(
        package=package, deleted_at__isnull=True,
    ):
        _tombstone_version(version, reason)
    PackageAlias.objects.filter(package=package).delete()
    package.delete()   # ← ADD THIS LINE
```

The `PackageVersion` rows are CASCADE-deleted when the Package row is
deleted. Because `_tombstone_version` already cleared all ZIP files, no
on-disk files are orphaned. The Package is now fully gone from all list
endpoints.

> **v12 note:** The suggested extension is to soft-delete the container
> (`Package.deleted_at`) so version history is preserved in the DB and the
> admin. Adopt this in v12 if audit retention becomes a requirement.

---

## Step 11 — Update `PackageVersionSerializer` (serializers.py)

File: `file_manager/serializers.py`

Replace `tombstoned`/`tombstone_reason`/`forked_from` with `deleted`/`delete_reason`/`base`:

```python
class PackageVersionSerializer(serializers.ModelSerializer):
    package = serializers.CharField(source='package.name', read_only=True)
    author = serializers.CharField(source='author.name', read_only=True)
    date = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()
    deleted = serializers.SerializerMethodField()
    base = serializers.SerializerMethodField()

    class Meta:
        model = PackageVersion
        fields = [
            'package', 'version', 'author', 'date',
            'summary', 'description', 'content_hash',
            'download_url', 'deleted', 'delete_reason', 'base',
        ]

    def get_date(self, obj):
        return obj.render_uploaded_at()

    def get_download_url(self, obj):
        if obj.is_deleted:
            return None
        return f'/api/packages/{obj.package.name}/versions/{obj.version}/download'

    def get_deleted(self, obj):
        return obj.is_deleted

    def get_base(self, obj):
        if obj.base_name:
            return {'name': obj.base_name, 'version': obj.base_version}
        return None
```

---

## Step 12 — Filter deleted versions from `latestVersion` (serializers.py)

File: `file_manager/serializers.py`, `PackageListItemSerializer.get_latest_version`

```python
def get_latest_version(self, obj):
    latest = (
        obj.versions
        .filter(deleted_at__isnull=True)   # ← exclude deleted
        .order_by('-version')
        .first()
    )
    if latest is None:
        return None
    return PackageVersionSerializer(latest).data
```

---

## Step 13 — Update `PackageDetailSerializer` select_related (serializers.py)

File: `file_manager/serializers.py`, `PackageDetailSerializer.get_versions`

Remove the `forked_from__package` join (no longer serialized; `base` comes
from plain fields):

```python
def get_versions(self, obj):
    qs = obj.versions.order_by('-version').select_related('author')
    return PackageVersionSerializer(qs, many=True).data
```

---

## Step 14 — Update `history.py`

File: `file_manager/history.py`

### `_render_version_block` (lines 51–78)

- Line 52: `version.is_tombstoned` → `version.is_deleted`
- Line 52: heading suffix `'(tombstoned)'` → `'(deleted)'`
- Line 58: `version.is_tombstoned` → `version.is_deleted`
- Line 68: `version.is_tombstoned` → `version.is_deleted`
- Line 69: `version.tombstone_reason` → `version.delete_reason`
- Line 70: label `'**Tombstoned:**'` → `'**Deleted:**'`

### `_versions_block` (lines 81–91)

The fork label still reads from `forked_from` (retained until v12):
```python
if v.forked_from_id:
    ancestor = v.forked_from
    label = f'{ancestor.package.name} v{ancestor.version}'
```
No change needed here — `forked_from` FK remains.

### Module docstring (top of file, line 9)

Update the example block:
```
### Version <n>[ (deleted)]
- **Deleted:** <reason>
```

---

## Step 15 — Update `package_parsing.py` version-block regex

File: `file_manager/package_parsing.py`, line 98

Update `_VERSION_BLOCK_RE` to match the new `(deleted)` suffix (used by
`parse_top_history_header` / fork detection):

```python
_VERSION_BLOCK_RE = re.compile(
    r'^###\s+Version\s+(?P<n>\d+)(?:\s+\(deleted\))?\s*$', re.MULTILINE
)
```

---

## Step 16 — Update tests

Files: `file_manager/tests_v4.py`, `file_manager/tests_v6.py`,
`file_manager/tests_pages.py`, `file_manager/tests_org_isolation.py`

Search for every occurrence of:
- `tombstoned` → `deleted` (field names, JSON keys, assertion strings)
- `tombstone_reason` → `delete_reason`
- `tombstoned_at` → `deleted_at`
- `forked_from` in API response assertions → `base`
- `is_tombstoned` → `is_deleted`
- `latest` alias auto-created assertions → remove or change to verify `latest` is NOT auto-created

Add new test cases:
- Version delete clears `description`, retains `summary`, `version`, `content_hash`.
- `DELETE /api/packages/{name}/` removes the package from `GET /api/packages/`.
- Alias pointing at a deleted version is NOT detached (static alias contract).
- `latestVersion` in `GET /api/packages/` is `null` when all versions deleted.
- Publish with `base_name`/`base_version` form fields returns `base` in the response.
- `content_hash` is bare lowercase hex (no `sha256:` prefix).

---

## Step 17 — Deploy checklist

1. Apply migrations: `python manage.py migrate`
2. Verify no `sha256:` prefixes remain: `SELECT content_hash FROM file_manager_packageversion WHERE content_hash LIKE 'sha256:%'`
3. Deploy server.
4. Release client update that drops `tombstoned`/`forked_from` shims and flips to `deleted`/`base`.
5. The `latest` alias rows already in the DB are harmless — `PackageLatestDownloadView` still reads them; they are just no longer auto-managed.
