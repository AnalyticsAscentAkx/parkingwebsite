"""Programmatic page generation.

Two sources feed the same templates:
  from_db()    production, once history exists
  from_feed()  builds straight off the DOT-NL GeoJSON with no database, so the
               pages can be built and reviewed before day one of history

Indexation discipline, which is the main risk in a build this size: a station
page is noindex until it has MIN_HISTORY_DAYS of measured history. Publishing
80k pages with nothing on them would cost more domain authority than the pages
could ever earn back. Aggregate pages (city, intent, card) index immediately
because they are never thin.
"""
import gzip
import json
from collections import defaultdict
from datetime import datetime

import orjson

from .. import config, fetch
from . import templates as T
from .templates import esc, slug

CITY_LABEL = {
    "amsterdam": "Amsterdam", "rotterdam": "Rotterdam", "den-haag": "The Hague",
    "utrecht": "Utrecht", "eindhoven": "Eindhoven", "groningen": "Groningen",
    "maastricht": "Maastricht", "leiden": "Leiden", "haarlem": "Haarlem",
    "breda": "Breda", "delft": "Delft", "nijmegen": "Nijmegen",
    "tilburg": "Tilburg", "zwolle": "Zwolle", "almere": "Almere",
    "arnhem": "Arnhem", "amersfoort": "Amersfoort", "apeldoorn": "Apeldoorn",
    "s-hertogenbosch": "Den Bosch", "enschede": "Enschede",
}

# A city page embeds its stations as JSON for the client-side pricing, so the
# list is paginated rather than shipped whole. 250 keeps a page near 40 KB.
PAGE_SIZE = 250

# A hub for a village with one charge point is thin by any measure, so it is
# generated (people still land on it) but kept out of the index.
MIN_CITY_STATIONS = 3

# Intent pages are rankings, and ranking eight chargers is not a ranking. They
# are only worth a URL where the list is long enough to be a real comparison.
MIN_INTENT_STATIONS = 25

INTENTS = {
    "most-reliable": ("reliable", "Most reliable chargers",
                      "Ranked by measured uptime over the last 30 days."),
    "cheapest":      ("cheap", "Cheapest chargers",
                      "Ranked by total cost of a session, charge plus parking."),
    "fast-charging": ("fast", "Fast charging",
                      "DC and high-power AC, ranked by delivered kW."),
}


def eligible_intents(stations: list[dict]) -> list[str]:
    """Return only comparisons with enough records to support their promise."""
    enough_history = sum(
        1 for s in stations
        if (s.get("hist_days") or 0) >= config.MIN_HISTORY_DAYS and s.get("up") is not None
    ) >= MIN_INTENT_STATIONS
    enough_prices = sum(
        1 for s in stations if s.get("ppk") is not None
    ) >= MIN_INTENT_STATIONS
    enough_fast = sum(1 for s in stations if (s.get("kw") or 0) >= 43) >= MIN_INTENT_STATIONS
    return [key for key, available in (
        ("most-reliable", enough_history),
        ("cheapest", enough_prices),
        ("fast-charging", enough_fast),
    ) if available]


# --------------------------------------------------------------- sources
def from_feed(limit_cities: int = 0) -> dict[str, list[dict]]:
    """Build station records straight from the GeoJSON bulk file.

    The GeoJSON has no city field, so the city is taken from the postcode
    town in the OCPI file when available and otherwise left ungrouped. This
    path exists so the design can be reviewed on real data immediately.
    """
    raw = fetch.get(config.OCPI_LOCATIONS_URL, force=True)
    locs = orjson.loads(raw.body)

    by_city: dict[str, list[dict]] = defaultdict(list)
    for loc in locs:
        city = (loc.get("city") or "").strip()
        if not city:
            continue
        coords = loc.get("coordinates") or {}
        evses = loc.get("evses") or []
        if not evses:
            continue
        kw = 0.0
        for e in evses:
            for c in e.get("connectors") or []:
                w = c.get("max_electric_power")
                if w:
                    kw = max(kw, float(w) / 1000.0)
                elif c.get("max_voltage") and c.get("max_amperage"):
                    ph = 3 if (c.get("power_type") or "") == "AC_3_PHASE" else 1
                    kw = max(kw, float(c["max_voltage"]) * float(c["max_amperage"]) * ph / 1000.0)
        by_city[slug(city)].append({
            "id": loc.get("id"),
            "n": (loc.get("address") or loc.get("name") or "Charging point").strip(),
            "cpo": ((loc.get("operator") or {}).get("name")),
            "lat": float(coords["latitude"]) if coords.get("latitude") else None,
            "lon": float(coords["longitude"]) if coords.get("longitude") else None,
            "kw": round(kw, 1) if kw else None,
            "up": None,       # no history yet
            "h": None,        # no 30-day strip yet
            "ppk": None,      # no tariff join in feed mode
            "fee": None,
            "pw": None,       # no parking windows in feed mode
            "evses": len(evses),
            "city_label": city,
            "postal": loc.get("postal_code"),
        })
    if limit_cities:
        top = sorted(by_city.items(), key=lambda kv: -len(kv[1]))[:limit_cities]
        return dict(top)
    return dict(by_city)


