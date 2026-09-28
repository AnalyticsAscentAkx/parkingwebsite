"""Writes the generated pages to disk and maintains the sitemaps."""
import shutil
from datetime import date
from pathlib import Path

from .. import config
from . import generate as G
from .templates import slug

EV_CHARGER = "ev-charger"
EV_CHARGING = "ev-charging"


def _write(path: Path, html: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def measured_days() -> int:
    """How long the collector has actually been running. Drives both the
    headline stat and the noindex gate, so it is read once and passed down."""
    try:
        from .. import db
        row = db.one(
            "SELECT COUNT(DISTINCT day)::int AS d FROM reliability_daily")
        return int(row["d"]) if row and row["d"] else 0
    except Exception:
        return 0


def build(source: str = "db", cities: list[str] | None = None,
          max_cities: int = 0, stations: bool = True) -> dict:
    root = config.SITE_ROOT
    days = measured_days()

    by_city = G.from_db() if source == "db" else G.from_feed(limit_cities=max_cities)
    # A hub for a hamlet with two chargers earns no traffic and costs crawl
    # budget, so it never gets a URL at all.
    by_city = {k: v for k, v in by_city.items() if len(v) >= G.MIN_CITY_STATIONS}
    if cities:
        want = {slug(c) for c in cities}
        by_city = {k: v for k, v in by_city.items() if k in want}
    elif max_cities and source == "db":
        by_city = dict(sorted(by_city.items(), key=lambda kv: -len(kv[1]))[:max_cities])

    written = {"cities": 0, "intents": 0, "stations": 0, "indexable": 0, "noindex": 0}
    indexable_urls: list[str] = [f"{config.SITE_URL}/{EV_CHARGING}"]

    _write(root / f"{EV_CHARGING}.html", G.index_page(by_city, days))

    for city, sts in by_city.items():
        sts = sorted(sts, key=lambda s: (-(s.get("up") or 0), s["n"]))
        total = len(sts)
        city_evses = sum(x.get("evses") or 0 for x in sts)
        city_intents = G.eligible_intents(sts)
        for s0 in sts:
            s0["_city_total"] = total
            s0["_city_evses"] = city_evses
        pages = max(1, -(-total // G.PAGE_SIZE))

        for pg in range(1, pages + 1):
            chunk = sts[(pg - 1) * G.PAGE_SIZE: pg * G.PAGE_SIZE]
            html, ok = G.city_page(city, chunk, days, page=pg, pages=pages,
                                   intents=city_intents)
            dest = (root / EV_CHARGING / f"{city}.html" if pg == 1
                    else root / EV_CHARGING / city / f"page-{pg}.html")
            _write(dest, html)
            written["cities"] += 1
            if ok:
                url = (f"{config.SITE_URL}/{EV_CHARGING}/{city}" if pg == 1
                       else f"{config.SITE_URL}/{EV_CHARGING}/{city}/page-{pg}")
                indexable_urls.append(url)

        for intent in city_intents:
            _write(root / EV_CHARGING / city / f"{intent}.html",
                   G.intent_page(city, intent, sts, days))
            written["intents"] += 1
            indexable_urls.append(f"{config.SITE_URL}/{EV_CHARGING}/{city}/{intent}")

        if not stations:
            continue
        for st in sts:
            html, ok = G.station_page(city, st, days)
            page = f"{slug(st['n'])}-{slug(st['id'])[-8:]}"
            _write(root / EV_CHARGER / city / f"{page}.html", html)
            written["stations"] += 1
            if ok:
                written["indexable"] += 1
                indexable_urls.append(f"{config.SITE_URL}/{EV_CHARGER}/{city}/{page}")
            else:
                written["noindex"] += 1

    _write(root / "sitemap-ev.xml", _sitemap(indexable_urls))
    written["sitemap_urls"] = len(indexable_urls)
    return written


def _sitemap(urls: list[str]) -> str:
    today = date.today().isoformat()
    body = "".join(
        f"<url><loc>{u}</loc><lastmod>{today}</lastmod>"
        f"<changefreq>daily</changefreq></url>" for u in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"{body}</urlset>\n")


def clean() -> dict:
    """Remove everything the generator owns. Nothing else is touched."""
    root = config.SITE_ROOT
    removed = 0
    for p in (root / EV_CHARGER, root / EV_CHARGING):
        if p.exists():
            removed += sum(1 for _ in p.rglob("*.html"))
            shutil.rmtree(p)
    for f in (root / f"{EV_CHARGING}.html", root / "sitemap-ev.xml"):
        if f.exists():
            f.unlink()
            removed += 1
    return {"removed": removed}
