#!/usr/bin/env python3
"""
Normalisation + dedupe (spec section 1.2, principle 3).

Reads the raw autocomplete store for a given day and upserts clean rows into
the queries table. Dedupe key is (query_norm, source, location_tag); a repeat
bumps seen_count and last_seen instead of inserting a duplicate.

Location tagging: each raw record carries its seed_id. We map the seed back to
the location it was built from (greedy longest-name match against the known
location list) and the location_type from the seed_type.
"""
import json
import re
from pathlib import Path

from db import DATA_DIR, RAW_DIR, connect, now_iso, today_str
import seed_data

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")


def normalize_text(s: str) -> str:
    s = s.lower().strip()
    s = _PUNCT.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    return s


def _location_index():
    """Location names longest-first for greedy substring matching."""
    locs = seed_data.load_locations()
    idx = sorted(((name.lower(), name, ltype) for name, ltype in locs),
                 key=lambda x: -len(x[0]))
    return idx


def _seed_map():
    con = connect()
    rows = con.execute("SELECT id, seed_text, seed_type, language FROM seeds").fetchall()
    con.close()
    return {r["id"]: dict(r) for r in rows}


def _tag_location(seed_text, seed_type, loc_index):
    """Return (location_tag, location_type) or (None, None)."""
    st = (seed_text or "").lower()
    for lname_l, lname, ltype in loc_index:
        if lname_l in st:
            # prefer explicit type carried on the seed_type ("...:city")
            if seed_type and ":" in seed_type:
                ltype = seed_type.split(":", 1)[1] or ltype
            return lname, ltype
    if seed_type == "event":
        return None, "venue"
    return None, None


def _iter_raw_records(day):
    """Yield (source, raw_ref, record) for each raw autocomplete file of the day."""
    for source in ("autocomplete_google", "autocomplete_bing"):
        d = RAW_DIR / source / day
        if not d.is_dir():
            continue
        for f in d.glob("*.json"):
            raw_ref = str(f.relative_to(DATA_DIR))
            try:
                entries = json.loads(f.read_text("utf-8"))
            except Exception:
                continue
            for entry in entries:
                payload = entry.get("payload", {})
                yield source, raw_ref, payload


UPSERT = """
INSERT INTO queries
  (query_text, query_norm, language, source, seed_id,
   location_tag, location_type, first_seen, last_seen, seen_count, raw_ref)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
ON CONFLICT(query_norm, source, location_tag) DO UPDATE SET
  seen_count = seen_count + 1,
  last_seen  = excluded.last_seen
"""


def normalize_day(day=None) -> dict:
    day = day or today_str()
    loc_index = _location_index()
    seeds = _seed_map()
    ts = now_iso()
    con = connect()
    stats = {"raw_records": 0, "suggestions": 0, "upserts": 0}
    with con:
        for source, raw_ref, payload in _iter_raw_records(day):
            stats["raw_records"] += 1
            seed_id = payload.get("seed_id")
            lang = payload.get("lang")
            seed = seeds.get(seed_id, {})
            loc_tag, loc_type = _tag_location(
                seed.get("seed_text", ""), seed.get("seed_type", ""), loc_index)
            for sug in payload.get("suggestions", []):
                if not sug or not sug.strip():
                    continue
                stats["suggestions"] += 1
                norm = normalize_text(sug)
                if not norm:
                    continue
                con.execute(UPSERT, (
                    sug, norm, lang, source, seed_id,
                    loc_tag, loc_type, ts, ts, raw_ref,
                ))
                stats["upserts"] += 1
    # report distinct rows
    n = con.execute("SELECT COUNT(*) FROM queries").fetchone()[0]
    con.close()
    stats["queries_total"] = n
    return stats


if __name__ == "__main__":
    print(normalize_day())
