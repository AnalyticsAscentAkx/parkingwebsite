#!/usr/bin/env python3
"""Write the one usage number the map shows visitors: stops priced recently.

A "stop priced" is a GA4 `select` event, fired when someone opens a charger
or car park and sees the price for their stay. Map pans fire results_shown
on every move, so that event would overstate real use and is not counted.

The figure is a floor, not an estimate: GA4 only sees visitors who accepted
analytics cookies, and the owner's own traffic (analyticascent.com) is
taken out. The page says "at least" for that reason, and hides the line
below MIN_SHOWN so it never advertises an empty map.

Rerunnable: on any API failure the existing file is left untouched.

Usage:
  python3 usage_stat.py            # writes data/usage.json
  python3 usage_stat.py --dry-run  # prints, writes nothing
"""
import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
OUT = REPO / "data" / "usage.json"
KEY = os.environ.get("GSC_SA_KEY", os.path.expanduser("~/.secrets/parkingnetherlands-gsc.json"))
PROPERTY = os.environ.get("GA4_PROPERTY_ID", "503850038")
DAYS = 28
OWNER_SOURCES = ("analyticascent",)   # sessionSource substrings that are the owner testing


def pull():
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import (DateRange, Dimension, Filter,
                                                    FilterExpression, Metric, RunReportRequest)
    from google.oauth2 import service_account
    creds = service_account.Credentials.from_service_account_file(
        KEY, scopes=["https://www.googleapis.com/auth/analytics.readonly"])
    r = BetaAnalyticsDataClient(credentials=creds).run_report(RunReportRequest(
        property=f"properties/{PROPERTY}",
        date_ranges=[DateRange(start_date=f"{DAYS}daysAgo", end_date="yesterday")],
        dimensions=[Dimension(name="sessionSource")],
        metrics=[Metric(name="eventCount")],
        dimension_filter=FilterExpression(filter=Filter(
            field_name="eventName", string_filter=Filter.StringFilter(value="select")))))
    stops = 0
    for row in r.rows:
        if any(s in row.dimension_values[0].value for s in OWNER_SOURCES):
            continue
        stops += int(row.metric_values[0].value)
    return stops


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    try:
        stops = pull()
    except Exception as e:
        sys.exit(f"usage_stat: GA4 pull failed, {OUT.name} left as it was ({e})")
    end = date.today() - timedelta(days=1)
    doc = {"stops_priced": stops, "days": DAYS,
           "from": str(end - timedelta(days=DAYS - 1)), "to": str(end),
           "generated": str(date.today()),
           "source": "GA4 select events (a charger or car park opened and priced); "
                     "consented visitors only; owner traffic excluded"}
    print(f"usage_stat: {stops} stops priced in {DAYS} days ({doc['from']} to {doc['to']})")
    if not a.dry_run:
        OUT.write_text(json.dumps(doc, indent=1) + "\n")


if __name__ == "__main__":
    main()