def from_db() -> dict[str, list[dict]]:
    """Production source. Joins registry, reliability history and parking."""
    from .. import db
    rows = db.query(
        """SELECT s.station_id, s.name, s.address, s.cpo, s.lat, s.lon, s.city,
                  s.postal_code,
                  COUNT(DISTINCT e.evse_id)::int AS evses,
                  MAX(c.max_power_kw) AS kw,
                  ROUND(AVG(r.uptime_pct), 1) AS up,
                  COUNT(DISTINCT r.day)::int AS hist_days,
                  l.area_id
           FROM station s
           JOIN evse e ON e.station_id = s.station_id
           LEFT JOIN connector c ON c.evse_id = e.evse_id
           LEFT JOIN reliability_daily r
             ON r.evse_id = e.evse_id AND r.day > current_date - 30
           LEFT JOIN station_parking_link l ON l.station_id = s.station_id
           WHERE s.city IS NOT NULL AND s.lat IS NOT NULL
           GROUP BY s.station_id, l.area_id"""
    )

    windows = defaultdict(list)
    for w in db.query(
        "SELECT area_id, day_of_week, start_min, end_min, price_per_hour FROM parking_tariff"
    ):
        windows[w["area_id"]].append(
            [w["day_of_week"], w["start_min"], w["end_min"], float(w["price_per_hour"])])

    prices = {r["station_id"]: r for r in db.query(
        """SELECT s.station_id,
                  MAX(t.price_per_kwh) AS ppk, MAX(t.start_fee) AS fee
           FROM station s
           JOIN evse e ON e.station_id = s.station_id
           JOIN connector c ON c.evse_id = e.evse_id
           JOIN LATERAL unnest(c.tariff_ids) AS tid ON true
           JOIN cpo_tariff t ON t.tariff_id = tid
           GROUP BY s.station_id""")}

    hist = defaultdict(dict)
    for r in db.query(
        """SELECT s.station_id, r.day, ROUND(AVG(r.uptime_pct),1) AS up
           FROM reliability_daily r
           JOIN evse e ON e.evse_id = r.evse_id
           JOIN station s ON s.station_id = e.station_id
           WHERE r.day > current_date - 30
           GROUP BY s.station_id, r.day"""):
        hist[r["station_id"]][str(r["day"])] = float(r["up"]) if r["up"] is not None else None

    by_city = defaultdict(list)
    for r in rows:
        p = prices.get(r["station_id"], {})
        days = sorted(hist.get(r["station_id"], {}))
        by_city[slug(r["city"])].append({
            "id": r["station_id"],
            "n": (r["address"] or r["name"] or "Charging point").strip(),
            "cpo": r["cpo"],
            "lat": float(r["lat"]), "lon": float(r["lon"]),
            "kw": float(r["kw"]) if r["kw"] else None,
            "up": float(r["up"]) if r["up"] is not None else None,
            "h": [hist[r["station_id"]][d] for d in days] or None,
            "hist_days": r["hist_days"] or 0,
            "ppk": float(p["ppk"]) if p.get("ppk") else None,
            "fee": float(p["fee"]) if p.get("fee") else None,
            "pw": windows.get(r["area_id"]) or None,
            "evses": r["evses"],
            "city_label": r["city"],
            "postal": r["postal_code"],
        })
    return dict(by_city)


