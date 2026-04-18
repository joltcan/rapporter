# Claude Status – Scoutläger ärendesystem (ticket system)

Klistra in hela detta dokument i Claude på en ny dator för att fortsätta arbetet.

---

## Projektöversikt

Webbaserat ärendesystem för scoutläger. En förenklad intern helpdesk: logga
incidenter/önskemål som "tickets" med prioritet, kategori, status och ägare.
Lägerdeltagare kan skanna en QR-kod för att se status på publika tickets utan
inloggning. TV-vy för övervakning av kö i realtid.

**Plats:** `/Users/jolt/Seafile/FRO/scouter/rapporter/` (Seafile-synkad)

## Stack
- Python 3.12 / Flask 3 / SQLAlchemy / Alembic / Flask-Login / Flask-WTF / Flask-Limiter
- PostgreSQL 17 (docker), Gunicorn, Caddy reverse proxy
- Bootstrap 5, Jinja2, mobilvänligt, svenska + engelska (browser-detect)
- Docker Compose: 3 services (db, web, caddy), alla non-root (ingen bitnami)

## Design

### Roller
- **Admin** – full åtkomst, kan hantera användare/kategorier och radera tickets
- **Editor** – kan skapa och redigera tickets
- **Viewer** – kan endast läsa

### Ticket-statusar
`ny` → `paborjad` → `avslutad` (terminal), plus `pausad` och `avvisad` (terminal).
Vid transition till terminal status fylls `closed_at` i automatiskt om tom.

### Prioriteter
- P1 Akut (röd)
- P2 Viktig (orange)
- P3 Låg (grön)

### Publika tickets
Om `is_public=true` kan vem som helst (utan login) se ticket via `/tickets/p/<id>`.
Den publika vyn visar ENDAST: id, status, kategori, prioritet, skapad, stängd.
Ingen beskrivning, feedback, titel eller historik läcker.

### Kategorier
Skapas on-the-fly när man skriver i ticket-formuläret. Normaliseras
(lowercase, trimmad, kollapsad whitespace) som nyckel, men visningsnamnet
behåller första-bokstav-stor. `usage_count` hindrar borttagning om den används.

## Vad som är klart

