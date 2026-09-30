#!/usr/bin/env python3
"""Pull Keyword Planner search volumes for parkingnetherlands.com.

Auth is the same service account the Search Console agent uses. The Google Ads
API takes a service account key directly: no OAuth refresh token, no
domain-wide delegation. Developer tokens were sunset on 2026-09-09, so access
is granted per Cloud project instead.

The account has live spend, so volumes come back as exact averages rather than
the "1K to 10K" buckets a dormant account is given.

Usage:
  python3 volumes.py "günstig parken amsterdam" "parkeren amsterdam" --lang de
"""
import argparse
import os
import sys

CUSTOMER_ID = os.environ.get("ADS_CUSTOMER_ID", "2059477268")
KEY = os.environ.get("GSC_SA_KEY", os.path.expanduser(
    "~/.secrets/parkingnetherlands-gsc.json"))

# Google Ads criterion ids.
LANGS = {"en": "1000", "de": "1001", "fr": "1002", "nl": "1010"}
GEOS = {"nl": "2528", "de": "2276", "be": "2056", "fr": "2250", "uk": "2826"}


def client():
    from google.ads.googleads.client import GoogleAdsClient
    return GoogleAdsClient.load_from_dict({
        "json_key_file_path": KEY,
        "use_proto_plus": True,
    })


def ideas(seeds, lang="nl", geo="nl", limit=60):
    c = client()
    svc = c.get_service("KeywordPlanIdeaService")
    req = c.get_type("GenerateKeywordIdeasRequest")
    req.customer_id = CUSTOMER_ID
    req.language = f"languageConstants/{LANGS[lang]}"
    req.geo_target_constants.append(f"geoTargetConstants/{GEOS[geo]}")
    req.include_adult_keywords = False
    req.keyword_seed.keywords.extend(seeds)
    rows = []
    for r in svc.generate_keyword_ideas(request=req):
        m = r.keyword_idea_metrics
        rows.append({
            "keyword": r.text,
            "volume": m.avg_monthly_searches or 0,
            "competition": m.competition.name,
        })
    rows.sort(key=lambda x: -x["volume"])
    return rows[:limit]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("seeds", nargs="+")
    ap.add_argument("--lang", default="nl", choices=sorted(LANGS))
    ap.add_argument("--geo", default="nl", choices=sorted(GEOS))
    ap.add_argument("--limit", type=int, default=60)
    a = ap.parse_args()
    try:
        rows = ideas(a.seeds, a.lang, a.geo, a.limit)
    except Exception as e:
        sys.exit(f"ERROR: {e}")
    print(f"{'keyword':50} {'monthly':>9}  competition")
    for r in rows:
        print(f"{r['keyword'][:50]:50} {r['volume']:>9,}  {r['competition']}")
