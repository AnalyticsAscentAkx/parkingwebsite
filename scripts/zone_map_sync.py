#!/usr/bin/env python3
"""
Street-parking tariff zone map builder.

Joins RDW street-section polygons (GEOMETRIE GEBIED) to hourly tariffs
(GEBIED REGELING -> TIJDVAK -> TARIEFDEEL), buffers + unions the sections
per price band, and writes one compact GeoJSON per city to ../zones/.

Bands (EUR/hour, weekday 14:00): <2, 2-3, 3-4.5, 4.5-6, 6+
Usage: python3 zone_map_sync.py
"""
import json
import re
from pathlib import Path

from shapely import wkt as shp_wkt
from shapely.geometry import mapping
from shapely.ops import unary_union

import rdw_tariff_sync as rdw

BANDS = [
    (0.01, 2.0,  "b1", "under €2/hr"),
    (2.0,  3.0,  "b2", "€2 – €3/hr"),
    (3.0,  4.5,  "b3", "€3 – €4.50/hr"),
    (4.5,  6.0,  "b4", "€4.50 – €6/hr"),
    (6.0,  99.0, "b5", "€6+/hr"),
]
FREE_BAND = (0.0, 0.01, "b0", "free / €0")

# merge Haarlem's two manager ids under one slug
CITY_IDS = {}
for amid, slug in rdw.CITIES.items():
    CITY_IDS.setdefault(slug, []).append(amid)


def band_of(rate):
    if rate <= FREE_BAND[1]:
        return FREE_BAND[2]
    for lo, hi, key, _ in BANDS:
        if lo <= rate < hi:
            return key
    return "b5"


def build_city(slug, amids):
    sections = []  # (shapely geom, rate)
    for amid in amids:
        try:
            geo = rdw.fetch("nsk3-v9n7", areamanagerid=amid)
            regs = rdw.fetch("qtex-qwd8", areamanagerid=amid)
            frames = rdw.fetch("ixf8-gtwq", areamanagerid=amid)
            parts = rdw.fetch("534e-5vdg", areamanagerid=amid)
        except Exception as e:
            print(f"[warn] {slug}/{amid}: {e}")
            continue

        reg_by_area = {}
        for r in regs:
            # BETAALDP = paid street; VERGUNP = permit zones where visitors
            # can usually pay too (all of central Amsterdam) — kept only if a
            # non-zero visitor tariff resolves below
            if rdw.active(r, "enddatearearegulation") and r.get("usageid") in ("BETAALDP", "VERGUNP"):
                reg_by_area.setdefault(r["areaid"], (r["regulationid"], r["usageid"]))

        codes = {}
        for f in frames:
            if not rdw.active(f, "enddatetimeframe") or not f.get("farecalculationcode"):
                continue
            st = int(f.get("starttimetimeframe") or 0)
            en = int(f.get("endtimetimeframe") or 2400)
            if not (st <= 1400 <= en):
                continue
            key = f["regulationid"]
            if f.get("daytimeframe") == "WOENSDAG":
                codes[key] = f["farecalculationcode"]
            else:
                codes.setdefault(key, f["farecalculationcode"])

        parts_by_code = {}
        for p in parts:
            if rdw.active(p, "enddatefarepart"):
                parts_by_code.setdefault(p["farecalculationcode"], []).append(p)
        for c in parts_by_code:
            parts_by_code[c].sort(key=lambda p: float(p["startdurationfarepart"]))

        # Geometry rows are versioned per section. Amsterdam's centre rows all
        # carry stale end-dates while the areas remain actively regulated, so:
        # use current rows when the area has any; otherwise fall back to the
        # area's most recent expired batch.
        rows_by_area = {}
        for g in geo:
            aid = g["areaid"]
            if aid in reg_by_area:
                rows_by_area.setdefault(aid, []).append(g)
        chosen = []
        for aid, rows in rows_by_area.items():
            current = [g for g in rows if (g.get("enddatearea") or "2999")[:4] >= rdw.TODAY[:4]]
            if current:
                chosen.extend(current)
            else:
                latest = max((g.get("enddatearea") or "") for g in rows)
                chosen.extend(g for g in rows if (g.get("enddatearea") or "") == latest)
        for g in chosen:
            areaid = g["areaid"]
            reg = reg_by_area.get(areaid)
            if not reg:
                continue
            regid, usage = reg
            code = codes.get(regid)
            if not code or code not in parts_by_code:
                continue
            w = g.get("areageometryastext", "")
            if "POLYGON" not in w:
                continue
            try:
                geom = shp_wkt.loads(w)
            except Exception:
                continue
            rate = rdw.fare_cost(parts_by_code[code], 60)
            if usage == "VERGUNP" and (rate is None or rate <= 0):
                continue   # permit-only, no visitor tariff — not paid street parking
            sections.append((geom, rate))

    if not sections:
        return None

    by_band = {}
    for geom, rate in sections:
        by_band.setdefault(band_of(rate), []).append(geom)

    features = []
    for key, geoms in by_band.items():
        # buffer to fuse parking bays into street corridors, then shrink + simplify
        merged = unary_union([g.buffer(0.00045) for g in geoms])
        merged = merged.buffer(-0.0002).simplify(0.00008)
        if merged.is_empty:
            continue
        label = FREE_BAND[3] if key == FREE_BAND[2] else next(b[3] for b in BANDS if b[2] == key)
        features.append({
            "type": "Feature",
            "properties": {"band": key, "label": label, "n": len(geoms)},
            "geometry": mapping(merged),
        })

    fc = {"type": "FeatureCollection", "features": features}
    # trim coordinate precision to ~1 m
    txt = re.sub(r"(\d+\.\d{5})\d+", r"\1", json.dumps(fc, separators=(",", ":")))
    return txt, len(sections)


def main():
    out = Path(__file__).resolve().parent.parent / "zones"
    out.mkdir(exist_ok=True)
    summary = {}
    for slug, amids in CITY_IDS.items():
        res = build_city(slug, amids)
        if not res:
            print(f"[--] {slug}: no priced street sections")
            continue
        txt, n = res
        (out / f"{slug}.json").write_text(txt, encoding="utf-8")
        summary[slug] = n
        print(f"[ok] {slug}: {n} street sections -> {len(txt)//1024} KB")
    (out / "index.json").write_text(json.dumps(summary))


if __name__ == "__main__":
    main()