### Infrastruktur
- [x] `docker-compose.yml` – db/web/caddy, healthcheck, internal network
- [x] `Dockerfile` – Python 3.12-slim, non-root `appuser`, kör `flask db upgrade && flask seed` vid start
- [x] `Caddyfile` – `auto_https` via env (`off` för offline camp, `on` för Let's Encrypt)
- [x] `.env` / `.env.example` – `CADDY_DOMAIN`, `CADDY_AUTO_HTTPS`, `ALLOW_INSECURE_COOKIES`, `BASE_URL`

### Modeller (`app/models.py`)
- [x] `User` – id, username, password_hash (bcrypt), role (admin/editor/viewer)
- [x] `Category` – id, name (display), name_key (normaliserad unik), usage_count
- [x] `Ticket` – id, created_at, priority (1-3), category_id, title, description,
       feedback, is_public, status, closed_at, creator_id
- [x] `TicketHistory` – id, ticket_id, field, old_value, new_value, changed_at, user_id

### i18n (`app/i18n.py`)
- [x] Lättvikts dict-baserad översättning (svenska + engelska, inga `.po`-filer)
- [x] `detect_locale()`: `?lang=` → cookie → Accept-Language → sv default
- [x] `_('key', **kwargs)` som Jinja-global
- [x] `/set-language/<lang>` sätter `scout_locale`-cookie
- [x] `status_label`, `priority_label`, `role_label` som Jinja-globals

### Auth (`app/auth/`)
- [x] Login med bcrypt, rate limit 10/min per IP
- [x] QR-kod fyller i `?u=username` (ingen auto-login)
- [x] Cookie-secure styrs av `ALLOW_INSECURE_COOKIES` (offline HTTP-läge)

### Admin-panel (`app/admin/`)
- [x] Dashboard: status_counts, priority_counts, open_count, queue_length,
       p1_count, senaste/recent tickets, progress bars
- [x] Användarhantering: skapa/redigera/ta bort, välj roll, QR-kod
- [x] Kategorihantering: skapa, lista, ta bort (blockeras om usage_count > 0)
- [x] `@admin_required`-decorator

### Tickets (`app/tickets/`)
- [x] Lista med filter (status/prioritet/kategori/fritextsök)
- [x] Skapa/redigera formulär med:
  - Created datetime (förifyllt med nu)
  - Priority 1-3
  - Category (autocomplete via datalist, lowercase-nyckel)
  - Title (valfri), Description, Feedback
  - Public checkbox
  - Status (default "ny")
  - Closed_at (autofyllt vid terminal status)
- [x] Visa ticket med QR-kod (publika länken om `is_public`), delbar URL, historik (collapsible)
- [x] `/tickets/p/<id>` – publik vy utan beskrivning
- [x] `/tickets/<id>/qr.png` – genererad QR-bild
- [x] `/tv` – fullscreen dark-theme dashboard med 3 kolumner (ny/paborjad/avslutad),
       prioritetsordnad, auto-refresh 60s, minimal info, ingen läcka
- [x] `editor_required`-decorator; `admin_required` för delete
- [x] Full ändringshistorik via `_log_change()`

### Säkerhet
- [x] CSRF på alla formulär
- [x] Rollbaserad åtkomst
- [x] Seed: `flask seed` skapar `sysadm`/`ninja01` admin (idempotent)

## Filstruktur
```
rapporter/
├── docker-compose.yml
├── Caddyfile
├── Dockerfile
├── requirements.txt
├── wsgi.py
├── .env / .env.example / .gitignore
├── INSTRUCTIONS.md              ← ursprunglig spec (svenska)
├── CLAUDE_STATUS.md             ← denna fil
├── app/
│   ├── __init__.py              ← create_app(), flask seed CLI, _bool_env
│   ├── models.py                ← User, Category, Ticket, TicketHistory
│   ├── i18n.py                  ← översättningar + detect_locale
│   ├── auth/routes.py           ← /auth/login, /auth/logout
│   ├── admin/routes.py          ← /admin/* (dashboard, users, categories)
│   ├── tickets/routes.py        ← /tickets/*, /tickets/p/<id>, /tv
│   └── templates/
│       ├── base.html            ← scout-green-tema, språk-dropdown
│       ├── auth/login.html
│       ├── admin/{dashboard,users,user_form,categories,qr_code}.html
│       └── tickets/{list,form,view,public,tv}.html
└── migrations/
    └── versions/0001_initial_schema.py
```

## Starta lokalt
```bash
cd /Users/jolt/Seafile/FRO/scouter/rapporter
docker compose up -d
# Offline camp: http://<lan-ip>  (CADDY_DOMAIN=localhost, CADDY_AUTO_HTTPS=off)
# Public:       https://domain   (sätt CADDY_DOMAIN, CADDY_AUTO_HTTPS=on)
# Logga in:     sysadm / ninja01
```

## Drift-lägen (styrs via `.env`)
| Läge | `CADDY_DOMAIN` | `CADDY_AUTO_HTTPS` | `ALLOW_INSECURE_COOKIES` | `BASE_URL` |
|------|----------------|---------------------|--------------------------|------------|
| Offline camp | `localhost` | `off` | `1` | `http://<lan-ip>` |
| Public/prod  | `rapporter.example.se` | `on` | `0` | `https://rapporter.example.se` |

## Möjliga nästa steg
- [ ] Smoke-test i riktig docker compose-miljö
- [ ] E-postnotis vid P1
- [ ] CSV-export av tickets
- [ ] Fler TV-lägen (tex endast P1)
- [ ] PDF-export av enskild ticket
