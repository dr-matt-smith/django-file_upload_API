# Publishing to PythonAnywhere

## Prerequisites
- A free or paid PythonAnywhere account
- Your code pushed to a GitHub repository

---

## Step 1: Upload Your Code

Open a Bash console on PythonAnywhere and clone your repo:

```bash
git clone git@github.com:drmattsmith/django-file_upload_API.git
```

Set up SSH keys on GitHub beforehand if needed.

---

## Step 2: Create a Virtualenv and Install Dependencies

```bash
mkvirtualenv --python=/usr/bin/python3.13 file-upload-venv
pip install -r django-file_upload_API/requirements.txt
```

To reactivate in future sessions:

```bash
workon file-upload-venv
```

---

## Step 3: Configure Settings

Create a `.env` file in the project root on PythonAnywhere:

```bash
nano ~/django-file_upload_API/.env
```

Add the following:

```
DJANGO_SECRET_KEY=your-secret-key-here
DEBUG=False
```

`settings.py` automatically loads this file and reads `SECRET_KEY` from `DJANGO_SECRET_KEY`. Never commit `.env` to version control.

Then edit `file_upload_api/settings.py` to add your PythonAnywhere domain:

```python
ALLOWED_HOSTS = ['drmattsmith.pythonanywhere.com']
```

No database changes needed — SQLite is already configured and will work as-is.

---

## Step 4: Run Migrations

```bash
cd django-file_upload_API
python manage.py migrate
```

---

## Step 5: Create a Superuser

```bash
python manage.py createsuperuser
```

---

## Step 6: Collect Static Files

Add this to `settings.py` if not already present:

```python
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
```

Then run:

```bash
python manage.py collectstatic
```

---

## Step 7: Create a Web App

- Go to the **Web tab** → **Add a new web app**
- Choose **Manual configuration**
- Choose **Python 3.13**

---

## Step 8: Configure the Virtualenv

In the **Virtualenv** section of the Web tab, enter:

```
file-upload-venv
```

---

## Step 9: Edit the WSGI File

Click the WSGI file link in the Web tab and replace the Django section with:

```python
import os
import sys

path = '/home/drmattsmith/django-file_upload_API'
if path not in sys.path:
    sys.path.insert(0, path)

os.environ['DJANGO_SETTINGS_MODULE'] = 'file_upload_api.settings'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

Save the file.

---

## Step 10: Configure Static and Media Files

In the **Web tab → Static Files** section, add two mappings:

| URL      | Path                                                          |
|----------|---------------------------------------------------------------|
| /static/ | /home/drmattsmith/django-file_upload_API/staticfiles/        |
| /media/  | /home/drmattsmith/django-file_upload_API/media/              |

---

## Step 11: Reload and Test

Click **Reload** in the Web tab, then visit:

- `https://drmattsmith.pythonanywhere.com/api/files/` — API
- `https://drmattsmith.pythonanywhere.com/admin/` — Admin panel

---

## Ongoing Maintenance

After any code changes:

```bash
git pull
python manage.py migrate        # if models changed
python manage.py collectstatic  # if static files changed
```

Then click **Reload** in the Web tab.

---

## Notes

- SQLite is suitable for testing and small-scale use; migrate to MySQL for production
- Check the **error log** in the Web tab if anything goes wrong
- Media file uploads will be stored under `/home/drmattsmith/django-file_upload_API/media/`
