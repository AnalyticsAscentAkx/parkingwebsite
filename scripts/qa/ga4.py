#!/usr/bin/env python3
"""Pull GA4 behaviour and put it beside what Search Console says.

The two answer different questions and the gap between them is the useful
part. Search Console says how many people chose the site from a results page;
GA4 says what happened to them after. A page with impressions and no sessions
is an indexing or snippet problem; sessions with no engagement is a page
problem.

Auth is the same service account as everything else. It must be added as a
Viewer on the GA4 property itself: Admin > Property access management. Google
Cloud project access is not enough and the API will return 403 until it is
done.

Usage:
  GA4_PROPERTY_ID=123456789 python3 ga4.py
  python3 ga4.py --days 28
"""
import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent.parent / "data" / "qa"
KEY = os.environ.get("GSC_SA_KEY", os.path.expanduser(
    "~/.secrets/parkingnetherlands-gsc.json"))


def client():
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.oauth2 import service_account
    creds = service_account.Credentials.from_service_account_file(
        KEY, scopes=["https://www.googleapis.com/auth/analytics.readonly"])
    return BetaAnalyticsDataClient(credentials=creds)


def discover_property():
    """Find the property without hardcoding an id that may be the wrong one.

    This account has had more than one 'Parking Netherlands' property, one of
    them in a personal Gmail that must never be used, so resolving it from the
    service account's own access is safer than remembering a number.
    """
    import urllib.request
    from google.oauth2 import service_account
    import google.auth.transport.requests as tr
    c = service_account.Credentials.from_service_account_file(
        KEY, scopes=["https://www.googleapis.com/auth/analytics.readonly"])
    c.refresh(tr.Request())
    req = urllib.request.Request(
        "https://analyticsadmin.googleapis.com/v1beta/accountSummaries",
        headers={"Authorization": "Bearer " + c.token})
    d = json.load(urllib.request.urlopen(req, timeout=30))
    props = []
    for a in d.get("accountSummaries", []):
        for p in a.get("propertySummaries", []):
            props.append((a.get("displayName"), p.get("displayName"),
                          p.get("property", "").split("/")[-1]))
    return props


def report(cid, days):
    from google.analytics.data_v1beta.types import (
        DateRange, Dimension, Metric, RunReportRequest)
    c = client()
    end = date.today()
    start = end - timedelta(days=days)
    rng = [DateRange(start_date=start.isoformat(), end_date=end.isoformat())]

    def run(dims, mets, limit=15):
        r = c.run_report(RunReportRequest(
            property=f"properties/{cid}", date_ranges=rng,
            dimensions=[Dimension(name=d) for d in dims],
            metrics=[Metric(name=m) for m in mets], limit=limit))
        return [([v.value for v in row.dimension_values],
                 [v.value for v in row.metric_values]) for row in r.rows]

    out = {"property": cid, "days": days,
           "from": start.isoformat(), "to": end.isoformat()}
    tot = run([], ["sessions", "totalUsers", "screenPageViews",
                   "averageSessionDuration", "bounceRate"])
    if tot:
        d, m = tot[0]
        out["totals"] = dict(sessions=int(float(m[0])), users=int(float(m[1])),
                             pageviews=int(float(m[2])),
                             avg_seconds=round(float(m[3]), 1),
                             bounce_rate=round(float(m[4]) * 100, 1))
    out["by_channel"] = [{"channel": d[0], "sessions": int(float(m[0]))}
                         for d, m in run(["sessionDefaultChannelGroup"], ["sessions"])]
    out["top_pages"] = [{"page": d[0], "views": int(float(m[0])),
                         "avg_seconds": round(float(m[1]), 1)}
                        for d, m in run(["pagePath"], ["screenPageViews",
                                                       "userEngagementDuration"])]
    out["by_country"] = [{"country": d[0], "sessions": int(float(m[0]))}
                         for d, m in run(["country"], ["sessions"], 8)]
    out["by_device"] = [{"device": d[0], "sessions": int(float(m[0]))}
                        for d, m in run(["deviceCategory"], ["sessions"])]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=28)
    ap.add_argument("--property", default=os.environ.get("GA4_PROPERTY_ID"))
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    if a.list or not a.property:
        try:
            props = discover_property()
        except Exception as e:
            sys.exit(f"ERROR listing properties: {str(e)[:300]}")
        if not props:
            sys.exit("No GA4 properties visible. Add "
                     "parkingnetherlands-gsc@arctic-marking-486216-f3"
                     ".iam.gserviceaccount.com as a Viewer under "
                     "GA4 Admin > Property access management.")
        for acct, name, pid in props:
            print(f"  {pid:14} {name}   (account: {acct})")
        if a.list:
            return 0
        a.property = props[0][2]
        print(f"\nusing property {a.property}\n")

    try:
        d = report(a.property, a.days)
    except Exception as e:
        sys.exit(f"ERROR: {str(e)[:400]}")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "ga4.json").write_text(json.dumps(d, indent=1))
    t = d.get("totals", {})
    print(f"GA4 {d['from']} to {d['to']}")
    print(f"  sessions {t.get('sessions',0):,}   users {t.get('users',0):,}   "
          f"views {t.get('pageviews',0):,}")
    print(f"  avg session {t.get('avg_seconds',0)}s   bounce {t.get('bounce_rate',0)}%")
    print("\n  channels:")
    for c in d["by_channel"][:6]:
        print(f"    {c['sessions']:6,}  {c['channel']}")
    print("\n  top pages:")
    for p in d["top_pages"][:10]:
        print(f"    {p['views']:6,}  {p['page'][:52]}")
    print(f"\n-> {OUT / 'ga4.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
