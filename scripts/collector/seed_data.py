#!/usr/bin/env python3
"""
Seed inputs for the collector (spec section 2).

A seed = (location, modifier, language). Collectors expand seeds; the cross
product of location x modifier x language is the seed universe.

LOCATIONS below are a strong working core: the largest / highest parking-demand
Dutch municipalities plus the special POIs the spec calls out (airports,
hospitals, stadiums, ferries, beaches, P+R, border towns). The full 342
gemeenten can be dropped into locations_extra.txt (one "name|type" per line)
and they are merged in automatically - see load_locations().
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ---- Locations: (name, location_type) --------------------------------------
# location_type: city | airport | hospital | stadium | ferry | beach | pr | border | venue | region
CITIES = [
    "Amsterdam", "Rotterdam", "Den Haag", "Utrecht", "Eindhoven", "Groningen",
    "Tilburg", "Almere", "Breda", "Nijmegen", "Apeldoorn", "Haarlem",
    "Arnhem", "Enschede", "Amersfoort", "Zaanstad", "Haarlemmermeer",
    "Den Bosch", "Zwolle", "Zoetermeer", "Leeuwarden", "Leiden", "Maastricht",
    "Dordrecht", "Ede", "Alphen aan den Rijn", "Westland", "Alkmaar", "Emmen",
    "Delft", "Venlo", "Deventer", "Sittard", "Helmond", "Oss", "Amstelveen",
    "Hilversum", "Heerlen", "Hengelo", "Purmerend", "Roosendaal", "Schiedam",
    "Lelystad", "Gouda", "Spijkenisse", "Vlaardingen", "Almelo", "Assen",
    "Bergen op Zoom", "Capelle aan den IJssel", "Veenendaal", "Katwijk",
    "Zeist", "Nieuwegein", "Hoorn", "Den Helder", "Roermond", "Doetinchem",
    "Terneuzen", "Kampen", "Woerden", "Middelburg", "Vlissingen", "Harderwijk",
    "Weert", "Tiel", "Rijswijk", "Ridderkerk", "Barneveld", "Zutphen",
    "Wageningen", "Sneek", "Heerenveen", "Goes", "Zaltbommel",
]
POIS = [
    ("Schiphol", "airport"), ("Eindhoven Airport", "airport"),
    ("Rotterdam The Hague Airport", "airport"), ("Maastricht Aachen Airport", "airport"),
    ("Groningen Airport Eelde", "airport"),
    ("Johan Cruijff Arena", "stadium"), ("Ziggo Dome", "venue"),
    ("Ahoy Rotterdam", "venue"), ("GelreDome", "stadium"),
    ("Jaarbeurs Utrecht", "venue"), ("De Kuip", "stadium"),
    ("Philips Stadion", "stadium"), ("RAI Amsterdam", "venue"),
    ("Hoek van Holland", "ferry"), ("IJmuiden", "ferry"),
    ("Harlingen", "ferry"), ("Den Helder haven", "ferry"),
    ("Zandvoort", "beach"), ("Scheveningen", "beach"), ("Noordwijk", "beach"),
    ("Bloemendaal aan Zee", "beach"), ("Katwijk aan Zee", "beach"),
    ("Circuit Zandvoort", "venue"),
    ("Erasmus MC", "hospital"), ("UMC Utrecht", "hospital"),
    ("Amsterdam UMC", "hospital"), ("Radboudumc", "hospital"),
    ("UMCG Groningen", "hospital"), ("Maastricht UMC", "hospital"),
    ("Efteling", "venue"), ("Walibi Holland", "venue"),
]
# Border/coastal towns that pull German/Belgian/British demand (spec section 6)
BORDER = [
    ("Venlo", "border"), ("Enschede", "border"), ("Arnhem", "border"),
    ("Maastricht", "border"), ("Breda", "border"), ("Roosendaal", "border"),
    ("Nijmegen", "border"), ("Kerkrade", "border"), ("Winterswijk", "border"),
    ("Sluis", "border"),
]

# ---- Modifiers per language (spec section 2) -------------------------------
MODIFIERS = {
    "en": [
        "parking", "park", "car park", "parking cost", "cheap parking",
        "free parking", "overnight parking", "parking near", "where to park",
        "parking fine", "parking app", "EV charging parking",
        "disabled parking", "motorhome parking", "park and ride",
    ],
    "nl": [
        "parkeren", "parkeergarage", "gratis parkeren", "goedkoop parkeren",
        "parkeertarief", "parkeerboete", "parkeervergunning", "P+R",
        "parkeren kosten", "parkeerplaats", "opladen parkeren",
    ],
    "de": [
        "parken", "parkplatz", "kostenlos parken", "parkgebuhren",
        "parkhaus", "guenstig parken",
    ],
    "fr": [
        "stationnement", "parking gratuit", "se garer",
    ],
}

# ---- Temporal / event seeds (spec section 6) -------------------------------
# Venue-anchored recurring demand. The collector seeds these ahead of spikes.
EVENT_VENUES = [
    "Ziggo Dome", "Ahoy Rotterdam", "Johan Cruijff Arena", "Jaarbeurs Utrecht",
    "GelreDome", "RAI Amsterdam", "Circuit Zandvoort",
]
EVENT_TERMS = [
    "Lowlands", "Pinkpop", "Down The Rabbit Hole", "Sail Amsterdam",
    "Zandvoort GP", "Koningsdag Amsterdam", "concert", "festival",
]


def load_locations():
    """
    Returns a list of (name, location_type). Merges the embedded core with any
    locations_extra.txt lines ("name|type") so the full 342 gemeenten can be
    added without touching code.
    """
    locs = [(c, "city") for c in CITIES] + POIS + BORDER
    extra = HERE / "locations_extra.txt"
    if extra.is_file():
        for line in extra.read_text("utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "|" in line:
                name, ltype = line.split("|", 1)
                locs.append((name.strip(), ltype.strip() or "city"))
            else:
                locs.append((line, "city"))
    # de-dupe on (name, type), keep first
    seen, out = set(), []
    for name, ltype in locs:
        key = (name.lower(), ltype)
        if key not in seen:
            seen.add(key)
            out.append((name, ltype))
    return out
