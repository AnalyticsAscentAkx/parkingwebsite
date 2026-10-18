#!/usr/bin/env python3
"""Find what to improve next, with the evidence attached, and rank it.

This automates the hunt that produced the 2026-10-18 fixes. That day the
useful findings came from putting three sources beside each other rather than
from any one of them:

  * Analytics said 28 of 134 visitors hit an empty result list, and that six
    people tapped "near me" sixty-two times between them.
  * The published charger data said why: a good GPS fix zooms to a single
    street, and three of nine Dutch residential spots have no charger inside
    that box.
  * The index watch said one page was unknown to Google, and the sitemap said
    that same page was the only one of 1,467 with no date on it.

None of those is a finding alone. Together they are three fixes.

IT DOES NOT CHANGE THE SITE. It writes data/qa/improvements.md and exits.
That is deliberate: on the day this was written, two changes backed by good
analytics were shipped without a rendering check and had to be reverted
within hours. Evidence that a change should help is not evidence that it
did, so a human decides, and scripts/qa/smoke_map.py guards the result.

Usage:
    python3 scripts/qa/improve.py              # last 60 days
    python3 scripts/qa/improve.py --days 28
    python3 scripts/qa/improve.py --json
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "qa"
SITE = "https://parkingnetherlands.com"
KEY = os.environ.get("GSC_SA_KEY", os.path.expanduser("~/.secrets/parkingnetherlands-gsc.json"))
PROPERTY = os.environ.get("GA4_PROPERTY_ID", "503850038")
# Arrivals from the agency site are the owner. Two weeks running they were a
# fifth of all sessions, and reading them as visitors flatters every number.
OWNER_REFERRER = "analyticascent.com"


# ------------------------------------------------------------------ analytics
def ga_events(days):
    """eventName -> (events, users), owner traffic removed. {} if unavailable."""
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import (
            DateRange, Dimension, Metric, RunReportRequest, FilterExpression, Filter)
        from google.oauth2 import service_account
    except Exception:
        return None
    try:
        creds = service_account.Credentials.from_service_account_file(
            KEY, scopes=["https://www.googleapis.com/auth/analytics.readonly"])
        client = BetaAnalyticsDataClient(credentials=creds)
        end = date.today()
        start = end - timedelta(days=days)
        req = RunReportRequest(
            property=f"properties/{PROPERTY}",
            date_ranges=[DateRange(start_date=start.isoformat(), end_date=end.isoformat())],
            dimensions=[Dimension(name="eventName")],
            metrics=[Metric(name="eventCount"), Metric(name="totalUsers")],
            dimension_filter=FilterExpression(not_expression=FilterExpression(
                filter=Filter(field_name="sessionSource", string_filter=Filter.StringFilter(
                    value=OWNER_REFERRER,
                    match_type=Filter.StringFilter.MatchType.CONTAINS)))),
            limit=60)
        rows = client.run_report(req).rows
        return {r.dimension_values[0].value:
                (int(float(r.metric_values[0].value)), int(float(r.metric_values[1].value)))
                for r in rows}
    except Exception:
        return None


# --------------------------------------------------------------------- checks
def check_interaction(ev, findings):
    if not ev:
        findings.append(("info", "analytics", "Analytics unavailable",
                         "No interaction evidence this run. Check the key at "
                         f"{KEY} and that google-analytics-data is installed."))
        return
    users = ev.get("first_visit", (0, 0))[1] or ev.get("session_start", (0, 0))[1]
    zero = ev.get("zero_results", (0, 0))
    shown = ev.get("results_shown", (0, 0))
    near = ev.get("near_me", (0, 0))
    filt = ev.get("filter", (0, 0))
    srt = ev.get("sort", (0, 0))
    sel = ev.get("select", (0, 0))
    dirs = ev.get("directions", (0, 0))

    total_renders = zero[0] + shown[0]
    if total_renders and zero[0] / total_renders > 0.25:
        findings.append(("high", "empty results",
                         f"{zero[0]} of {total_renders} result renders were empty "
                         f"({100*zero[0]/total_renders:.0f}%), hitting {zero[1]} users"
                         + (f" of {users}" if users else ""),
                         "Register `reason` as a GA4 custom dimension to split this by "
                         "filters / outside_nl / empty_area, then fix the dominant one."))
    if near[1] and near[0] / max(near[1], 1) > 4:
        findings.append(("high", "near me",
                         f"{near[0]} taps from only {near[1]} people "
                         f"({near[0]/near[1]:.1f} each)",
                         "Repeated taps mean the first one did not satisfy. Check what the "
                         "map shows immediately after a locate, not just that it located."))
    if users and filt[1] / max(users, 1) < 0.10:
        findings.append(("medium", "filters",
                         f"filters used by {filt[1]} of {users} visitors ({filt[0]} events)",
                         "A control this cold should not occupy prime space. Note that the "
                         "chips render twice, once over the map and once in the panel."))
    if users and srt[0] <= 2:
        findings.append(("low", "sort",
                         f"sort used {srt[0]} time(s) by {srt[1]} person",
                         "Four permanent buttons for this. Consider folding into the list header."))
    if sel[0] and dirs[0] / max(sel[0], 1) < 0.15:
        findings.append(("medium", "funnel",
                         f"{sel[0]} cards opened but only {dirs[0]} directions taps",
                         "People open a card and stop. Look at what the card asks them to do next."))


def check_indexing(findings):
    path = ROOT / "data" / "gsc" / "index_watch.jsonl"
    if not path.exists():
        return
    try:
        rows = [json.loads(l) for l in path.read_text("utf-8").splitlines() if l.strip()]
        last = rows[-1]
    except Exception:
        return
    tot = last.get("total", {})
    n, idx = tot.get("n", 0), tot.get("indexed", 0)
    if n and idx / n < 0.75:
        findings.append(("high", "indexing",
                         f"{idx} of {n} sampled URLs indexed ({100*idx/n:.0f}%)",
                         "Worst sections first: " + ", ".join(
                             f"{k} {v.get('indexed')}/{v.get('n')}"
                             for k, v in sorted(last.get("sections", {}).items(),
                                                key=lambda kv: kv[1].get("indexed", 0))[:3])))
    unknown = [u for u, v in last.get("canaries", {}).items()
               if "unknown" in str(v.get("coverage", "")).lower()]
    if unknown:
        findings.append(("high", "indexing",
                         f"Google reports {len(unknown)} key page(s) as unknown: "
                         + ", ".join(unknown),
                         "Check the sitemap entry, internal links and the canonical for each "
                         "before assuming it is an authority problem."))


def check_sitemap(findings):
    try:
        sm = urllib.request.urlopen(SITE + "/sitemap.xml", timeout=30).read().decode("utf-8", "replace")
    except Exception:
        return
    urls = re.findall(r"<url>(.*?)</url>", sm, re.S)
    if not urls:
        return
    missing = [u for u in urls if "<lastmod>" not in u]
    if missing:
        locs = [re.search(r"<loc>([^<]+)</loc>", u).group(1).replace(SITE, "") for u in missing[:5]]
        findings.append(("medium", "sitemap",
                         f"{len(missing)} of {len(urls)} URLs have no <lastmod>",
                         "e.g. " + ", ".join(locs) +
                         ". A page claiming daily change with no date to back it is a weak signal."))
    dupes = [u for u in urls if u.count("<lastmod>") > 1]
    if dupes:
        findings.append(("high", "sitemap", f"{len(dupes)} URLs carry more than one <lastmod>",
                         "The sitemap generator is writing duplicates; the file may not validate."))


def check_render(findings):
    """Run the render guard and report it here too, so one file tells the story."""
    import subprocess
    smoke = ROOT / "scripts" / "qa" / "smoke_map.py"
    if not smoke.exists():
        return
    try:
        r = subprocess.run([sys.executable, str(smoke), "--json"],
                           capture_output=True, text=True, timeout=600)
        data = json.loads(r.stdout or "{}")
    except Exception as e:
        findings.append(("info", "render", "Render check could not run", str(e)[:120]))
        return
    fails = data.get("failures") or []
    if fails:
        findings.append(("high", "render", f"The live map failed {len(fails)} render check(s)",
                         " | ".join(fails[:3])))


# --------------------------------------------------------------------- report
RANK = {"high": 0, "medium": 1, "low": 2, "info": 3}


def write_report(findings, days):
    findings.sort(key=lambda f: RANK.get(f[0], 9))
    lines = [f"# What to improve next", "",
             f"Generated {date.today().isoformat()} by scripts/qa/improve.py, "
             f"{days} days of analytics with owner traffic removed.", "",
             "This file changes nothing on its own. Each item is a claim with the "
             "evidence next to it; a person decides, and scripts/qa/smoke_map.py "
             "guards whatever ships.", ""]
    if not findings:
        lines += ["Nothing stood out this run.", ""]
    for sev, area, claim, detail in findings:
        lines += [f"## [{sev}] {area}: {claim}", "", detail, ""]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "improvements.md").write_text("\n".join(lines) + "\n", "utf-8")
    return OUT / "improvements.md"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--skip-render", action="store_true")
    a = ap.parse_args()

    findings = []
    check_interaction(ga_events(a.days), findings)
    check_indexing(findings)
    check_sitemap(findings)
    if not a.skip_render:
        check_render(findings)
    path = write_report(findings, a.days)

    if a.json:
        print(json.dumps([{"severity": s, "area": ar, "claim": c, "detail": d}
                          for s, ar, c, d in findings], indent=1))
    else:
        print(f"improve: {len(findings)} finding(s) -> {path.relative_to(ROOT)}")
        for sev, area, claim, _ in findings:
            print(f"  [{sev:6}] {area}: {claim}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
