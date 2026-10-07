#!/usr/bin/env python3
"""Turn an operator outage into a post while people are searching for it.

The 26 <operator>-storing pages already carry today's fault share per operator,
refreshed every half hour. Nobody looks at them until Fastned or Shell goes
down, and that is the hour "fastned storing" spikes in search. This script
keeps a daily log of each operator's fault share, and when today's share is a
spike against the trailing 30 days it drafts a post (English and Dutch) with
the numbers and the link, ready to paste into a forum, Reddit or LinkedIn.

  python3 scripts/alerts/outage_watch.py            # log today, draft alerts
  python3 scripts/alerts/outage_watch.py --dry-run  # show what would be drafted

Log: data/alerts/operator-down.jsonl (one line per operator per day).
Drafts: outreach/alerts/<date>-<operator>.md. Nothing is posted anywhere;
the owner decides. Needs 7 days of log before it can call a spike.
"""
import json, re, sys, datetime, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / "data/alerts/operator-down.jsonl"
DRAFTS = ROOT / "outreach/alerts"
TODAY = datetime.date.today().isoformat()
MIN_HISTORY = 7
MIN_POINTS = 100          # tiny operators flap; a spike at 12 posts is noise

META_RE = re.compile(r'content="(\d+) van de ([\d.]+) openbare (.+?)-laadpunten staan nu als buiten gebruik gemeld, ([\d,]+)% tegen ([\d,]+)% landelijk')

def read_today():
    rows = []
    for p in sorted(ROOT.glob("*-storing.html")):
        m = META_RE.search(p.read_text("utf-8", errors="ignore"))
        if not m: continue
        down, total, name = int(m.group(1)), int(m.group(2).replace(".", "")), m.group(3)
        rows.append({"day": TODAY, "slug": p.stem, "operator": name, "down": down, "total": total,
                     "pct": float(m.group(4).replace(",", ".")), "national": float(m.group(5).replace(",", "."))})
    return rows

def history():
    if not LOG.exists(): return {}
    out = {}
    for line in LOG.read_text("utf-8").splitlines():
        if not line.strip(): continue
        r = json.loads(line)
        out.setdefault(r["slug"], {})[r["day"]] = r
    return out

def is_spike(today, past):
    """Today is a spike when it is at least double the trailing median and at
    least two points above it, on an operator big enough to matter."""
    if today["total"] < MIN_POINTS or len(past) < MIN_HISTORY: return None
    med = statistics.median(r["pct"] for r in past)
    if today["pct"] >= max(2 * med, med + 2.0, 3.0):
        return med
    return None

def draft(t, med):
    op, pct, nat = t["operator"], t["pct"], t["national"]
    url = f"https://parkingnetherlands.com/{t['slug']}"
    en = (f"{op} has {t['down']} of its {t['total']:,} public charge points in the Netherlands reported out of order right now, "
          f"{pct:.1f}% against a 30-day median of {med:.1f}% and a national figure of {nat:.1f}%. "
          f"Per city, updated every half hour, from the national charge point register: {url}")
    nl = (f"Bij {op} staan nu {t['down']} van de {t['total']:,} openbare laadpunten in Nederland als buiten gebruik gemeld, "
          f"{pct:.1f}% tegen een mediaan van {med:.1f}% over 30 dagen en {nat:.1f}% landelijk. "
          f"Per stad, elk half uur bijgewerkt, uit het nationaal laadpuntenregister: {url}").replace(",", " ").replace(".", ",").replace(" ", ".")
    # the replace dance above swaps decimal and thousands separators for Dutch; URLs have no digits with separators
    nl = nl.replace("parkingnetherlands,com", "parkingnetherlands.com").replace("https://", "https://")
    return f"""# Outage draft: {op}, {TODAY}

Nothing has been posted. Check the operator's own status page first; if the
fault is real, paste one of these where people are asking. Reddit
r/elektrischrijden and the Tweakers EV forum pick up operator outages within
the hour; LinkedIn from the Analytics Ascent account for the data angle.

## English

{en}

## Nederlands

{nl}

## Numbers

| | Today | 30-day median | National |
|---|---|---|---|
| Out of order | {pct:.1f}% ({t['down']} of {t['total']:,}) | {med:.1f}% | {nat:.1f}% |
"""

def main():
    dry = "--dry-run" in sys.argv
    today = read_today()
    if not today:
        print("outage_watch: no operator pages found"); return 1
    past = history()
    cutoff = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    alerts = []
    for t in today:
        prev = [r for d, r in past.get(t["slug"], {}).items() if cutoff <= d < TODAY]
        med = is_spike(t, prev)
        if med is not None: alerts.append((t, med))
    if not dry:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        kept = [l for l in (LOG.read_text("utf-8").splitlines() if LOG.exists() else []) if l.strip() and json.loads(l)["day"] != TODAY]
        LOG.write_text("\n".join(kept + [json.dumps(r, ensure_ascii=False) for r in today]) + "\n", "utf-8")
        DRAFTS.mkdir(parents=True, exist_ok=True)
        for t, med in alerts:
            (DRAFTS / f"{TODAY}-{t['slug']}.md").write_text(draft(t, med), "utf-8")
    days = len({d for s in past.values() for d in s})
    print(f"outage_watch: {len(today)} operators logged for {TODAY}, {days} days of history, {len(alerts)} alert(s)" + (" (dry run)" if dry else ""))
    for t, med in alerts:
        print(f"  ALERT {t['operator']}: {t['pct']:.1f}% out of order vs median {med:.1f}% -> outreach/alerts/{TODAY}-{t['slug']}.md")
    return 0

if __name__ == "__main__":
    sys.exit(main())
