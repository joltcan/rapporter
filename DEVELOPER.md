# Developer Guide

This document covers everything you need to get the project running locally and understand how to extend it.

---

## Quick Start

### Prerequisites

- Docker and Docker Compose
- No local Python install required (everything runs in containers)

### 1. Clone and configure

```sh
git clone <repo>
cd rapporter
cp .env.example .env
```

The defaults in `.env.example` work for local development. You only need to set `SECRET_KEY`:

```sh
echo "SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')" >> .env
```

### 2. Start the dev stack

```sh
docker compose up
```

This starts **only PostgreSQL and the Flask app** (Caddy is production-only). The `docker-compose.override.yml` is applied automatically and switches the app to Flask dev server with hot-reload.

The app is available at **http://localhost:5000**.

On first start, migrations and seed data run automatically. Default admin login:

| Username | Password |
|---|---|
| `sysadm` | `ninja01` |

### 3. Stop

```sh
docker compose down          # keep database volume
docker compose down -v       # also delete database
```

---

## How Dev vs Production Differs

| | Development | Production |
|---|---|---|
| Server | `flask run --reload` | Gunicorn (4 workers) |
| Hot reload | Yes | No |
| Caddy | Not started | Started via `--profile prod` |
| Port | 5000 (direct) | 80 / 443 (via Caddy) |
| Debug | On | Off |

The override file `docker-compose.override.yml` is picked up automatically by Docker Compose in dev. It mounts the entire project directory into the container so code changes take effect immediately without rebuilding.

To start production locally (all three services):

```sh
docker compose --profile prod up
```

---

## Database

### Migrations

Migrations live in `migrations/versions/`. The container runs `flask db upgrade` on startup automatically.

To create a new migration after changing models:

```sh
docker compose exec web flask db migrate -m "describe the change"
docker compose exec web flask db upgrade
```

### Seed data

```sh
docker compose exec web flask seed
```

Creates the default `sysadm` admin if it doesn't exist. Safe to run repeatedly (idempotent).

### Direct database access

```sh
docker compose exec db psql -U rapporter -d rapporter
```

---

## Project Layout

```
app/
├── __init__.py          # App factory: creates Flask app, registers blueprints, defines CLI commands
├── models.py            # All SQLAlchemy models: Camp, User, Incident
├── auth/
│   └── routes.py        # GET/POST /login, GET /logout
├── incidents/
│   └── routes.py        # CRUD for incidents — /incidents/
└── admin/
    └── routes.py        # Admin panel — /admin/ (users, camps, custom fields, reports)
```

### Blueprints

| Blueprint | Prefix | Who can access |
|---|---|---|
| `auth` | `/` | Everyone |
| `incidents` | `/incidents` | Logged-in users |
| `admin` | `/admin` | Admins only (`@admin_required`) |

The root route `/` redirects based on role: admins → `/admin`, users → `/incidents`, unauthenticated → `/login`.

---

## Models

### Camp

Represents a scout camp or event.

```python
id, name, location, start_date, end_date, is_active, custom_fields (JSON), created_at
```

`custom_fields` is a list of field definitions, for example:

```json
[
  {"name": "patrol_name", "label": "Patrullnamn", "type": "text", "required": false},
  {"name": "severity_code", "label": "Allvarlighetskod", "type": "dropdown", "options": ["A", "B", "C"]}
]
```

### User

```python
id, username, password_hash, role ("admin"|"user"), camp_id (FK, optional), created_at
```

Use `user.set_password(plain)` and `user.check_password(plain)`. The `is_admin` property checks `role == "admin"`.

### Incident

```python
id, camp_id (FK), reporter_id (FK), occurred_at, involved_person,
incident_type, severity, status, description, action_taken,
followup_notes, needs_followup, extra_data (JSON), created_at, updated_at
```

`extra_data` stores values for a camp's custom fields, keyed by field name.

**Incident types (Swedish):** `olycka`, `sjukdom`, `konflikt`, `materialbrist`, `säkerhet`, `övrigt`

**Severity:** `låg`, `medium`, `hög`

**Status:** `öppen`, `pågående`, `stängd`

---

## Adding a New Feature

### New page / route

1. Decide which blueprint it belongs to (`auth`, `incidents`, `admin`) or create a new one.
2. Add the route function in `routes.py`.
3. Add a template in `app/templates/<blueprint>/`.
4. If the route needs admin-only access, use the `@admin_required` decorator (defined in `admin/routes.py`).

### New model field

1. Add the column to the model in `models.py`.
2. Generate a migration: `docker compose exec web flask db migrate -m "add field X to Y"`
3. Apply it: `docker compose exec web flask db upgrade`

### New camp custom field type

Custom field types are handled in the incident form template (`app/templates/incidents/form.html`). Add a new `{% elif field.type == "yourtype" %}` branch to render the input, and handle it in the route when saving `extra_data`.

---

## Security Notes

- Passwords are hashed with **bcrypt** — never store or compare plain text.
- All forms use **CSRF tokens** via Flask-WTF. Don't disable `WTF_CSRF_ENABLED`.
- Login is **rate-limited** to 10 attempts per minute per IP (Flask-Limiter).
- Redirect targets are validated — only relative paths are accepted to prevent open redirect.
- Users can only view/edit their own incidents unless they are admins.
- The app runs as a non-root `appuser` inside the container.

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | Yes | — | Flask session secret |
| `DATABASE_URL` | Yes | `postgresql://rapporter:rapporter@db:5432/rapporter` | DB connection string |
| `POSTGRES_DB` | No | `rapporter` | DB name |
| `POSTGRES_USER` | No | `rapporter` | DB user |
| `POSTGRES_PASSWORD` | No | `rapporter` | DB password |
| `FLASK_ENV` | No | `production` | `development` enables debug mode |
| `CADDY_DOMAIN` | Prod only | `localhost` | Domain for Caddy TLS |
| `BASE_URL` | Prod only | `https://localhost` | Base URL used in QR code links |

---

## Common Tasks

```sh
# Run with logs visible
docker compose up

# Rebuild after changing requirements.txt or Dockerfile
docker compose up --build

# Open a shell in the web container
docker compose exec web bash

# Run Flask CLI commands
docker compose exec web flask <command>

# Check logs
docker compose logs web
docker compose logs db
```
