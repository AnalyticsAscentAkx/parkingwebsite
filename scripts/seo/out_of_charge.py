#!/usr/bin/env python3
"""
"My EV ran out of charge in the Netherlands": the safety steps, what the
breakdown service actually does, and how far you really are from a charger.

Why this page exists. The obvious version of this topic is a fear piece that
sells breakdown insurance. The honest version is the opposite, and we are the
only site that can prove it: we hold every public charge point in the country
with its live fault status, so we can measure the distance from anywhere on
Dutch land to the nearest charger that is working right now, rather than
asserting that running flat is a disaster.

It reads the published cell data under ev-data/, so it needs no database, and
the Dutch land outline from CBS via PDOK, cached per run.

Outputs
  ev-out-of-charge.html                   the page
  data/charge-coverage-2026.json / .csv   the measurements (CC BY 4.0)

Usage: python3 scripts/seo/out_of_charge.py [--offline]
Needs numpy, scipy and shapely, which live in the system python, not in the
scripts/ev venv.
"""
import argparse
import csv
import datetime
import glob
import json
import math
import pathlib
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
SITE = "https://parkingnetherlands.com"
TODAY = datetime.date.today().isoformat()
CACHE = ROOT / "scripts" / "seo" / ".cache"
GEO = CACHE / "nl-municipalities-4326.json"
GEO_URL = ("https://service.pdok.nl/cbs/gebiedsindelingen/2026/wfs/v1_0?request=GetFeature"
           "&service=WFS&version=2.0.0&typeName=gemeente_gegeneraliseerd"
           "&outputFormat=json&srsName=EPSG:4326")

# The Wadden islands sit 20 km+ from a fast charger, but the gap is open water,
# not road. Reporting them as the worst places to run flat would be a lie of
# framing, so they are named separately rather than silently dropped.
ISLANDS = {"Schiermonnikoog", "Vlieland", "Terschelling", "Ameland", "Texel"}

LAT, LON, KW, PTS, DOWN = 3, 4, 5, 6, 10      # cell record layout, see ev-map.js
FAST_KW = 50
LAT0 = 52.1
KX = 111.320 * math.cos(math.radians(LAT0))    # km per degree of longitude here
KY = 110.574                                   # km per degree of latitude


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def export_stamp():
    """When the charge point snapshot this page measures was actually taken.

    The page's whole claim is that the fault status is current, so it must date
    the export rather than the build. Faults move hourly; saying "today" when
    the cells were written this morning would be close enough to true to be
    careless."""
    meta = ROOT / "ev-data" / "meta.json"
    if meta.exists():
        g = json.loads(meta.read_text("utf-8")).get("generated")
        if g:
            return g.replace("T", " ").replace("+00:00", " UTC")
    return TODAY


def load_points():
    """Every published charge point, with its power and whether it is out."""
    out = []
    for f in glob.glob(str(ROOT / "ev-data" / "cells" / "*.json")):
        for r in json.loads(pathlib.Path(f).read_text("utf-8")):
            kw = r[KW] if len(r) > KW else None
            pts = r[PTS] if len(r) > PTS else 1
            down = r[DOWN] if len(r) > DOWN else 0
            out.append({"lat": float(r[LAT]), "lon": float(r[LON]),
                        "kw": float(kw) if kw else None,
                        "all_down": bool(pts and down and down >= pts)})
    return out


def land(offline=False):
    CACHE.mkdir(parents=True, exist_ok=True)
    if not GEO.exists():
        if offline:
            sys.exit("no cached land outline and --offline given")
        GEO.write_text(urllib.request.urlopen(GEO_URL, timeout=240).read().decode("utf-8"))
    return json.loads(GEO.read_text("utf-8"))["features"]


