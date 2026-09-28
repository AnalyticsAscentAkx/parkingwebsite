"""RDW open parking data -> parking_area / parking_tariff.

Licence note, and it runs the opposite way to every other source here:
RDW publishes as CC-0, so commercial use and resale are fine, but the terms
forbid naming RDW as the source or using its logo. So nothing derived from
this loader may carry an RDW credit. CBS and NDW are the reverse and must be
credited. See config.ATTRIBUTION_NDW.

Dataset ids are imported from config, which takes them from the ids already
in scripts/rdw_tariff_sync.py so the two pipelines cannot drift apart.
"""
import datetime
import math
import re
import urllib.parse

import httpx

from . import config, db

# Only facility types the site publishes. Street zones are priced per-zone
# elsewhere and would double-count against garage tariffs.
USAGE_OK = {"GARAGEP", "TERREINP", "PARKRIDE", "PR"}

_TODAY = datetime.date.today().strftime("%Y%m%d")

# RDW names the day in Dutch, one row per day, rather than seven boolean columns.
_DAY_INDEX = {"MAANDAG": 1, "DINSDAG": 2, "WOENSDAG": 3, "DONDERDAG": 4,
              "VRIJDAG": 5, "ZATERDAG": 6, "ZONDAG": 7}


def _fetch(dataset: str, **params) -> list[dict]:
    """Socrata SODA read, paginated. $$app_token is optional and only raises
    the rate limit, so the loader works with no credentials at all."""
    params.setdefault("$limit", 50000)
    out, offset = [], 0
    while True:
        p = dict(params, **{"$offset": offset})
        if config.RDW_APP_TOKEN:
            p["$$app_token"] = config.RDW_APP_TOKEN
        url = config.RDW_BASE.format(dataset) + "?" + urllib.parse.urlencode(p)
        r = httpx.get(url, headers={"User-Agent": config.USER_AGENT}, timeout=120)
        r.raise_for_status()
        batch = r.json()
        out.extend(batch)
        if len(batch) < params["$limit"]:
            return out
        offset += params["$limit"]


def _wkt_point(wkt: str | None) -> tuple[float | None, float | None]:
    if not wkt:
        return None, None
    m = re.search(r"POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)\s*\)", wkt, re.I)
    return (float(m.group(2)), float(m.group(1))) if m else (None, None)


def _minutes(hhmm: str | None) -> int | None:
    """RDW time fields arrive as HHMM or HH:MM:SS depending on the dataset."""
    if not hhmm:
        return None
    s = str(hhmm).replace(":", "").strip()
    if not s.isdigit():
        return None
    s = s.zfill(4)[:4]
    return int(s[:2]) * 60 + int(s[2:])


def _active(row: dict, field: str) -> bool:
    """RDW keeps expired rows in place, so every join has to filter on the
    end date or a 2021 tariff will be priced as current."""
    return (row.get(field) or "29991231")[:8] >= _TODAY


def fare_cost(parts: list[dict], minutes: float) -> float:
    """Cost of a stay under RDW's stepped fare ladder.

    Fares are duration bands with a step size, not a flat hourly rate: the
    first 30 minutes can be free, the next hour charged per 20 minutes, and
    so on. Averaging that to one number misprices short stays badly, which is
    exactly the case a charging stop falls into.
    """
    total = 0.0
    for p in parts:
        start = float(p.get("startdurationfarepart") or 0)
        end = float(p.get("enddurationfarepart") or 999999)
        step = max(float(p.get("stepsizefarepart") or 1), 1)
        amount = float(p.get("amountfarepart") or 0)
        if minutes <= start:
            break
        covered = min(minutes, end) - start
        if covered > 0:
            total += math.ceil(covered / step) * amount
    return round(total, 2)


