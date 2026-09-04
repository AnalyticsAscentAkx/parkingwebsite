#!/usr/bin/env python3
"""
Phase 1 deliverable (spec section 10).

A CSV, weekly, with: query, language, location, source, times_seen, top_domains,
forum_in_top10, our_position, plus GSC impressions/clicks where we have them.

Sorted by seen_count descending (nothing clever), filtered to where we do NOT
already rank (our_position null or > 10). This is the low-hanging-fruit list:
real demand, thin/absent supply, no page of ours in the top 10.

You read it. You pick 10. You write them.
"""
import csv
import json
import sys

from db import DATA_DIR, connect, today_str

QUERY = """
SELECT
  q.id, q.query_text, q.language, q.location_tag, q.location_type,
  q.source, q.seen_count,
  s.top_domains, s.has_forum, s.our_position, s.has_ai_answer,
  o.impressions AS gsc_impr, o.clicks AS gsc_clicks, o.position AS gsc_pos
FROM queries q
LEFT JOIN serp_snapshots s ON s.query_id = q.id
LEFT JOIN outcomes o        ON o.query_id = q.id AND o.cohort = 'gsc'
"""


def _dedupe_best(rows):
    """One row per normalised query, keeping the richest source/signal."""
    best = {}
    for r in rows:
        key = (r["query_text"] or "").lower().strip()
        cur = best.get(key)
        # prefer rows that have a SERP snapshot, then higher seen_count
        score = (r["our_position"] is not None or r["top_domains"] is not None,
                 r["seen_count"] or 0, r["gsc_impr"] or 0)
        if cur is None or score > cur[0]:
            best[key] = (score, r)
    return [v[1] for v in best.values()]


def generate(min_seen=1, include_ranked=False, limit=1000) -> str:
    con = connect()
    rows = con.execute(QUERY).fetchall()
    con.close()
    rows = _dedupe_best(rows)

    out = []
    for r in rows:
        pos = r["our_position"]
        if not include_ranked and pos is not None and pos <= 10:
            continue                      # we already rank -> not low-hanging
        if (r["seen_count"] or 0) < min_seen and not r["gsc_impr"]:
            continue
        domains = ""
        if r["top_domains"]:
            try:
                domains = "; ".join(json.loads(r["top_domains"])[:5])
            except Exception:
                domains = r["top_domains"]
        out.append({
            "query": r["query_text"],
            "language": r["language"] or "",
            "location": r["location_tag"] or "",
            "location_type": r["location_type"] or "",
            "source": r["source"],
            "times_seen": r["seen_count"] or 0,
            "gsc_impressions": r["gsc_impr"] or "",
            "gsc_clicks": r["gsc_clicks"] if r["gsc_clicks"] is not None else "",
            "top_domains": domains,
            "forum_in_top10": "" if r["has_forum"] is None else int(r["has_forum"]),
            "ai_overview": "" if r["has_ai_answer"] is None else int(r["has_ai_answer"]),
            "our_position": "" if pos is None else pos,
        })

    # spec: sort by seen_count desc; GSC impressions as secondary useful tiebreak
    out.sort(key=lambda d: (d["times_seen"], d["gsc_impressions"] or 0), reverse=True)
    out = out[:limit]

    path = DATA_DIR / f"shortlist_{today_str()}.csv"
    fields = ["query", "language", "location", "location_type", "source",
              "times_seen", "gsc_impressions", "gsc_clicks", "top_domains",
              "forum_in_top10", "ai_overview", "our_position"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out)

    print(f"  [shortlist] {len(out)} rows -> {path}")
    print("  Top 20 low-hanging queries by demand:")
    for d in out[:20]:
        loc = f" [{d['location']}]" if d["location"] else ""
        print(f"    x{d['times_seen']:>2} ({d['language']}) {d['query'][:52]}{loc}")
    return str(path)


if __name__ == "__main__":
    generate(min_seen=int(sys.argv[1]) if len(sys.argv) > 1 else 1)
