#!/usr/bin/env python3
"""Where should public charging go next? A hexagon-level answer for the Netherlands.

The national figure says there is no problem. The Netherlands has about 4.55 GW
of publicly accessible charging power for roughly 1.3 million electric cars,
which is 3.5 kW per car against the 1.3 kW per battery electric vehicle that
AFIR (Regulation (EU) 2023/1804, Article 3) requires member states to provide.
Nationally we are at more than twice the legal floor.

A national average is the wrong instrument for a question about places. This
model asks the same question of every two-kilometre hexagon in the country.

WHY HEXAGONS AND NOT MUNICIPALITIES
Municipal borders are administrative. A charger two hundred metres over a
boundary serves you perfectly well, and a municipal average hides the
difference between a terraced suburb with driveways and a tower block district
three kilometres away. Hexagons also have one property squares lack: all six
neighbours share an edge and sit at the same distance, so neighbourhood
statistics are not distorted by the diagonal.

The hexagon is a reporting unit, not a catchment. Two kilometres across is a
district, not a walk.

WHY NOT SIMPLY EVs PER CHARGER
Because roughly four fifths of charging happens at home, and a household with a
driveway barely touches the public network. The demand that public infrastructure
has to carry comes from people who cannot charge where they sleep, and the
literature on charging deserts is consistent that the predictor of that is
housing: flats, and rented housing, without dedicated off-street parking.

So demand here is not "electric cars". It is "electric cars owned by households
in multi-family housing", which is the closest thing the open data supports to
"electric cars with nowhere private to plug in". That makes every number in this
model a LOWER BOUND on local need: a terraced street with no driveway counts as
served when it is not.

CHAIN OF ESTIMATES, EACH STATED
  cars per neighbourhood          CBS wijken en buurten 2024, observed
  EV share per municipality       CBS fleet statistics via our /ev-adoption, observed
  EVs per neighbourhood           cars x municipal EV share            MODELLED
  share of dwellings that are flats  CBS, observed (88% of neighbourhoods)
  EVs without home charging       EVs x flats share                   MODELLED
  charging power per hexagon      our register of 80,700 stations, observed
  required power                  1.3 kW x EVs without home charging  AFIR rate,
                                  applied locally, which AFIR itself does not do

Usage:
  python3 charging_gap.py
  python3 charging_gap.py --across 2000      # hexagon width in metres
"""
import argparse
import csv
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "ev"))

BUURTEN = ROOT / "data" / "research" / "buurten-2024.json"
EVDATA = ROOT / "data" / "ev-adoption-2026.json"
OUT_GEO = ROOT / "data" / "research" / "charging-gap-hexes.json"
OUT_CSV = ROOT / "data" / "research" / "charging-gap-2026.csv"
OUT_SUM = ROOT / "data" / "research" / "charging-gap-summary.json"

AFIR_KW_PER_BEV = 1.3          # Regulation (EU) 2023/1804, Article 3
LAT0, LON0 = 52.15, 5.4        # centre of the projection, middle of the country
R = 6371000.0

# CBS and our fleet table spell ten municipalities differently. Nothing clever,
# just the list, so a rename upstream fails loudly instead of silently dropping
# a city.
ALIAS = {
    "'s-Gravenhage": "Den Haag", "Beek (L.)": "Beek",
    "Bergen (L.)": "Bergen (Limburg)", "Bergen (NH.)": "Bergen (Noord-Holland)",
    "Hengelo (O.)": "Hengelo", "Laren (NH.)": "Laren",
    "Middelburg (Z.)": "Middelburg", "Rijswijk (ZH.)": "Rijswijk",
    "Stein (L.)": "Stein",
}
DROP = {"Buitenland"}          # CBS bucket for addresses outside the country


def project(lat, lon):
    """Equirectangular about the middle of the country. Over 300 km of the
    Netherlands the error is under half a percent, which is nothing against a
    two-kilometre bin."""
    x = R * math.radians(lon - LON0) * math.cos(math.radians(LAT0))
    y = R * math.radians(lat - LAT0)
    return x, y


def unproject(x, y):
    lat = math.degrees(y / R) + LAT0
    lon = math.degrees(x / (R * math.cos(math.radians(LAT0)))) + LON0
    return lat, lon


def hex_of(x, y, s):
    """Pointy-top axial coordinates, then cube rounding to the nearest centre."""
    q = (math.sqrt(3) / 3 * x - y / 3) / s
    r = (2 * y / 3) / s
    cx, cz = q, r
    cy = -cx - cz
    rx, ry, rz = round(cx), round(cy), round(cz)
    dx, dy, dz = abs(rx - cx), abs(ry - cy), abs(rz - cz)
    if dx > dy and dx > dz:
        rx = -ry - rz
    elif dy > dz:
        ry = -rx - rz
    else:
        rz = -rx - ry
    return int(rx), int(rz)


