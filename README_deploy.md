# Security Changes for Public Repository

The following changes were made to make the project safe to publish as a public GitHub repository.

## What Changed

- **`.env`** — stores the secret key and `DEBUG=True` locally (already gitignored)
- **`.env.example`** — safe template committed to the repo so others know what's needed
- **`settings.py`** — reads `DJANGO_SECRET_KEY` and `DEBUG` from environment instead of hardcoding them
- **`test_api/config.py`** — stores test credentials locally (added to `.gitignore`)
- **`test_api/config.example.py`** — safe template committed to the repo
- **All test scripts** — now import from `config.py` instead of hardcoding credentials

## Setup for New Developers

1. Copy `.env.example` to `.env` and fill in your secret key:
   ```bash
   cp .env.example .env
   ```

2. Copy `test_api/config.example.py` to `test_api/config.py` and fill in your credentials:
   ```bash
   cp test_api/config.example.py test_api/config.py
   ```