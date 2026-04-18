"""Swedish word list used to generate share-link secrets.

Kept deliberately short and generic (nature, scouting, everyday objects)
so a single word is memorable and easy to read aloud or write on a
clipboard. Combined with rate limiting on the public endpoint, one word
is enough to stop casual URL enumeration of camp tickets.

All words are lowercase. Swedish åäö is allowed -- URLs URL-encode them
automatically and the QR code round-trips them transparently.
"""

import secrets


WORDS = (
    # Nature / landscape
    "skog", "sten", "bro", "mark", "gran", "tall", "ek", "lind", "lönn",
    "löv", "bark", "kvist", "gren", "stam", "stig", "led", "holm", "kust",
    "vik", "berg", "dal", "sjö", "hav", "bäck", "fors", "källa", "damm",
    "träd", "blomma", "gräs", "mossa", "ljung", "hed", "myr", "kärr",
    "äng", "fält", "åker", "park", "strand", "klippa", "fjäll", "höjd",
    "slätt", "lund", "glänta", "ö", "udd", "näs", "rot", "frö", "knopp",
    "tuva", "grop", "branta", "håla",
    # Weather / sky
    "sol", "måne", "stjärna", "moln", "regn", "snö", "storm", "vind",
    "frost", "dimma", "åska", "blixt", "regnbåge", "gryning", "skymning",
    "dag", "kväll", "morgon", "natt", "himmel", "is", "skur", "bris",
    # Animals
    "varg", "björn", "räv", "hare", "älg", "hjort", "lo", "mård", "utter",
    "bäver", "skata", "kråka", "örn", "uggla", "svan", "gås", "and",
    "trana", "tjäder", "mus", "groda", "orm", "ödla", "fjäril", "bi",
    "humla", "mask", "fisk", "gädda", "abborre", "lax", "öring", "säl",
    "get", "får", "häst", "ko", "hund", "katt", "kanin", "igel", "mal",
    # Scouting / camp gear
    "knop", "eld", "tält", "rep", "yxa", "kniv", "kompass", "karta",
    "ryggsäck", "lykta", "båt", "kanot", "paddel", "skida", "flagga",
    "scout", "patrull", "läger", "hajk", "vandring", "spis", "pinne",
    "lina", "båge", "pil", "vimpel", "halsduk", "spång", "lampa",
    "sovsäck", "liggunderlag", "stormkök", "stormtändare",
    # Food
    "bröd", "ost", "smör", "ägg", "äpple", "bär", "svamp", "potatis",
    "morot", "mjölk", "honung", "salt", "peppar", "kaffe", "te", "soppa",
    "gröt", "bulle", "kaka", "glass", "saft", "juice", "nöt", "kanel",
    "blåbär", "lingon", "hallon", "jordgubbe", "körsbär", "päron",
    # Colors
    "röd", "grön", "blå", "gul", "vit", "svart", "grå", "brun", "rosa",
    "lila", "orange", "turkos", "guld", "silver",
    # Everyday objects
    "bok", "stol", "bord", "dörr", "fönster", "vägg", "tak", "golv",
    "klocka", "spegel", "nyckel", "brev", "kort", "boll", "spel", "mynt",
    "ring", "pärla", "band", "tråd", "nål", "kanna", "skål", "fat",
    "gaffel", "sked", "mugg", "flaska", "hink", "kärra", "vagn",
    # Things / small / simple
    "penna", "krita", "sudd", "block", "häfte", "pärm", "mapp", "rör",
    "knapp", "hake", "krok", "snöre", "länk", "kedja", "magnet", "plåt",
    "sten", "kork", "glas", "lera", "sand", "grus", "jord", "vatten",
    "luft", "salt", "eld", "is",
    # Camp roles / verbs-as-nouns (safe)
    "spejare", "vandrare", "seglare", "fiskare", "jägare", "bagare",
    "smed", "kock",
    # Misc nature words
    "hassel", "enbär", "nypon", "rosen", "viol", "vitsippa", "blåklocka",
    "tussilago", "maskros", "prästkrage", "smörblomma", "ranunkel",
)


def random_word():
    """Pick a single word uniformly at random from the list."""
    return secrets.choice(WORDS)
