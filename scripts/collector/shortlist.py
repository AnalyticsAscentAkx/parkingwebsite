#!/usr/bin/env python3
"""
Phase 1 deliverable (spec section 10).

A CSV, weekly, ONE ROW PER CLUSTER (not per raw query), with: representative
query, language, intent, location, location_type, source(s), times seen (summed
over the cluster), top-10 domains, forum-in-top-10 flag, our current position,
and a one-line "why surfaced".

Filtered to is_parking=1 and to clusters where we do NOT already rank
(our_position null or > 10). Sorted by summed seen_count descending. This is the
low-hanging-fruit list: real demand, thin/absent supply, no page of ours top-10.

Ships a second small rejects sample alongside it (spec 10): 20-30 rows from the
`rejects` table, so a human can spot-check in five minutes whether the relevance
gate is throwing away good queries or letting drift through, and tune it.

You read it. You pick 10 clusters. You write one page each.
"""
import csv
import json
import sys

from db import DATA_DIR, connect, today_str

# is_parking gate is enforced here; NULL is_parking (pre-migration rows) is
# treated as unknown and excluded so the shortlist only surfaces gated demand.
QUERY = """
SELECT
  q.id, q.query_text, q.query_norm, q.cluster_id, q.language, q.intent,
  q.location_tag, q.location_type, q.source, q.seen_count,
  s.top_domains, s.has_forum, s.our_position, s.has_ai_answer,
  o.impressions AS gsc_impr, o.clicks AS gsc_clicks, o.position AS gsc_pos
FROM queries q
LEFT JOIN serp_snapshots s ON s.query_id = q.id
LEFT JOIN outcomes o        ON o.query_id = q.id AND o.cohort = 'gsc'
WHERE q.is_parking = 1
"""


def _serp_richness(r):
    return (r["our_position"] is not None or r["top_domains"] is not None,
            r["seen_count"] or 0, r["gsc_impr"] or 0)


def _cluster_key(r):
    # NULL cluster_id (e.g. clustering not run) -> each query is its own cluster.
    return r["cluster_id"] if r["cluster_id"] is not None else f"q{r['id']}"


def _why_surfaced(rep, times_seen, forum, our_pos, gsc_impr, gsc_clicks, ai):
    reasons = [f"seen {times_seen}x"]
    if forum:
        reasons.append("forum in top 10 (thin supply)")
    if our_pos is None:
        reasons.append("we don't rank")
    elif our_pos > 10:
        reasons.append(f"we rank #{our_pos} (page 2+)")
    if gsc_impr and not gsc_clicks:
        reasons.append("impressions, no clicks (wrong page)")
    if ai:
        reasons.append("AI overview present")
    return "; ".join(reasons[:3])


def _collapse_clusters(rows):
    """Group rows by cluster; return one aggregated record per cluster."""
    groups = {}
    for r in rows:
        groups.setdefault(_cluster_key(r), []).append(r)

    out = []
    for cid, members in groups.items():
        rep = max(members, key=lambda r: r["seen_count"] or 0)   # representative
        serp = max(members, key=_serp_richness)                  # richest supply
        times_seen = sum(r["seen_count"] or 0 for r in members)
        sources = sorted({r["source"] for r in members})
        gsc_impr = sum(r["gsc_impr"] or 0 for r in members)
        gsc_clicks = sum(r["gsc_clicks"] or 0 for r in members)
        our_pos = serp["our_position"]
        forum = serp["has_forum"]
        ai = serp["has_ai_answer"]
        domains = ""
        if serp["top_domains"]:
            try:
                domains = "; ".join(json.loads(serp["top_domains"])[:5])
            except Exception:
                domains = serp["top_domains"]
        out.append({
            "cluster_id": cid,
            "query": rep["query_text"],
            "cluster_size": len(members),
            "language": rep["language"] or "",
            "intent": rep["intent"] or "",
            "location": rep["location_tag"] or "",
            "location_type": rep["location_type"] or "",
            "sources": ",".join(sources),
            "times_seen": times_seen,
            "gsc_impressions": gsc_impr or "",
            "gsc_clicks": gsc_clicks or "",
            "top_domains": domains,
            "forum_in_top10": "" if forum is None else int(forum),
            "ai_overview": "" if ai is None else int(ai),
            "our_position": "" if our_pos is None else our_pos,
            "why_surfaced": _why_surfaced(rep, times_seen, forum, our_pos,
                                          gsc_impr, gsc_clicks, ai),
            "_our_pos_raw": our_pos,
        })
    return out


def _write_rejects_sample(con, n=30) -> str:
    rows = con.execute(
        "SELECT query_text, reason, source, created_at "
        "FROM rejects ORDER BY RANDOM() LIMIT ?", (n,)
    ).fetchall()
    path = DATA_DIR / f"rejects_sample_{today_str()}.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["query_text", "reason", "source", "created_at"])
        for r in rows:
            w.writerow([r["query_text"], r["reason"], r["source"], r["created_at"]])
    print(f"  [rejects sample] {len(rows)} rows -> {path}")
    return str(path)


def generate(min_seen=1, include_ranked=False, limit=1000) -> str:
    con = connect()
    rows = con.execute(QUERY).fetchall()
    clusters = _collapse_clusters(rows)
    con2 = con  # keep open for rejects sample

    out = []
    for d in clusters:
        pos = d["_our_pos_raw"]
        if not include_ranked and pos is not None and pos <= 10:
            continue                      # we already rank -> not low-hanging
        if d["times_seen"] < min_seen and not d["gsc_impressions"]:
            continue
        d.pop("_our_pos_raw", None)
        out.append(d)

    out.sort(key=lambda d: (d["times_seen"], d["gsc_impressions"] or 0),
             reverse=True)
    out = out[:limit]

    path = DATA_DIR / f"shortlist_{today_str()}.csv"
    fields = ["cluster_id", "query", "cluster_size", "language", "intent",
              "location", "location_type", "sources", "times_seen",
              "gsc_impressions", "gsc_clicks", "top_domains", "forum_in_top10",
              "ai_overview", "our_position", "why_surfaced"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out)

    print(f"  [shortlist] {len(out)} clusters -> {path}")
    print("  Top 20 low-hanging clusters by demand:")
    for d in out[:20]:
        loc = f" [{d['location']}]" if d["location"] else ""
        print(f"    x{d['times_seen']:>3} ({d['language']}) "
              f"{d['query'][:48]}{loc}  <- {d['why_surfaced']}")

    _write_rejects_sample(con2)
    con2.close()
    return str(path)


if __name__ == "__main__":
    generate(min_seen=int(sys.argv[1]) if len(sys.argv) > 1 else 1)
