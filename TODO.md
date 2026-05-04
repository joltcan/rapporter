# Förbättringar

Tydligen jobbar de andra scouterna efter SBAR:

”Vid rapportering eller överlämning av ärenden inom organisationen, oavsett kanal, använder vi i möjligaste mån metoden SBAR, där den som rapporterar eller överlämnar beskriver:
S - Situation: Vad är problemet eller situationen?
B - Bakgrund: Vilken bakgrundsinformation är relevant för situationen?
A - Aktuellt tillstånd: Vad är den aktuella bedömningen av läget?
R - Rekommendation: Vad bör göras? Vilka är rekommendationerna för fortsatt hantering?
Vid skriftlig rapportering ska det även framgå vem som rapporterar detta till vem och vid vilken tidpunkt. ”

Se nedan och utveckla ovastående.

## Klart
- [x] **Morgonrapport-vy** — `/tickets/morgonrapport`. Rotationstimme styrs från Inställningar (default 08:00). KPI-rutorna är klickbara länkar till filtrerad ärendelista; varje ärende-rad är klickbar till ticketen. Print-stöd.
- [x] **Övergripande kategorier** — Säkerhet, Miljö, Hälsa, Väder, Övrigt seedade i ny `categories`-tabell. Admin kan lägga till/ta bort (utom Övrigt) och sätta sortering via `/admin/categories`.
- [x] **Taggar** — Det som tidigare hette kategorier är nu `tags`. Sätts i efterhand på ticket, kan ändras, oanvända kan tas bort. En tagg kan kopplas till flera kategorier via `/admin/tags`.
- [x] **Tids-filter på `/tickets/`** — Skapad/Uppdaterad/Avslutad + från/till. Används av morgonrapportens KPI-länkar.
- [x] **TV-display-läge** — admin styr om TV-korten visar beskrivning (default, trunkerad till ~160 tecken med 2-rads clamp + kategori-badge inline) eller bara kategori + taggar.
- [x] **Inställningar** (`/admin/settings`) — `system_settings` key/value-tabell + sektionerad sida. Initialt två settings: TV-läge och morgonrapportens rotationstimme.

## SBAR-mappning (utredning - vänta med implementation)

Befintliga fält tycks redan täcka delar av SBAR. Tentativ mappning:

- **S** (Situation) → `description`
- **B** (Bakgrund) → `note` (intern anteckning)
- **A** (Aktuellt tillstånd) → `priority`
- **R** (Rekommendation) → ?? (oklart, behöver utredas)

Att ta ställning till innan något görs:
- Är `note` rätt plats för B? Note är idag intern och visas aldrig publikt - B i SBAR är inte hemligt.
- Räcker prioritet (P1/P2/P3) som A, eller behövs en fritextbedömning?
- Vad blir R? Eget fält? Återanvända `feedback` ("Återkoppla till")?
- Ska UI:t märka upp fälten med S/B/A/R-etiketter så det blir tydligt för SBAR-vana användare?
- "Vid skriftlig rapportering ska det framgå vem som rapporterar till vem och vid vilken tidpunkt" - rapportör + tidpunkt finns, men "till vem" saknas.

---
*Senast uppdaterad: 2026-05-04*
