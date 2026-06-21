"""End-to-end upload pipeline for Workshop packages.

Takes a Django UploadedFile (a ZIP), validates `package.toml`, persists
the new `PackageVersion` (creating `Package` and/or `Author` rows as
needed, scoped to the caller's organisation), regenerates `HISTORY.md`
from the DB, and repackages the ZIP with the updated history.

Packages have nothing to do with publishing pages (decoupled in v8) —
uploads never publish anything. Pages are a standalone ZIP-upload feature
in `pages.py`.
"""
from __future__ import annotations

import hashlib
import io
import zipfile

from django.core.files.base import ContentFile
from django.db import transaction

from .history import render_history
from .models import Author, Package, PackageVersion
from .package_parsing import (
    PackageValidationError,
    ParsedPackage,
    parse_package_zip,
    parse_top_history_header,
)


class PackagePipelineError(Exception):
    """Raised on upload-pipeline failures with a user-facing message.

    Subclasses may set `http_status` and `extra` to communicate the HTTP
    status and additional response body fields back to the view layer.
    """

    http_status = 400
    extra: dict | None = None


class HeadMismatchError(PackagePipelineError):
    http_status = 409

    def __init__(self, current_head: int):
        super().__init__('head moved')
        self.extra = {'head': current_head}


def _read_uploaded_bytes(django_file) -> bytes:
    """Read the bytes from a Django UploadedFile (works in-memory or temp)."""
    pos = django_file.tell() if hasattr(django_file, 'tell') else None
    try:
        django_file.seek(0)
        data = django_file.read()
    finally:
        if pos is not None:
            try:
                django_file.seek(pos)
            except Exception:
                pass
    return data



def _repackage_zip(original_bytes: bytes, history_md: str) -> bytes:
    """Return a new ZIP that mirrors the original except HISTORY.md is
    injected/replaced. package.toml passes through verbatim (v10: no
    version stamping)."""
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


def _detect_fork(parsed: ParsedPackage, organisation) -> PackageVersion | None:
    """Return an ancestor `PackageVersion` if the upload is a valid fork.

    Only called for new package names. Returns None if no embedded
    history, or if the embedded header references a package/version that
    doesn't exist in the caller's organisation, or if it self-references.
    Fork lineage is scoped to the organisation — you cannot fork from
    another org's package.
    """
    if not parsed.history_md:
        return None
    header = parse_top_history_header(parsed.history_md)
    if header is None:
        return None
    ancestor_name, ancestor_version = header
    if ancestor_name == parsed.name:
        return None
    try:
        return (
            PackageVersion.objects
            .select_related('package')
            .get(
                package__organisation=organisation,
                package__name=ancestor_name,
                version=ancestor_version,
            )
        )
    except PackageVersion.DoesNotExist:
        return None



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
    author: str = '',
) -> PackageVersion:
    """Validate, persist, repackage, and (for `page`) publish an uploaded ZIP.

    `expected_name` — if set, the manifest's name must match it (URL-name
    vs manifest-name guard).
    `parent_version` — if set, must equal the package's current head;
    otherwise raises HeadMismatchError.
    `author` — form-supplied author name (takes precedence over manifest).

    Returns the newly created `PackageVersion`. Raises
    `PackageValidationError` for content failures and
    `PackagePipelineError` (or subclasses) for pipeline failures.
    """
    original_bytes = _read_uploaded_bytes(django_file)

    parsed = parse_package_zip(io.BytesIO(original_bytes))

    if expected_name is not None and parsed.name != expected_name:
        raise PackageValidationError(
            f"manifest name '{parsed.name}' does not match URL '{expected_name}'"
        )

    author_name = author or parsed.author or ''
    if not author_name:
        raise PackageValidationError(
            'author is required (supply via multipart `author` field or '
            '`[package].author` in package.toml)'
        )

    author_obj, _ = Author.objects.get_or_create(
        organisation=organisation, name=author_name,
    )

    with transaction.atomic():
        existing = (
            Package.objects
            .select_for_update()
            .filter(organisation=organisation, name=parsed.name)
            .first()
        )

        if existing is not None:
            # New version of an existing package.
            latest = (
                PackageVersion.objects
                .filter(package=existing)
                .order_by('-version')
                .first()
            )
            current_head = latest.version if latest else 0
            if parent_version is not None and parent_version != current_head:
                raise HeadMismatchError(current_head)

            next_version = current_head + 1
            forked_from = None
            package = existing
        else:
            # Brand-new package. Create row, then maybe attach fork pointer.
            if parent_version is not None and parent_version != 0:
                raise HeadMismatchError(0)
            package = Package.objects.create(
                organisation=organisation,
                name=parsed.name,
            )
            next_version = 1
            forked_from = _detect_fork(parsed, organisation)
            if forked_from is not None and not base_name:
                base_name = forked_from.package.name
                base_version = forked_from.version

        version = PackageVersion.objects.create(
            package=package,
            version=next_version,
            author=author_obj,
            summary=summary or '',
            description=description or '',
            forked_from=forked_from,
            base_name=base_name or '',
            base_version=base_version,
            zip_file=ContentFile(b'placeholder', name='placeholder.zip'),
        )

        history_md = render_history(package)
        repacked = _repackage_zip(original_bytes, history_md)
        version.content_hash = hashlib.sha256(repacked).hexdigest()

        # Overwrite the placeholder file with the repackaged ZIP. Delete the
        # placeholder explicitly so it's not orphaned in storage.
        version.zip_file.delete(save=False)
        version.zip_file.save(
            f'v{version.version}.zip',
            ContentFile(repacked),
            save=True,
        )

    return version
