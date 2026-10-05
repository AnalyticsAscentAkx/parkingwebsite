#!/usr/bin/env python3
"""Pull CBS neighbourhood statistics once and keep only what the hex model needs.

PDOK serves the CBS wijken-en-buurten layer as WFS, keyless. The full payload is
around 130 MB because every neighbourhood carries its polygon and 244 columns.
We need nine of those columns and a single point per neighbourhood, so the
geometry is reduced to a centroid as it streams past and thrown away.

CBS suppresses values in neighbourhoods too small to publish without identifying
people, and writes the suppression as -99997 rather than null. Those are turned
into None here, at the edge, so nothing downstream mistakes a sentinel for a
count.
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data" / "research" / "buurten-2024.json"
WFS = "https://service.pdok.nl/cbs/wijkenbuurten/2024/wfs/v1_0"
FIELDS = ["buurtcode", "buurtnaam", "gemeentenaam", "aantalInwoners",
          "personenautosTotaal", "percentageMeergezinswoning",
          "percentageHuurwoningen", "oppervlakteLandInHa",
          "stedelijkheidAdressenPerKm2"]
PAGE = 500
SUPPRESSED = {-99997, -99995, -99994, -99993}


def clean(v):
    """CBS writes 'cannot publish' as a large negative sentinel, not null."""
    if isinstance(v, (int, float)) and int(v) in SUPPRESSED:
        return None
    return v


def centroid(geom):
    """Area-weighted centroid is overkill at this resolution; the mean of the
    outer ring is within a few hundred metres and the hexes are kilometres."""
    if not geom:
        return None
    def rings(g):
        if g["type"] == "Polygon":
            return [g["coordinates"][0]]
        if g["type"] == "MultiPolygon":
            return [p[0] for p in g["coordinates"]]
        return []
    pts = [pt for r in rings(geom) for pt in r]
    if not pts:
        return None
    return [round(sum(p[0] for p in pts) / len(pts), 6),
            round(sum(p[1] for p in pts) / len(pts), 6)]


def main():
    out, start, t0 = [], 0, time.time()
    while True:
        url = (f"{WFS}?service=WFS&version=2.0.0&request=GetFeature"
               f"&typeName=wijkenbuurten:buurten&outputFormat=application/json"
               f"&count={PAGE}&startIndex={start}&propertyName={','.join(FIELDS)}"
               # Without this PDOK answers in its native EPSG:28992, whose
               # metres look enough like coordinates to bin silently into the
               # wrong hexagons. Asked for 4326 it returns lon, lat.
               f"&srsName=EPSG:4326")
        req = urllib.request.Request(url, headers={
            "User-Agent": "parkingnetherlands-research (+https://parkingnetherlands.com/about)"})
        # Thirty-odd requests against one host; roughly one in twenty drops the
        # TLS record. Retry rather than lose the whole run at page 25.
        page = None
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    page = json.load(r)
                break
            except Exception as e:
                if attempt == 4:
                    raise
                print(f"    retry {attempt+1} at {start}: {type(e).__name__}", flush=True)
                time.sleep(2 * (attempt + 1))
        feats = page.get("features", [])
        if not feats:
            break
        for f in feats:
            p = f.get("properties", {})
            c = centroid(f.get("geometry"))
            if not c:
                continue
            out.append({
                "code": p.get("buurtcode"), "name": p.get("buurtnaam"),
                "gm": p.get("gemeentenaam"),
                "pop": clean(p.get("aantalInwoners")),
                "cars": clean(p.get("personenautosTotaal")),
                "flats": clean(p.get("percentageMeergezinswoning")),
                "rent": clean(p.get("percentageHuurwoningen")),
                "ha": clean(p.get("oppervlakteLandInHa")),
                "urb": clean(p.get("stedelijkheidAdressenPerKm2")),
                "lon": c[0], "lat": c[1],
            })
        start += PAGE
        print(f"  {start:>6} fetched, {len(out):>6} kept, {time.time()-t0:4.0f}s", flush=True)
        if len(feats) < PAGE:
            break

    # Fail loudly rather than write a file that looks fine and is 200 km out.
    lats = [b["lat"] for b in out]
    lons = [b["lon"] for b in out]
    if not (50.0 < min(lats) and max(lats) < 54.0 and 3.0 < min(lons) and max(lons) < 7.5):
        sys.exit(f"coordinates are not WGS84 degrees over the Netherlands: "
                 f"lat {min(lats):.1f}..{max(lats):.1f} lon {min(lons):.1f}..{max(lons):.1f}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    pop = sum(b["pop"] or 0 for b in out)
    cars = sum(b["cars"] or 0 for b in out)
    print(f"\n  neighbourhoods : {len(out):,}")
    print(f"  population     : {pop:,}")
    print(f"  cars           : {cars:,}")
    print(f"  with flats pct : {sum(1 for b in out if b['flats'] is not None):,}")
    print(f"-> {OUT} ({OUT.stat().st_size/1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
