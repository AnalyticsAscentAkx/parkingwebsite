#!/usr/bin/env python3
"""Put a Google Maps and Apple Maps link on every P+R card.

Garage detail pages already carry directions links, 323 of 324 of them. The
P+R cards on city pages carried none, on 24 pages, which is the one place a
visitor has decided where to park and has nowhere to go next. Asked for by
the owner on 2026-10-19: "i want it on everything, so people can directly go
from here to google and apple etc maps".

Coordinates come from rdw-data.js, the national parking register export that
already ships with the site, matched on the card's own name. Nothing is
invented: a card whose name cannot be matched is left exactly as it was,
because a directions link to the wrong car park is worse than no link.

The link format matches the one the charger map already uses, so the whole
site hands over the same way:
    Google  https://www.google.com/maps/dir/?api=1&destination=LAT,LNG
    Apple   https://maps.apple.com/?daddr=LAT,LNG&dirflg=d

Idempotent: a card that already has a link row is skipped, so the daily job
can run this as often as it likes.

    python3 scripts/seo/map_links.py            # write
    python3 scripts/seo/map_links.py --dry-run  # report only
"""
import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "rdw-data.js"
MARKER = "pk-go"


def load_places():
    """Every car park in the register export, by city, lowercased for matching."""
    text = DATA.read_text("utf-8")
    i = text.find("{")
    depth = 0
    for j, ch in enumerate(text[i:], i):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                break
    raw = json.loads(text[i:j + 1])
    out = []
    for city, rows in raw.items():
        for g in rows:
            if g.get("lat") is None or g.get("lng") is None:
                continue
            out.append({"city": city, "name": g["name"], "lat": g["lat"], "lng": g["lng"],
                        "key": norm(g["name"])})
    return out


def norm(s):
    """Strip the decoration so 'P+R ArenA (Amsterdam)' meets 'P+R Arena'."""
    s = s.lower()
    s = re.sub(r"\(.*?\)", " ", s)                  # trailing "(Amsterdam)"
    s = s.replace("p&r", "pr").replace("p+r", "pr")
    s = re.sub(r"\b(parkeergarage|garage|parking)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def match(card_name, places, city_hint):
    """The register entry this card means, or None. Prefers the page's own city."""
    want = norm(card_name)
    if not want:
        return None
    pool = [p for p in places if p["city"] == city_hint] or places
    exact = [p for p in pool if p["key"] == want]
    if exact:
        return exact[0]
    # a card called "pr zeeburg" should take "pr zeeburg", never "pr zeeburg iii"
    starts = sorted([p for p in pool if p["key"].startswith(want + " ") or p["key"] == want],
                    key=lambda p: len(p["key"]))
    if starts:
        return starts[0]
    contains = sorted([p for p in pool if want in p["key"]], key=lambda p: len(p["key"]))
    if contains and len(want) >= 6:
        return contains[0]
    return None


# Cities the pages are about, longest first so "den haag" beats "haag".
CITIES = ["den haag", "the hague", "s hertogenbosch", "amsterdam", "rotterdam", "utrecht",
          "eindhoven", "groningen", "maastricht", "nijmegen", "haarlem", "tilburg",
          "arnhem", "breda", "delft", "leiden", "zwolle", "schiphol", "almere"]


def city_of(path, html):
    """The city a page is about, for a search fallback. '' when unsure."""
    stem = path.stem.lower().replace("-", " ")
    for c in sorted(CITIES, key=len, reverse=True):
        if c in stem:
            return c
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    if m:
        h = re.sub(r"<[^>]+>", " ", m.group(1)).lower()
        for c in sorted(CITIES, key=len, reverse=True):
            if c in h:
                return c
    return ""


def links_html(place=None, search=None):
    """A directions link when we know where it is, a search link when we only
    know what it is called. Never a link for a card that is not a place."""
    if place:
        g = f"https://www.google.com/maps/dir/?api=1&destination={place['lat']},{place['lng']}"
        a = f"https://maps.apple.com/?daddr={place['lat']},{place['lng']}&dirflg=d"
        name, verb = place["name"], "Directions to"
    else:
        q = quote_plus(search)
        g = f"https://www.google.com/maps/search/?api=1&query={q}"
        a = f"https://maps.apple.com/?q={q}"
        name, verb = search, "Find"
    return (f'<div class="{MARKER}">'
            f'<a href="{g}" target="_blank" rel="noopener" '
            f'aria-label="{verb} {name} in Google Maps">Google Maps</a>'
            f'<a href="{a}" target="_blank" rel="noopener" '
            f'aria-label="{verb} {name} in Apple Maps">Apple Maps</a>'
            f'</div>')


CARD_OPEN = re.compile(r'<div class="pk(?:\s[^"]*)?">')   # not pk-n, pk-r, pk-d
NAME = re.compile(r'<div class="pk-n">(.*?)</div>', re.S)
DIV = re.compile(r"<div\b|</div>", re.I)


def div_end(html, start):
    """Index of the </div> that closes the <div> opening at `start`.

    Sibling elements inside a card are also class="pk-something", so a naive
    search for the next "pk" lands inside the card it is trying to measure.
    Count the nesting instead.
    """
    depth = 0
    for m in DIV.finditer(html, start):
        if m.group(0).lower().startswith("</"):
            depth -= 1
            if depth == 0:
                return m.start()
        else:
            depth += 1
    return -1


def process(path, places, dry):
    html = path.read_text("utf-8")
    if '<div class="pk' not in html:
        return 0, 0
    city_hint = path.stem.lower().replace("-", " ").split()[0]
    city = city_of(path, html)
    inserts = []
    added = skipped = 0
    for om in CARD_OPEN.finditer(html):
        close = div_end(html, om.start())
        if close < 0:
            continue
        card = html[om.start():close]
        nm = NAME.search(card)
        if not nm:
            continue
        if MARKER in card:
            skipped += 1
            continue
        name = re.sub(r"<[^>]+>", "", nm.group(1)).strip()
        place = match(name, places, city_hint)
        if place:
            inserts.append((close, links_html(place=place)))
            added += 1
            continue
        # No coordinates. Only fall back to a map SEARCH when the card names a
        # specific park-and-ride site, which the "pr" token identifies after
        # normalisation. Cards that are really a city ("Breda") or a
        # commercial option ("Off-Site Parking") get nothing, because a link
        # to the wrong place is worse than no link.
        if "pr" in norm(name).split() and city:
            inserts.append((close, links_html(search=f"{name} {city}")))
            added += 1
            continue
        skipped += 1
    if added and not dry:
        for at, frag in sorted(inserts, reverse=True):
            html = html[:at] + frag + html[at:]
        path.write_text(html, "utf-8")
    return added, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    places = load_places()
    total_a = total_s = pages = 0
    for p in sorted(ROOT.rglob("*.html")):
        if any(x in p.parts for x in ("scripts", "node_modules", "outreach", "embed")):
            continue
        added, skipped = process(p, places, a.dry_run)
        if added or skipped:
            pages += 1
            total_a += added
            total_s += skipped
            if added:
                print(f"  {p.relative_to(ROOT)}: +{added} link rows"
                      + (f", {skipped} unmatched" if skipped else ""))
    verb = "would add" if a.dry_run else "added"
    print(f"map_links: {verb} {total_a} link rows across {pages} pages, "
          f"{total_s} cards left alone")
    return 0


if __name__ == "__main__":
    sys.exit(main())