def load() -> dict:
    areas = _fetch(config.RDW["gebied"])
    regs = _fetch(config.RDW["gebied_regeling"])
    geoms = _fetch(config.RDW["geometrie"])
    specs = _fetch(config.RDW["specificaties"])
    tijdvak = _fetch(config.RDW["tijdvak"])
    tarief = _fetch(config.RDW["tariefdeel"])

    geo_by_area = {}
    for g in geoms:
        lat, lon = _wkt_point(g.get("areageometryastext") or g.get("areageometry"))
        if lat is not None:
            geo_by_area[g.get("areaid")] = (lat, lon)

    spec_by_area = {s.get("areaid"): s for s in specs}

    # area -> regulation. Both ids are scoped by the area manager, so the key
    # is the pair, never the code alone.
    usage_by_area, reg_by_area = {}, {}
    for r in regs:
        if not _active(r, "enddatearearegulation"):
            continue
        aid = r.get("areaid")
        if r.get("usageid"):
            usage_by_area[aid] = r["usageid"]
        if r.get("regulationid"):
            reg_by_area[aid] = (r.get("areamanagerid"), r["regulationid"])

    area_rows = []
    for a in areas:
        aid = a.get("areaid")
        usage = usage_by_area.get(aid, "")
        lat, lon = geo_by_area.get(aid, (None, None))
        spec = spec_by_area.get(aid, {})
        cap = spec.get("capacity") or spec.get("capacityev")
        name = (a.get("areadesc") or "").replace("\ufffd", "e").strip() or None
        area_rows.append((
            aid, None, None, usage not in USAGE_OK,
            int(cap) if cap and str(cap).isdigit() else None,
            lat, lon, name,
        ))
    db.upsert("parking_area",
              ["area_id", "geom", "city", "on_street", "capacity", "lat", "lon", "name"],
              ["area_id"], area_rows)

    # (manager, farecalculationcode) -> ordered fare ladder
    ladders: dict[tuple, list] = {}
    for t in tarief:
        if not _active(t, "enddatefarepart"):
            continue
        key = (t.get("areamanagerid"), t.get("farecalculationcode"))
        ladders.setdefault(key, []).append(t)
    for parts in ladders.values():
        parts.sort(key=lambda x: float(x.get("startdurationfarepart") or 0))

    # (manager, regulationid) -> the day/time windows it applies in
    by_reg: dict[tuple, list] = {}
    for tv in tijdvak:
        if not _active(tv, "enddatetimeframe"):
            continue
        by_reg.setdefault((tv.get("areamanagerid"), tv.get("regulationid")), []).append(tv)

    fare_rows, seen, seen_fare = [], {}, set()
    for aid, reg_key in reg_by_area.items():
        for tv in by_reg.get(reg_key, []):
            day = _DAY_INDEX.get((tv.get("daytimeframe") or "").strip().upper())
            if not day:
                continue
            start, end = _minutes(tv.get("starttimetimeframe")), _minutes(tv.get("endtimetimeframe"))
            if start is None or end is None or end <= start:
                continue
            code = tv.get("farecalculationcode")
            parts = ladders.get((tv.get("areamanagerid"), code)) or []
            if not parts:
                continue

            # An hourly figure for display, taken from the ladder rather than
            # invented, plus a day cap where the ladder actually flattens out.
            per_hour = fare_cost(parts, 60)
            day_max = fare_cost(parts, 1440)

            # A zone can publish several products for the same window: the
            # hourly tariff, a dagkaart, an avondkaart. The visitor pays the
            # cheapest one that covers the stay, and for a charging stop that
            # is the one with the lowest one-hour cost. Keep that ladder.
            k = (aid, day, start)
            prev = seen.get(k)
            if prev is None or per_hour < prev[4]:
                seen[k] = (aid, day, start, end, per_hour, day_max, code)

            fk = (aid, code)
            if fk not in seen_fare:
                seen_fare.add(fk)
                for p in parts:
                    fare_rows.append((
                        aid, code,
                        int(float(p.get("startdurationfarepart") or 0)),
                        int(float(p.get("enddurationfarepart") or 999999)),
                        int(float(p.get("stepsizefarepart") or 1)),
                        float(p.get("amountfarepart") or 0),
                    ))

    tariff_rows = list(seen.values())
    db.execute("TRUNCATE parking_tariff")
    db.upsert("parking_tariff",
              ["area_id", "day_of_week", "start_min", "end_min", "price_per_hour", "daily_max", "fare_code"],
              ["area_id", "day_of_week", "start_min"], tariff_rows)
    db.upsert("parking_fare_part",
              ["area_id", "fare_code", "start_min", "end_min", "step_min", "amount"],
              ["area_id", "fare_code", "start_min"], fare_rows)

    return {"areas": len(area_rows), "tariff_windows": len(tariff_rows),
            "fare_parts": len(fare_rows), "priced_areas": len({r[0] for r in tariff_rows})}


def link_stations(max_m: float = 400.0) -> dict:
    """Precompute the nearest parking area per charging station.

    This join is the whole point of the product: it is what lets a page say
    what a session actually costs, charge plus park, rather than charge alone.
    """
    stations = db.query(
        "SELECT station_id, lat, lon FROM station WHERE lat IS NOT NULL")
    # Public chargers stand at the kerb, so the parking they imply is the
    # street zone, never the garage across the road with its day ticket.
    areas = db.query(
        "SELECT area_id, lat, lon FROM parking_area WHERE lat IS NOT NULL AND on_street")
    if not areas:
        return {"linked": 0, "note": "no parking areas loaded yet"}

    # Bucket areas into ~0.01 degree cells so this is not 80k x 60k.
    grid: dict[tuple[int, int], list] = {}
    for a in areas:
        grid.setdefault((int(a["lat"] * 100), int(a["lon"] * 100)), []).append(a)

    rows = []
    for s in stations:
        ci, cj = int(s["lat"] * 100), int(s["lon"] * 100)
        best, best_d = None, None
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for a in grid.get((ci + di, cj + dj), ()):
                    dlat = (a["lat"] - s["lat"]) * 111_320
                    dlon = (a["lon"] - s["lon"]) * 68_000  # cos(52 deg) at NL latitude
                    d = (dlat * dlat + dlon * dlon) ** 0.5
                    if best_d is None or d < best_d:
                        best, best_d = a["area_id"], d
        if best and best_d <= max_m:
            rows.append((s["station_id"], best, round(best_d, 1)))

    db.execute("TRUNCATE station_parking_link")
    db.upsert("station_parking_link",
              ["station_id", "area_id", "distance_m"], ["station_id"], rows)
    db.execute("UPDATE station_parking_link SET linked_at = now()")
    return {"linked": len(rows), "stations": len(stations)}