# --------------------------------------------------------------- fragments
def _payload(stations: list[dict], with_urls: str | None = None) -> str:
    """Compact JSON for the client. Short keys keep a 500-row city page small."""
    out = []
    for s in stations:
        rec = {k: s[k] for k in ("id", "n", "cpo", "lat", "lon", "kw", "up", "h", "ppk", "fee", "pw")
               if s.get(k) is not None}
        if with_urls:
            rec["url"] = f"/ev-charger/{with_urls}/{slug(s['n'])}-{slug(s['id'])[-8:]}"
        out.append(rec)
    return json.dumps(out, separators=(",", ":"), ensure_ascii=False)


def _window_control(kwh_default: int = 20) -> str:
    return f"""<div class="ev-window">
  <h2>What will this stop cost</h2>
  <p>Set when you arrive and leave. Parking is charged only for the minutes inside a paid window, so the total moves with the time of day.</p>
  <div class="ev-fields">
    <div class="ev-field"><label for="evArrive">Arriving</label>
      <input type="datetime-local" id="evArrive" data-stamp=""></div>
    <div class="ev-field"><label for="evLeave">Leaving</label>
      <input type="datetime-local" id="evLeave" data-stamp=""></div>
    <div class="ev-field"><label for="evKwh">Energy, kWh</label>
      <input type="number" id="evKwh" class="ev-kwh" value="{kwh_default}" min="1" max="120" step="1" aria-label="kWh needed"></div>
  </div>
</div>"""


def _table(sort_default: str = "reliable") -> str:
    btn = lambda k, label: (
        f'<button data-sort="{k}" aria-pressed="{"true" if k == sort_default else "false"}">{label}</button>')
    return f"""<div class="ev-tablewrap">
  <div class="ev-tbar">
    <span class="ev-count" id="evCount">Loading</span>
    <div class="ev-sort" role="group" aria-label="Sort chargers">
      {btn('reliable', 'Reliability')}{btn('cheap', 'Total cost')}{btn('fast', 'Power')}
    </div>
  </div>
  <div class="ev-scroll"><div id="evRows" role="listbox" aria-label="Chargers"></div></div>
</div>"""


def _sources_note(measured_days: int) -> str:
    since = (f"Uptime is measured from our own polling of the national charging feed, "
             f"{measured_days} days so far." if measured_days else
             "Uptime measurement starts once the collector has been running; "
             "no reliability history is published yet.")
    return (f'<p class="ev-src">{since} Charging point data: '
            f'{config.ATTRIBUTION_NDW}. Parking tariffs come from the Dutch national '
            f'parking register. Prices are indicative and exclude session fees your '
            f'card issuer may add.</p>')


