#!/usr/bin/env python3
"""
RDW parking data sync — rebuilds garage dataset with official tariffs.

Joins RDW open data (opendata.rdw.nl, CC0):
  GEBIED (adw6-9hsg)            area names
  GEBIED REGELING (qtex-qwd8)   area -> regulation (+ usage type)
  GEOMETRIE GEBIED (nsk3-v9n7)  area -> WKT point
  SPECIFICATIES (b3us-f26s)     capacity, EV points, max height
  TIJDVAK (ixf8-gtwq)           regulation -> fare calculation per day/time
  TARIEFDEEL (534e-5vdg)        fare calculation -> stepped fare parts

Outputs:
  ../rdw-data.js        website data file (map + search consume this)
  garages.json          full dataset for the garage page generator

Usage: python3 rdw_tariff_sync.py
"""
import json
import math
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = "https://opendata.rdw.nl/resource/{}.json"
TODAY = datetime.now().strftime("%Y%m%d")

# municipality code (areamanagerid) -> city slug on the site
CITIES = {
    "363": "amsterdam",
    "599": "rotterdam",
    "518": "the-hague",
    "344": "utrecht",
    "772": "eindhoven",
    "14":  "groningen",
    "935": "maastricht",
    "546": "leiden",
    "392": "haarlem",
    "394": "haarlem",      # Haarlemmermeer (Hoofddorp / near Schiphol)
    "758": "breda",
    "503": "delft",
    "268": "nijmegen",
    "855": "tilburg",
    "193": "zwolle",
}
# usage types we publish (garages, parking lots, P+R) — street zones excluded
USAGE_OK = {"GARAGEP", "TERREINP", "PARKRIDE", "PR"}

CITY_NAMES = {
    "amsterdam": "Amsterdam", "rotterdam": "Rotterdam", "the-hague": "The Hague",
    "utrecht": "Utrecht", "eindhoven": "Eindhoven", "groningen": "Groningen",
    "maastricht": "Maastricht", "leiden": "Leiden", "haarlem": "Haarlem",
    "breda": "Breda", "delft": "Delft", "nijmegen": "Nijmegen",
    "tilburg": "Tilburg", "zwolle": "Zwolle",
}


def fetch(dataset, **params):
    params.setdefault("$limit", 50000)
    url = BASE.format(dataset) + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "parkingnetherlands.com data sync"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def active(row, end_field, fmt_len=8):
    end = (row.get(end_field) or "29991231")[:fmt_len]
    return end >= TODAY


def clean_name(desc):
    name = desc.replace("�", "é").strip()
    return name


def slugify(name, city):
    s = re.sub(r"\s*\((.*?)\)\s*$", "", name)          # drop trailing "(Amsterdam)"
    s = re.sub(r"^(Garage|Parkeergarage|Parkeerterrein|Parking|Terrein)\s+", "", s, flags=re.I)
    s = s.lower()
    s = s.replace("é", "e").replace("ë", "e").replace("ü", "u").replace("ö", "o")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return f"{s}-{city}"


def fare_cost(parts, minutes):
    """Cost in EUR for a stay of `minutes` under a sorted list of fare parts."""
    total = 0.0
    for p in parts:
        start = float(p["startdurationfarepart"])
        end = float(p["enddurationfarepart"])
        step = max(float(p.get("stepsizefarepart") or 1), 1)
        amount = float(p["amountfarepart"])
        if minutes <= start:
            break
        covered = min(minutes, end) - start
        if covered > 0:
            total += math.ceil(covered / step) * amount
    return round(total, 2)


NPR_CITY = {  # "(City)" suffix in facility names -> our slug
    "amsterdam": "amsterdam", "rotterdam": "rotterdam",
    "den haag": "the-hague", "'s-gravenhage": "the-hague",
    "utrecht": "utrecht", "eindhoven": "eindhoven", "groningen": "groningen",
    "maastricht": "maastricht", "leiden": "leiden", "haarlem": "haarlem",
    "breda": "breda", "delft": "delft", "nijmegen": "nijmegen",
    "tilburg": "tilburg", "zwolle": "zwolle",
}


def npr_cost_fn(tariffs):
    """Build a cost(minutes) function from NPR intervalRates, or None."""
    import time as _t
    now = _t.time()
    best = None
    for t in tariffs:
        end = t.get("endOfPeriod")
        if end and end < now:
            continue
        days = t.get("validityDays") or []
        score = 2 if ("Wed" in days or not days) else 1
        rates = [r for r in (t.get("intervalRates") or [])
                 if not r.get("validityEndOfPeriod") or r["validityEndOfPeriod"] > now]
        if not rates:
            continue
        if best is None or score > best[0]:
            best = (score, rates)
    if not best:
        return None
    rates = sorted(best[1], key=lambda r: r.get("durationFrom") or 0)

    def cost(mins):
        total = 0.0
        for r in rates:
            if r.get("durationType") != "Minutes":
                return None
            frm = r.get("durationFrom") or 0
            until = r.get("durationUntil")
            until = float("inf") if until in (-1, None) else until
            if mins <= frm:
                break
            covered = min(mins, until) - frm
            per = r.get("chargePeriod") or 60
            total += math.ceil(covered / per) * (r.get("charge") or 0)
        return round(total, 2)
    return cost


