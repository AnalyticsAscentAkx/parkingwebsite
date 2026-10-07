#!/usr/bin/env python3
"""Notice the day the Dutch charge point feed starts carrying the AFIR fields.

The OCPI NAP Data Extension 1.0 (September 2026) adds fields to the NDW feed
and makes others mandatory. None of the new ones is populated yet. When an
operator fills one in, or when a watched field jumps by ten points, that is
a story (the scorecard page changes) and a data upgrade for the map. This
script compares today's field counts, as written by scripts/seo/afir_scorecard.py
into data/afir-scorecard-2026.json, with the previous run and drafts a note.

  python3 scripts/alerts/feed_fields_watch.py            # log today, draft on change
  python3 scripts/alerts/feed_fields_watch.py --dry-run

Log: data/alerts/feed-fields.jsonl (one line per day). Drafts: outreach/alerts/<date>-feed-fields.md.
"""
import json, sys, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data/afir-scorecard-2026.json"
LOG = ROOT / "data/alerts/feed-fields.jsonl"
DRAFTS = ROOT / "outreach/alerts"
TODAY = datetime.date.today().isoformat()
JUMP = 10.0   # percentage points of the relevant population

# (label, group, key, population group) : population is what the share is taken over
WATCH = [
    ("operator legal name",        "location", "legal_name",     "location"),
    ("NUTS region",                "location", "region",         "location"),
    ("service support",            "location", "services",       "location"),
    ("helpdesk phone",             "location", "help_phone",     "location"),
    ("parking places",             "location", "parking_places", "location"),
    ("card brands accepted",       "evse",     "payment_brands", "evse"),
    ("contactless payment",        "capability", "CONTACTLESS_CARD_SUPPORT", "evse"),
    ("bank card reader",           "capability", "CREDIT_CARD_PAYABLE", "evse"),
    ("ad hoc tariff typed",        "tariff_type", "AD_HOC_PAYMENT", "tariff"),
    ("tariff type present (any)",  "tariff",   "type",           "tariff"),
    ("status UNKNOWN",             "status",   "UNKNOWN",        "evse"),
]

def snapshot():
    d = json.loads(SRC.read_text("utf-8"))
    f = d["fields"]
    pop = {"location": d["locations"], "tariff": d["tariffs"], "evse": sum(f["status"].values())}
    out = {"day": d["snapshot"], "pop": pop, "fields": {}}
    for label, grp, key, pg in WATCH:
        cnt = f.get(grp, {}).get(key, 0)
        out["fields"][label] = {"count": cnt, "pct": round(100.0 * cnt / pop[pg], 2) if pop[pg] else 0.0}
    return out

def previous():
    if not LOG.exists(): return None
    lines = [l for l in LOG.read_text("utf-8").splitlines() if l.strip()]
    return json.loads(lines[-1]) if lines else None

def changes(now, prev):
    out = []
    for label, cur in now["fields"].items():
        was = (prev or {}).get("fields", {}).get(label, {"count": 0, "pct": 0.0})
        if was["count"] == 0 and cur["count"] > 0:
            out.append((label, was, cur, "first appearance"))
        elif abs(cur["pct"] - was["pct"]) >= JUMP:
            out.append((label, was, cur, "jump"))
    return out

def draft(now, diff):
    DRAFTS.mkdir(parents=True, exist_ok=True)
    p = DRAFTS / f"{TODAY}-feed-fields.md"
    rows = "\n".join(f"| {l} | {w['count']:,} ({w['pct']}%) | {c['count']:,} ({c['pct']}%) | {why} |" for l, w, c, why in diff)
    p.write_text(f"""# The NDW charge point feed changed on {TODAY}

| Field | Before | Now | What |
|---|---|---|---|
{rows}

Scorecard: https://parkingnetherlands.com/afir-scorecard (rebuilt today with these numbers).

Post, if it is the ad hoc price or card payment moving:

> The Dutch charge point register just started publishing [field]. Six months after the AFIR
> deadline that is the first time a driver without a subscription can read [what it means]
> from the national data. Field by field, per operator: https://parkingnetherlands.com/afir-scorecard

Also: if a new field appeared (legal_name, region, services, payment_brands, parking_places),
the map can use it; open an issue for the ev-map build.
""", "utf-8")
    return p

def main():
    dry = "--dry-run" in sys.argv
    if not SRC.exists():
        print("feed watch: no scorecard data yet"); return
    now = snapshot(); prev = previous()
    diff = changes(now, prev)
    if prev and prev["day"] == now["day"]:
        print(f"feed watch: already logged {now['day']}");
    elif not dry:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh: fh.write(json.dumps(now, ensure_ascii=False) + "\n")
    if prev is None:
        print("feed watch: first snapshot logged, nothing to compare"); return
    if diff:
        p = None if dry else draft(now, diff)
        for l, w, c, why in diff: print(f"feed watch: CHANGE {l}: {w['count']:,} -> {c['count']:,} ({why})")
        if p: print(f"feed watch: draft {p.relative_to(ROOT)}")
    else:
        print("feed watch: no field changes")

if __name__ == "__main__":
    main()
