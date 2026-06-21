Version 10 — Implementation Plan
==================================
Publish & pages ingestion contract: absolute URLs, manifest convergence,
author persistence, page manifest

Covers alignment §2, §3, §4, §5. All changes are in `file_manager/`.
Depends on v9 being deployed first (or in the same release), because the
content-hash format decision (bare hex) is shared.

> Suggested extensions deferred to v12: make the manifest entirely
> optional (400 when `path` form field is absent instead of requiring
> any manifest file); explicit 400 cap on `summary` length; author-source
> precedence rule (manifest author as fallback only, 400 when neither present).

---

## Step 1 — Add `CANONICAL_ORIGIN` setting (settings.py)

File: `file_upload_api/settings.py`

The absolute page URL must not be built from the inbound `Host` header
(which varies behind proxies). Add a configured canonical origin:

```python
CANONICAL_ORIGIN = os.environ.get('CANONICAL_ORIGIN', '')
```

Set this in the `.env` file / PythonAnywhere env vars to the public URL
of the deployment, e.g. `https://myorg.pythonanywhere.com`.

When `CANONICAL_ORIGIN` is empty (local dev without the env var) the URL
falls back to a host-relative path so existing local tests don't break.

---

## Step 2 — Make `page_url()` return an absolute URL (pages.py)

File: `file_manager/pages.py`, `page_url` function (line 45)

```python
from django.conf import settings

def page_url(org, path: str) -> str:
    base = getattr(settings, 'CANONICAL_ORIGIN', '').rstrip('/')
    return f'{base}/pages/{org.slug}/{path}/'
```

All consumers of `page_url` — `_page_body` in `views.py` (line 544) and
`PageSerializer.get_url` in `serializers.py` (line 104–105) — inherit the
change automatically with no further edits.

---

## Step 3 — Add `author` fields to `Page` and `PagePublication` (models.py)

File: `file_manager/models.py`

The multipart `author` form field is free text (not tied to a user FK),
so store it as a `CharField`:

```python
# Page model — add after `published_by`
author = models.CharField(max_length=255, blank=True)

# PagePublication model — add after `published_by`
author = models.CharField(max_length=255, blank=True)
```

These fields are blank so existing rows require no backfill — they remain
empty until the page is republished with the v10 server.

---

## Step 4 — Create and run the Django migration

Generate the migration for the new `author` fields:

```
python manage.py makemigrations file_manager \
    --name v10_page_author_field
```

The migration adds:
- `AddField('Page', 'author', CharField(max_length=255, blank=True, default=''))`
- `AddField('PagePublication', 'author', CharField(max_length=255, blank=True, default=''))`

Run: `python manage.py migrate`

---

## Step 5 — Accept `author` and `path` from the multipart form in `PagesView.post` (views.py)

File: `file_manager/views.py`, `PagesView.post` (lines 562–601)

### 5a — Read `path` from the form field

Read `path` from the form as the primary source. Fall back to parsing the
ZIP manifest if the form field is absent (backward compatibility during the
client rollout window).

```python
form_path = (request.data.get('path') or '').strip()
form_author = (request.data.get('author') or '').strip()
```

### 5b — Accept singular `page.toml` in `pages_parsing.py` (see Step 7)

### 5c — Validate path and proceed

Replace the current `parse_pages_zip` → `validate_publish_path` flow:

```python
if form_path:
    # Form field takes precedence; still validate the ZIP is well-formed.
    try:
        path = validate_publish_path(form_path)
    except PagesValidationError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    # Validate ZIP is readable without requiring a manifest.
    try:
        _validate_zip_only(upload)   # see Step 6
    except PagesValidationError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
else:
    # Legacy: read path from the ZIP manifest (pages.toml / page.toml).
    try:
        parsed = parse_pages_zip(upload)
        path = parsed.path
    except PagesValidationError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    upload.seek(0)
```

### 5d — Pass author to `publish()`

```python
page = publish(
    self.org, path, upload,
    principal_user=request.user,
    author=form_author,
)
```

---

## Step 6 — Add `_validate_zip_only` helper (pages_parsing.py)

File: `file_manager/pages_parsing.py`

When `path` arrives via the form field, the server no longer needs a
manifest but must still confirm the upload is a valid ZIP:

```python
def _validate_zip_only(zip_path_or_file) -> None:
    """Raise PagesValidationError if the file is not a readable ZIP."""
    try:
        with zipfile.ZipFile(zip_path_or_file, 'r'):
            pass
    except zipfile.BadZipFile as exc:
        raise PagesValidationError(
            'invalid pages bundle - file is not a valid ZIP'
        ) from exc
```

