#!/usr/bin/env python3
"""Remove every public statement that the parking data comes from RDW.

RDW's CC0 bijsluiter forbids naming RDW as the source and using its house
style. The data may still be described as "the national parking register
(NPR)". This rewrites the wording on every public page and in the generators
that produce pages, so the daily job cannot reintroduce it.

Idempotent; prints what changed. Run the audit afterwards.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Ordered: longer, more specific phrases first. Case-sensitive on purpose.
REPLACEMENTS = [
    # links presenting the RDW portal as the source
    (r'<a href="https://opendata\.rdw\.nl"[^>]*>RDW Open Data \(NPR\)</a>, CC0 licence',
     'the national parking register (NPR), CC0 open data'),
    (r'<a href="https://opendata\.rdw\.nl"[^>]*>RDW Open Data</a> \(CC0\)',
     'national parking register open data (CC0)'),
    (r'published as open data by RDW - the same dataset', 'published as CC0 open data - the same dataset'),
    (r'published by RDW \(opendata\.rdw\.nl, CC0 licence\)', 'published as CC0 open data'),
    (r'Source: RDW Open Data / NPR \(CC0\)', 'Source: national parking register (NPR), CC0 open data'),
    (r'DATA: RDW·NPR \(CC0\)', 'DATA: NATIONAL PARKING REGISTER (CC0)'),
    (r'DATA: RDW OPEN DATA · CC0', 'DATA: NATIONAL PARKING REGISTER · CC0'),
    # tariff / register phrasing
    (r'the RDW/NPR tariff table', 'the national parking register (NPR) tariff table'),
    (r'official RDW national parking register', 'official national parking register'),
    (r'the RDW national parking register', 'the national parking register'),
    (r'from the official RDW register', 'from the official national parking register'),
    (r'from the RDW register', 'from the national parking register'),
    (r'Computed from the official RDW register', 'Computed from the official national parking register'),
    (r'official RDW tariff tables', 'official national register tariff tables'),
    (r'official RDW tariff data', 'official national register tariff data'),
    (r'official RDW tariffs', 'official national register tariffs'),
    (r'official RDW data', 'official national register data'),
    (r'RDW official data', 'national register data'),
    (r'Official RDW data', 'Official national register data'),
    # facility / legend wording
    (r'official RDW-registered location', 'listed in the national parking register'),
    (r'RDW-registered parking garages', 'register-listed parking garages'),
    (r'RDW-registered parking garage', 'register-listed parking garage'),
    (r'RDW-registered', 'register-listed'),
    (r'Orange pins are official RDW garages', 'Orange pins are garages from the national parking register'),
    (r'Official Garages \(RDW\)', 'Registered garages (NPR)'),
    (r'Garages \(RDW\)', 'Registered garages'),
    (r'Parking garages with EV charging \(RDW\)', 'Parking garages with EV charging (national register)'),
    (r'\(RDW data\)', '(national register data)'),
    (r'RDW garages with EV charging', 'register garages with EV charging'),
    (r'showing RDW data only', 'showing register data only'),
    (r'RDW Official Parking Data — opendata\.rdw\.nl \(CC0, Nederlandse overheid\)',
     'National parking register (NPR) data, CC0 open data'),
    (r'Joins RDW open data \(opendata\.rdw\.nl, CC0\)', 'Joins national parking register open data (CC0)'),
    (r'sourced from Amsterdam municipality \+ RDW open data', 'sourced from Amsterdam municipality + national parking register open data'),
    (r'Data: <a href="https://opendata\.rdw\.nl"[^>]*>RDW Open Data</a>', 'Data: national parking register open data'),
    (r'<a href="https://opendata\.rdw\.nl"[^>]*>([^<]*)</a>', r'\1'),
]

# OpenStreetMap tile policy: attribution must read "(c) OpenStreetMap contributors"
# and link the copyright page. Several pages abbreviated it to "OSM" or credited
# CARTO for tiles that come from openstreetmap.org.
OSM_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
OSM_ATTR_RE = re.compile(r"""attribution:\s*(['"])(?:(?!\1).)*\1""")


def fix_osm_attribution(path: Path) -> int:
    src = path.read_text("utf-8", errors="surrogateescape")
    if "tile.openstreetmap.org" not in src:
        return 0
    out = OSM_ATTR_RE.sub(lambda m: "attribution:'" + OSM_ATTRIBUTION + "'", src)
    if out != src:
        path.write_text(out, "utf-8", errors="surrogateescape")
        return 1
    return 0

PUBLIC = [p for g in ("*.html", "garage/*.html", "*.js") for p in ROOT.glob(g)]
GENERATORS = [
    ROOT / "scripts/generate_garage_pages.py",
    ROOT / "scripts/daily/generate_poi_page.py",
    ROOT / "scripts/rdw_tariff_sync.py",
    ROOT / "scripts/ev/evlayer/seo/templates.py",
]


def rewrite(path: Path) -> int:
    src = path.read_text("utf-8", errors="surrogateescape")
    out = src
    for pat, rep in REPLACEMENTS:
        out = re.sub(pat, rep, out)
    if out != src:
        path.write_text(out, "utf-8", errors="surrogateescape")
        return 1
    return 0


def main():
    changed = sum(rewrite(p) for p in PUBLIC if p.is_file())
    gens = sum(rewrite(p) for p in GENERATORS if p.exists())
    osm = sum(fix_osm_attribution(p) for p in PUBLIC + GENERATORS if p.is_file())
    print(f"fix_rdw: rewrote {changed} public files, {gens} generator files; OSM attribution fixed in {osm}")
    # What survives (excluding code identifiers) needs a human.
    ident = re.compile(r"RDW_DATA|addRDWMarkers|rdw-data\.js|layers\.rdw|vis\.rdw|['\"]rdw['\"]|Dutch RDW \(vehicle authority\)")
    left = {}
    for p in PUBLIC:
        if not p.is_file():
            continue
        t = ident.sub("", p.read_text("utf-8", errors="replace"))
        for m in re.finditer(r"\bRDW\b", t):
            left.setdefault(p.relative_to(ROOT).as_posix(), []).append(
                re.sub(r"\s+", " ", t[max(0, m.start() - 50): m.end() + 50]))
    if left:
        print(f"still naming RDW in {len(left)} file(s):")
        for f, snips in list(left.items())[:15]:
            print(f"  {f}: …{snips[0]}…")
        return 1
    print("no public RDW statements remain")
    return 0


if __name__ == "__main__":
    sys.exit(main())
