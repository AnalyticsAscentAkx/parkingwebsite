#!/usr/bin/env python3
"""A daily scorecard that answers one question: is this getting better?

Most analytics reports show levels. Levels on a site this size are noise: 14
sessions one day and 9 the next means nothing. What means something is the
direction over a week, so every number here is the last 7 days against the 7
before it, and the report leads with the single figure that matters rather
than a wall of them.

The metrics are ordered as a funnel, because that is where the answer lives.
Pages have to be indexed before they can be shown, shown before they can be
clicked, clicked before anyone arrives. When clicks are flat, the funnel says
which stage is holding it up, which a dashboard of totals never does.

Deliberately absent: pageviews, engagement rate, bounce rate, time on page.
At this volume they move randomly and invite reading meaning into noise.

Usage:
  python3 scorecard.py            # write and print
  python3 scorecard.py --quiet
"""
import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OUT = REPO / "data" / "qa"
KEY = os.environ.get("GSC_SA_KEY", os.path.expanduser(
    "~/.secrets/parkingnetherlands-gsc.json"))
PROP = os.environ.get("GSC_PROPERTY", "sc-domain:parkingnetherlands.com")
GA4 = os.environ.get("GA4_PROPERTY_ID", "503850038")

# Search Console data is incomplete for the last two or three days, so a
# window that includes them always looks like a decline. End three days back.
LAG = 3


def arrow(now, before, higher_is_better=True, pct=False):
    """A change is worth showing only if it is big enough to act on."""
    if before in (None, 0):
        return ("new" if now else "flat"), "="
    d = (now - before) / before
    if abs(d) < 0.05:
        return "flat", "="
    good = (d > 0) == higher_is_better
    sign = "+" if d > 0 else ""
    return f"{sign}{d*100:.0f}%", ("up" if good else "down")


def gsc():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    c = service_account.Credentials.from_service_account_file(
        KEY, scopes=["https://www.googleapis.com/auth/webmasters.readonly"])
    s = build("searchconsole", "v1", credentials=c, cache_discovery=False)
    end = date.today() - timedelta(days=LAG)

    def window(days_back_start, days_back_end, dims=None, n=25):
        body = {"startDate": (end - timedelta(days=days_back_start)).isoformat(),
                "endDate": (end - timedelta(days=days_back_end)).isoformat(),
                "rowLimit": n}
        if dims:
            body["dimensions"] = dims
        return s.searchanalytics().query(siteUrl=PROP, body=body).execute().get("rows", [])

    def totals(a, b):
        r = window(a, b)
        if not r:
            return dict(clicks=0, impressions=0, ctr=0, position=0)
        x = r[0]
        return dict(clicks=x["clicks"], impressions=x["impressions"],
                    ctr=x["ctr"], position=x["position"])

    return {"now": totals(6, 0), "prev": totals(13, 7),
            "pages": window(6, 0, ["page"], 10)}


def ga4():
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import (
            DateRange, Dimension, Metric, RunReportRequest)
        from google.oauth2 import service_account
    except ImportError:
        return None
    c = service_account.Credentials.from_service_account_file(
        KEY, scopes=["https://www.googleapis.com/auth/analytics.readonly"])
    cl = BetaAnalyticsDataClient(credentials=c)

    def run(start, end, dims=(), mets=("sessions",), limit=20):
        r = cl.run_report(RunReportRequest(
            property=f"properties/{GA4}",
            date_ranges=[DateRange(start_date=start, end_date=end)],
            dimensions=[Dimension(name=d) for d in dims],
            metrics=[Metric(name=m) for m in mets], limit=limit))
        return [([v.value for v in x.dimension_values],
                 [float(v.value) for v in x.metric_values]) for x in r.rows]

    def one(start, end):
        r = run(start, end, (), ("sessions", "totalUsers"))
        return (r[0][1] if r else [0, 0])

    now, prev = one("7daysAgo", "today"), one("14daysAgo", "8daysAgo")
    # The map is the product. Using it is the only event that means someone
    # got what they came for.
    ev = run("7daysAgo", "today", ("eventName",), ("eventCount",), 25)
    product = {k[0]: v[0] for k, v in ev
               if k[0] in ("search", "select", "directions", "near_me",
                           "start_charging", "results_shown")}
    return {"sessions": now[0], "users": now[1],
            "prev_sessions": prev[0], "product": product}


def indexing():
    # Two copies exist: this working tree and the automation clone that the
    # scheduled watcher actually writes to. Preferring the local one read a
    # stale file and reported zero pages indexed. Take whichever was written
    # most recently.
    cands = [REPO / "data" / "gsc" / "index_watch.jsonl",
             Path.home() / "parking-site" / "data" / "gsc" / "index_watch.jsonl"]
    cands = [c for c in cands if c.is_file()]
    if not cands:
        return None
    src = max(cands, key=lambda c: c.stat().st_mtime)
    h = [json.loads(l) for l in src.read_text().splitlines() if l.strip()]
    if not h:
        return None
    # Weight by real section size, never a plain average of the section rates:
    # the sections differ by a factor of eighty and an unweighted mean reads
    # roughly double the truth.
    sizes = {"en pages": 116, "en garages": 324, "nl pages": 16,
             "nl garages": 323, "de pages": 16, "de garages": 323,
             "fr pages": 16, "fr garages": 323}
    def est(entry):
        tot = 0
        for sec, n in sizes.items():
            b = entry["sections"].get(sec)
            if b and b["n"]:
                tot += b["indexed"] / b["n"] * n
        return tot
    now = est(h[-1])
    week = next((est(e) for e in h if e["at"] >= (
        date.today() - timedelta(days=7)).isoformat()), None)
    canaries = h[-1].get("canaries") or {}
    return {"now": now, "week_ago": week, "total": sum(sizes.values()),
            "key_indexed": sum(1 for v in canaries.values() if v.get("verdict") == "PASS"),
            "key_total": len(canaries)}


