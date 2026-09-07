#!/usr/bin/env python3
"""
Collector 1 - Autocomplete (spec section 3). Highest yield, keyless.

Google + Bing suggest endpoints, alphabet (a-z) and digit (0-9) expansion,
depth-2 recursion on materially-longer suggestions, polite rate limiting with
jitter, rotating user agents and hard 429 backoff.

Resilience deltas (spec 3.1/3.2):
  - Resume/idempotency: a seed whose raw file already exists for today is
    skipped, so an interrupted overnight run restarts where it stopped for free.
  - Soft-block detection: a rate-limited suggest endpoint often answers HTTP 200
    with an EMPTY array instead of a 429. We track the empty-200 rate over a
    rolling window and, past a threshold, cool down (pause + lengthen jitter)
    rather than hammering and writing empties as if they were real droughts.
  - HTTP outcome counters (429 / 403 / empty-200) are returned for run_manifest.

Writes every response body to the raw store (source autocomplete_google /
autocomplete_bing). Normalisation is a separate step (normalize.py) that reads
the raw store - collectors stay dumb (design principle 3).
"""
import json
import random
import string
import time
import urllib.parse
import urllib.request
from collections import deque

from db import raw_exists, write_raw

UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E153 Safari/604.1",
]

GL_BY_LANG = {"nl": "nl", "en": "nl", "de": "de", "fr": "fr"}
BING_MKT = {"nl": "nl-NL", "en": "en-GB", "de": "de-DE", "fr": "fr-FR"}
EXPANSION = list(string.ascii_lowercase) + [str(d) for d in range(10)]


class Backoff(Exception):
    pass


def _get_json(url: str, timeout: int = 12):
    """Return (data, status). status in {'ok','403','429','neterr'}."""
    req = urllib.request.Request(url, headers={"User-Agent": random.choice(UAS)})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise Backoff()
        if e.code == 403:
            return None, "403"
        return None, "neterr"
    except Exception:
        return None, "neterr"
    try:
        return json.loads(raw), "ok"
    except Exception:
        return None, "neterr"


def suggest_google(q: str, lang: str):
    url = ("https://suggestqueries.google.com/complete/search"
           "?client=firefox&hl=%s&gl=%s&q=%s"
           % (lang, GL_BY_LANG.get(lang, "nl"), urllib.parse.quote(q)))
    d, status = _get_json(url)
    sugg = d[1] if isinstance(d, list) and len(d) > 1 else []
    return sugg, status


def suggest_bing(q: str, lang: str):
    url = ("https://api.bing.com/osjson.aspx?query=%s&mkt=%s"
           % (urllib.parse.quote(q), BING_MKT.get(lang, "nl-NL")))
    d, status = _get_json(url)
    sugg = d[1] if isinstance(d, list) and len(d) > 1 else []
    return sugg, status


ENGINES = {
    "google": ("autocomplete_google", suggest_google),
    "bing": ("autocomplete_bing", suggest_bing),
}


class SoftBlockGuard:
    """
    Rolling-window empty-200 detector (spec 3.2). Records the outcome of each
    successful (200) suggest call as empty/non-empty. When the empty rate over
    the last `window` samples exceeds `threshold`, a soft block is assumed:
    pause, lengthen jitter, and let the caller rotate agent (UAs are already
    random per request). Non-200 outcomes (429/403/neterr) are not counted here.
    """
    def __init__(self, window=40, min_sample=20, threshold=0.20):
        self.buf = deque(maxlen=window)
        self.min_sample = min_sample
        self.threshold = threshold
        self.trips = 0
        self.jitter_mult = 1.0

    def record(self, was_empty: bool):
        self.buf.append(1 if was_empty else 0)

    def empty_rate(self) -> float:
        return sum(self.buf) / len(self.buf) if self.buf else 0.0

    def tripped(self) -> bool:
        return len(self.buf) >= self.min_sample and self.empty_rate() > self.threshold

    def cool_down(self):
        """Back off and lengthen future jitter; clear the window so we re-measure."""
        self.trips += 1
        self.jitter_mult = min(self.jitter_mult * 1.75, 8.0)
        pause = random.uniform(30, 90) * min(self.jitter_mult, 4.0)
        print(f"  [soft-block] empty-200 rate {self.empty_rate():.0%} over "
              f"{len(self.buf)} calls -> cooling down {pause:.0f}s "
              f"(jitter x{self.jitter_mult:.1f}, trip #{self.trips})")
        time.sleep(pause)
        self.buf.clear()


