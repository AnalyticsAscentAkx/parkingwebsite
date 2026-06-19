#!/usr/bin/env python3
"""
Keyword research for parkingnetherlands.com.

Combines three free signals into a ranked keyword opportunity list:

  1. Google autocomplete  — what people actually start typing (free, no auth)
  2. People-also-ask scrape — informational queries that surface as featured boxes
  3. Google Trends (pytrends)  — relative search volume + rising terms in the NL

Output:
  keyword_research.csv  — one row per keyword, scored by composite_score
  keyword_research.md   — human-readable summary by topic cluster

Usage:
  pip install pytrends requests beautifulsoup4 pandas
  python3 scripts/keyword_research.py

  # narrow the seed set:
  python3 scripts/keyword_research.py --seeds "amsterdam parking,schiphol parking"

The composite score weights:
  - 0.5 × normalized trends_score (recent NL interest, 0-100)
  - 0.3 × seed_relevance (1.0 if seed appears in keyword, else 0.5)
  - 0.2 × query_intent (0.4 informational, 0.7 commercial, 1.0 transactional)

Tweak weights in main(). The point isn't a perfect score — it's a defensible
ranking you can act on without paying for Ahrefs.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from urllib.parse import quote

import requests

DEFAULT_SEEDS = [
    "parking netherlands",
    "amsterdam parking",
    "rotterdam parking",
    "the hague parking",
    "utrecht parking",
    "schiphol parking",
    "free parking netherlands",
    "p+r amsterdam",
    "blue zone parking",
    "dutch parking fines",
    "parking apps netherlands",
    "ev charging netherlands",
    "weekend parking amsterdam",
    "long term parking schiphol",
    "parkbee",
    "cheap parking amsterdam",
]

INFORMATIONAL_PREFIXES = ("how", "what", "why", "where", "when", "is", "can", "do", "does")
COMMERCIAL_PREFIXES = ("best", "compare", "top", "review", "cheap", "cheapest", "vs")
TRANSACTIONAL_PREFIXES = ("book", "buy", "reserve", "find", "near me")


@dataclass
class KeywordRow:
    keyword: str
    seed: str
    source: str
    trends_score: float = 0.0
    rising: int = 0
    intent: str = "informational"
    composite_score: float = 0.0
    notes: list[str] = field(default_factory=list)


def autocomplete(query: str, locale: str = "nl-NL") -> list[str]:
    """Hit Google's public autocomplete endpoint (no auth)."""
    url = f"https://suggestqueries.google.com/complete/search?client=firefox&hl=en&gl=nl&q={quote(query)}"
    try:
        r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        data = r.json()
        return data[1] if len(data) > 1 else []
    except Exception as e:
        print(f"  ! autocomplete fail for {query!r}: {e}", file=sys.stderr)
        return []


def expand_seed(seed: str) -> list[str]:
    """Get autocomplete for the seed + each letter-suffixed variant."""
    out = set(autocomplete(seed))
    for ch in "abcdefghijklmnopqrstuvwxyz":
        for x in autocomplete(f"{seed} {ch}"):
            out.add(x)
        time.sleep(0.12)
    return sorted(out)


def people_also_ask(query: str) -> list[str]:
    """Best-effort PAA scrape via Google search. Brittle, but free."""
    url = f"https://www.google.com/search?q={quote(query)}&hl=en&gl=nl"
    try:
        r = requests.get(url, timeout=8, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
        })
        r.raise_for_status()
    except Exception as e:
        print(f"  ! PAA fetch fail for {query!r}: {e}", file=sys.stderr)
        return []

    # Heuristic: PAA questions appear as data-q="..." or in role=heading boxes
    questions = set()
    for m in re.findall(r'data-q="([^"]{8,140})"', r.text):
        questions.add(m)
    for m in re.findall(r'aria-label="([^"]{8,140}\?)"', r.text):
        questions.add(m)
    return sorted(questions)


def classify_intent(kw: str) -> str:
    k = kw.lower()
    first = k.split()[0] if k else ""
    if any(t in k for t in TRANSACTIONAL_PREFIXES):
        return "transactional"
    if first in COMMERCIAL_PREFIXES or any(c in k for c in COMMERCIAL_PREFIXES):
        return "commercial"
    if first in INFORMATIONAL_PREFIXES or k.endswith("?"):
        return "informational"
    return "informational"


def intent_weight(intent: str) -> float:
    return {"transactional": 1.0, "commercial": 0.7, "informational": 0.4}.get(intent, 0.4)


def trends_scores(keywords: list[str], geo: str = "NL") -> dict[str, tuple[float, int]]:
    """Returns {kw: (interest_0_100, is_rising_bool_as_int)}.

    Calls pytrends in chunks of 5 (its limit).  If pytrends isn't installed or
    Google throttles, we fall back to zeros — keywords still rank by intent +
    seed relevance.
    """
    try:
        from pytrends.request import TrendReq
    except ImportError:
        print("  ! pytrends not installed; skipping trends scoring (pip install pytrends)", file=sys.stderr)
        return {kw: (0.0, 0) for kw in keywords}

    pt = TrendReq(hl="en-US", tz=0, retries=2, backoff_factor=0.5)
    out: dict[str, tuple[float, int]] = {}
    for i in range(0, len(keywords), 5):
        chunk = keywords[i:i+5]
        try:
            pt.build_payload(chunk, timeframe="today 12-m", geo=geo)
            iot = pt.interest_over_time()
            rel = pt.related_queries()
        except Exception as e:
            print(f"  ! trends chunk fail {chunk}: {e}", file=sys.stderr)
            for kw in chunk: out[kw] = (0.0, 0)
            time.sleep(2)
            continue
        for kw in chunk:
            score = float(iot[kw].mean()) if (not iot.empty and kw in iot.columns) else 0.0
            rising = rel.get(kw, {}).get("rising")
            is_rising = 1 if rising is not None and len(rising) > 0 else 0
            out[kw] = (score, is_rising)
        time.sleep(1.4)
    return out