def add_npr_dynamic(garages):
    """Merge facilities from npropendata.rdw.nl (dynamic parking register)."""
    import time
    url = "https://npropendata.rdw.nl/parkingdata/v2/"
    req = urllib.request.Request(url, headers={"User-Agent": "parkingnetherlands.com data sync"})
    with urllib.request.urlopen(req, timeout=60) as r:
        index = json.load(r)["ParkingFacilities"]

    def city_of(name):
        m = re.search(r"\(([^)]+)\)\s*$", name)
        if not m:
            return None
        return NPR_CITY.get(m.group(1).strip().lower())

    todo = [f for f in index if city_of(f.get("name", ""))]
    print(f"[npr] {len(todo)} facilities match covered cities; fetching static data…")

    existing = [(g["lat"], g["lng"], g["name"].lower()) for g in garages.values()]
    added = 0
    for f in todo:
        city = city_of(f["name"])
        try:
            req = urllib.request.Request(f["staticDataUrl"], headers={"User-Agent": "parkingnetherlands.com data sync"})
            with urllib.request.urlopen(req, timeout=30) as r:
                info = json.load(r).get("parkingFacilityInformation", {})
        except Exception:
            continue
        time.sleep(0.03)

        name = clean_name(info.get("name") or f["name"])
        # skip street parking / permit areas
        if re.search(r"straatparkeren|vergunning|belanghebbenden", name, re.I):
            continue
        aps = info.get("accessPoints") or []
        loc = None
        for ap in aps:
            locs = ap.get("accessPointLocation") or []
            l = locs[0] if isinstance(locs, list) and locs else (locs if isinstance(locs, dict) else {})
            if l.get("latitude"):
                loc = (float(l["latitude"]), float(l["longitude"]))
                break
        if not loc or not (50.5 < loc[0] < 53.6 and 3.2 < loc[1] < 7.3):
            continue
        # dedupe against register areas and prior npr entries (<120 m or same name)
        nrm = re.sub(r"[^a-z0-9]", "", name.lower())
        dup = False
        for lat, lng, ename in existing:
            if abs(lat - loc[0]) < 0.0012 and abs(lng - loc[1]) < 0.0018:
                dup = True; break
            if nrm and nrm == re.sub(r"[^a-z0-9]", "", ename):
                dup = True; break
        if dup:
            continue

        specs = (info.get("specifications") or [{}])[0]
        cap = specs.get("capacity")
        ev = specs.get("chargingPointCapacity")
        op = info.get("operator") or {}
        op_url = (op.get("url") or "").strip()
        if op_url and not op_url.startswith("http"):
            op_url = "https://" + op_url
        rec = {
            "areaid": "NPR_" + f["identifier"][:8],
            "amid": "npr",
            "city": city,
            "name": name if name.endswith(")") else f"{name} ({CITY_NAMES[city]})",
            "slug": slugify(name, city),
            "lat": round(loc[0], 6),
            "lng": round(loc[1], 6),
            "capacity": int(cap) if cap else None,
            "ev_points": int(ev) if ev else None,
            "max_height_cm": None,
            "regulations": [],
            "is_pr": bool(re.search(r"p\+r", name, re.I)),
        }
        if op.get("name"):
            rec["op"] = op["name"].strip()
        if op_url:
            rec["op_url"] = op_url
        cost = npr_cost_fn(info.get("tariffs") or [])
        if cost:
            h1, h3, d1 = cost(60), cost(180), cost(1440)
            if h1 is not None and 0 <= h1 <= 15 and d1 is not None:
                rec["rate_hr"], rec["rate_3h"], rec["rate_day"] = h1, h3, d1
        garages[rec["areaid"]] = rec
        existing.append((rec["lat"], rec["lng"], rec["name"].lower()))
        added += 1
    print(f"[npr] added {added} new facilities from the dynamic register")


