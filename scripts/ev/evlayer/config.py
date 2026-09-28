"""Configuration. Everything tunable lives here as one constant."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # scripts/ev/
CACHE = ROOT / "cache"
MIGRATIONS = ROOT / "migrations"


def _env(key: str, default: str = "") -> str:
    """Read from the process env, falling back to scripts/ev/.env."""
    if key in os.environ:
        return os.environ[key]
    envfile = ROOT / ".env"
    if envfile.exists():
        for line in envfile.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() == key:
                return v.strip()
    return default


DSN = _env("EVLAYER_DSN", "postgresql://evlayer:evlayer@localhost:5433/evlayer")

# Spec default: 5 minutes. Charger state does not flip faster than this in
# practice, and 5 min cuts storage and bandwidth ~80% against a 1 min poll.
POLL_SECONDS = int(_env("POLL_SECONDS", "300"))

# A station page stays noindex until it has this much real history. This is
# the single most important SEO rule in the spec: 80k thin pages sink the
# domain, so nothing is indexable before it has something to show.
MIN_HISTORY_DAYS = int(_env("MIN_HISTORY_DAYS", "30"))

SITE_ROOT = (ROOT / _env("SITE_ROOT", "../..")).resolve()
RDW_APP_TOKEN = _env("RDW_APP_TOKEN", "")

# ------------------------------------------------------------------ sources
# DOT-NL bulk files. All anonymous HTTP GET, no key, conditional-GET capable.
GEOJSON_URL = "https://opendata.ndw.nu/charging_point_locations.geojson.gz"
OCPI_LOCATIONS_URL = "https://opendata.ndw.nu/charging_point_locations_ocpi.json.gz"
OCPI_TARIFFS_URL = "https://opendata.ndw.nu/charging_point_tariffs_ocpi.json.gz"

# The bbox endpoint silently caps at 1000 features with no paging flag and is
# documented as "in development". Deliberately unused: the pipeline reads the
# bulk files instead.

USER_AGENT = "parkingnetherlands.com ev-layer (contact: craakash@analytics-ascent.com)"

# RDW Socrata dataset ids, reused from scripts/rdw_tariff_sync.py so the two
# pipelines cannot drift apart.
RDW = {
    "gebied": "adw6-9hsg",          # area names
    "gebied_regeling": "qtex-qwd8",  # area -> regulation
    "geometrie": "nsk3-v9n7",        # area -> WKT point
    "specificaties": "b3us-f26s",    # capacity, EV points, max height
    "tijdvak": "ixf8-gtwq",          # regulation -> fare calc per day/time
    "tariefdeel": "534e-5vdg",       # fare calc -> stepped fare parts
}
RDW_BASE = "https://opendata.rdw.nl/resource/{}.json"

SITE_URL = "https://parkingnetherlands.com"
SITE_NAME = "Parking Netherlands"

# Attribution rules, encoded so they cannot be got wrong by hand:
#   DOT-NL / NDW  -> must attribute
#   CBS           -> CC-BY, must attribute
#   RDW           -> CC-0 but crediting RDW is explicitly NOT allowed
ATTRIBUTION_NDW = "Laadpuntdata: NDW / DOT-NL"
