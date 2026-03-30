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
    name = os.path.splitext(zip_filename)[0]
    dest_dir = os.path.join(settings.PUBLIC_ROOT, name)

    # Delete existing folder if present
    if os.path.exists(dest_dir):
        shutil.rmtree(dest_dir)

    os.makedirs(dest_dir, exist_ok=True)

    # Extract ZIP contents, sanitizing member paths
    with zipfile.ZipFile(zip_file_path, 'r') as zf:
        for member in zf.infolist():
            member_path = os.path.normpath(member.filename)
            if member_path.startswith('..') or os.path.isabs(member_path):
                continue  # skip unsafe paths
            zf.extract(member, dest_dir)

    # Generate index.html if not present
    if not os.path.exists(os.path.join(dest_dir, 'index.html')):
        _generate_index(dest_dir, name)

    return f'/public/{name}/'


def _generate_index(dest_dir: str, folder_name: str):
    """Creates a simple index.html listing all files in dest_dir as links."""
    files = []
    for root, dirs, filenames in os.walk(dest_dir):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
        for filename in sorted(filenames):
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