def hex_centre(q, r, s):
    return s * math.sqrt(3) * (q + r / 2), s * 1.5 * r


def hex_ring(q, r, s):
    """The six corners, as lat/lon, for drawing."""
    cx, cy = hex_centre(q, r, s)
    pts = []
    for i in range(6):
        a = math.radians(60 * i - 30)
        lat, lon = unproject(cx + s * math.cos(a), cy + s * math.sin(a))
        pts.append([round(lon, 5), round(lat, 5)])
    pts.append(pts[0])
    return pts


CATCHMENT_M = 1000.0    # how far someone will walk to an overnight charger


def decay(d, r=None):
    """Weight a charger by how far away it is, to zero at the catchment edge.

    A charger 50 metres outside a hexagon boundary serves that hexagon exactly
    as well as one 50 metres inside it. Counting only what falls within the
    polygon made a Groningen neighbourhood the worst place in the country with
    no charging at all; it has 61 chargers within two kilometres and the
    nearest is 1.08 km away. The hexagon was measuring its own edges.

    So supply is counted by catchment rather than containment, and shared
    between everyone who can reach it, which is what two-step floating
    catchment area does and why the charging-desert literature uses it.

    r is read at call time. Binding it as a default froze it at import and
    made a catchment sweep return an identical answer at every radius, which
    read as reassuring robustness and was a bug.
    """
    if r is None:
        r = CATCHMENT_M
    if d >= r:
        return 0.0
    x = d / r
    return math.exp(-3.0 * x * x) - math.exp(-3.0)


