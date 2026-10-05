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
OVERRIDES = ROOT / "data" / "tariff-overrides.json"


def matches(g, m):
    return all(g.get(k) == v for k, v in m.items())


def main():
    garages = json.loads(GARAGES.read_text())
    spec = json.loads(OVERRIDES.read_text())
    total = 0
    for ov in spec["overrides"]:
        hit = [g for g in garages if matches(g, ov["match"])]
        for g in hit:
            for k, v in ov["set"].items():
                g[k] = v
            g["tariff_source"] = ov["source"]
            g["tariff_checked"] = ov["checked"]
            g["tariff_note"] = ov["note"]
        total += len(hit)
        print(f"  {ov['match']} -> {ov['set']}  ({len(hit)} facilities)")
        if not hit:
            print("    WARNING: matched nothing. Has the upstream schema changed?")
    GARAGES.write_text(json.dumps(garages, ensure_ascii=False, indent=1))
    print(f"\n  {total} facilities corrected -> {GARAGES}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
