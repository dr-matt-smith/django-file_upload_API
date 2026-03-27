# Security Changes for Public Repository

The following changes were made to make the project safe to publish as a public GitHub repository.

## What Changed

- **`.env`** — stores the secret key and `DEBUG=True` locally (already gitignored)
- **`.env.example`** — safe template committed to the repo so others know what's needed
- **`settings.py`** — reads `DJANGO_SECRET_KEY` and `DEBUG` from environment instead of hardcoding them
## Setup for New Developers

1. Copy `.env.example` to `.env` and fill in your secret key:
   ```bash
   cp .env.example .env
   ```