#!/usr/bin/env python3
"""Add opening behaviour to the garage data: can you get your car out, and when can you get in.

Two RDW tables that nobody surfaces, joined onto the garages we already have.

  figd-gux7  PARKING OPEN     exitpossibleallday, openallyear
  edv8-qiyg  PARKING TOEGANG  per-day entry windows

`exitpossibleallday` is the one that matters. Where it is 0 the barrier does
not open outside the garage's hours, so a car parked late is a car you collect
tomorrow. Measured on the current data that is 12 of 169 matched garages, 7%:
frequent enough to be worth warning about, rare enough that the warning still
carries information. A flag that fires on everything is wallpaper.

Coverage is partial and that is stated rather than hidden. Of 323 garages, 203
carry a real RDW area manager id (the rest are NPR-derived and have no
counterpart in these tables), and 169 of those match. Anything unmatched gets
no claim at all, because "we do not know" and "you can leave whenever" must not
look the same on a page.

Usage:
  python3 enrich_access.py            # update scripts/garages.json in place
  python3 enrich_access.py --dry-run
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
GARAGES = REPO / "scripts" / "garages.json"
UA = "parkingnetherlands-research (+https://parkingnetherlands.com/about)"

OPEN_DS = "figd-gux7"     # PARKING OPEN
ACCESS_DS = "edv8-qiyg"   # PARKING TOEGANG

DAY_ORDER = ["MAANDAG", "DINSDAG", "WOENSDAG", "DONDERDAG",
             "VRIJDAG", "ZATERDAG", "ZONDAG"]
DAY_EN = {"MAANDAG": "Mon", "DINSDAG": "Tue", "WOENSDAG": "Wed",
          "DONDERDAG": "Thu", "VRIJDAG": "Fri", "ZATERDAG": "Sat",
          "ZONDAG": "Sun"}


def rdw(dataset, limit=50000):
    url = f"https://opendata.rdw.nl/resource/{dataset}.json?$limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def newest_per_area(rows, stamp_field):
    """These tables are append-only: one row per change, keyed by start date.
    Taking the max start date gives the record in force today."""
    out = {}
    for r in rows:
        k = (r.get("areamanagerid"), r.get("areaid"))
        if k[0] is None or k[1] is None:
            continue
        if k not in out or (r.get(stamp_field) or "") > (out[k].get(stamp_field) or ""):
            out[k] = r
    return out


def hhmm(v):
    """RDW writes entry times as an integer like 500 or 2200, meaning 05:00
    and 22:00. 2400 is a real value and means midnight, not an error."""
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    if n < 0 or n > 2400:
        return None
    return f"{n // 100:02d}:{n % 100:02d}"


def entry_windows(rows):
    """Collapse the per-day rows into {DAY: 'hh:mm-hh:mm'}, dropping days that
    are open around the clock since those carry no warning."""
    by = {}
    for r in rows:
        d = (r.get("days") or "").upper()
        a, b = hhmm(r.get("enterfrom")), hhmm(r.get("enteruntil"))
        if d not in DAY_EN or not a or not b:
            continue
        if a == "00:00" and b in ("24:00", "00:00"):
            continue
        by[d] = f"{a}-{b}"
    return by


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    garages = json.loads(GARAGES.read_text())
    by_key = {(str(g["amid"]), str(g["areaid"])): g for g in garages}
    register_ids = {k for k in by_key if k[0] != "npr"}

    print(f"garages: {len(garages)}, with an RDW area manager id: {len(register_ids)}")
    print("fetching PARKING OPEN ...", flush=True)
    opens = newest_per_area(rdw(OPEN_DS), "startofperiod")
    print("fetching PARKING TOEGANG ...", flush=True)
    access_rows = rdw(ACCESS_DS)

    grouped = {}
    for r in access_rows:
        k = (r.get("areamanagerid"), r.get("areaid"))
        grouped.setdefault(k, []).append(r)

    stats = {"exit_known": 0, "locked": 0, "year_known": 0,
             "seasonal": 0, "entry": 0}
    for k, g in by_key.items():
        # Clear any previous enrichment so a removed upstream record does not
        # leave a stale claim on the page.
        for f in ("exit_any_time", "open_all_year", "entry_hours"):
            g.pop(f, None)
        o = opens.get(k)
        if o:
            if o.get("exitpossibleallday") in ("0", "1"):
                g["exit_any_time"] = o["exitpossibleallday"] == "1"
                stats["exit_known"] += 1
                stats["locked"] += not g["exit_any_time"]
            if o.get("openallyear") in ("0", "1"):
                g["open_all_year"] = o["openallyear"] == "1"
                stats["year_known"] += 1
                stats["seasonal"] += not g["open_all_year"]
        w = entry_windows(grouped.get(k, []))
        if w:
            g["entry_hours"] = {DAY_EN[d]: w[d] for d in DAY_ORDER if d in w}
            stats["entry"] += 1

    print(f"\n  exit behaviour known for : {stats['exit_known']} garages")
    print(f"    cannot exit at any hour: {stats['locked']}")
    print(f"  open-all-year known for  : {stats['year_known']}")
    print(f"    closed part of the year: {stats['seasonal']}")
    print(f"  entry hours published    : {stats['entry']}")

    if a.dry_run:
        print("\ndry run, nothing written")
        return 0
    GARAGES.write_text(json.dumps(garages, ensure_ascii=False, indent=1))
    print(f"\n-> {GARAGES}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
