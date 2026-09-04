#!/usr/bin/env python3
"""
Collector 1 - Autocomplete (spec section 3). Highest yield, keyless.

Google + Bing suggest endpoints, alphabet (a-z) and digit (0-9) expansion,
depth-2 recursion on materially-longer suggestions, polite rate limiting with
jitter, rotating user agents and hard 429 backoff.

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

from db import write_raw

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
    req = urllib.request.Request(url, headers={"User-Agent": random.choice(UAS)})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise Backoff()
        return None
    except Exception:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def suggest_google(q: str, lang: str):
    url = ("https://suggestqueries.google.com/complete/search"
           "?client=firefox&hl=%s&gl=%s&q=%s"
           % (lang, GL_BY_LANG.get(lang, "nl"), urllib.parse.quote(q)))
    d = _get_json(url)
    return d[1] if isinstance(d, list) and len(d) > 1 else []


def suggest_bing(q: str, lang: str):
    url = ("https://api.bing.com/osjson.aspx?query=%s&mkt=%s"
           % (urllib.parse.quote(q), BING_MKT.get(lang, "nl-NL")))
    d = _get_json(url)
    return d[1] if isinstance(d, list) and len(d) > 1 else []


ENGINES = {
    "google": ("autocomplete_google", suggest_google),
    "bing": ("autocomplete_bing", suggest_bing),
}


def _throttle(rps: float):
    base = 1.0 / max(rps, 0.1)
    time.sleep(base + random.uniform(0, base))


def _fetch_with_backoff(fn, q, lang, rps):
    """One suggest call with 429 backoff (exponential, capped)."""
    delay = 5.0
    for _ in range(5):
        try:
            res = fn(q, lang)
            _throttle(rps)
            return res
        except Backoff:
            time.sleep(delay + random.uniform(0, delay))
            delay = min(delay * 2, 120)
    return []


def collect_for_seed(seed_row, engines, expand, recurse, rps, stats):
    """
    Runs one seed through the chosen engines. Writes raw. Returns list of
    (source, query_text) discovered (deduped within the seed).
    """
    seed_text = seed_row["seed_text"]
    lang = seed_row["language"] or "nl"
    seed_id = seed_row["id"]
    found = {}  # (source, query_lower) -> query_text

    def run_query(qtext, source, fn, depth):
        sugg = _fetch_with_backoff(fn, qtext, lang, rps)
        stats["requests"] += 1
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
      stats:   {seeds, requests, unique}
    """
    stats = {"seeds": 0, "requests": 0, "unique": 0}
    records = []
    for row in seed_rows:
        for source, qtext in collect_for_seed(
                row, engines, expand, recurse, rps, stats):
            records.append((row["id"], row["language"], source, qtext))
        stats["seeds"] += 1
        if stats["seeds"] % progress_every == 0:
            print(f"  ...{stats['seeds']} seeds, "
                  f"{stats['requests']} requests, {len(records)} raw hits")
    stats["unique"] = len(records)
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