def _throttle(rps: float, mult: float = 1.0):
    base = (1.0 / max(rps, 0.1)) * mult
    time.sleep(base + random.uniform(0, base))


def _fetch_with_backoff(fn, q, lang, rps, stats, guard):
    """
    One suggest call with 429 backoff (exponential, capped) and soft-block
    accounting. Returns the suggestion list (possibly empty).
    """
    delay = 5.0
    for _ in range(5):
        try:
            sugg, status = fn(q, lang)
            stats["requests"] += 1
            if status == "403":
                stats["http_403"] += 1
            elif status == "ok":
                empty = not sugg
                if empty:
                    stats["empty_200"] += 1
                guard.record(empty)
                if guard.tripped():
                    guard.cool_down()
            _throttle(rps, guard.jitter_mult)
            return sugg
        except Backoff:
            stats["http_429"] += 1
            time.sleep(delay + random.uniform(0, delay))
            delay = min(delay * 2, 120)
    return []


def collect_for_seed(seed_row, engines, expand, recurse, rps, stats, guard):
    """
    Runs one seed through the chosen engines. Writes raw. Returns list of
    (source, query_text) discovered (deduped within the seed).

    Resume: for each engine, a seed whose raw file for today already exists is
    skipped without re-fetching (idempotency, spec 3.1).
    """
    seed_text = seed_row["seed_text"]
    lang = seed_row["language"] or "nl"
    seed_id = seed_row["id"]
    found = {}  # (source, query_lower) -> query_text

    def run_query(qtext, source, fn, depth):
        sugg = _fetch_with_backoff(fn, qtext, lang, rps, stats, guard)
        write_raw(source, seed_text, {
            "engine": source, "query_sent": qtext, "lang": lang,
            "seed_id": seed_id, "depth": depth, "suggestions": sugg,
        })
        new_long = []
        for s in sugg:
            key = (source, s.lower().strip())
            if key not in found:
                found[key] = s
                # candidate for recursion: materially longer than the seed
                if len(s) > len(seed_text) + 4:
                    new_long.append(s)
        return new_long

    for ename in engines:
        source, fn = ENGINES[ename]
        # Resume: skip a seed/engine already fetched today. Check ONCE up front,
        # before we write anything, so within-run appends don't self-skip.
        if raw_exists(source, seed_text):
            stats["skipped"] += 1
            continue
        # base + alphabet/digit expansion
        variants = [seed_text]
        if expand:
            variants += [f"{seed_text} {c}" for c in EXPANSION]
        longer = []
        for v in variants:
            longer += run_query(v, source, fn, 0)
        # depth-2 recursion (no further alphabet expansion, cost control)
        if recurse >= 2:
            for s in dict.fromkeys(longer):   # unique, order-preserving
                run_query(s, source, fn, 1)

    return [(src, txt) for (src, _), txt in found.items()]


def collect(seed_rows, engines=("google",), expand=True, recurse=2,
            rps=1.7, progress_every=50):
    """
    Collect across many seeds. Returns dict:
      records: list of (seed_id, language, source, query_text)
      stats:   {seeds, requests, unique, skipped, http_429, http_403,
                empty_200, soft_block_trips}
    """
    stats = {"seeds": 0, "requests": 0, "unique": 0, "skipped": 0,
             "http_429": 0, "http_403": 0, "empty_200": 0}
    guard = SoftBlockGuard()
    records = []
    for row in seed_rows:
        for source, qtext in collect_for_seed(
                row, engines, expand, recurse, rps, stats, guard):
            records.append((row["id"], row["language"], source, qtext))
        stats["seeds"] += 1
        if stats["seeds"] % progress_every == 0:
            print(f"  ...{stats['seeds']} seeds, "
                  f"{stats['requests']} requests, {len(records)} raw hits, "
                  f"{stats['skipped']} skipped, "
                  f"empty-200 {stats['empty_200']}, 429 {stats['http_429']}")
    stats["unique"] = len(records)
    stats["soft_block_trips"] = guard.trips
    return {"records": records, "stats": stats}


if __name__ == "__main__":
    # tiny smoke test
    from db import connect, init_db
    init_db()
    con = connect()
    rows = con.execute(
        "SELECT * FROM seeds WHERE language='en' ORDER BY id LIMIT 2"
    ).fetchall()
    con.close()
    out = collect(rows, engines=("google",), expand=False, recurse=1, rps=3)
    print("stats:", out["stats"])
    for r in out["records"][:15]:
        print("  ", r[2], "|", r[3])