---

## Step 7 — Accept singular `page.toml` alongside `pages.toml` (pages_parsing.py)

File: `file_manager/pages_parsing.py`, `_read_toml_at_root` (lines 67–73)

Update the manifest-finding function to check `page.toml` (singular) first,
then fall back to `pages.toml`:

```python
def _read_toml_at_root(zf: zipfile.ZipFile) -> bytes | None:
    """Return bytes of a top-level `page.toml` or `pages.toml` (singular preferred)."""
    candidates = ('page.toml', 'pages.toml')
    for info in zf.infolist():
        name = info.filename.replace('\\', '/')
        if '/' not in name.rstrip('/') and name.lower() in candidates:
            with zf.open(info) as fh:
                return fh.read()
    return None
```

Update the error message in `parse_pages_zip` (line 89–91) to name both:

```python
raise PagesValidationError(
    'invalid pages bundle - missing top-level `page.toml` or `pages.toml`'
)
```

Also update `_publishable_members` in `pages.py` (line 85) so neither
manifest file is extracted as web content:

```python
_MANIFESTS = frozenset({'page.toml', 'pages.toml'})

# in _publishable_members:
if name.lower() in _MANIFESTS:
    continue
```

Replace the `_MANIFEST = 'pages.toml'` constant with `_MANIFESTS`.

---

## Step 8 — Persist `author` in `publish()` (pages.py)

File: `file_manager/pages.py`, `publish` function (line 109)

Add `author: str = ''` parameter and persist it:

```python
def publish(org, path: str, django_file, *, principal_user=None, author: str = ''):
    ...
    page, _ = Page.objects.update_or_create(
        organisation=org,
        path=path,
        defaults={
            'zip_file': django_file,
            'content_hash': digest,
            'published_by': _user_or_none(principal_user),
            'author': author,           # ← ADD
        },
    )
    PagePublication.objects.create(
        organisation=org,
        path=path,
        action='publish',
        content_hash=digest,
        published_by=_user_or_none(principal_user),
        author=author,                  # ← ADD
    )
```

---

## Step 9 — Expose `author` in `PageSerializer` (serializers.py)

File: `file_manager/serializers.py`, `PageSerializer`

Update `get_published_by` to prefer the stored `author` CharField, falling
back to the authenticated user and then `'service'`:

```python
class PageSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    published_at = serializers.SerializerMethodField()
    published_by = serializers.SerializerMethodField()

    class Meta:
        model = Page
        fields = ['path', 'url', 'published_at', 'published_by', 'content_hash']

    def get_url(self, obj):
        return page_url(obj.organisation, obj.path)   # now absolute (Step 2)

    def get_published_at(self, obj):
        return obj.published_at.strftime('%Y-%m-%dT%H:%M:%SZ')

    def get_published_by(self, obj):
        if obj.author:
            return obj.author
        if obj.published_by:
            return obj.published_by.get_username()
        return 'service'
```

Also update `_page_body` in `views.py` (line 541–547) to include the author:

```python
def _page_body(org, page):
    return {
        'path': page.path,
        'url': page_url(org, page.path),
        'published_at': page.published_at.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'content_hash': page.content_hash,
        'published_by': page.author or (
            page.published_by.get_username() if page.published_by else 'service'
        ),
    }
```

---

## Step 10 — Accept `author` from the multipart form for package publish (views.py + package_pipeline.py)

### views.py — PackageVersionsView.post

File: `file_manager/views.py`, `PackageVersionsView.post` (line 226+)

Read `author` from the form:

```python
author = (request.data.get('author') or '').strip()
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
    base_name=base_name,       # from v9 Step 6
    base_version=base_version, # from v9 Step 6
    author=author,             # ← ADD (v10)
)
```

### package_pipeline.py — process_upload

File: `file_manager/package_pipeline.py`

Add `author: str = ''` parameter:

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
    author: str = '',          # ← ADD (v10)
) -> PackageVersion:
```

Change the Author lookup to prefer the form-supplied name, falling back to
the manifest `author` field (which is now optional — see Step 11):

```python
author_name = author or parsed.author or ''
if not author_name:
    raise PackageValidationError(
        'author is required (supply via multipart `author` field or `[package].author` in package.toml)'
    )
