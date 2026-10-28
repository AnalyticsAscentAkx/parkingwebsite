#!/usr/bin/env python3
"""Add a "Book nearby with ParkBee" block to garage pages.

ParkBee sells spaces in office and hotel garages that are mostly not in the
national parking register, so they never appear in our price comparison. A
driver looking at a register garage is still served by a bookable space a few
minutes' walk away, and ParkBee is a partner programme (data-aff="parkbee" in
affiliates.js).

Source: scripts/parkbee/parkbee_garages.json, written by
scripts/parkbee/collect.py from ParkBee's own landing pages. Each ParkBee
garage links to the landing page it is booked from.

Idempotent: the block sits between <!-- parkbee:start/end --> markers, is
replaced on every run and removed when no ParkBee garage is near. Runs after
the garage generators in the daily job, because they rewrite these pages.

Usage:
    python3 scripts/seo/parkbee_links.py
"""
import html
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
NEAR_M = 500           # about six minutes on foot
SAME_M = 20            # the ParkBee pin is this register garage
MAX_ROWS = 3

START, END = "<!-- parkbee:start -->", "<!-- parkbee:end -->"
ANCHOR = "<!-- compare:end -->"


def metres(a_lat, a_lon, b_lat, b_lon):
    k = math.pi / 180
    x = (b_lon - a_lon) * k * math.cos((a_lat + b_lat) * k / 2)
    y = (b_lat - a_lat) * k
    return 6371000 * math.hypot(x, y)


def esc(s):
    return html.escape(str(s), quote=True)


def block(g, near):
    short = g["name"].rsplit(" (", 1)[0]
    same = [p for d, p in near if d <= SAME_M]
    rows = [(d, p) for d, p in near if d > SAME_M][:MAX_ROWS]
    out = []
    if same:
        out.append(f'<h2>Book {esc(short)} ahead with ParkBee</h2>')
        out.append(f'<p>ParkBee sells spaces in this car park, booked in advance in its app or on its site. '
                   f'You pay ParkBee\'s rate for the slot plus a one-off service fee, instead of the drive-in tariff above.</p>'
                   f'<p><a class="btn btn-primary btn-sm" data-aff="parkbee" href="{esc(same[0]["url"])}">Book on ParkBee</a></p>')
    if rows:
        out.append(f'<h2>{"Other bookable" if same else "Bookable"} garages near {esc(short)}</h2>')
        out.append('<p>These ParkBee car parks are not in the national register, so their prices are not in our '
                   'comparison. You book a slot ahead in the ParkBee app or on its site; a booking adds a one-off service fee.</p>')
        trs = "".join(
            f'<tr><td>{esc(p["name"])}<br><small>{esc(p.get("address") or "")}</small></td>'
            f'<td class="num">{round(d / 10) * 10:,} m</td>'
            f'<td class="num">{(str(p["max_height_m"]).rstrip("0").rstrip(".") + " m") if p.get("max_height_m") else "not stated"}</td>'
            f'<td><a data-aff="parkbee" href="{esc(p["url"])}">Book on ParkBee</a></td></tr>'
            for d, p in rows)
        out.append('<div class="tbl-wrap"><table><thead><tr><th>Garage</th><th>Walk</th><th>Max height</th><th></th></tr></thead>'
                   f'<tbody>{trs}</tbody></table></div>')
    out.append('<p class="glangs">Partner links: we may earn a commission if you book, at no extra cost to you.</p>')
    return "\n".join(out)


def main():
    pb = json.loads((ROOT / "scripts/parkbee/parkbee_garages.json").read_text("utf-8"))
    ours = json.loads((ROOT / "scripts/garages.json").read_text("utf-8"))
    added = removed = skipped = 0
    for g in ours:
        f = ROOT / "garage" / f'{g["slug"]}.html'
        if not f.exists():
            continue
        text = f.read_text("utf-8")
        near = sorted(((metres(g["lat"], g["lng"], p["lat"], p["lon"]), p) for p in pb), key=lambda x: x[0])
        near = [(d, p) for d, p in near if d <= NEAR_M]
        text = re.sub(re.escape(START) + r".*?" + re.escape(END) + r"\n?", "", text, flags=re.S)
        if near:
            if ANCHOR not in text:
                skipped += 1
                continue
            text = text.replace(ANCHOR, f"{ANCHOR}\n{START}\n{block(g, near)}\n{END}", 1)
            added += 1
        else:
            removed += 1
        if text != f.read_text("utf-8"):
            f.write_text(text, "utf-8")
    print(f"parkbee block on {added} garage pages, none near on {removed}, no anchor on {skipped}")


if __name__ == "__main__":
    main()
