#!/usr/bin/env python3
"""Record a change so the scorecard can tell you later whether it worked.

Measuring without remembering what you changed is just watching. Every SEO
edit here is a guess: this title will earn more clicks than that one. A guess
is only worth making if someone checks it afterwards, and nobody ever
remembers to, so the check has to be automatic.

Each entry captures the page's numbers at the moment of the edit. The
scorecard then compares the same length of window after the change against
that baseline, and says plainly whether it helped, did nothing, or hurt.
Entries are kept even when the answer is "it hurt", because those are the
useful ones.

Usage:
  python3 logchange.py /parking-fines "title now leads with the amount"
  python3 logchange.py --list
"""
import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
LOG = REPO / "data" / "qa" / "changes.jsonl"
KEY = os.environ.get("GSC_SA_KEY", os.path.expanduser(
    "~/.secrets/parkingnetherlands-gsc.json"))
PROP = os.environ.get("GSC_PROPERTY", "sc-domain:parkingnetherlands.com")
SITE = "https://parkingnetherlands.com"
WINDOW = 28


def page_stats(path, days=WINDOW, end=None):
    """Clicks, impressions, CTR and position for one page over a window."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    c = service_account.Credentials.from_service_account_file(
        KEY, scopes=["https://www.googleapis.com/auth/webmasters.readonly"])
    s = build("searchconsole", "v1", credentials=c, cache_discovery=False)
    end = end or (date.today() - timedelta(days=3))
    body = {
        "startDate": (end - timedelta(days=days - 1)).isoformat(),
        "endDate": end.isoformat(),
        "rowLimit": 1,
        "dimensionFilterGroups": [{"filters": [
            {"dimension": "page", "operator": "equals",
             "expression": SITE + path}]}],
    }
    rows = s.searchanalytics().query(siteUrl=PROP, body=body).execute().get("rows", [])
    if not rows:
        return dict(clicks=0, impressions=0, ctr=0.0, position=0.0)
    r = rows[0]
    return dict(clicks=r["clicks"], impressions=r["impressions"],
                ctr=round(r["ctr"], 5), position=round(r["position"], 2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("page", nargs="?", help="site path, e.g. /parking-fines")
    ap.add_argument("what", nargs="?", help="what you changed, in a few words")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    if a.list or not a.page:
        if not LOG.is_file():
            print("no changes recorded yet")
            return 0
        for line in LOG.read_text().splitlines():
            if not line.strip():
                continue
            e = json.loads(line)
            b = e["baseline"]
            print(f"  {e['at']}  {e['page']:30} {e['what'][:44]}")
            print(f"              baseline: {b['clicks']:.0f} clicks, "
                  f"{b['impressions']:.0f} impr, {b['ctr']*100:.2f}%, pos {b['position']}")
        return 0

    if not a.what:
        sys.exit("say what you changed, in a few words")
    try:
        base = page_stats(a.page)
    except Exception as e:
        sys.exit(f"ERROR reading Search Console: {str(e)[:200]}")

    entry = {"at": date.today().isoformat(), "page": a.page, "what": a.what,
             "window_days": WINDOW, "baseline": base}
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"recorded {a.page}: {a.what}")
    print(f"  baseline over {WINDOW} days: {base['clicks']:.0f} clicks, "
          f"{base['impressions']:.0f} impressions, {base['ctr']*100:.2f}% CTR, "
          f"position {base['position']}")
    print(f"  the scorecard will judge it once {WINDOW} days have passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