def bucket(points, size):
    """Cheap spatial index. Brute force here is 6,000 hexagons by 80,000
    stations, half a billion pairs; bucketing by the catchment size makes it
    nine buckets per lookup."""
    g = {}
    for i, (x, y, *rest) in enumerate(points):
        g.setdefault((int(x // size), int(y // size)), []).append(i)
    return g


def nearby(g, x, y, size):
    bx, by = int(x // size), int(y // size)
    out = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            out.extend(g.get((bx + dx, by + dy), ()))
    return out


def two_step(hexes, stations):
    """hexes: [(x, y, dependent_evs)]   stations: [(x, y, kw)]
    Returns kW of public charging reachable per dependent EV, per hexagon."""
    size = CATCHMENT_M
    hg = bucket([(h[0], h[1]) for h in hexes], size)

    # Step one: each station divides its power among the demand that can reach it.
    ratio = []
    for sx, sy, kw in stations:
        dem = 0.0
        for i in nearby(hg, sx, sy, size):
            hx, hy, dep = hexes[i]
            if dep <= 0:
                continue
            w = decay(math.hypot(hx - sx, hy - sy))
            if w > 0:
                dem += dep * w
        ratio.append(kw / dem if dem > 0 else 0.0)

    # Step two: each place sums the ratios of the stations it can reach.
    sg = bucket([(s[0], s[1]) for s in stations], size)
    acc = []
    for hx, hy, dep in hexes:
        a = 0.0
        for j in nearby(sg, hx, hy, size):
            sx, sy, _ = stations[j]
            w = decay(math.hypot(hx - sx, hy - sy))
            if w > 0:
                a += ratio[j] * w
        acc.append(a)
    return acc


def load_stations():
    from evlayer import db
    rows = db.query(
        """SELECT s.lat, s.lon, COALESCE(SUM(c.max_power_kw), 0) AS kw,
                  COUNT(DISTINCT e.evse_id) AS pts
           FROM station s
           JOIN evse e ON e.station_id = s.station_id
           JOIN connector c ON c.evse_id = e.evse_id
           WHERE s.lat IS NOT NULL AND s.lon IS NOT NULL
           GROUP BY s.station_id, s.lat, s.lon""")
    return [(float(r["lat"]), float(r["lon"]), float(r["kw"] or 0), int(r["pts"] or 0))
            for r in rows]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--across", type=float, default=2000.0,
                    help="hexagon width across the flats, in metres")
    ap.add_argument("--catchment", type=float, default=None,
                    help="how far a resident will walk to a charger, in metres")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--sweep", action="store_true",
                    help="also run a range of catchments and record the spread")
    a = ap.parse_args()
    if a.catchment:
        globals()["CATCHMENT_M"] = a.catchment
    s = a.across / math.sqrt(3)
    hex_km2 = (3 * math.sqrt(3) / 2) * s * s / 1e6

    buurten = json.loads(BUURTEN.read_text())
    muni = {m["name"]: m for m in json.loads(EVDATA.read_text())["municipalities"]}

    # EV share per municipality, as a fraction of private cars.
    share = {}
    for name, m in muni.items():
        if m.get("private_cars"):
            share[name] = (m["ev_estimate"] or 0) / m["private_cars"]

    # Municipality mean flats share, population weighted, to stand in where CBS
    # suppressed the neighbourhood figure.
    acc = defaultdict(lambda: [0.0, 0.0])
    for b in buurten:
        gm = ALIAS.get(b["gm"], b["gm"])
        if b["flats"] is not None and b["pop"]:
            acc[gm][0] += b["flats"] * b["pop"]
            acc[gm][1] += b["pop"]
    muni_flats = {k: v[0] / v[1] for k, v in acc.items() if v[1]}

    cells = defaultdict(lambda: {
        "pop": 0.0, "cars": 0.0, "ev": 0.0, "dep": 0.0, "kw": 0.0, "pts": 0,
        "flats_w": 0.0, "rent_w": 0.0, "wsum": 0.0, "city": defaultdict(float),
        "imputed": 0, "nb": 0})

    unmatched = set()
    demand_pts = []
    for b in buurten:
        gm = ALIAS.get(b["gm"], b["gm"])
        if gm in DROP or not b["cars"]:
            continue
        if gm not in share:
            unmatched.add(gm)
            continue
        flats = b["flats"]
        imputed = flats is None
        if imputed:
            flats = muni_flats.get(gm)
            if flats is None:
                continue
        ev = b["cars"] * share[gm]
        dep = ev * (flats / 100.0)
        x, y = project(b["lat"], b["lon"])
        hk = hex_of(x, y, s)
        demand_pts.append((x, y, dep, hk))
        c = cells[hk]
        c["pop"] += b["pop"] or 0
        c["cars"] += b["cars"]
        c["ev"] += ev
        c["dep"] += dep
        c["nb"] += 1
        c["imputed"] += 1 if imputed else 0
        w = b["pop"] or 1
        c["flats_w"] += flats * w
        c["rent_w"] += (b["rent"] or 0) * w
        c["wsum"] += w
        c["city"][gm] += b["pop"] or 1

    if unmatched:
        sys.exit(f"municipality names with no EV figure: {sorted(unmatched)[:6]} "
                 f"({len(unmatched)} total). Add them to ALIAS.")

    station_pts = []
    for lat, lon, kw, pts in load_stations():
        x, y = project(lat, lon)
        c = cells[hex_of(x, y, s)]
        c["kw"] += kw          # what literally stands inside, kept as a fact
        c["pts"] += pts
        if kw > 0:
            station_pts.append((x, y, kw))

    # Accessibility, which is the number that actually means something. The
    # containment figure above says what is inside the polygon; this says what
    # a resident can reach on foot, with each charger shared between everyone
    # who can reach it.
    # Demand sits at neighbourhood centroids, not hexagon centres. A hexagon is
    # two kilometres across, so measuring from its middle puts every resident on
    # the rim up to a kilometre away from where they actually live, and that
    # alone invented the worst "charging desert" in the first run. Neighbourhoods
    # are a few hundred metres across and are where people actually are.
    acc_b = two_step([(x, y, dep) for x, y, dep, _ in demand_pts], station_pts)
    print(f"  2SFCA over {len(station_pts):,} stations and {len(demand_pts):,} "
          f"neighbourhoods, {CATCHMENT_M:.0f} m catchment")

    # Roll the neighbourhood answer up to the hexagon, weighted by the demand it
    # is an answer for, so a hexagon reads as what its residents experience.
    agg = {}
    for (x, y, dep, hk), av in zip(demand_pts, acc_b):
        w = agg.setdefault(hk, [0.0, 0.0])
        w[0] += av * dep
        w[1] += dep
    keys = list(cells.keys())
    access = [(agg[k][0] / agg[k][1]) if k in agg and agg[k][1] > 0 else 0.0
              for k in keys]

    feats, rows = [], []
    for i, (q, r) in enumerate(keys):
        c = cells[(q, r)]
        if c["dep"] < 1 and c["kw"] <= 0:
            continue
        per = access[i]                       # kW reachable per dependent EV
        req = AFIR_KW_PER_BEV * c["dep"]
        # Shortfall expressed as power, so it can be added up nationally and
        # read as "this many chargers".
        gap = max(0.0, (AFIR_KW_PER_BEV - per)) * c["dep"]
        city = max(c["city"], key=c["city"].get) if c["city"] else ""
        rec = {
            "q": q, "r": r, "city": city,
            "pop": round(c["pop"]), "cars": round(c["cars"]),
            "ev": round(c["ev"]), "dep": round(c["dep"]),
            "kw": round(c["kw"]), "pts": c["pts"],
            "req": round(req), "gap": round(gap),
            "per": round(per, 2),
            "flats": round(c["flats_w"] / c["wsum"], 1) if c["wsum"] else None,
            "rent": round(c["rent_w"] / c["wsum"], 1) if c["wsum"] else None,
            "nb": c["nb"], "imputed": c["imputed"],
        }
        rows.append(rec)
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [hex_ring(q, r, s)]},
            "properties": rec,
        })

    rows.sort(key=lambda z: -z["gap"])
    national_kw = sum(z["kw"] for z in rows)
    national_ev = sum(z["ev"] for z in rows)
    national_dep = sum(z["dep"] for z in rows)
    short = [z for z in rows if z["gap"] > 0 and z["dep"] >= 50]
    served = [z for z in rows if z["dep"] >= 50]
    pers = sorted(z["per"] for z in served if z["per"] is not None)
    zero = [z for z in served if z["per"] <= 0]

    summary = {
        "generated": __import__("datetime").date.today().isoformat(),
        "hex_across_m": a.across, "hex_km2": round(hex_km2, 2),
        "hexes": len(rows),
        "hexes_with_demand": len(served),
        "afir_kw_per_bev": AFIR_KW_PER_BEV,
        "national_kw": round(national_kw),
        "national_ev": round(national_ev),
        "national_dep_ev": round(national_dep),
        "national_kw_per_ev": round(national_kw / national_ev, 2) if national_ev else None,
        "national_kw_per_dep_ev": round(national_kw / national_dep, 2) if national_dep else None,
        "short_hexes": len(short),
        "short_share": round(100 * len(short) / len(served), 1) if served else None,
        "short_total_kw": round(sum(z["gap"] for z in short)),
        "short_people": sum(z["pop"] for z in short),
        "catchment_m": CATCHMENT_M,
        "no_access_hexes": len(zero),
        "no_access_people": sum(z["pop"] for z in zero),
        "median_kw_per_dep_ev": round(statistics.median(pers), 2) if pers else None,
        "p10_kw_per_dep_ev": round(pers[len(pers) // 10], 2) if pers else None,
        "worst": rows[:40],
    }

    OUT_GEO.parent.mkdir(parents=True, exist_ok=True)
    OUT_GEO.write_text(json.dumps(
        {"type": "FeatureCollection", "features": feats}, separators=(",", ":")))
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    # How far someone will walk is a judgement, not a measurement, and the
    # answer moves a lot with it: at 600 m seventy-one neighbourhoods fall
    # short, at two kilometres nine do. Publishing one number from one radius
    # would be picking the story. The sweep goes in the file so the reader can
    # see the whole curve.
    if a.sweep:
        import copy
        keep = CATCHMENT_M
        sweep = []
        for rad in (600, 800, 1000, 1250, 1500, 2000):
            globals()["CATCHMENT_M"] = float(rad)
            ab = two_step([(x, y, dep) for x, y, dep, _ in demand_pts], station_pts)
            ag = {}
            for (x, y, dep, hk), av in zip(demand_pts, ab):
                w = ag.setdefault(hk, [0.0, 0.0])
                w[0] += av * dep
                w[1] += dep
            vals = []
            for k in keys:
                c = cells[k]
                if c["dep"] < 50:
                    continue
                vals.append((ag[k][0] / ag[k][1]) if k in ag and ag[k][1] > 0 else 0.0)
            vals.sort()
            sweep.append({
                "catchment_m": rad,
                "hexes": len(vals),
                "short": sum(1 for v in vals if v < AFIR_KW_PER_BEV),
                "zero": sum(1 for v in vals if v <= 0),
                "median": round(statistics.median(vals), 2) if vals else None,
                "p10": round(vals[len(vals) // 10], 2) if vals else None,
            })
            print(f"    catchment {rad:>5} m: {sweep[-1]['short']:>3} short, "
                  f"median {sweep[-1]['median']}")
        globals()["CATCHMENT_M"] = keep
        summary["sweep"] = sweep

    OUT_SUM.write_text(json.dumps(summary, indent=1))

    print(f"  hexagons {a.across:.0f} m across ({hex_km2:.2f} km2): {len(rows):,}")
    print(f"  with 50+ dependent EVs           : {len(served):,}")
    print(f"  national power                   : {national_kw/1e6:.2f} GW")
    print(f"  kW per EV / per dependent EV     : {summary['national_kw_per_ev']} / {summary['national_kw_per_dep_ev']}")
    print(f"  hexes below the AFIR rate        : {len(short):,} ({summary['short_share']}%)")
    print(f"  people living in them            : {summary['short_people']:,}")
    print(f"  combined shortfall               : {summary['short_total_kw']/1000:.1f} MW")
    print(f"\n  worst ten:")
    for z in rows[:10]:
        print(f"    {z['city'][:20]:<20} gap {z['gap']:>6,} kW  dep EV {z['dep']:>5,}  "
              f"have {z['kw']:>6,} kW  flats {z['flats']}%")
    print(f"\n-> {OUT_GEO.name} ({OUT_GEO.stat().st_size/1e6:.1f} MB), {OUT_CSV.name}, {OUT_SUM.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
