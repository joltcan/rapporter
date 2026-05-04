# Rapporter

Ett enkelt ärendesystem för läger och annat. Problem, önskemål och uppgifter rapporteras som ärenden med prioritet, kategori, taggar och status.

Finns även en TV-vy för att visa öppna ärenden på storskärm, en morgonrapport-vy för dagliga genomgångar, samt publika delningslänkar med lösenord så anmälaren kan följa statusen.

Gränssnittet är på svenska (med engelska som alternativ).

## Kom igång

Kräver Docker och Docker Compose.

```sh
cp .env.example .env
# sätt minst SECRET_KEY i .env
docker compose -f docker-compose.yml --profile prod up -d
```

Detta startar PostgreSQL, Flask-appen (Gunicorn) och Caddy med automatisk
HTTPS.

För utveckling räcker det med `docker compose up` (utan `--profile prod`) —
då körs appen i debug-läge på http://localhost:8000 och Caddy hoppas över.

## Inloggning första gången

| Användarnamn | Lösenord |
|---|---|
| `sysadm` | `bananipyjamas` |

**Byt lösenord direkt efter första inloggningen.**

## Roller

- **Admin** — full åtkomst, hanterar användare, kategorier och taggar
- **Redaktör** — skapar och ändrar ärenden, ser översikt och morgonrapport
- **Läsare** — endast läsåtkomst (inkl. morgonrapport)

## Klassificering

- **Kategori** — övergripande grupp (Säkerhet, Miljö, Hälsa, Väder, Övrigt). Varje ärende tillhör exakt en. Admin sköter listan via `/admin/categories`.
- **Taggar** — fria etiketter för analys i efterhand. Redaktörer skapar dem direkt vid rapportering; admin döper om, tar bort oanvända och kan koppla taggar till en eller flera kategorier via `/admin/tags`.

## Morgonrapport

`/tickets/morgonrapport` visar nya, ändrade och avslutade ärenden i ett valbart tidsfönster (default föregående rotationstimme → samma idag, lokal tid). KPI-rutorna på toppen är klickbara och tar dig till motsvarande filtrerad ärendelista. Tänkt att projiceras eller skrivas ut inför morgonmöten.

## TV-skärm

`/tickets/tv` visar öppna ärenden i tre kolumner (Ny / Påbörjad / Avslutad). Korten kan visa antingen beskrivning (default) eller bara kategori + taggar — admin styr läget via Inställningar så förbipasserande inte kan ändra vad som projiceras. Anteckning (intern) visas aldrig.

## Inställningar

`/admin/settings` (admin) har körtidsknappar för:
- om TV-skärmen ska visa beskrivning eller bara kategori/taggar
- vilken timme på dygnet morgonrapportens default-fönster ska rotera

## Utveckling

Se [DEVELOPER.md](DEVELOPER.md) för projektstruktur, migrationer och
utvecklingsflöde.
