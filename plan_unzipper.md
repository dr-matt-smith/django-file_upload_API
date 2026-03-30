# Plan: ZIP Auto-Unzipper Feature

## Overview

When a ZIP file is uploaded, automatically extract its contents into a `/public/{name}/` directory served as static files. Replace existing directories on re-upload. Generate an `index.html` if the ZIP doesn't contain one.

---

## Current State

- Uploads are saved to `MEDIA_ROOT/uploads/YYYY/MM/DD/`
- Upload entry point: `FileUploadView.post()` in `file_manager/views.py`
- `MEDIA_ROOT` = `BASE_DIR/media/`
- No existing public/static serving beyond `/media/`

---

## Target Behavior

| Input | Result |
|---|---|
| Upload `matt.zip` | Extract to `media/public/matt/`, serve at `/public/matt/` |
| Upload `monday12.zip` | Extract to `media/public/monday12/`, serve at `/public/monday12/` |
| Re-upload `matt.zip` | Delete existing `media/public/matt/`, recreate |
| ZIP with no `index.html` | Auto-generate `media/public/matt/index.html` listing all files as links |

---

## Implementation Steps

### Step 1 — Add `PUBLIC_ROOT` and serve `/public/` URL

**File:** `file_upload_api/settings.py`

Add:
```python
PUBLIC_ROOT = os.path.join(BASE_DIR, 'media', 'public')
PUBLIC_URL = '/public/'
```

**File:** `file_upload_api/urls.py`

Add a static/media serve rule for the public directory (similar to how `MEDIA_ROOT` is served):
```python
from django.views.static import serve
from django.conf import settings

urlpatterns += [
    path('public/<path:path>', serve, {'document_root': settings.PUBLIC_ROOT}),
]
```

This makes `media/public/matt/index.html` accessible at `/public/matt/index.html`.

---

### Step 2 — Create ZIP extraction utility

**New file:** `file_manager/zip_utils.py`

```python
import zipfile
import os
import shutil
from django.conf import settings

def extract_zip_to_public(zip_file_path: str, zip_filename: str) -> str:
    """
    Extracts a ZIP file into PUBLIC_ROOT/{name}/.
    Deletes existing directory if present.
    Generates index.html if not included in the ZIP.
    Returns the public URL path, e.g. '/public/matt/'.
    """
    name = os.path.splitext(zip_filename)[0]          # "matt.zip" → "matt"
    dest_dir = os.path.join(settings.PUBLIC_ROOT, name)

    # (2) Delete existing folder if present
    if os.path.exists(dest_dir):
        shutil.rmtree(dest_dir)

    os.makedirs(dest_dir, exist_ok=True)

    # (1) Extract ZIP contents
    with zipfile.ZipFile(zip_file_path, 'r') as zf:
        # Security: strip any absolute paths or ".." traversal from member names
        for member in zf.infolist():
            member_path = os.path.normpath(member.filename)
            if member_path.startswith('..') or os.path.isabs(member_path):
                continue  # skip unsafe paths
            zf.extract(member, dest_dir)

    # Generate index.html if not present
    index_path = os.path.join(dest_dir, 'index.html')
    if not os.path.exists(index_path):
        _generate_index(dest_dir, name)

    return f'/public/{name}/'


def _generate_index(dest_dir: str, folder_name: str):
    """Creates a simple index.html listing all files in dest_dir as links."""
    files = []
    for root, dirs, filenames in os.walk(dest_dir):
        # Sort for consistent ordering; skip hidden files
        dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
        for filename in sorted(filenames):
            if filename == 'index.html':
                continue
            rel_path = os.path.relpath(os.path.join(root, filename), dest_dir)
            files.append(rel_path)

    links = '\n'.join(
        f'    <li><a href="{f}">{f}</a></li>' for f in files
    )
    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{folder_name}</title></head>
<body>
  <h1>{folder_name}</h1>
  <ul>
{links}
  </ul>
</body>
</html>
"""
    with open(os.path.join(dest_dir, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(html)
```

Key security note: strip path traversal attempts (`../`) from ZIP member names before extraction.

---

### Step 3 — Hook extraction into the upload view

**File:** `file_manager/views.py`

In `FileUploadView.post()`, after `serializer.save()` succeeds, detect ZIP and trigger extraction:

```python
import os
from .zip_utils import extract_zip_to_public

class FileUploadView(APIView):
    def post(self, request):
        serializer = UploadedFileSerializer(data=request.data)
        if serializer.is_valid():
            instance = serializer.save()

            # ZIP auto-extraction
            original_name = request.FILES['file'].name
            if original_name.lower().endswith('.zip'):
                public_url = extract_zip_to_public(
                    instance.file.path,
                    original_name
                )
                data = serializer.data
                data['public_url'] = public_url
                return Response(data, status=status.HTTP_201_CREATED)

            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
```

The response includes a `public_url` field for ZIP uploads so callers know where to find the extracted files.

---

### Step 4 — Create `media/public/` directory

Ensure the directory exists (can be done at startup or as a one-time setup):

```bash
mkdir -p media/public
```

Or add to settings.py startup:
```python
os.makedirs(PUBLIC_ROOT, exist_ok=True)
```

---

### Step 5 — Tests

**File:** `file_manager/tests.py`

Add test cases:

1. **Upload a ZIP** → verify `media/public/{name}/` directory is created, `public_url` in response
2. **ZIP without index.html** → verify `index.html` is auto-generated with links
3. **ZIP with index.html** → verify existing `index.html` is preserved
4. **Re-upload same ZIP** → verify old directory is replaced, not merged
5. **Path traversal in ZIP** → verify unsafe members are skipped (security test)
6. **Non-ZIP upload** → verify no extraction, normal response

---

## Files Changed / Created

| File | Action |
|---|---|
| `file_upload_api/settings.py` | Add `PUBLIC_ROOT`, `PUBLIC_URL`; ensure directory created |
| `file_upload_api/urls.py` | Add `serve` route for `/public/<path>` |
| `file_manager/zip_utils.py` | **New** — extraction + index generation logic |
| `file_manager/views.py` | Trigger extraction after ZIP upload |
| `file_manager/tests.py` | Add ZIP extraction test cases |

---

## Decisions / Notes

- **No new DB model needed** — extracted files are filesystem-only; the original ZIP is still tracked in `UploadedFile`
- **Replacement is always full** — `shutil.rmtree` + recreate, no incremental merge (per spec)
- **`index.html` is only auto-generated** if the ZIP doesn't include one — existing ones are preserved
- **Security:** ZIP path traversal is sanitized before extraction (critical for any ZIP handling)
- **Production note:** The `serve` view is fine for development; in production, configure Nginx to serve `PUBLIC_ROOT` directly for better performance
