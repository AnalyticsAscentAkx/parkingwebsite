#!/usr/bin/env python3
"""Apply data/tariff-overrides.json to scripts/garages.json.

The register is the right source for where a car park is and how many spaces it
has. It is not the right source for what a municipality charges, and for P+R it
is demonstrably wrong: every Amsterdam P+R site is listed at 1.00 euro for one
hour, three hours and a full day, which is the rate the city dropped years ago.
We published that figure on roughly two hundred pages because we trusted the
feed and never opened the city's own page.

This runs after rdw_tariff_sync so a register refresh cannot quietly put the old
number back, and it prints what it changed so the correction is visible in the
build log rather than buried in a diff.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GARAGES = ROOT / "scripts" / "garages.json"
RDW_JS = ROOT / "rdw-data.js"
OVERRIDES = ROOT / "data" / "tariff-overrides.json"


def matches(g, m):
    return all(g.get(k) == v for k, v in m.items())


def remap_windows(g, mapping):
    """The time-banded tariff carries the same stale amounts as the flat rate,
    and it is the one the garage pages print as a table. Each band is
    [start_hhmm, end_hhmm, first_hour, day]; only the two money columns move,
    and only from a value we are explicitly correcting."""
    w = g.get("windows")
    if not isinstance(w, dict):
        return 0
    n = 0
    for day, bands in w.items():
        for b in bands:
            for i in (2, 3):
                if len(b) > i and b[i] in mapping:
                    b[i] = mapping[b[i]]
                    n += 1
    return n


def main():
    garages = json.loads(GARAGES.read_text())
    spec = json.loads(OVERRIDES.read_text())
    total = 0
    for ov in spec["overrides"]:
        hit = [g for g in garages if matches(g, ov["match"])]
        for g in hit:
            for k, v in ov["set"].items():
                g[k] = v
            if ov.get("remap_windows"):
                wmap = {float(k): v for k, v in ov["remap_windows"].items()}
                remap_windows(g, wmap)
            g["tariff_source"] = ov["source"]
            g["tariff_checked"] = ov["checked"]
            g["tariff_note"] = ov["note"]
        total += len(hit)
        print(f"  {ov['match']} -> {ov['set']}  ({len(hit)} facilities)")
        if not hit:
            print("    WARNING: matched nothing. Has the upstream schema changed?")
    GARAGES.write_text(json.dumps(garages, ensure_ascii=False, indent=1))
    print(f"\n  {total} facilities corrected -> {GARAGES}")
    print(f"  {apply_to_rdw_js(spec)} facilities corrected -> {RDW_JS}")
    return 0


def apply_to_rdw_js(spec):
    """The same correction, applied to the file the MAP reads.

    garages.json feeds the garage pages; rdw-data.js feeds the map and the
    parking search. Only the first was being corrected, so the map showed
    1,00 EUR a day for an Amsterdam P+R while that car park's own page said
    6,00 EUR: a six-fold disagreement between two screens of the same
    product. Found 2026-10-19.

    The file is "const RDW_DATA = { ... };" with a comment header, so the
    object is lifted out by brace matching, corrected, and written back with
    the header intact.
    """
    if not RDW_JS.exists():
        return 0
    text = RDW_JS.read_text("utf-8")
    start = text.find("{")
    depth = 0
    for end, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                break
    data = json.loads(text[start:end + 1])
    n = 0
    for ov in spec["overrides"]:
        wmap = {float(k): v for k, v in (ov.get("remap_windows") or {}).items()}
        for city, rows in data.items():
            for g in rows:
                # The two files describe the same facilities with different
                # keys: garages.json has "city" and "is_pr", rdw-data.js has
                # the city as its dict key and spells the flag "pr". Normalise
                # before matching, or the override silently corrects nothing.
                probe = dict(g, city=city)
                if "pr" in g and "is_pr" not in g:
                    probe["is_pr"] = bool(g["pr"])
                if not matches(probe, ov["match"]):
                    continue
                for k, v in ov["set"].items():
                    g[k] = v
                if wmap:
                    remap_windows(g, wmap)
                n += 1
    RDW_JS.write_text(text[:start] + json.dumps(data, ensure_ascii=False) + text[end + 1:], "utf-8")
    return n


if __name__ == "__main__":
    sys.exit(main())