def main():
    site_dir = Path(__file__).resolve().parent.parent
    garages = {}   # areaid -> record

    # entrance GPS coordinates (global dataset, joined via IN-UITGANG below)
    gps_by_ref = {}
    for row in fetch("k3dr-ge3w", locationreferencetype="I-O"):
        end = (row.get("enddatelocation") or "29991231")[:8]
        if end >= TODAY:
            gps_by_ref[row["locationreference"]] = (float(row["latitude"]), float(row["longitude"]))

    # coordinates from the previous dataset build, used as last-resort fallback
    legacy_file = Path(__file__).resolve().parent / "legacy-coords.json"
    legacy = json.loads(legacy_file.read_text()) if legacy_file.exists() else {}

    for amid, city in CITIES.items():
        try:
            areas = fetch("adw6-9hsg", areamanagerid=amid)
            regs = fetch("qtex-qwd8", areamanagerid=amid)
            geo = fetch("nsk3-v9n7", areamanagerid=amid)
            specs = fetch("b3us-f26s", areamanagerid=amid)
            gates = fetch("c653-u9z2", areamanagerid=amid)
        except Exception as e:
            print(f"[warn] fetch failed for {amid}: {e}", file=sys.stderr)
            continue

        gate_coord = {}
        for gt in gates:
            ref = gt.get("entranceexitid")
            if ref in gps_by_ref and gt["areaid"] not in gate_coord:
                gate_coord[gt["areaid"]] = gps_by_ref[ref]

        desc_by_area = {a["areaid"]: a.get("areadesc", "") for a in areas
                        if active(a, "enddatearea")}
        geo_by_area = {}
        for g in geo:
            end = (g.get("enddatearea") or "2999")[:4]
            if end < TODAY[:4]:
                continue
            coords = re.findall(r"(\d+\.\d+) (\d+\.\d+)", g.get("areageometryastext", ""))
            if coords:
                lngs = [float(c[0]) for c in coords]
                lats = [float(c[1]) for c in coords]
                geo_by_area[g["areaid"]] = (sum(lats) / len(lats), sum(lngs) / len(lngs))
        spec_by_area = {s["areaid"]: s for s in specs}

        garage_name = re.compile(r"(garage|parkeergarage|parkeerterrein|p\+r|parkeren .*terrein|parking)", re.I)
        reg_by_area = {}
        for r in regs:
            if not active(r, "enddatearearegulation"):
                continue
            desc = desc_by_area.get(r["areaid"], "")
            if r.get("usageid") not in USAGE_OK and not garage_name.search(desc):
                continue
            reg_by_area.setdefault(r["areaid"], []).append(r["regulationid"])

        for areaid, regids in reg_by_area.items():
            desc = desc_by_area.get(areaid)
            latlng = geo_by_area.get(areaid) or gate_coord.get(areaid) or \
                (tuple(legacy[areaid]) if areaid in legacy else None)
            if not desc or not latlng:
                continue
            name = clean_name(desc)
            spec = spec_by_area.get(areaid, {})
            garages[areaid] = {
                "areaid": areaid,
                "amid": amid,
                "city": city,
                "name": name,
                "slug": slugify(name, city),
                "lat": round(latlng[0], 6),
                "lng": round(latlng[1], 6),
                "capacity": int(spec["capacity"]) if spec.get("capacity") else None,
                "ev_points": int(spec["chargingpointcapacity"]) if spec.get("chargingpointcapacity") else None,
                "max_height_cm": int(spec["maximumvehicleheight"]) if spec.get("maximumvehicleheight") and spec["maximumvehicleheight"] != "0" else None,
                "regulations": regids,
                "is_pr": "P+R" in name or "P+r" in name,
            }
        print(f"[ok] {CITY_NAMES[city]:12s} ({amid}): {len(reg_by_area)} candidate areas")

    # tariffs: one fetch per areamanagerid for TIJDVAK + TARIEFDEEL
    for amid in sorted({g["amid"] for g in garages.values()}):
        try:
            frames = fetch("ixf8-gtwq", areamanagerid=amid)
            parts = fetch("534e-5vdg", areamanagerid=amid)
        except Exception as e:
            print(f"[warn] tariff fetch failed for {amid}: {e}", file=sys.stderr)
            continue

        parts_by_code = {}
        for p in parts:
            if not active(p, "enddatefarepart"):
                continue
            parts_by_code.setdefault(p["farecalculationcode"], []).append(p)
        for code in parts_by_code:
            parts_by_code[code].sort(key=lambda p: float(p["startdurationfarepart"]))

        # regulation -> farecalculationcode for a typical weekday afternoon
        code_by_reg = {}
        for f in frames:
            if not active(f, "enddatetimeframe"):
                continue
            day = f.get("daytimeframe", "")
            code = f.get("farecalculationcode")
            if not code:
                continue
            start = int(f.get("starttimetimeframe") or 0)
            end = int(f.get("endtimetimeframe") or 2400)
            covers_afternoon = start <= 1400 <= end
            key = f["regulationid"]
            if day == "WOENSDAG" and covers_afternoon:
                code_by_reg[key] = code            # prefer explicit Wednesday
            elif key not in code_by_reg and covers_afternoon:
                code_by_reg[key] = code

        for g in garages.values():
            if g["amid"] != amid or "rate_hr" in g:
                continue
            for regid in g["regulations"]:
                code = code_by_reg.get(regid)
                if code and code in parts_by_code:
                    fp = parts_by_code[code]
                    g["rate_hr"] = fare_cost(fp, 60)
                    g["rate_3h"] = fare_cost(fp, 180)
                    g["rate_day"] = fare_cost(fp, 1440)
                    break

    # --- national dynamic parking register (npropendata.rdw.nl) ---
    # gemeente-published facilities incl. commercial operators missing from NPR areas
    try:
        add_npr_dynamic(garages)
    except Exception as e:
        print(f"[warn] npropendata sync failed: {e}", file=sys.stderr)

    # same garage can appear under several register areas (e.g. day-card variants);
    # keep the record with tariff data, or the richer one
    by_slug = {}
    for g in garages.values():
        cur = by_slug.get(g["slug"])
        if cur is None:
            by_slug[g["slug"]] = g
        else:
            score = lambda x: (x.get("rate_hr") is not None, x.get("capacity") is not None)
            if score(g) > score(cur):
                by_slug[g["slug"]] = g
    result = list(by_slug.values())
    with_tariff = sum(1 for g in result if g.get("rate_hr") is not None)
    print(f"\n{len(result)} garages, {with_tariff} with official tariffs")

    # --- garages.json (generator input) ---
    result.sort(key=lambda g: (g["city"], g["name"]))
    (site_dir / "scripts" / "garages.json").write_text(
        json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")

    # --- rdw-data.js (website payload) ---
    by_city = {}
    for g in result:
        rec = {"name": g["name"], "slug": g["slug"], "lat": g["lat"], "lng": g["lng"]}
        for k in ("capacity", "ev_points", "max_height_cm", "rate_hr", "rate_3h", "rate_day", "op", "op_url"):
            if g.get(k) is not None:
                rec[k] = g[k]
        if g["is_pr"]:
            rec["pr"] = 1
        by_city.setdefault(g["city"], []).append(rec)

    js = (
        "// RDW Official Parking Data — opendata.rdw.nl (CC0, Nederlandse overheid)\n"
        f"// Generated by scripts/rdw_tariff_sync.py on {datetime.now():%Y-%m-%d}\n"
        "// rate_hr / rate_3h / rate_day = official NPR tariff for 1h / 3h / 24h stay (EUR)\n"
        "const RDW_DATA = " + json.dumps(by_city, ensure_ascii=False) + ";\n"
        + ADD_MARKERS_JS
    )
    (site_dir / "rdw-data.js").write_text(js, encoding="utf-8")
    print("wrote rdw-data.js and scripts/garages.json")


ADD_MARKERS_JS = r"""
function rdwPrice(g){
  if(g.rate_hr==null) return '';
  if(g.rate_hr===0 && g.rate_day===0) return '<div style="font-size:13px;color:#059669;font-weight:600">Free parking</div>';
  return '<div style="font-size:13px;color:#0f172a"><strong>€'+g.rate_hr.toFixed(2)+'</strong>/hr · €'+(g.rate_day!=null?g.rate_day.toFixed(2):'—')+'/day</div>';
}
function addRDWMarkers(map, citySlug) {
    const garages = RDW_DATA[citySlug] || [];
    const markers = [];
    garages.forEach(g => {
        const m = L.marker([g.lat, g.lng], {
            icon: L.divIcon({
                html: `<svg xmlns="http://www.w3.org/2000/svg" width="26" height="34" viewBox="0 0 26 34"><path d="M13 0C5.8 0 0 5.8 0 13c0 9.75 13 21 13 21s13-11.25 13-21C26 5.8 20.2 0 13 0z" fill="${g.pr?'#0891B2':'#6366F1'}" opacity="0.85"/><circle cx="13" cy="12" r="6.5" fill="white" opacity="0.95"/><text x="13" y="16" text-anchor="middle" font-size="8" font-weight="bold" fill="${g.pr?'#0891B2':'#6366F1'}" font-family="sans-serif">P</text></svg>`,
                iconSize:[26,34],iconAnchor:[13,34],popupAnchor:[0,-36],className:''
            })
        }).addTo(map);
        m.bindPopup(`<div style="font-family:sans-serif;min-width:180px;padding:4px"><div style="font-size:14px;font-weight:600;color:#0f172a;margin-bottom:4px">${g.name}</div>${rdwPrice(g)}<div style="font-size:11px;color:#94a3b8;margin-top:4px">Official RDW data (opendata.rdw.nl)</div><a href="/garage/${g.slug}" style="display:block;margin-top:8px;font-size:12px;font-weight:600;color:#2337C6;text-decoration:none">Garage details →</a></div>`);
        markers.push(m);
    });
    return markers;
}
"""

if __name__ == "__main__":
    main()
