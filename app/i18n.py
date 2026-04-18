"""Lightweight two-language translation layer.

No pybabel compile step is required -- all translations live in the
TRANSLATIONS dict below. Templates use `{{ _('Some text') }}` which, at
render time, resolves to the Swedish or English variant based on:

1. explicit `?lang=sv|en` query or cookie set by the user, or
2. the browser's Accept-Language header, or
3. Swedish as the fallback default.

Keys in the TRANSLATIONS dict are the *English* source strings. The
English side is included explicitly so that untranslated strings still
produce identical output on both locales.
"""

from flask import request, g


DEFAULT_LOCALE = "sv"
SUPPORTED_LOCALES = ("sv", "en")
LOCALE_COOKIE = "scout_locale"


# Keyed by English source string. Missing keys fall back to the source.
TRANSLATIONS = {
    "en": {},  # English source is the key, so no overrides needed.
    "sv": {
        # --- General ---
        "Scout Tickets": "Scout Ärenden",
        "Ticket system": "Ärendesystem",
        "Sign in": "Logga in",
        "Sign out": "Logga ut",
        "Username": "Användarnamn",
        "Password": "Lösenord",
        "Remember me": "Kom ihåg mig",
        "Incorrect username or password.": "Felaktigt användarnamn eller lösenord.",
        "You have signed out.": "Du har loggat ut.",
        "Please sign in to continue.": "Logga in för att fortsätta.",
        "Save": "Spara",
        "Cancel": "Avbryt",
        "Edit": "Redigera",
        "Delete": "Ta bort",
        "Back": "Tillbaka",
        "Actions": "Åtgärder",
        "Yes": "Ja",
        "No": "Nej",
        "Language": "Språk",

        # --- Navigation ---
        "Overview": "Översikt",
        "Tickets": "Ärenden",
        "New ticket": "Nytt ärende",
        "Users": "Användare",
        "Categories": "Kategorier",
        "TV dashboard": "TV-skärm",
        "Public view": "Publik vy",

        # --- Roles ---
        "Administrator": "Administratör",
        "Editor": "Redaktör",
        "Viewer": "Läsare",
        "Role": "Roll",

        # --- Ticket fields ---
        "Title": "Titel",
        "Description": "Beskrivning",
        "Feedback": "Återkoppling",
        "Priority": "Prioritet",
        "Category": "Kategori",
        "Status": "Status",
        "Created": "Skapad",
        "Closed": "Avslutad",
        "Updated": "Uppdaterad",
        "Public": "Publik",
        "Reporter": "Rapportör",
        "History": "Historik",

        # --- Priorities ---
        "P1 – Critical": "P1 – Akut",
        "P2 – Important": "P2 – Viktig",
        "P3 – Low": "P3 – Låg",
        "P1 – Critical (safety, injury, something broken right now)":
            "P1 – Akut (säkerhet, skada, något är trasigt just nu)",
        "P2 – Important (affects activities, no danger)":
            "P2 – Viktig (påverkar aktiviteter men ingen fara)",
        "P3 – Low (wish, nice-to-have, can wait)":
            "P3 – Låg (önskemål, nice-to-have, kan vänta)",

        # --- Statuses ---
        "New": "Ny",
        "Started": "Påbörjad",
        "Resolved": "Avslutad",
        "Paused": "Pausad",
        "Rejected": "Avvisad",

        # --- Dashboard / widgets ---
        "Open tickets": "Öppna ärenden",
        "Total tickets": "Totalt ärenden",
        "In queue": "I kö",
        "Critical (P1)": "Akuta (P1)",
        "Recently updated": "Senast ändrade",
        "Queue length": "Kölängd",
        "By priority": "Efter prioritet",
        "By status": "Efter status",
        "Latest tickets": "Senaste ärenden",
        "No tickets yet.": "Inga ärenden ännu.",
        "Show all": "Visa alla",

        # --- Ticket form ---
        "Ticket title (optional, shown on dashboards)": "Titel (valfri, visas på dashboard)",
        "Describe what happened": "Beskriv vad som hänt",
        "Short feedback line": "Kort återkoppling",
        "Choose or type a new category": "Välj eller skriv in en ny kategori",
        "Make this ticket public":
            "Gör detta ärende publikt",
        "Public tickets can be viewed by anyone with the link. Only status, category, created and closed times are shown.":
            "Publika ärenden kan ses av vem som helst med länken. Endast status, kategori, skapad och avslutad visas.",
        "Save ticket": "Spara ärende",

        # --- Ticket view ---
        "Ticket #": "Ärende #",
        "Share link": "Delningslänk",
        "Scan to open this ticket": "Skanna för att öppna ärendet",
        "Download QR code": "Ladda ned QR-kod",
        "This ticket is public — anyone with the link can see its status.":
            "Ärendet är publikt — vem som helst med länken kan se status.",
        "Change log": "Ändringshistorik",
        "No changes yet.": "Inga ändringar ännu.",
        "changed": "ändrade",
        "from": "från",
        "to": "till",
        "created ticket": "skapade ärendet",
        "(empty)": "(tomt)",
        "Show history": "Visa historik",
        "Hide history": "Dölj historik",

        # --- Public view ---
        "Ticket status": "Ärendestatus",
        "This ticket is not public.": "Detta ärende är inte publikt.",

        # --- Categories admin ---
        "Manage categories": "Hantera kategorier",
        "Category name": "Kategorinamn",
        "Used in": "Används i",
        "tickets": "ärenden",
        "No categories yet.": "Inga kategorier ännu.",
        "New category": "Ny kategori",
        "A category with this name already exists.": "En kategori med detta namn finns redan.",
        "Category added.": "Kategori tillagd.",
        "Category removed.": "Kategori borttagen.",
        "Cannot remove a category that is in use.": "Kan inte ta bort en kategori som används.",

        # --- Users admin ---
        "Manage users": "Hantera användare",
        "New user": "Ny användare",
        "Edit user": "Redigera användare",
        "Leave blank to keep current password.": "Lämna tomt för att behålla nuvarande lösenord.",
        "Password (min 6 characters).": "Lösenord (minst 6 tecken).",
        "Only letters, numbers and underscores.": "Endast bokstäver, siffror och understreck.",
        "Username already taken.": "Användarnamnet är upptaget.",
        "Password required for new users.": "Lösenord krävs för nya användare.",
        "User %(name)s created.": "Användare %(name)s skapad.",
        "User %(name)s updated.": "Användare %(name)s uppdaterad.",
        "User %(name)s removed.": "Användare %(name)s borttagen.",
        "You cannot remove your own account.": "Du kan inte ta bort ditt eget konto.",
        "QR code": "QR-kod",

        # --- TV dashboard ---
        "Live ticket board": "Live-tavla",
        "Updated %(time)s": "Uppdaterad %(time)s",

        # --- Validation ---
        "Enter a username.": "Ange ett användarnamn.",
        "Enter a password.": "Ange ett lösenord.",
        "Description is required.": "Beskrivning krävs.",
        "You are not allowed to do that.": "Du saknar behörighet för detta.",
        "Ticket saved.": "Ärendet sparat.",
        "Ticket removed.": "Ärendet borttaget.",
        "Not found.": "Hittades inte.",

        # --- Misc ---
        "Log in with the account your administrator gave you.":
            "Logga in med kontot din administratör har gett dig.",
        "— none —": "— ingen —",
        "Filter": "Filtrera",
        "Search": "Sök",
        "Clear": "Rensa",
        "All": "Alla",
        "Any priority": "Alla prioriteter",
        "Any status": "Alla statusar",
        "Any category": "Alla kategorier",
    },
}