def fingerprint(kw: str) -> str:
    return re.sub(r"\s+", " ", kw.lower().strip())


def gather(seeds: Iterable[str]) -> list[KeywordRow]:
    rows: dict[str, KeywordRow] = {}
    for seed in seeds:
        print(f"→ Expanding seed: {seed}")
        for kw in expand_seed(seed):
            f = fingerprint(kw)
            if f in rows: continue
            rows[f] = KeywordRow(keyword=kw, seed=seed, source="autocomplete", intent=classify_intent(kw))
        for kw in people_also_ask(seed):
            f = fingerprint(kw)
            if f in rows:
                rows[f].source = "autocomplete+paa"
                continue
            rows[f] = KeywordRow(keyword=kw, seed=seed, source="paa", intent=classify_intent(kw))
        time.sleep(0.6)
    return list(rows.values())


def score(rows: list[KeywordRow], seeds: list[str]) -> None:
    print(f"→ Scoring {len(rows)} keywords via Google Trends (NL geo)…")
    keywords = [r.keyword for r in rows]
    ts = trends_scores(keywords)
    max_score = max((s for s, _ in ts.values()), default=1.0) or 1.0
    seed_lc = [s.lower() for s in seeds]
    for r in rows:
        s, rising = ts.get(r.keyword, (0.0, 0))
        r.trends_score = s
        r.rising = rising
        norm_trends = s / max_score
        rel = 1.0 if any(seed in r.keyword.lower() for seed in seed_lc) else 0.5
        r.composite_score = 0.5 * norm_trends + 0.3 * rel + 0.2 * intent_weight(r.intent)
        if rising:
            r.composite_score += 0.05
            r.notes.append("rising")
        if "vs" in r.keyword or "best" in r.keyword:
            r.notes.append("comparison")


def write_csv(rows: list[KeywordRow], path: Path) -> None:
    rows_sorted = sorted(rows, key=lambda r: r.composite_score, reverse=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["keyword", "seed", "source", "intent", "trends_score", "rising", "composite_score", "notes"])
        for r in rows_sorted:
            w.writerow([r.keyword, r.seed, r.source, r.intent, f"{r.trends_score:.2f}", r.rising, f"{r.composite_score:.4f}", ";".join(r.notes)])


def write_md(rows: list[KeywordRow], path: Path) -> None:
    by_seed: dict[str, list[KeywordRow]] = {}
    for r in rows:
        by_seed.setdefault(r.seed, []).append(r)
    lines = ["# Keyword research — parkingnetherlands.com", "",
             f"Generated from {len(rows)} unique keywords across {len(by_seed)} topic seeds.", "",
             "## Top 25 overall (by composite score)", ""]
    top = sorted(rows, key=lambda r: r.composite_score, reverse=True)[:25]
    lines += [f"| # | Keyword | Intent | Trends | Score |", "|---|---|---|---|---|"]
    for i, r in enumerate(top, 1):
        lines.append(f"| {i} | `{r.keyword}` | {r.intent} | {r.trends_score:.0f} | {r.composite_score:.3f} |")
    lines.append("")
    lines.append("## By topic cluster")
    for seed, items in by_seed.items():
        items.sort(key=lambda r: r.composite_score, reverse=True)
        lines.append(f"\n### {seed}\n")
        for r in items[:10]:
            tag = " (rising)" if r.rising else ""
            lines.append(f"- `{r.keyword}` · {r.intent} · score {r.composite_score:.3f}{tag}")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Keyword research for parkingnetherlands.com")
    ap.add_argument("--seeds", help="Comma-separated seed list (overrides defaults)")
    ap.add_argument("--out", default="keyword_research", help="Output filename prefix")
    args = ap.parse_args()

    seeds = [s.strip() for s in args.seeds.split(",")] if args.seeds else DEFAULT_SEEDS
    print(f"Seeds ({len(seeds)}): {', '.join(seeds)}\n")

    rows = gather(seeds)
    if not rows:
        print("No keywords gathered — network failures?", file=sys.stderr)
        return 1

    score(rows, seeds)

    csv_path = Path(f"{args.out}.csv")
    md_path = Path(f"{args.out}.md")
    write_csv(rows, csv_path)
    write_md(rows, md_path)

    print(f"\n✓ Wrote {csv_path} ({len(rows)} rows)")
    print(f"✓ Wrote {md_path}")
    print(f"\nTop 5 opportunities:")
    for r in sorted(rows, key=lambda r: r.composite_score, reverse=True)[:5]:
        print(f"  · {r.keyword!r}  [{r.intent}, score={r.composite_score:.3f}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
