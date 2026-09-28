"""Static data export for the charger map.

80k chargers is roughly 6 MB of JSON, far too much to embed or to fetch in one
go. The export is therefore split two ways:

  cities.json          one row per town, for the zoomed-out view and search
  cells/{x}_{y}.json   a 0.25 degree grid, fetched only for the visible area

The map loads a handful of small cells for wherever the viewer is looking, so
the page stays light and the whole thing remains static files on a CDN.
"""
import json
from datetime import datetime, timezone
import math
from collections import defaultdict
from pathlib import Path

from .. import config, db

CELL = 0.1           # degrees; ~11 km north-south, ~7 km east-west in NL
DATA_DIR = "ev-data"

# A handful of feed rows carry impossible coordinates: Dutch street names
# plotted at 0,0, at lat 90/lon 135, and in Kansas and India. They are a
# rounding error in count (16 of 80,018) but they render as markers in the
# wrong hemisphere, so the export clips to the Netherlands.
NL_BBOX = {"lat0": 50.6, "lat1": 53.8, "lon0": 3.2, "lon1": 7.3}


def cell_key(lat: float, lon: float) -> str:
    return f"{math.floor(lon / CELL)}_{math.floor(lat / CELL)}"


def _round(v, n=5):
    return round(float(v), n)


def export() -> dict:
    root: Path = config.SITE_ROOT / DATA_DIR
    cells_dir = root / "cells"
    cells_dir.mkdir(parents=True, exist_ok=True)
    for old in cells_dir.glob("*.json"):
        old.unlink()

    rows = db.query(
        """SELECT s.station_id, s.name, s.address, s.cpo, s.lat, s.lon, s.city,
                  COUNT(DISTINCT e.evse_id)::int AS evses,
                  MAX(c.max_power_kw) AS kw,
                  ROUND(AVG(r.uptime_pct), 1) AS up,
                  COUNT(DISTINCT r.day)::int AS days,
                  l.area_id,
                  COUNT(*) FILTER (WHERE e.status_current IN
                    ('OUTOFORDER','INOPERATIVE'))::int AS down_now
           FROM station s
           JOIN evse e ON e.station_id = s.station_id
           LEFT JOIN connector c ON c.evse_id = e.evse_id
           LEFT JOIN reliability_daily r
             ON r.evse_id = e.evse_id AND r.day > current_date - 30
           LEFT JOIN station_parking_link l ON l.station_id = s.station_id
           WHERE s.lat BETWEEN %(lat0)s AND %(lat1)s
             AND s.lon BETWEEN %(lon0)s AND %(lon1)s
           GROUP BY s.station_id, l.area_id""",
        NL_BBOX
    )

    # Charging price per station, from the CPO ad-hoc tariffs.
    price = {r["station_id"]: r for r in db.query(
        """SELECT s.station_id, MAX(t.price_per_kwh) AS ppk, MAX(t.start_fee) AS fee
           FROM station s
           JOIN evse e ON e.station_id = s.station_id
           JOIN connector c ON c.evse_id = e.evse_id
           JOIN LATERAL unnest(c.tariff_ids) AS tid ON true
           JOIN cpo_tariff t ON t.tariff_id = tid
           WHERE t.price_per_kwh IS NOT NULL
           GROUP BY s.station_id""")}

    # Parking windows, shared by many stations, so they are sent once and
    # referenced by id rather than copied onto every marker.
    # Each window names its fare ladder; the ladder is shipped once per code so
    # the page prices a stay the way the meter does, band by band, instead of
    # multiplying an hourly figure.
    windows = defaultdict(lambda: {"w": [], "f": {}})
    for w in db.query(
        """SELECT area_id, day_of_week, start_min, end_min, fare_code
           FROM parking_tariff WHERE fare_code IS NOT NULL"""):
        windows[w["area_id"]]["w"].append(
            [w["day_of_week"], w["start_min"], w["end_min"], w["fare_code"]])
    for fp in db.query(
        """SELECT area_id, fare_code, start_min, end_min, step_min, amount
           FROM parking_fare_part ORDER BY area_id, fare_code, start_min"""):
        if fp["area_id"] in windows:
            windows[fp["area_id"]]["f"].setdefault(fp["fare_code"], []).append(
                [fp["start_min"], fp["end_min"], fp["step_min"], round(float(fp["amount"]), 2)])

    cells = defaultdict(list)
    cities = defaultdict(lambda: {"n": 0, "e": 0, "lat": 0.0, "lon": 0.0, "up": [], "kw": 0})
    used_areas = set()

    for r in rows:
        lat, lon = float(r["lat"]), float(r["lon"])
        p = price.get(r["station_id"], {})
        area = r["area_id"] if r["area_id"] in windows else None
        if area:
            used_areas.add(area)

        rec = [
            r["station_id"],
            (r["address"] or r["name"] or "Charging point").strip()[:60],
            r["cpo"] or "",
            _round(lat), _round(lon),
            float(r["kw"]) if r["kw"] else 0,
            r["evses"] or 1,
            float(r["up"]) if r["up"] is not None else None,
            round(float(p["ppk"]), 3) if p.get("ppk") else None,
            area,
            r["down_now"] or 0,
        ]
        cells[cell_key(lat, lon)].append(rec)

        if r["city"]:
            c = cities[r["city"]]
            c["n"] += 1
            c["e"] += r["evses"] or 1
            c["lat"] += lat
            c["lon"] += lon
            c["kw"] = max(c["kw"], float(r["kw"]) if r["kw"] else 0)
            if r["up"] is not None:
                c["up"].append(float(r["up"]))

    for key, recs in cells.items():
        (cells_dir / f"{key}.json").write_text(
            json.dumps(recs, separators=(",", ":"), ensure_ascii=False))

    city_list = sorted(
        ({"name": name,
          "n": c["n"], "e": c["e"],
          "lat": _round(c["lat"] / c["n"], 4), "lon": _round(c["lon"] / c["n"], 4),
          "kw": c["kw"],
          "up": round(sum(c["up"]) / len(c["up"]), 1) if c["up"] else None}
         for name, c in cities.items() if c["n"] > 0),
        key=lambda x: -x["n"])

    (root / "cities.json").write_text(
        json.dumps(city_list, separators=(",", ":"), ensure_ascii=False))
    (root / "tariffs.json").write_text(
        json.dumps({a: windows[a] for a in used_areas},
                   separators=(",", ":"), ensure_ascii=False))

    cards = db.query(
        """SELECT DISTINCT ON (card) card, price_per_kwh, start_fee
           FROM card_tariff WHERE cpo_match = '*' AND price_per_kwh > 0
           ORDER BY card, valid_from DESC""")
    (root / "cards.json").write_text(json.dumps(
        [{"card": c["card"], "kwh": float(c["price_per_kwh"]),
          "fee": float(c["start_fee"] or 0)} for c in cards],
        separators=(",", ":"), ensure_ascii=False))

    total = sum(len(v) for v in cells.values())
    sizes = [(cells_dir / f"{k}.json").stat().st_size for k in cells]
    meta = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "stations": total,
        "cells": len(cells),
        "cities": len(city_list),
        "priced_areas": len(used_areas),
        "largest_cell_kb": round(max(sizes) / 1024, 1) if sizes else 0,
        "cities_json_kb": round((root / "cities.json").stat().st_size / 1024, 1),
        "days_measured": db.one(
            "SELECT COUNT(DISTINCT day) AS d FROM reliability_daily")["d"] or 0,
    }
    (root / "meta.json").write_text(json.dumps(meta, separators=(",", ":")))
    return meta