def measure(points, feats):
    import numpy as np
    import shapely
    from scipy.spatial import cKDTree
    from shapely.geometry import shape
    from shapely.ops import unary_union

    def xy(lat, lon):
        return (lon * KX, lat * KY)

    fast = [p for p in points if p["kw"] and p["kw"] >= FAST_KW]
    fast_ok = [p for p in fast if not p["all_down"]]
    tree = lambda sel: cKDTree(np.array([xy(p["lat"], p["lon"]) for p in sel]))
    t_all, t_fast, t_ok = tree(points), tree(fast), tree(fast_ok)

    area = unary_union([shape(f["geometry"]) for f in feats])
    minx, miny, maxx, maxy = area.bounds
    step = 0.02                                   # about 2.2 km
    lons = np.arange(minx, maxx, step * (KY / KX))
    lats = np.arange(miny, maxy, step)
    LO, LA = np.meshgrid(lons, lats)
    keep = shapely.contains_xy(area, LO.ravel(), LA.ravel())
    glat, glon = LA.ravel()[keep], LO.ravel()[keep]
    G = np.column_stack([glon * KX, glat * KY])

    d_all, _ = t_all.query(G)
    d_fast, _ = t_fast.query(G)
    d_ok, _ = t_ok.query(G)
    penalty = d_ok - d_fast

    def q(d):
        p = np.percentile(d, [50, 90, 95])
        return {"median": round(float(p[0]), 1), "p90": round(float(p[1]), 1),
                "p95": round(float(p[2]), 1), "max": round(float(d.max()), 1)}

    cent = [(f["properties"].get("statnaam"), shape(f["geometry"]).centroid) for f in feats]
    main = [(n, c) for n, c in cent if n not in ISLANDS]
    dm, _ = t_ok.query(np.array([xy(c.y, c.x) for _, c in main]))
    worst = [{"name": main[i][0], "km": round(float(dm[i]), 1)} for i in np.argsort(-dm)[:10]]
    isl = [(n, c) for n, c in cent if n in ISLANDS]
    di, _ = t_ok.query(np.array([xy(c.y, c.x) for _, c in isl])) if isl else ([], None)
    islands = sorted([{"name": isl[i][0], "km": round(float(di[i]), 1)} for i in range(len(isl))],
                     key=lambda r: -r["km"])

    return {
        "generated": export_stamp(),
        "built": TODAY,
        "grid_points": int(len(glat)),
        "stations": len(points),
        "fast": len(fast),
        "fast_working": len(fast_ok),
        "fast_out": len(fast) - len(fast_ok),
        "fast_out_pct": round(100 * (len(fast) - len(fast_ok)) / max(len(fast), 1), 1),
        "any": q(d_all), "fastest": q(d_fast), "working": q(d_ok),
        "penalty_mean_km": round(float(penalty.mean()), 2),
        "penalty_p90_km": round(float(np.percentile(penalty, 90)), 1),
        "penalty_max_km": round(float(penalty.max()), 1),
        "penalty_over_5km_pct": round(float(100 * (penalty > 5).mean()), 1),
        "within": {str(k): round(float(100 * (d_ok <= k).mean()), 1) for k in (5, 10, 15, 20, 25)},
        "worst_mainland": worst,
        "islands": islands,
    }


