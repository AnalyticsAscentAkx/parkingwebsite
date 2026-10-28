#!/usr/bin/env python3
"""Collect ParkBee's Dutch garages and match them to our garage pages.

ParkBee has no public per-garage URL: a garage is booked from one of its
"poi" or "area" landing pages, and each of those pages embeds the records of
the garages near it (id, name, coordinates, address, height, EV spots). This
reads those pages from ParkBee's own sitemap (robots.txt allows everything),
keeps every garage once, and gives each the landing page where it is listed
first, which is the page a driver would book it from.

Then each ParkBee garage is matched to the nearest garage in
scripts/garages.json within MATCH_M metres.

Polite and rerunnable: pages are cached in scripts/parkbee/cache/, at most
4 requests in flight, backs off on 429. Delete the cache to refresh.

Usage:
    python3 scripts/parkbee/collect.py           # crawl (cached) + match
    python3 scripts/parkbee/collect.py --offline # match from cache only
"""
import argparse
import gzip
import hashlib
import json
import math
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CACHE = HERE / "cache"
UA = "Mozilla/5.0 (compatible; parkingnetherlands.com garage matcher)"
SITEMAP = "https://parkbee.com/sitemap.xml"
WORKERS = 4
MATCH_M = 120          # a ParkBee pin and an RDW garage pin for the same entrance


def fetch(url, offline=False):
    CACHE.mkdir(exist_ok=True)
    f = CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".html")
    if f.exists():
        return f.read_text(errors="replace")
    if offline:
        return ""
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
            text = body.decode("utf-8", errors="replace")
            f.write_text(text)
            time.sleep(0.5)
            return text
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(10 * (attempt + 1))
                continue
            if e.code == 404:
                f.write_text("")
                return ""
            time.sleep(2 * (attempt + 1))
        except Exception:
            time.sleep(2 * (attempt + 1))
    return ""


def landing_pages(offline):
    xml = fetch(SITEMAP, offline)
    urls = re.findall(r"<loc>([^<]+)</loc>", xml)
    # English pages only (the nl/fr/de copies list the same garages); Dutch cities only.
    keep = [u for u in urls
            if re.match(r"https://parkbee\.com/en/city/[^/]+/(poi|area)/", u)
            and not re.search(r"/city/(london|brussel|bruxelles|antwerpen|gent)", u)]
    return sorted(set(keep))


def garages_in(html):
    html = html.replace("\\u002F", "/")
    dec = json.JSONDecoder()
    out = []
    for m in re.finditer(r'\{"garageId":"', html):
        try:
            obj, _ = dec.raw_decode(html, m.start())
        except ValueError:
            continue
        if obj.get("countryCode") == "NL" and obj.get("latitude"):
            out.append(obj)
    return out


def metres(a_lat, a_lon, b_lat, b_lon):
    k = math.pi / 180
    x = (b_lon - a_lon) * k * math.cos((a_lat + b_lat) * k / 2)
    y = (b_lat - a_lat) * k
    return 6371000 * math.hypot(x, y)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    pages = landing_pages(args.offline)
    with ThreadPoolExecutor(WORKERS) as ex:
        htmls = list(ex.map(lambda u: fetch(u, args.offline), pages))

    pb = {}
    for url, html in zip(pages, htmls):
        for pos, g in enumerate(garages_in(html)):
            gid = g["garageId"]
            rec = pb.setdefault(gid, {
                "id": gid, "name": g.get("name"), "lat": g["latitude"], "lon": g["longitude"],
                "address": g.get("streetAddress"), "postcode": g.get("postalCode"),
                "city": g.get("city"), "state": g.get("state"),
                "max_height_m": g.get("maximumHeadSpaceInMeters"),
                "ev_spots": g.get("evChargingSpots"), "prebook": g.get("prepaidAllowed"),
                "url": url, "pos": pos})
            # A garage also shows up on pages for other towns nearby; the page
            # in its own city is the one to book from, then the earliest slot.
            city = re.sub(r"[^a-z]+", "-", (g.get("city") or "").lower()).strip("-")
            rank = (f"/city/{city}/" not in url, pos)
            if "rank" not in rec or rank < rec["rank"]:
                rec["url"], rec["pos"], rec["rank"] = url, pos, rank
    for g in pb.values():
        g.pop("rank", None)
    live = [g for g in pb.values() if g["state"] == "Live"]

    ours = json.loads((ROOT / "scripts" / "garages.json").read_text())
    matches = []
    for g in live:
        best = min(ours, key=lambda o: metres(g["lat"], g["lon"], o["lat"], o["lng"]))
        d = metres(g["lat"], g["lon"], best["lat"], best["lng"])
        if d <= MATCH_M:
            matches.append({"slug": best["slug"], "our_name": best["name"], "parkbee_id": g["id"],
                            "parkbee_name": g["name"], "metres": round(d), "url": g["url"]})

    (HERE / "parkbee_garages.json").write_text(json.dumps(sorted(live, key=lambda g: (g["city"] or "", g["name"] or "")), indent=1, ensure_ascii=False))
    (HERE / "matches.json").write_text(json.dumps(sorted(matches, key=lambda m: m["metres"]), indent=1, ensure_ascii=False))
    by_city = {}
    for g in live:
        by_city[g["city"]] = by_city.get(g["city"], 0) + 1
    print(f"{len(pages)} landing pages, {len(pb)} garages ({len(live)} live), "
          f"{len(matches)} matched to our {len(ours)} garages within {MATCH_M} m")
    print("live by city:", dict(sorted(by_city.items(), key=lambda kv: -kv[1])[:12]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
