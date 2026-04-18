# Rapporter — Scout Incident Reporting System

A web-based incident reporting and management system for scout camps. Camp leaders and staff can report and track incidents during events; administrators manage users, camps, and generate reports.

The interface is in Swedish.

---

## Features

- **Incident reports** — Log accidents, illness, conflicts, material shortages, safety issues, and other events with severity levels and follow-up tracking
- **Multi-camp support** — Each user belongs to a camp; admins have visibility across all camps
- **Custom fields** — Each camp can define its own extra fields (text, dropdown, checkbox, date) that appear on incident forms
- **QR code login** — Generate per-user QR codes that pre-fill the username on the login page, useful for quick access at camp
- **Reports & export** — Filter incidents by camp, type, severity, status, and date range; export to semicolon-delimited CSV (Excel-compatible with Swedish characters)
- **Role-based access** — `admin` role for management, `user` role for reporters; users only see their own reports

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, Flask 3 |
| Database | PostgreSQL 17 |
| ORM / Migrations | SQLAlchemy 2, Flask-Migrate / Alembic |
| Auth | Flask-Login, bcrypt, Flask-WTF (CSRF) |
| Frontend | Jinja2 templates, Bootstrap 5.3 |
| Production server | Gunicorn |
| Reverse proxy | Caddy 2 (HTTPS) |
| Container | Docker, Docker Compose |

---

## Deployment (Production)

### 1. Copy and configure environment

```sh
cp .env.example .env
```

Edit `.env` and set at minimum:

| Variable | Description |
|---|---|
| `SECRET_KEY` | Random hex string — `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | PostgreSQL connection string |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | Database credentials |
| `CADDY_DOMAIN` | Your domain name (e.g. `rapporter.example.com`) |
| `BASE_URL` | Full URL used in QR code links (e.g. `https://rapporter.example.com`) |

### 2. Start all services

```sh
docker compose --profile prod up -d
```

This starts PostgreSQL, the Flask app (via Gunicorn), and Caddy (reverse proxy with automatic HTTPS).

On first start, the container runs database migrations and seeds a default admin account automatically.

### 3. Default admin credentials

| Username | Password |
|---|---|
| `sysadm` | `ninja01` |

**Change the password immediately after first login.**

---

## Project Structure

```
app/
├── __init__.py        # App factory, config, CLI commands
├── models.py          # Database models (Camp, User, Incident)
├── auth/              # Login / logout
├── incidents/         # Incident CRUD
├── admin/             # Admin panel (users, camps, fields, reports)
└── templates/         # Jinja2 HTML templates

migrations/            # Alembic migration versions
Dockerfile
docker-compose.yml
docker-compose.override.yml   # Dev overrides (auto-applied locally)
Caddyfile
.env.example
```

---

## Data Model

- **Camp** — A scout camp or event. Has a name, location, dates, active flag, and optional custom field definitions (JSON).
- **User** — A system account. Belongs to one camp (optional for admins). Role is `admin` or `user`.
- **Incident** — A reported event. Belongs to a camp and a reporter. Includes type, severity, status, description, actions taken, follow-up notes, and any camp-specific extra fields.

---

## Developer Setup

See [DEVELOPER.md](DEVELOPER.md).
