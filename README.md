# Rapporter

Ett enkelt ärendesystem för scoutläger. Problem, önskemål och uppgifter
rapporteras som ärenden med prioritet, kategori och status. Finns även en
TV-vy för att visa öppna ärenden på storskärm samt publika delningslänkar
med lösenord så anmälaren kan följa statusen.

Gränssnittet är på svenska (med engelska som alternativ).

## Kom igång

Kräver Docker och Docker Compose.

```sh
cp .env.example .env
# sätt minst SECRET_KEY i .env
docker compose --profile prod up -d
```

Detta startar PostgreSQL, Flask-appen (Gunicorn) och Caddy med automatisk
HTTPS.

För utveckling räcker det med `docker compose up` (utan `--profile prod`) —
då körs appen i debug-läge på http://localhost:8000 och Caddy hoppas över.

## Inloggning första gången

| Användarnamn | Lösenord |
|---|---|
| `sysadm` | `ninja01` |

**Byt lösenord direkt efter första inloggningen.**

## Roller

- **Admin** — full åtkomst, hanterar användare och kategorier
- **Redaktör** — skapar och ändrar ärenden, ser översikt
- **Läsare** — endast läsåtkomst

## Utveckling

Se [DEVELOPER.md](DEVELOPER.md) för projektstruktur, migrationer och
utvecklingsflöde.
