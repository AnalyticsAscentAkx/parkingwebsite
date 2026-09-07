#!/usr/bin/env python3
"""
Normalisation + dedupe + relevance gate + clustering (spec 1.2, 3.4, 4.5).

Reads the raw autocomplete store for a given day and upserts clean rows into
the queries table. Dedupe key is (query_norm, source, location_tag), where
query_norm is lowercased, punctuation-stripped AND token-sorted so word-order
variants ("parkeren amsterdam" / "amsterdam parkeren") collapse to one row.

Relevance gate (spec 3.4): autocomplete off a parking seed still returns drift
("amsterdam weather", "amsterdam hotels"). Each suggestion is gated by a cheap
multilingual is_parking check. Failures are written to the `rejects` table with
reason='not_parking' (never silently dropped) so the filter's precision can be
audited from the rejects sample.

Near-duplicate clustering (spec 4.5): after upsert, queries sharing a location
are grouped by stemmed-token Jaccard so the shortlist shows one row per real
intent, not five near-identical ones.

Location tagging: each raw record carries its seed_id. We map the seed back to
the location it was built from (greedy longest-name match) and set location_type
from the seed_type.
"""
import json
import re

from db import (DATA_DIR, RAW_DIR, connect, insert_reject, now_iso, today_str)
import seed_data

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")

# --- relevance gate (spec 3.4) ----------------------------------------------
# Strong parking stems across NL/EN/DE/FR. A normalised query containing any of
# these (and no hard-drift term) is is_parking=1. Substring match on the
# space-padded norm keeps it cheap and language-agnostic.
_PARKING_STEMS = (
    "parking", "parkeer", "parkeren", "parkeerg", "parkeerplaats",
    "parkeergarage", "parkeertarief", "parkeerboete", "parkeervergunning",
    "car park", "carpark", "garage", "p r", "park and ride", "park ride",
    "parken", "parkplatz", "parkhaus", "parkgebuhr", "parkgebuhren",
    "stationnement", "parcheggio", "valet",
)
# Weak token: bare "park" is parking-ish only when not one of these drift uses.
_WEAK_PARK = "park"
_PARK_DRIFT = (
    "national park", "hyde park", "vondelpark", "business park", "science park",
    "park hotel", "amusement park", "theme park", "park ranger", "park avenue",
    "linkin park", "jurassic park", "south park", "park city",
)
# Hard drift: kill even if a parking token is present (rare but real).
_HARD_DRIFT = (
    "weather", "weer ", "wetter", "meteo", "hotel", "restaurant", "wikipedia",
    "population", "bevolking", "vacature", "jobs", "news", "nieuws",
)


