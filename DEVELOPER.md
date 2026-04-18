# Developer Guide

Everything needed to run the project locally and extend it.

---

## Quick start

Requires Docker and Docker Compose — no local Python install needed.

```sh
git clone <repo>
cd rapporter
cp .env.example .env
echo "SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')" >> .env
docker compose up
```

The override file (`docker-compose.override.yml`) is applied automatically
and switches the web container to Flask's dev server with reload. The app
is available at **http://localhost:8000**.

On first start, `flask db upgrade` and `flask seed` run as part of the dev
command, creating the schema and the default admin:

| Username | Password |
|---|---|
| `sysadm` | `bananipyjamas` |

Stop with `docker compose down` (add `-v` to wipe the database volume).

---

## Dev vs production

| | Development | Production |
|---|---|---|
| Trigger | `docker compose up` | `docker compose -f docker-compose.yml --profile prod up -d` |
| App server | `flask run --reload` | Gunicorn |
| Caddy | Not started | Started (HTTP + HTTPS) |
| Port exposed | 8000 | 80 / 443 via Caddy |
| Source mount | Bind-mounted | Baked into image |
| Migrations / seed | Run automatically on container start | Run by deploy workflow |

The explicit `-f docker-compose.yml` in the prod command is important:
without it, Docker Compose auto-loads `docker-compose.override.yml`
and its `flask run --reload` command wins over the Dockerfile's
Gunicorn `CMD`. Passing `-f` disables the automatic override merge.

Production is also deployed from master via a GitHub Actions workflow
(`.github/workflows/deploy.yml`) that runs on a self-hosted runner
labelled `lluw`.

---

## Project layout

```
app/
├── __init__.py          # App factory, extensions, CLI commands
├── models.py            # SQLAlchemy models: User, Category, Ticket, TicketHistory
├── i18n.py              # Two-language dict-based translations (sv/en)
├── wordlist.py          # Swedish words used as public-share tokens
├── auth/routes.py       # /login, /logout
├── tickets/routes.py    # /tickets/* — list, create, view, edit, advance,
│                        #   public share, QR, TV dashboard
├── admin/routes.py      # /admin/* — dashboard, users, categories
├── static/              # Static assets (served directly by the web container)
└── templates/
    ├── base.html
    ├── auth/, tickets/, admin/

migrations/versions/     # Alembic migrations (0001 initial, 0002 public_token)
Dockerfile
docker-compose.yml           # Base stack (db, web, caddy under prod profile)
docker-compose.override.yml  # Dev overrides (auto-applied)
Caddyfile
.env.example
.github/workflows/deploy.yml # Self-hosted deploy workflow
```

### Blueprints

| Blueprint | URL prefix | Access |
|---|---|---|
| `auth` | `/` | Everyone |
| `tickets` | `/tickets` | Logged-in users; `/tickets/p/<id>/<token>` is public |
| `admin` | `/admin` | Dashboard open to admin + editor; user/category mgmt admin-only |

The root route `/` redirects to `/tickets/`.

---

## Models

### User

```python
id, username, password_hash, role ("admin"|"editor"|"viewer"), created_at
```

`user.set_password(plain)` / `user.check_password(plain)` use bcrypt.
`user.is_admin` and `user.can_edit` (admin or editor) are the common
role checks.

### Category

Normalised (lowercased, trimmed) unique `name`, plus a `display_name`
preserving the original casing. `usage_count` is maintained by the ticket
routes so unused categories can be safely removed.

### Ticket

```python
id, title, description, feedback, priority (1..3), status,
category_id, reporter_id, is_public, public_token,
created_at, db_created_at, updated_at, closed_at
```

**Statuses** (stored as ASCII slugs, labels resolved via i18n):
`ny`, `paborjad`, `avslutad`, `pausad`, `avvisad`

**Priorities:** `1` = P1 critical, `2` = P2 important, `3` = P3 low

`created_at` is user-editable (for backdating); `db_created_at` records
the immutable row-insertion moment.

### TicketHistory

One row per changed field. `field='__created__'` marks the creation
event. The edit/advance routes call `_log_change` per field to build the
audit trail.

---

## Localisation

`app/i18n.py` holds a dict keyed by English source strings with Swedish
overrides. Templates call `{{ _('Some text') }}`; untranslated keys fall
back to English. Locale detection order:

1. `?lang=sv|en` query argument
2. `scout_locale` cookie (set by the language dropdown)
3. Swedish as default (browser `Accept-Language` is intentionally ignored)

No pybabel compile step is needed.

---

## Public share links

Making a ticket public generates a short Swedish word as `public_token`.
The public URL is `/tickets/p/<id>/<token>`, rate-limited to 30 requests
per minute. Tokens are cleared when the ticket is made private again, so
old links stop working. Comparison uses `hmac.compare_digest` on
UTF-8-encoded bytes (the wordlist contains å/ä/ö).

---

## Database

### Migrations

Migrations live in `migrations/versions/`. Create a new one after model
changes:

```sh
docker compose exec web flask db migrate -m "describe the change"
docker compose exec web flask db upgrade
```

The dev container runs `flask db upgrade` on startup; the deploy
workflow runs it explicitly before swapping in new containers.

### Direct DB access

```sh
docker compose exec db psql -U rapporter -d rapporter
```

### Seed

```sh
docker compose exec web flask seed
```

Creates `sysadm` if it doesn't exist. Idempotent.

---

## Adding a new feature

1. **Route** — add to the relevant blueprint (`tickets`, `admin`, `auth`)
   or create a new one in `app/`.
2. **Template** — add to `app/templates/<blueprint>/`.
3. **Translations** — add Swedish entries to `TRANSLATIONS["sv"]` in
   `app/i18n.py`. English source strings need no entry.
4. **Access control** — use `@login_required`, `@editor_required`
   (tickets) or `@admin_required` (admin).
5. **History** — if you touch `Ticket` fields, log changes with
   `_log_change(ticket, field, old, new, current_user)`.

---

## Security notes

- Passwords hashed with bcrypt; never compare plain text.
- CSRF tokens on every form (Flask-WTF). Hidden `csrf_token` input for
  plain-POST buttons like delete and advance.
- Login rate-limited to 10/min per IP; public-share endpoint 30/min.
- Redirect targets on `set-language` and login are validated to be
  relative.
- The container runs as non-root `appuser`.

---

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | Yes | — | Flask session secret |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | No | `rapporter` | DB credentials |
| `DATABASE_URL` | No | derived from POSTGRES_* | Overrides the default URL |
| `REDIS_URL` | No | `memory://` | Rate-limit counter store; falls back to in-memory if unset |
| `FLASK_ENV` | No | `production` | `development` enables debug mode |
| `BASE_URL` | Prod only | `http://localhost` | Base URL baked into QR codes and share links |
| `CADDY_DOMAIN` | Prod only | `localhost` | Host Caddy serves |
| `CADDY_AUTO_HTTPS` | Prod only | `on` | Set `off` for offline / LAN deployments |
| `ALLOW_INSECURE_COOKIES` | No | `0` | Set `1` when serving plain HTTP so the session cookie is sent |

---

## Common tasks

```sh
# Foreground logs
docker compose up

# Rebuild after requirements.txt / Dockerfile changes
docker compose up --build

# Shell into the web container
docker compose exec web bash

# Any Flask CLI command
docker compose exec web flask <command>

# Logs
docker compose logs -f web
docker compose logs -f db
```