# Labels for Ticket status and priority slugs. The helper returns the
# English source string; callers pipe it through `_()` to localise.
STATUS_LABELS = {
    "ny": "New",
    "paborjad": "Started",
    "avslutad": "Resolved",
    "pausad": "Paused",
    "avvisad": "Rejected",
}

PRIORITY_LABELS = {
    1: "P1 – Critical",
    2: "P2 – Important",
    3: "P3 – Low",
}

PRIORITY_LABELS_LONG = {
    1: "P1 – Critical (safety, injury, something broken right now)",
    2: "P2 – Important (affects activities, no danger)",
    3: "P3 – Low (wish, nice-to-have, can wait)",
}

ROLE_LABELS = {
    "admin": "Administrator",
    "editor": "Editor",
    "viewer": "Viewer",
}


def detect_locale():
    """Pick a locale for the current request.

    Precedence:
      1. explicit `?lang=` query argument
      2. the locale cookie (set by the dropdown)
      3. DEFAULT_LOCALE (Swedish)

    Browser Accept-Language is intentionally ignored so that the site
    defaults to Swedish regardless of the visitor's browser settings.
    """
    cached = getattr(g, "locale", None)
    if cached:
        return cached

    q = request.args.get("lang")
    if q in SUPPORTED_LOCALES:
        g.locale = q
        return q

    c = request.cookies.get(LOCALE_COOKIE)
    if c in SUPPORTED_LOCALES:
        g.locale = c
        return c

    g.locale = DEFAULT_LOCALE
    return DEFAULT_LOCALE


def gettext(source, **kwargs):
    """Translate `source` (English) into the current locale. Supports
    %()s-style keyword interpolation so callers can pass dynamic values
    without concatenating user-input into the lookup key."""
    locale = detect_locale()
    translated = TRANSLATIONS.get(locale, {}).get(source, source)
    if kwargs:
        try:
            return translated % kwargs
        except (KeyError, ValueError):
            return translated
    return translated


def status_label(slug):
    return gettext(STATUS_LABELS.get(slug, slug))


def priority_label(n):
    return gettext(PRIORITY_LABELS.get(n, f"P{n}"))


def priority_label_long(n):
    return gettext(PRIORITY_LABELS_LONG.get(n, f"P{n}"))


def role_label(slug):
    return gettext(ROLE_LABELS.get(slug, slug))


def init_app(app):
    """Register template globals and a `set-language` route."""
    from flask import redirect, request as flask_request, make_response, url_for

    app.jinja_env.globals["_"] = gettext
    app.jinja_env.globals["current_locale"] = detect_locale
    app.jinja_env.globals["status_label"] = status_label
    app.jinja_env.globals["priority_label"] = priority_label
    app.jinja_env.globals["priority_label_long"] = priority_label_long
    app.jinja_env.globals["role_label"] = role_label
    app.jinja_env.globals["supported_locales"] = SUPPORTED_LOCALES

    @app.route("/set-language/<lang>")
    def set_language(lang):
        target = flask_request.args.get("next") or "/"
        # Only allow internal relative redirects.
        if not target.startswith("/") or target.startswith("//"):
            target = "/"
        resp = make_response(redirect(target))
        if lang in SUPPORTED_LOCALES:
            # Long-lived cookie so the choice sticks across visits.
            resp.set_cookie(
                LOCALE_COOKIE,
                lang,
                max_age=60 * 60 * 24 * 365,
                httponly=False,
                samesite="Lax",
            )
        return resp