# ------------------------------------------------------------------ pages
def city_page(city_slug: str, stations: list[dict], measured_days: int,
              page: int = 1, pages: int = 1,
              intents: list[str] | None = None) -> tuple[str, bool]:
    """Returns (html, indexable). Page 1 lives at /ev-charging/{city}; later
    pages at /ev-charging/{city}/page-N, each canonical to itself so the set
    is crawlable without duplicating content onto one URL."""
    label = CITY_LABEL.get(city_slug) or (stations[0]["city_label"] if stations else city_slug.title())
    base = f"{config.SITE_URL}/ev-charging/{city_slug}"
    canonical = base if page == 1 else f"{base}/page-{page}"
    all_n = stations[0].get("_city_total", len(stations)) if stations else 0
    n = len(stations)
    evses = stations[0].get("_city_evses") if stations else 0
    if not evses:
        evses = sum(s.get("evses") or 0 for s in stations)
    with_hist = [s for s in stations if s.get("up") is not None]
    avg = round(sum(s["up"] for s in with_hist) / len(with_hist), 1) if with_hist else None

    suffix = "" if page == 1 else f" (page {page})"
    title = (f"EV charging {label}: {all_n} locations, {avg}% measured uptime{suffix} | {config.SITE_NAME}"
             if avg is not None else
             f"EV charging {label}: {all_n} locations and charging costs{suffix} | {config.SITE_NAME}")
    desc = (f"Compare public chargers in {label} with {avg}% measured uptime and estimated "
            f"charging plus parking costs. {all_n} locations, {evses} charge points."
            if avg is not None else
            f"Compare public chargers in {label}. See published charging prices and matched "
            f"parking tariffs where available. {all_n} locations, {evses} charge points.")

    ld = json.dumps([
        {"@context": "https://schema.org", "@type": "ItemList",
         "name": f"EV chargers in {label}",
         "numberOfItems": n,
         "itemListElement": [
             {"@type": "ListItem", "position": i + 1,
              "name": s["n"],
              "item": f"{config.SITE_URL}/ev-charger/{city_slug}/{slug(s['n'])}-{slug(s['id'])[-8:]}"}
             for i, s in enumerate(stations[:30])]},
        {"@context": "https://schema.org", "@type": "BreadcrumbList",
         "itemListElement": [
             {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{config.SITE_URL}/"},
             {"@type": "ListItem", "position": 2, "name": "EV charging", "item": f"{config.SITE_URL}/ev-charging"},
             {"@type": "ListItem", "position": 3, "name": label, "item": canonical}]},
    ], separators=(",", ":"))

    stats = f"""<div class="ev-since">
      <div><b>{all_n:,}</b><span>charging locations</span></div>
      <div><b>{evses:,}</b><span>charge points</span></div>
      {'<div><b>' + str(avg) + '%</b><span>average uptime, 30 days</span></div>' if avg is not None else ''}
      {'<div><b>' + str(measured_days) + '</b><span>days measured</span></div>' if measured_days else '<div><b>—</b><span>reliability history not available</span></div>'}
    </div>"""

    available_intents = intents if intents is not None else eligible_intents(stations)
    intent_links = " ".join(
        f'<a href="/ev-charging/{city_slug}/{k}">{INTENTS[k][1]}</a>'
        for k in available_intents)
    intent_section = (f'<p class="ev-src" style="border:none;padding-top:14px">'
                      f'Compare in {esc(label)}: {intent_links}</p>' if intent_links else "")

    def page_url(i):
        return f"/ev-charging/{city_slug}" if i == 1 else f"/ev-charging/{city_slug}/page-{i}"

    rel = ""
    if page > 1:
        rel += f'\n<link rel="prev" href="{config.SITE_URL}{page_url(page - 1)}">'
    if page < pages:
        rel += f'\n<link rel="next" href="{config.SITE_URL}{page_url(page + 1)}">'

    pager = ""
    if pages > 1:
        links = "".join(
            f'<a href="{page_url(i)}" class="ev-pg{" is-on" if i == page else ""}">{i}</a>'
            for i in range(1, pages + 1))
        pager = (f'<nav class="ev-pager" aria-label="More chargers in {esc(label)}">'
                 f'<span>Page {page} of {pages}</span><div>{links}</div></nav>')

    indexable = all_n >= MIN_CITY_STATIONS

    return f"""{T.head(title, desc, canonical, ld, indexable=indexable, extra_css=rel)}
<div class="evwrap">
  <div class="ev-head">
    <div class="ev-crumb"><a href="/">Home</a> / <a href="/ev-charging">EV charging</a> / {esc(label)}</div>
    <h1>EV charging in {esc(label)}</h1>
    <p class="ev-lede">Every public charging point in {esc(label)}, with how reliable it has actually
       been and what a session really costs once parking is counted. Pick your arrival and departure
       time to price the stop.</p>
    {stats}
  </div>
  <div class="ev-split">
    <div class="ev-mapcol">
      <div id="evmap"></div>
      <p class="ev-maphint">Green is above 97% uptime, amber above 90%, red below. Grey means not enough history yet. Select a pin to jump to it in the list.</p>
    </div>
    <div>
      {_window_control()}
      {_table()}
      {pager}
      {intent_section}
    </div>
  </div>
  {_sources_note(measured_days)}
</div>
<script>window.EV_DATA={{"stations":{_payload(stations, with_urls=city_slug)}}};</script>
<script src="/ev.js" defer></script>
{T.TAIL}""", indexable


def intent_page(city_slug: str, intent: str, stations: list[dict], measured_days: int) -> str:
    sort_key, heading, blurb = INTENTS[intent]
    label = CITY_LABEL.get(city_slug) or (stations[0]["city_label"] if stations else city_slug.title())
    canonical = f"{config.SITE_URL}/ev-charging/{city_slug}/{intent}"

    if sort_key == "fast":
        stations = [s for s in stations if (s.get("kw") or 0) >= 43]
    elif sort_key == "reliable":
        stations = [s for s in stations if (s.get("hist_days") or 0) >= config.MIN_HISTORY_DAYS and s.get("up") is not None]
    elif sort_key == "cheap":
        stations = [s for s in stations if s.get("ppk") is not None]
    # These pages are a ranking, so a top-N is the honest shape and keeps the
    # embedded payload small.
    stations = stations[:PAGE_SIZE]
    title = f"{heading} in {label} | {config.SITE_NAME}"
    desc = f"{blurb} {len(stations)} chargers in {label}, with charge plus parking cost per session."

    ld = json.dumps({
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{config.SITE_URL}/"},
            {"@type": "ListItem", "position": 2, "name": "EV charging", "item": f"{config.SITE_URL}/ev-charging"},
            {"@type": "ListItem", "position": 3, "name": label, "item": f"{config.SITE_URL}/ev-charging/{city_slug}"},
            {"@type": "ListItem", "position": 4, "name": heading, "item": canonical}]},
        separators=(",", ":"))

    return f"""{T.head(title, desc, canonical, ld, indexable=True)}
<div class="evwrap">
  <div class="ev-head">
    <div class="ev-crumb"><a href="/">Home</a> / <a href="/ev-charging">EV charging</a> /
      <a href="/ev-charging/{city_slug}">{esc(label)}</a> / {esc(heading)}</div>
    <h1>{esc(heading)} in {esc(label)}</h1>
    <p class="ev-lede">{esc(blurb)} Set your arrival and departure time to see what each one would
       actually cost, charging and parking together.</p>
  </div>
  <div class="ev-split">
    <div class="ev-mapcol">
      <div id="evmap"></div>
      <p class="ev-maphint">Select a pin to jump to it in the list.</p>
    </div>
    <div>{_window_control()}{_table(sort_default=sort_key)}</div>
  </div>
  {_sources_note(measured_days)}
</div>
<script>window.EV_DATA={{"stations":{_payload(stations, with_urls=city_slug)}}};</script>
<script src="/ev.js" defer></script>
{T.TAIL}"""


