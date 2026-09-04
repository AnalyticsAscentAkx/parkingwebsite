#!/usr/bin/env python3
"""
Collector 3 - Community and review mining (spec section 5).

Reddit: uses the public JSON search endpoint (keyless; a descriptive User-Agent
is enough at this volume). A highly-upvoted, thinly-answered question is a strong
gap signal, so we keep score + num_comments in the raw store.

Maps reviews / YouTube: stubbed with a clear integration point. Google Maps
reviews need the Places API (paid key) or a compliant scraper; wiring that is a
credentialed follow-up, so this module documents the shape and skips cleanly
rather than pretending (principle 2).

All community items are normalised into question-shaped strings before entering
the queries table (source='reddit').
"""
import json
import sys
import time
import urllib.parse
import urllib.request

from db import connect, now_iso, write_raw
from normalize import normalize_text, _location_index, _tag_location

SUBREDDITS = ["Netherlands", "Amsterdam", "Rotterdam", "DenHaag", "Utrecht",
              "thenetherlands", "Eindhoven"]
TERMS = ["parking", "parkeren", "park and ride", "parkeergarage", "parking fine"]
UA = {"User-Agent": "parkingnetherlands-demand-collector/1.0 (contact: site owner)"}


def _reddit_search(sub, term, limit=25):
    url = ("https://www.reddit.com/r/%s/search.json?q=%s&restrict_sr=1&sort=relevance&limit=%d"
           % (sub, urllib.parse.quote(term), limit))
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8", "ignore"))
    except Exception:
        return None


def collect_reddit(max_per=25) -> dict:
    loc_index = _location_index()
    ts = now_iso()
    con = connect()
    stats = {"requests": 0, "posts": 0, "upserts": 0, "blocked": 0}
    for sub in SUBREDDITS:
        for term in TERMS:
            data = _reddit_search(sub, term, max_per)
            stats["requests"] += 1
            if not data or "data" not in data:
                stats["blocked"] += 1
                time.sleep(2)
                continue
            children = data["data"].get("children", [])
            write_raw("reddit", f"{sub}:{term}",
                      {"sub": sub, "term": term, "count": len(children),
                       "titles": [c["data"].get("title") for c in children]})
            with con:
                for c in children:
                    d = c.get("data", {})
                    title = (d.get("title") or "").strip()
                    if not title:
                        continue
                    stats["posts"] += 1
                    # keep questions and parking-relevant titles
                    loc_tag, loc_type = _tag_location(title, "", loc_index)
                    con.execute("""INSERT INTO queries
                        (query_text, query_norm, language, source, seed_id,
                         location_tag, location_type, first_seen, last_seen,
                         seen_count, raw_ref)
                        VALUES (?,?,?, 'reddit', NULL, ?, ?, ?, ?, 1, NULL)
                        ON CONFLICT(query_norm, source, location_tag)
                        DO UPDATE SET seen_count = seen_count + 1,
                                      last_seen = excluded.last_seen""",
                        (title, normalize_text(title), None,
                         loc_tag, loc_type, ts, ts))
                    stats["upserts"] += 1
            time.sleep(1.5)
    con.close()
    if stats["blocked"]:
        print(f"  [reddit] note: {stats['blocked']} requests returned no data "
              "(rate-limited or blocked). Re-run later or add OAuth for volume.")
    print(f"  [reddit] {stats['posts']} posts -> {stats['upserts']} queries")
    return stats


def collect_maps_reviews():
    """
    STUB (documented integration point).
    For each parking garage / P+R in the seed list, pull Google Maps reviews and
    mine recurring pain phrases: 'couldn't find', 'confusing', 'expensive',
    'app didn't work', 'height limit', 'no charging'. Each recurring complaint is
    a page. Needs a Places API key (env GOOGLE_PLACES_KEY) or a compliant scraper.
    """
    import os
    if not os.environ.get("GOOGLE_PLACES_KEY"):
        print("  [maps_reviews] SKIP: set GOOGLE_PLACES_KEY to enable. "
              "Mines garage/P+R reviews for pain phrases -> page ideas.")
        return {"skipped": True}
    print("  [maps_reviews] key present but implementation is a follow-up (see docstring).")
    return {"skipped": True}


def collect() -> dict:
    r = collect_reddit()
    m = collect_maps_reviews()
    return {"reddit": r, "maps": m}


if __name__ == "__main__":
    print(collect_reddit(int(sys.argv[1]) if len(sys.argv) > 1 else 10))
