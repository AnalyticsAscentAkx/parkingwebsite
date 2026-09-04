#!/usr/bin/env python3
"""
Collector 5 - First-party demand (spec section 7). Cheapest, highest quality.

Pulls every Google Search Console query that earned an impression - including
ones you never targeted - and writes them as source='first_party' queries.
These are zero-competition demand signals because only you can see them.

Also flags the highest-value writes on the site: queries with impressions but
(near) zero clicks -> you appear but the page is wrong.

Reuses the service-account auth convention of scripts/gsc_agent (same env vars):
  GSC_SA_KEY   path to service-account JSON key
  GSC_PROPERTY e.g. "sc-domain:parkingnetherlands.com"

If creds/deps are missing this collector prints why and skips - it never breaks
the pipeline (design principle 2).
"""
import os
import sys
from datetime import date, timedelta

from db import connect, now_iso
from normalize import _location_index, _tag_location, normalize_text


def _service():
    key_path = os.environ.get("GSC_SA_KEY")
    prop = os.environ.get("GSC_PROPERTY")
    if not key_path or not prop:
        print("  [first_party] SKIP: set GSC_SA_KEY and GSC_PROPERTY "
              "(see scripts/gsc_agent/README.md).")
        return None, None
    if not os.path.isfile(key_path):
        print(f"  [first_party] SKIP: GSC_SA_KEY not found: {key_path}")
        return None, None
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        print("  [first_party] SKIP: missing deps. "
              "pip install -r scripts/gsc_agent/requirements.txt")
        return None, None
    creds = service_account.Credentials.from_service_account_file(
        key_path, scopes=["https://www.googleapis.com/auth/webmasters.readonly"])
    return build("searchconsole", "v1", credentials=creds,
                 cache_discovery=False), prop


def collect(days: int = 90) -> dict:
    service, prop = _service()
    if not service:
        return {"skipped": True}
    end = date.today() - timedelta(days=2)      # GSC data lags ~2 days
    start = end - timedelta(days=days)
    body = {
        "startDate": start.isoformat(), "endDate": end.isoformat(),
        "dimensions": ["query"], "rowLimit": 25000, "dataState": "final",
    }
    rows = service.searchanalytics().query(siteUrl=prop, body=body).execute().get("rows", [])
    loc_index = _location_index()
    ts = now_iso()
    con = connect()
    stats = {"rows": len(rows), "upserts": 0, "wrong_page": 0}
    with con:
        for r in rows:
            q = r["keys"][0]
            impr = r.get("impressions", 0)
            clicks = r.get("clicks", 0)
            pos = r.get("position", 0.0)
            loc_tag, loc_type = _tag_location(q, "", loc_index)
            con.execute("""
                INSERT INTO queries
                  (query_text, query_norm, language, source, seed_id,
                   location_tag, location_type, first_seen, last_seen,
                   seen_count, raw_ref)
                VALUES (?, ?, ?, 'first_party', NULL, ?, ?, ?, ?, 1, NULL)
                ON CONFLICT(query_norm, source, location_tag) DO UPDATE SET
                  seen_count = seen_count + 1, last_seen = excluded.last_seen
            """, (q, normalize_text(q), None, loc_tag, loc_type, ts, ts))
            stats["upserts"] += 1
            # record the GSC outcome so the feedback loop and shortlist can use it
            qid = con.execute(
                "SELECT id FROM queries WHERE query_norm=? AND source='first_party'",
                (normalize_text(q),)).fetchone()
            if qid:
                con.execute("""INSERT INTO outcomes
                    (query_id, page_url, published_at, cohort, impressions,
                     clicks, position, measured_at)
                    VALUES (?, NULL, NULL, 'gsc', ?, ?, ?, ?)""",
                    (qid["id"], impr, clicks, pos, ts))
            if impr >= 20 and clicks == 0:
                stats["wrong_page"] += 1
    con.close()
    print(f"  [first_party] {stats['rows']} GSC queries, "
          f"{stats['wrong_page']} appear-but-no-click (fix these first).")
    return stats


if __name__ == "__main__":
    print(collect(days=int(sys.argv[1]) if len(sys.argv) > 1 else 90))