def health():
    f = OUT / "issues.json"
    if not f.is_file():
        return None
    d = json.loads(f.read_text())
    return {"hard": d.get("hard", 0), "warn": d.get("warn", 0)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    try:
        g = gsc()
    except Exception as e:
        sys.exit(f"ERROR reading Search Console: {str(e)[:200]}")
    an = ga4()
    ix = indexing()
    hl = health()

    n, p = g["now"], g["prev"]
    L = []
    L.append(f"# Scorecard {date.today().isoformat()}")
    L.append("")

    # The headline. Clicks from search is the only number that is unambiguously
    # the goal; everything else is either upstream of it or a proxy.
    chg, dirn = arrow(n["clicks"], p["clicks"])
    verdict = {"up": "Better", "down": "Worse", "=": "Flat"}[dirn]
    L.append(f"## {verdict}: {n['clicks']:.0f} clicks this week, "
             f"{p['clicks']:.0f} the week before ({chg})")
    L.append("")
    L.append("_Search Console, seven days ending three days ago; the last "
             "few days are always incomplete._")
    L.append("")

    L.append("## The funnel")
    L.append("")
    L.append("| Stage | This week | Last week | Change |")
    L.append("|---|---|---|---|")
    if ix:
        c, _ = arrow(ix["now"], ix["week_ago"])
        was = f"{ix['week_ago']:.0f}" if ix['week_ago'] else "n/a"
        L.append(f"| Pages indexed | {ix['now']:.0f} of {ix['total']} | "
                 f"{was} | {c} |")
    c, _ = arrow(n["impressions"], p["impressions"])
    L.append(f"| Impressions | {n['impressions']:.0f} | {p['impressions']:.0f} | {c} |")
    c, _ = arrow(n["position"], p["position"], higher_is_better=False)
    L.append(f"| Average position | {n['position']:.1f} | {p['position']:.1f} | {c} |")
    c, _ = arrow(n["ctr"], p["ctr"])
    L.append(f"| Click-through rate | {n['ctr']*100:.1f}% | {p['ctr']*100:.1f}% | {c} |")
    c, _ = arrow(n["clicks"], p["clicks"])
    L.append(f"| Clicks | {n['clicks']:.0f} | {p['clicks']:.0f} | {c} |")
    if an:
        c, _ = arrow(an["sessions"], an["prev_sessions"])
        L.append(f"| Sessions, consented | {an['sessions']:.0f} | "
                 f"{an['prev_sessions']:.0f} | {c} |")
    L.append("")
    L.append("Read it top down. A stage that is flat while the one above it "
             "grew is where the problem is.")
    L.append("")

    if an and an["product"]:
        L.append("## Did anyone use the thing")
        L.append("")
        for k, v in sorted(an["product"].items(), key=lambda x: -x[1]):
            L.append(f"- {k}: {v:.0f}")
        L.append("")
        L.append("_Map interactions, not page views. Someone searching or "
                 "opening a charger got what they came for; someone who "
                 "loaded a page may not have._")
        L.append("")

    if ix and ix["key_total"]:
        L.append(f"## Key pages indexed: {ix['key_indexed']} of {ix['key_total']}")
        L.append("")

    L.append("## Best and worst pages this week")
    L.append("")
    L.append("| Page | Clicks | Impressions | CTR |")
    L.append("|---|---|---|---|")
    for r in g["pages"][:8]:
        u = r["keys"][0].replace("https://parkingnetherlands.com", "") or "/"
        L.append(f"| `{u}` | {r['clicks']:.0f} | {r['impressions']:.0f} | "
                 f"{r['ctr']*100:.1f}% |")
    L.append("")
    waste = [r for r in g["pages"] if r["impressions"] >= 40 and r["ctr"] < 0.02]
    if waste:
        w = max(waste, key=lambda r: r["impressions"])
        u = w["keys"][0].replace("https://parkingnetherlands.com", "") or "/"
        L.append(f"**Biggest waste:** `{u}` took {w['impressions']:.0f} "
                 f"impressions and {w['clicks']:.0f} clicks "
                 f"({w['ctr']*100:.1f}%). Rewrite its title and description "
                 f"before writing anything new.")
        L.append("")

    if hl:
        L.append(f"## Site health: {hl['hard']} hard, {hl['warn']} warnings")
        L.append("")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "scorecard.md").write_text("\n".join(L))
    if not a.quiet:
        print("\n".join(L))
    else:
        print(f"scorecard -> {OUT / 'scorecard.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
