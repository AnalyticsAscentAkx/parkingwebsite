#!/usr/bin/env python3
"""
Collector 2 - People Also Ask + SERP snapshot (spec section 4).

Uses Playwright (headless Chromium, NL locale). Expensive, so it runs only on
the top-N highest-seen_count NEW queries, not every seed.

For each query it records into serp_snapshots:
  - top 10 result domains
  - has_forum   (reddit/quora/tripadvisor/forum in top 10 = thin supply signal)
  - has_ai_answer
  - our_position (parkingnetherlands.com), null if absent
and inserts the PAA questions as source='paa' queries.

Best-effort by design: Google's DOM and consent flow change often and may show
a consent wall or captcha in a datacentre IP. If Playwright or its browser is
not installed, or the page can't be parsed, it logs and skips (principle 2).
Selectors are centralised below for easy tuning.
"""
import sys
from urllib.parse import quote, urlparse

from db import connect, now_iso, write_raw
from normalize import normalize_text, _location_index, _tag_location

OUR_DOMAIN = "parkingnetherlands.com"
FORUM_HINTS = ("reddit.com", "quora.com", "tripadvisor.", "forum", "iamexpat",
               "expatrepublic", "facebook.com")
SEARCH_URL = "https://www.google.nl/search?q={q}&hl=nl&gl=nl"


def _playwright():
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        print("  [paa] SKIP: playwright not installed. "
              "pip install playwright && python -m playwright install chromium")
        return None


def _domains_and_paa(page):
    """Extract result domains and PAA questions defensively."""
    domains, paa = [], []
    # organic result links
    for a in page.query_selector_all("a:has(h3)"):
        href = a.get_attribute("href") or ""
        if href.startswith("http"):
            netloc = urlparse(href).netloc.lower().replace("www.", "")
            if netloc and netloc not in domains:
                domains.append(netloc)
    # People Also Ask questions (several possible containers)
    for sel in ("div[jsname] div[role='heading'] span",
                "div[data-initq]",
                "div.related-question-pair"):
        for el in page.query_selector_all(sel):
            t = (el.inner_text() or "").strip()
            if t.endswith("?") and t not in paa:
                paa.append(t)
    return domains[:10], paa


def collect(limit=400, headless=True) -> dict:
    spw = _playwright()
    if not spw:
        return {"skipped": True}
    con = connect()
    # highest-seen_count queries we haven't snapshotted yet
    rows = con.execute("""
        SELECT q.id, q.query_text, q.query_norm, q.seen_count
        FROM queries q
        LEFT JOIN serp_snapshots s ON s.query_id = q.id
        WHERE s.id IS NULL AND q.source LIKE 'autocomplete%'
        GROUP BY q.id
        ORDER BY q.seen_count DESC, q.id
        LIMIT ?""", (limit,)).fetchall()
    loc_index = _location_index()
    ts = now_iso()
    stats = {"queries": 0, "paa_found": 0, "forum_hits": 0, "errors": 0}
    try:
        with spw() as p:
            browser = p.chromium.launch(headless=headless)
            ctx = browser.new_context(locale="nl-NL",
                                      user_agent=("Mozilla/5.0 (Windows NT 10.0; "
                                                  "Win64; x64) AppleWebKit/537.36 "
                                                  "Chrome/124.0 Safari/537.36"))
            page = ctx.new_page()
            for r in rows:
                try:
                    page.goto(SEARCH_URL.format(q=quote(r["query_text"])),
                              timeout=15000, wait_until="domcontentloaded")
                    page.wait_for_timeout(1200)
                    html = page.content()
                    raw_ref = write_raw("paa", r["query_text"],
                                        {"query_id": r["id"], "html_len": len(html)})
                    domains, paa = _domains_and_paa(page)
                    has_forum = int(any(any(h in d for h in FORUM_HINTS) for d in domains))
                    has_ai = int("AI Overview" in html or "generative" in html.lower())
                    our_pos = None
                    for i, d in enumerate(domains, 1):
                        if OUR_DOMAIN in d:
                            our_pos = i
                            break
                    with con:
                        con.execute("""INSERT INTO serp_snapshots
                            (query_id, captured_at, result_count, top_domains,
                             has_forum, has_ai_answer, our_position, raw_ref)
                            VALUES (?,?,?,?,?,?,?,?)""",
                            (r["id"], ts, len(domains),
                             __import__("json").dumps(domains),
                             has_forum, has_ai, our_pos, raw_ref))
                        for pq in paa:
                            loc_tag, loc_type = _tag_location(pq, "", loc_index)
                            con.execute("""INSERT INTO queries
                                (query_text, query_norm, language, source, seed_id,
                                 location_tag, location_type, first_seen, last_seen,
                                 seen_count, raw_ref)
                                VALUES (?,?,?,'paa',NULL,?,?,?,?,1,?)
                                ON CONFLICT(query_norm, source, location_tag)
                                DO UPDATE SET seen_count=seen_count+1,
                                              last_seen=excluded.last_seen""",
                                (pq, normalize_text(pq), None, loc_tag, loc_type,
                                 ts, ts, raw_ref))
                    stats["queries"] += 1
                    stats["paa_found"] += len(paa)
                    stats["forum_hits"] += has_forum
                    page.wait_for_timeout(2500)   # human-paced
                except Exception:
                    stats["errors"] += 1
            browser.close()
    except Exception as e:
        print(f"  [paa] SKIP: browser launch failed ({e}). "
              "Run: python -m playwright install chromium")
        return {"skipped": True, "reason": str(e)}
    con.close()
    print(f"  [paa] snapshotted {stats['queries']} queries, "
          f"{stats['paa_found']} PAA, {stats['forum_hits']} thin-supply (forum in top10)")
    return stats


if __name__ == "__main__":
    print(collect(limit=int(sys.argv[1]) if len(sys.argv) > 1 else 20))