def station_page(city_slug: str, st: dict, measured_days: int) -> tuple[str, bool]:
    """Returns (html, indexable). A station page is noindex until it has real
    history to show, which is the rule that keeps 80k thin pages out of the
    index and the domain out of trouble."""
    label = CITY_LABEL.get(city_slug) or st.get("city_label") or city_slug.title()
    name = st["n"]
    page_slug = f"{slug(name)}-{slug(st['id'])[-8:]}"
    canonical = f"{config.SITE_URL}/ev-charger/{city_slug}/{page_slug}"

    hist_days = st.get("hist_days") or 0
    indexable = hist_days >= config.MIN_HISTORY_DAYS and st.get("up") is not None

    up = st.get("up")
    up_txt = f"{up:.1f}% reliable" if up is not None else "reliability being measured"
    title = f"Charging point {name}, {label}: {up_txt} | {config.SITE_NAME}"
    desc = (f"{name} in {label}, operated by {st.get('cpo') or 'an unlisted operator'}. "
            f"{'Measured uptime ' + format(up, '.1f') + '%, ' if up is not None else ''}"
            f"plus what a session costs once parking is included.")

    ld = json.dumps([
        {"@context": "https://schema.org", "@type": "Place",
         "name": name, "url": canonical,
         "additionalType": "https://schema.org/EVChargingStation",
         "geo": {"@type": "GeoCoordinates", "latitude": st["lat"], "longitude": st["lon"]},
         "address": {"@type": "PostalAddress", "streetAddress": name,
                     "postalCode": st.get("postal"), "addressLocality": label,
                     "addressCountry": "NL"},
         "dateModified": datetime.now().strftime("%Y-%m-%d")},
        {"@context": "https://schema.org", "@type": "BreadcrumbList",
         "itemListElement": [
             {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{config.SITE_URL}/"},
             {"@type": "ListItem", "position": 2, "name": "EV charging", "item": f"{config.SITE_URL}/ev-charging"},
             {"@type": "ListItem", "position": 3, "name": label, "item": f"{config.SITE_URL}/ev-charging/{city_slug}"},
             {"@type": "ListItem", "position": 4, "name": name, "item": canonical}]},
    ], separators=(",", ":"))

    young = "" if indexable else f"""<div class="ev-young">
      This page is not published to search yet. We publish a charger only once it has
      {config.MIN_HISTORY_DAYS} days of measured history, so the reliability figure means something.
      So far: {hist_days} {'day' if hist_days == 1 else 'days'}.</div>"""

    facts = f"""<dl class="ev-facts">
      <div><dt>Operator</dt><dd style="font-size:13px">{esc(st.get('cpo') or 'Not published')}</dd></div>
      <div><dt>Charge points</dt><dd>{st.get('evses') or 1}</dd></div>
      <div><dt>Max power</dt><dd>{(str(st['kw']) + ' kW') if st.get('kw') else 'n/a'}</dd></div>
      <div><dt>Uptime, 30 days</dt><dd>{(format(up, '.1f') + '%') if up is not None else 'n/a'}</dd></div>
    </dl>"""

    return f"""{T.head(title, desc, canonical, ld, indexable=indexable)}
<div class="evwrap">
  <div class="ev-head">
    <div class="ev-crumb"><a href="/">Home</a> / <a href="/ev-charging">EV charging</a> /
      <a href="/ev-charging/{city_slug}">{esc(label)}</a> / {esc(name)}</div>
    <h1>{esc(name)}</h1>
    <p class="ev-lede">Public charging point in {esc(label)}, operated by
       {esc(st.get('cpo') or 'an operator that does not publish its name')}.</p>
  </div>
  {young}
  <div class="ev-detail">
    <div>
      <div class="ev-panel">
        <h2>Reliability</h2>
        <p class="note">Each bar is one day. We count a charge point as working when it reports
           available, charging or occupied. Out of order counts against it, and so does a long
           silence: an operator that stops reporting is not demonstrating uptime.</p>
        <div id="evStrip"></div>
      </div>
      <div class="ev-panel">
        <h2>Details</h2>
        {facts}
      </div>
    </div>
    <div>
      {_window_control()}
      <div class="ev-panel">
        <h2>Your session</h2>
        <p class="note">Charging and parking, for the window you set.</p>
        <div class="ev-bill" id="evBill"></div>
      </div>
      <div class="ev-tablewrap"><div class="ev-tbar"><span class="ev-count" id="evCount">Nearby</span>
        <div class="ev-sort"><button data-sort="reliable" aria-pressed="true">Reliability</button></div></div>
        <div class="ev-scroll"><div id="evRows" role="listbox" aria-label="Nearby chargers"></div></div></div>
    </div>
  </div>
  {_sources_note(measured_days)}
</div>
<script>window.EV_DATA={{"stations":{_payload([st], with_urls=city_slug)}}};</script>
<script src="/ev.js" defer></script>
{T.TAIL}"""


def index_page(cities: dict[str, list[dict]], measured_days: int) -> str:
    canonical = f"{config.SITE_URL}/ev-charging"
    ranked = sorted(cities.items(), key=lambda kv: -len(kv[1]))
    total = sum(len(v) for v in cities.values())
    rows = "".join(
        f'<div class="ev-row"><div><div class="ev-name">'
        f'<a href="/ev-charging/{c}">{esc(CITY_LABEL.get(c) or (v[0]["city_label"] if v else c.title()))}</a></div>'
        f'<div class="ev-meta"><span>{len(v):,} charging locations</span></div></div></div>'
        for c, v in ranked[:200])

    ld = json.dumps({"@context": "https://schema.org", "@type": "ItemList",
                     "name": "EV charging by city in the Netherlands",
                     "numberOfItems": len(ranked)}, separators=(",", ":"))

    return f"""{T.head(
        f"EV charging in the Netherlands: reliability and true cost | {config.SITE_NAME}",
        f"Measured uptime for {total:,} public charging locations across the Netherlands, "
        f"plus what a session actually costs once parking is counted.",
        canonical, ld, indexable=True)}
<div class="evwrap">
  <div class="ev-head">
    <div class="ev-crumb"><a href="/">Home</a> / EV charging</div>
    <h1>EV charging in the Netherlands</h1>
    <p class="ev-lede">Two things no charging map tells you: whether a charge point actually works,
       and what the stop costs once parking is added. We poll the national charging feed and keep the
       history, so reliability here is measured rather than claimed.</p>
    <div class="ev-since">
      <div><b>{total:,}</b><span>charging locations</span></div>
      <div><b>{len(ranked):,}</b><span>cities and towns</span></div>
      <div><b>{measured_days}</b><span>days measured</span></div>
    </div>
  </div>
  <div class="ev-tablewrap" style="margin:24px 0 40px">
    <div class="ev-tbar"><span class="ev-count">{len(ranked):,} places</span></div>
    <div>{rows}</div>
  </div>
  {_sources_note(measured_days)}
</div>
{T.TAIL}"""