author_obj, _ = Author.objects.get_or_create(
    organisation=organisation, name=author_name,
)
```

Replace the old `Author.objects.get_or_create(organisation=organisation, name=parsed.author)`.

---

## Step 11 — Make `[package].author` optional in `package_parsing.py`

File: `file_manager/package_parsing.py`, lines 77–81

Remove the hard 400 when `[package].author` is absent. Make `author`
optional in `ParsedPackage`:

```python
@dataclass(frozen=True)
class ParsedPackage:
    name: str
    author: str | None        # ← was `str`, now optional
    history_md: str | None
```

In `parse_package_zip`, replace the author-required block:

```python
# DELETE:
author = package_table.get('author')
if not author:
    raise PackageValidationError(
        "invalid package - missing `[package] 'author' property` in package.toml` file"
    )

# REPLACE WITH:
author = package_table.get('author') or None
```

Return:

```python
return ParsedPackage(
    name=str(name).strip(),
    author=str(author).strip() if author else None,
    history_md=history_md,
)
```

---

## Step 12 — Stop injecting `version = N` into the served ZIP (package_pipeline.py)

File: `file_manager/package_pipeline.py`

### 12a — Remove `_stamp_version_into_toml` usage

In `process_upload`, remove the two lines that call `_stamp_version_into_toml`:

```python
# DELETE:
_, original_toml = _read_original_toml(original_bytes)
stamped_toml = _stamp_version_into_toml(original_toml, next_version)
```

### 12b — Simplify `_repackage_zip`

The function currently injects both `HISTORY.md` and `package.toml`. In v10
it should only inject `HISTORY.md` — the original `package.toml` passes
through unchanged:

```python
def _repackage_zip(original_bytes: bytes, history_md: str) -> bytes:
    """Return a new ZIP that mirrors the original except HISTORY.md is
    injected/replaced. package.toml is preserved verbatim."""
    out_buf = io.BytesIO()
    history_written = False

    with zipfile.ZipFile(io.BytesIO(original_bytes), 'r') as src, \
            zipfile.ZipFile(out_buf, 'w', zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            normalised = info.filename.replace('\\', '/')
            parent, _, leaf = normalised.rpartition('/')
            if leaf.lower() == 'history.md':
                target = f'{parent}/HISTORY.md' if parent else 'HISTORY.md'
                dst.writestr(target, history_md)
                history_written = True
                continue
            with src.open(info) as fh:
                dst.writestr(info, fh.read())
        if not history_written:
            dst.writestr('HISTORY.md', history_md)

    return out_buf.getvalue()
```

Update the call site to drop the `stamped_toml` argument:

```python
repacked = _repackage_zip(original_bytes, history_md)
```

### 12c — Remove now-unused helpers

Delete `_stamp_version_into_toml` (lines 79–114) and `_read_original_toml`
(lines 189–199) — they are no longer called.

---

## Step 13 — Confirm `summary` length (no code change)

`PackageVersion.summary` is a `TextField` (unlimited in SQLite/PostgreSQL).
The client caps at 512 characters — the server already accepts any length.
No schema or validation change is required. Add a comment in `views.py`
near the `summary = request.data.get('summary', '')` line to document
the 512-char client convention if desired.

---

## Step 14 — Update tests

Files: `file_manager/tests_v4.py`, `file_manager/tests_v6.py`,
`file_manager/tests_pages.py`, `file_manager/tests_org_isolation.py`

Update or add tests for:
- Page `url` field in list/detail/publish responses is now absolute (starts
  with `CANONICAL_ORIGIN` or is still host-relative in test without the env var).
- Page publish with `author` multipart field returns `published_by = <that author>`.
- Page publish with `path` multipart field succeeds without a `pages.toml`.
- Page publish with `page.toml` (singular) in ZIP succeeds.
- Package publish with `author` multipart field (and NO `[package].author`
  in manifest) creates version with the correct author.
- Served ZIP for a package no longer contains a `version = N` line in
  `package.toml` (byte-identical to the source manifest).
- Package publish fails with a clear error when neither form `author` nor
  manifest `author` is present.

---

## Step 15 — Deploy checklist

1. Set `CANONICAL_ORIGIN` in `.env` / PythonAnywhere environment variables.
2. Apply migrations: `python manage.py migrate`
3. Deploy server.
4. Modern clients (already sending `author` and `path` as multipart fields)
   work unchanged and now receive absolute page URLs and correct `published_by`.
5. Clients that still embed `author` in the manifest continue working
   (fallback in `process_upload` Step 10).
6. Old installed packages are not rewritten; re-publishing produces a
   byte-identical-to-source `package.toml`.