# --------------------------------------------------------------------- render
def render(m):
    w = m["within"]
    rows = "\n".join(
        f'<tr><td>{esc(lab)}</td><td class="num">{v["median"]}</td><td class="num">{v["p90"]}</td>'
        f'<td class="num">{v["max"]}</td></tr>'
        for lab, v in (("Any public charge point", m["any"]),
                       ("A fast charger, 50 kW or more", m["fastest"]),
                       ("A fast charger working right now", m["working"])))
    worst = "\n".join(f'<tr><td>{esc(r["name"])}</td><td class="num">{r["km"]}</td></tr>'
                      for r in m["worst_mainland"])
    isl = ", ".join(f'{esc(r["name"])} {r["km"]} km' for r in m["islands"])

    faq = [
        ("How far am I likely to be from a charger if I run flat in the Netherlands?",
         f"From a random point on Dutch land the nearest public charge point of any kind is a median "
         f"{m['any']['median']} km away, and the nearest fast charger {m['fastest']['median']} km. "
         f"{w['10']}% of the country is within 10 km of a fast charger that is working right now. "
         f"Measured on {m['generated']} over {m['grid_points']:,} points on a 2 km grid."),
        ("Does it matter if the nearest fast charger is broken?",
         f"Almost never. Skipping to the next working one adds {m['penalty_mean_km']} km on average, "
         f"and only {m['penalty_over_5km_pct']}% of the country would have to travel more than 5 km "
         f"further. {m['fast_out']} of {m['fast']} fast chargers, {m['fast_out_pct']}%, are reporting "
         "every connector out of order at the moment."),
        ("What should I do first if I stop on a motorway?",
         "Hazard lights on before you get out. Get the car as far onto the hard shoulder as you can, "
         "with the front wheels turned towards the barrier. Leave through the passenger door, not the "
         "driver's door, and get behind the crash barrier, away from the car. Do not sit in the car "
         "and do not put a warning triangle out on a motorway. Then call for help and give the number "
         "on the nearest hectometre post."),
        ("Who do I call in the Netherlands?",
         "Your own breakdown service, or Rijkswaterstaat on 0800-8002 for a motorway. Call 112 only if "
         "someone is hurt or the car is in a live lane."),
        ("Will the breakdown service charge my car or tow it?",
         "The ANWB says the Wegenwacht gives the car enough charge to reach the nearest charge point "
         "or fast charger. Whether a flat battery counts as a covered breakdown, or is billed as an "
         "extra, depends on your policy, so check yours before you need it rather than after."),
        ("How far can I actually drive after the car says zero?",
         "Most cars keep a reserve and will do roughly another 10 to 15 km, depending on the model, "
         "the age of the battery and the temperature. Treat it as enough to reach an exit, not as "
         "range you can plan with."),
    ]
    # Native <details>, not the .fqi/.fqq pattern. Those accordions are bound by
    # the legacy shared.js, which the older hand-written pages load and freshly
    # generated pages do not, so .fqq here would render a question that never
    # opens. <details> needs no script and is what the city and EV adoption
    # generators already emit.
    faq_html = "".join(f'<details class="faq-item"><summary>{esc(q)}</summary>'
                       f'<p>{esc(a)}</p></details>' for q, a in faq)

    ld = [
        {"@context": "https://schema.org", "@type": "Dataset",
         "name": "Dutch charge point coverage: distance to the nearest working fast charger",
         "description": (f"Distance from {m['grid_points']:,} points on a 2 km grid over Dutch land to the "
                         f"nearest public charge point, the nearest fast charger of 50 kW or more, and the "
                         f"nearest fast charger with no fault reported, measured on {m['generated']}."),
         "url": f"{SITE}/ev-out-of-charge",
         "license": "https://creativecommons.org/licenses/by/4.0/",
         "isAccessibleForFree": True,
         "creator": {"@type": "Organization", "name": "Analytics Ascent", "url": "https://analyticascent.com"},
         "publisher": {"@type": "Organization", "name": "Parking Netherlands", "url": SITE},
         "dateModified": TODAY, "datePublished": TODAY,
         "spatialCoverage": {"@type": "Place", "name": "Netherlands",
                             "address": {"@type": "PostalAddress", "addressCountry": "NL"}},
         "variableMeasured": ["distance_to_any_charge_point_km", "distance_to_fast_charger_km",
                              "distance_to_working_fast_charger_km"],
         "isBasedOn": [
             {"@type": "Dataset", "name": "NDW / DOT-NL national charge point register",
              "description": "Live locations, power and operational status of public charge points in the Netherlands.",
              "license": "https://creativecommons.org/publicdomain/zero/1.0/",
              "creator": {"@type": "Organization", "name": "Nationaal Dataportaal Wegverkeer"}},
             {"@type": "Dataset", "name": "CBS gebiedsindelingen 2026, municipality boundaries",
              "description": "Generalised municipal boundaries for the Netherlands, used here as the land outline.",
              "license": "https://creativecommons.org/licenses/by/4.0/",
              "creator": {"@type": "Organization", "name": "Centraal Bureau voor de Statistiek",
                          "url": "https://www.cbs.nl/"}}],
         "distribution": [
             {"@type": "DataDownload", "encodingFormat": "application/json",
              "contentUrl": f"{SITE}/data/charge-coverage-2026.json"},
             {"@type": "DataDownload", "encodingFormat": "text/csv",
              "contentUrl": f"{SITE}/data/charge-coverage-2026.csv"}]},
        {"@context": "https://schema.org", "@type": "FAQPage",
         "mainEntity": [{"@type": "Question", "name": q,
                         "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]},
        {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE + "/"},
            {"@type": "ListItem", "position": 2, "name": "Out of charge",
             "item": f"{SITE}/ev-out-of-charge"}]},
    ]

    desc = (f"Ran out of charge in the Netherlands? The nearest fast charger is a median "
            f"{m['fastest']['median']} km away and {w['10']}% of the country is within 10 km of one "
            f"that is working. The safety steps, who to call, and where cover is actually thin.")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>EV out of charge in the Netherlands: what to do and how far you really are</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{SITE}/ev-out-of-charge">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
</head>
<body>
<div class="bc-bar"><div class="ct bc-in"><a href="/">Home</a> &rarr; <strong>Out of charge</strong></div></div>

<div class="ph"><div class="ct">
<h1>Your EV ran out of charge in the Netherlands</h1>
<p class="sub">First make yourself safe. Then know this: in this country you are almost never far
from a charger. We measured it, from {m['grid_points']:,} points across the land.</p>
</div></div>

<section class="sec"><div class="ct">
<div class="abox"><strong>In one minute.</strong> Hazard lights on before you open the door. Get the car
onto the hard shoulder, leave by the passenger side, and wait behind the barrier, not in the car.
Call your breakdown service, or Rijkswaterstaat on 0800-8002 on a motorway, and give the number on
the nearest hectometre post. Then relax a little: the nearest public charge point is a median
{m['any']['median']} km from any point in the Netherlands, the nearest fast charger
{m['fastest']['median']} km, and {w['10']}% of the country is within 10 km of a fast charger with
no fault reported right now.</div>

<h2 id="safe">Make yourself safe first</h2>
<ul>
<li><strong>Hazard lights on before you get out</strong>, not after.</li>
<li><strong>Get as far onto the hard shoulder as you can</strong>, with the front wheels turned
towards the barrier so the car cannot roll into the carriageway.</li>
<li><strong>Leave through the passenger door.</strong> Opening the driver's door puts you in the lane.</li>
<li><strong>Stand behind the crash barrier</strong> or well into the verge, away from the car. Being
hit at 100 to 130 km/h is the real risk here, not the flat battery.</li>
<li><strong>No warning triangle on a motorway.</strong> It is not compulsory to carry one in the
Netherlands, and walking back down a hard shoulder to place it is more dangerous than not having it.</li>
<li><strong>Call, and give the hectometre post number.</strong> Rijkswaterstaat is 0800-8002. Use 112
only if somebody is hurt or the car is stuck in a live lane.</li>
</ul>

<h2 id="who">What the breakdown service actually does</h2>
<p>The ANWB says the Wegenwacht will put enough charge in the car to reach the nearest charge point
or fast charger, rather than towing it to a garage. Whether a flat battery counts as a covered
breakdown or is billed on top depends on your policy. That is worth checking before you need it,
because it is one of the few exclusions people only discover at the roadside.</p>
<p>Most cars keep a reserve past zero, usually another 10 to 15 km depending on model, battery age
and temperature. Treat that as enough to reach an exit, not as range to plan with.</p>

<h2 id="howfar">How far you actually are</h2>
<p>We took {m['grid_points']:,} points on a 2 km grid over Dutch land and measured the straight-line
distance from each to the nearest charge point in the national register, using the live fault
status on {m['generated']}. Road distance will be longer, but the shape of the answer holds.</p>
<div class="tbl-wrap"><table>
<thead><tr><th>Distance to the nearest&hellip;</th><th>Median</th><th>9 in 10 within</th><th>Worst</th></tr></thead>
<tbody>
{rows}
</tbody></table></div>
<p class="note">Kilometres, straight line. Measured {m['generated']} across {m['stations']:,} public
charge points, of which {m['fast']:,} deliver 50 kW or more.</p>

<div class="three">
<div class="card"><div class="k">Within 5 km</div><h3>{w['5']}%</h3><p>of Dutch land is within 5 km of a fast charger reporting no fault.</p></div>
<div class="card"><div class="k">Within 10 km</div><h3>{w['10']}%</h3><p>within 10 km. At 15 km it is {w['15']}%.</p></div>
<div class="card"><div class="k">Out of order</div><h3>{m['fast_out_pct']}%</h3><p>of fast chargers have every connector out of order right now, {m['fast_out']} of {m['fast']:,}.</p></div>
</div>

<h2 id="faults">Does a broken charger strand you?</h2>
<p>Almost never, and this surprised us. If the nearest fast charger is completely out of order,
driving on to the next working one adds <strong>{m['penalty_mean_km']} km on average</strong>. Only
{m['penalty_over_5km_pct']}% of the country would have to travel more than 5 km further, and the
worst case anywhere is {m['penalty_max_km']} km. Dutch charging density is high enough that a fault
is an annoyance rather than an emergency.</p>

<h2 id="thin">Where cover is genuinely thin</h2>
<p>These are the mainland municipalities whose centre is furthest from a working fast charger.</p>
<div class="tbl-wrap"><table>
<thead><tr><th>Municipality</th><th>km to a working fast charger</th></tr></thead>
<tbody>
{worst}
</tbody></table></div>
<p class="note">The Wadden islands are further still, but the gap is open water rather than road, so
they are listed separately: {isl}. Distances are from the municipal centre, so a town on the edge of
a large municipality may be closer or further than the figure suggests.</p>

<h2 id="avoid">How not to end up here</h2>
<p>The map prices every charge point for the stop you are planning and shows which ones are
reporting a fault, so you can pick one that will actually work.
<a href="/ev-charging">Open the charger map</a>, or read
<a href="/ev-parking">what charging costs in the Netherlands</a>.</p>

<h2 id="faq">Common questions</h2>
{faq_html}

<h2 id="data">The data</h2>
<p>Everything above is downloadable:
<a href="/data/charge-coverage-2026.json">JSON</a> and
<a href="/data/charge-coverage-2026.csv">CSV</a>, CC BY 4.0.
Charge point locations and status come from the national charge point register published through
NDW / DOT-NL; the land outline is CBS municipal boundaries via PDOK.
Measured {m['generated']}.</p>
</div></section>
</body>
</html>
"""


def write_data(m):
    d = ROOT / "data"
    d.mkdir(exist_ok=True)
    (d / "charge-coverage-2026.json").write_text(json.dumps(m, indent=1), "utf-8")
    with open(d / "charge-coverage-2026.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["measure", "median_km", "p90_km", "p95_km", "max_km"])
        for lab, k in (("any_charge_point", "any"), ("fast_charger", "fastest"),
                       ("working_fast_charger", "working")):
            v = m[k]
            w.writerow([lab, v["median"], v["p90"], v["p95"], v["max"]])
        w.writerow([])
        w.writerow(["municipality", "km_to_working_fast_charger", "type"])
        for r in m["worst_mainland"]:
            w.writerow([r["name"], r["km"], "mainland"])
        for r in m["islands"]:
            w.writerow([r["name"], r["km"], "wadden island"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()
    pts = load_points()
    if not pts:
        sys.exit("no charge point cells under ev-data/cells; run the ev export first")
    m = measure(pts, land(a.offline))
    (ROOT / "ev-out-of-charge.html").write_text(render(m), "utf-8")
    write_data(m)
    print(f"out_of_charge: {m['stations']:,} points, {m['fast']:,} fast "
          f"({m['fast_out']} fully out), grid {m['grid_points']:,}")
    print(f"  median to any {m['any']['median']} km, to fast {m['fastest']['median']} km, "
          f"{m['within']['10']}% within 10 km of a working fast charger")
    print(f"  -> ev-out-of-charge.html + data/charge-coverage-2026.json/.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