def normalize_text(s: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace, token-SORT."""
    s = s.lower().strip()
    s = _PUNCT.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    toks = s.split()
    return " ".join(sorted(toks))


def _clean_padded(s: str) -> str:
    """Cleaned (not token-sorted) form, space-padded, for substring gating."""
    s = _PUNCT.sub(" ", s.lower())
    s = _WS.sub(" ", s).strip()
    return f" {s} "


def is_parking(query_text: str) -> bool:
    """Cheap multilingual relevance gate. See module docstring / spec 3.4."""
    padded = _clean_padded(query_text)
    if any(d in padded for d in _HARD_DRIFT):
        return False
    if any(stem in padded for stem in _PARKING_STEMS):
        return True
    # bare "park" only counts if it isn't a known non-parking "... park" use
    if f" {_WEAK_PARK} " in padded or padded.strip().endswith(" park") \
            or padded.strip().startswith("park "):
        if not any(d in padded for d in _PARK_DRIFT):
            return True
    return False


# --- light stemmer for clustering -------------------------------------------
_STEM_SUFFIXES = ("eren", "tje", "ing", "en", "er", "es", "de", "s", "e")
_STOP = {"de", "het", "een", "in", "op", "te", "the", "a", "to", "of", "for",
         "and", "en", "near", "bij", "voor", "am", "im", "le", "la", "du"}
# Standalone "parking" words fold to one canonical token so the MODIFIER
# ("gratis", "goedkoop", "boete") drives clustering, not the ubiquitous root.
# Dutch compounds (parkeerboete, parkeertarief, parkeervergunning) are NOT here
# on purpose: they must stay distinct so different intents don't over-merge.
_PARK_CANON = {
    "parking", "parkeren", "parkeer", "parken", "parkplatz", "park",
    "stationnement", "parcheggio", "garage", "parkeergarage", "parkhaus",
    "carpark", "parkeerplaats", "parkeerplaatsen",
}
_DBL_VOWEL = re.compile(r"([aeiou])\1")


def _stem(tok: str) -> str:
    tok = _DBL_VOWEL.sub(r"\1", tok)          # oo->o, aa->a, ee->e (NL spelling)
    for suf in _STEM_SUFFIXES:
        if len(tok) > len(suf) + 2 and tok.endswith(suf):
            return tok[: -len(suf)]
    return tok


def _stem_set(query_norm: str) -> frozenset:
    out = set()
    for t in query_norm.split():
        if t in _STOP:
            continue
        out.add("park" if t in _PARK_CANON else _stem(t))
    return frozenset(out)


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


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
  (query_text, query_norm, is_parking, language, source, seed_id,
   location_tag, location_type, first_seen, last_seen, seen_count, raw_ref)
VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, 1, ?)
ON CONFLICT(query_norm, source, location_tag) DO UPDATE SET
  seen_count = seen_count + 1,
  last_seen  = excluded.last_seen
"""


def assign_clusters(con) -> int:
    """
    Greedy near-duplicate clustering over is_parking=1 queries (spec 4.5).
    Queries are bucketed by location_tag; within a bucket, a query joins the
    first cluster whose representative stem-set has Jaccard >= threshold, else
    it seeds a new cluster. Returns the number of clusters assigned.
    """
    THRESH = 0.55
    rows = con.execute(
        "SELECT id, query_norm, location_tag FROM queries WHERE is_parking = 1"
    ).fetchall()
    buckets = {}
    for r in rows:
        buckets.setdefault(r["location_tag"], []).append(r)

    next_cid = 1
    updates = []
    for _loc, group in buckets.items():
        clusters = []  # list of (cluster_id, representative stem_set)
        for r in group:
            sset = _stem_set(r["query_norm"])
            joined = None
            for cid, rep in clusters:
                if _jaccard(sset, rep) >= THRESH:
                    joined = cid
                    break
            if joined is None:
                joined = next_cid
                clusters.append((joined, sset))
                next_cid += 1
            updates.append((joined, r["id"]))
    con.executemany("UPDATE queries SET cluster_id = ? WHERE id = ?", updates)
    return next_cid - 1


def normalize_day(day=None) -> dict:
    day = day or today_str()
    loc_index = _location_index()
    seeds = _seed_map()
    ts = now_iso()
    con = connect()
    stats = {"raw_records": 0, "suggestions": 0, "upserts": 0, "rejected": 0}
    seen_rejects = set()   # avoid re-inserting the same reject within a run
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
                if not is_parking(sug):
                    stats["rejected"] += 1
                    rkey = (sug.lower().strip(), "not_parking")
                    if rkey not in seen_rejects:
                        seen_rejects.add(rkey)
                        insert_reject(con, sug, "not_parking", source, raw_ref)
                    continue
                con.execute(UPSERT, (
                    sug, norm, lang, source, seed_id,
                    loc_tag, loc_type, ts, ts, raw_ref,
                ))
                stats["upserts"] += 1
        stats["clusters"] = assign_clusters(con)
    n = con.execute("SELECT COUNT(*) FROM queries").fetchone()[0]
    con.close()
    stats["queries_total"] = n
    return stats


if __name__ == "__main__":
    print(normalize_day())
