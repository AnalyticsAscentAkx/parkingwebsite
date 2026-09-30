#!/usr/bin/env python3
"""Track how much of the site Google has actually indexed.

Clicks are the wrong thing to watch right now. This site earns about 1.6 a
day, so an hour of Search Console data holds a handful of impressions and
almost always zero clicks: watching that hourly is watching noise. The number
that will genuinely move over the next fortnight is how many of the 1,455
submitted pages Google has crawled and indexed, and the URL Inspection API
answers that directly.

It samples a FIXED set of urls, the same ones every run, so successive runs
are comparable. The sample is stratified across site sections, because the
English pages and the 1,292 new localized ones are on completely different
footings and a blended number would hide that.

Quota is 2,000 inspections a day. The default sample of 60 leaves room to run
this every couple of hours.

Usage:
  python3 index_watch.py              # inspect the sample, append, print
  python3 index_watch.py --history    # just show the trend, no API calls
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OUT = Path(os.environ.get("GSC_OUT_DIR", REPO / "data" / "gsc"))
LOG = OUT / "index_watch.jsonl"
SITEMAP = "https://parkingnetherlands.com/sitemap.xml"
PROP = os.environ.get("GSC_PROPERTY", "sc-domain:parkingnetherlands.com")

# Which bucket a url belongs to. Order matters, first match wins.
# Named pages checked EVERY run, on top of the random sample.
#
# The sample is a proportion estimator, and while only about 1% of the site is
# indexed it will read 0% whatever happens: 40 urls drawn from 1,455 with 15
# indexed expects 0.4 hits. That is too coarse to see the first movement. These
# are the pages whose status actually answers "is it working", including the
# three language hubs that were pushed into the crawl queue by hand on
# 2026-09-30, so watch these first and the percentages later.
CANARIES = [
    "https://parkingnetherlands.com/",
    "https://parkingnetherlands.com/nl/",
    "https://parkingnetherlands.com/de/",
    "https://parkingnetherlands.com/fr/",
    "https://parkingnetherlands.com/parking-fines",
    "https://parkingnetherlands.com/amsterdam-cheap-parking",
    "https://parkingnetherlands.com/ev-charging",
    "https://parkingnetherlands.com/about",
]

SECTIONS = [
    ("nl garages", lambda p: p.startswith("/nl/") and "/garage/" in p),
    ("de garages", lambda p: p.startswith("/de/") and "/garage/" in p),
    ("fr garages", lambda p: p.startswith("/fr/") and "/garage/" in p),
    ("en garages", lambda p: p.startswith("/garage/")),
    ("nl pages", lambda p: p.startswith("/nl/")),
    ("de pages", lambda p: p.startswith("/de/")),
    ("fr pages", lambda p: p.startswith("/fr/")),
    ("en pages", lambda p: True),
]


def section_of(url):
    path = re.sub(r"^https?://[^/]+", "", url) or "/"
    for name, test in SECTIONS:
        if test(path):
            return name
    return "en pages"


def fetch_sitemap():
    req = urllib.request.Request(SITEMAP, headers={"User-Agent": "index-watch"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return re.findall(r"<loc>([^<]+)</loc>", r.read().decode("utf-8"))


def sample(urls, per_section):
    """A stable, evenly spread sample per section.

    Sorting by a hash of the url gives an arbitrary but REPEATABLE order, so
    the same pages are inspected every run and the trend means something. A
    random sample would make each run measure a different population.
    """
    buckets = {}
    for u in urls:
        buckets.setdefault(section_of(u), []).append(u)
    picked = []
    for name in sorted(buckets):
        ranked = sorted(
            buckets[name],
            key=lambda u: hashlib.sha1(u.encode()).hexdigest(),
        )
        picked += [(name, u) for u in ranked[:per_section]]
    return picked


def service():
    key = os.environ.get("GSC_SA_KEY")
    if not key or not Path(key).is_file():
        sys.exit("ERROR: GSC_SA_KEY is not set or missing. See README.md.")
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_file(
        key, scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
    )
    return build("searchconsole", "v1", credentials=creds,
                 cache_discovery=False)


def inspect(svc, url):
    r = svc.urlInspection().index().inspect(
        body={"inspectionUrl": url, "siteUrl": PROP}
    ).execute()
    idx = r.get("inspectionResult", {}).get("indexStatusResult", {})
    return {
        "verdict": idx.get("verdict", "UNKNOWN"),
        "coverage": idx.get("coverageState", "unknown"),
        "crawled": bool(idx.get("lastCrawlTime")),
    }


def run(per_section, pause):
    svc = service()
    rows = sample(fetch_sitemap(), per_section)
    print(f"inspecting {len(rows)} urls across "
          f"{len(set(s for s, _ in rows))} sections\n")
    results = []
    for i, (sec, url) in enumerate(rows, 1):
        try:
            r = inspect(svc, url)
        except Exception as e:  # keep going, one bad url must not kill the run
            r = {"verdict": "ERROR", "coverage": str(e)[:80], "crawled": False}
        results.append({"section": sec, "url": url, **r})
        print(f"  [{i:>3}/{len(rows)}] {sec:12} "
              f"{r['verdict']:8} {r['coverage'][:44]}")
        time.sleep(pause)

    canary = {}
    print()
    for url in CANARIES:
        try:
            r = inspect(svc, url)
        except Exception as e:
            r = {"verdict": "ERROR", "coverage": str(e)[:80], "crawled": False}
        canary[url.replace("https://parkingnetherlands.com", "") or "/"] = r
        print(f"  canary {url.replace('https://parkingnetherlands.com','') or '/':26}"
              f" {r['verdict']:8} {r['coverage'][:44]}")
        time.sleep(pause)

    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    by = {}
    for r in results:
        b = by.setdefault(r["section"], {"n": 0, "indexed": 0, "crawled": 0})
        b["n"] += 1
        b["indexed"] += r["verdict"] == "PASS"
        b["crawled"] += r["crawled"]
    entry = {"at": stamp, "sections": by, "canaries": canary,
             "total": {
                 "n": len(results),
                 "indexed": sum(b["indexed"] for b in by.values()),
                 "crawled": sum(b["crawled"] for b in by.values()),
             }}
    OUT.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def show(entry=None):
    if not LOG.is_file():
        print("no history yet")
        return
    hist = [json.loads(l) for l in LOG.read_text().splitlines() if l.strip()]
    if not hist:
        return
    last = entry or hist[-1]
    print(f"\n{'section':12} {'sampled':>8} {'crawled':>8} {'indexed':>8}"
          f" {'indexed %':>10}")
    for sec in sorted(last["sections"]):
        b = last["sections"][sec]
        pct = b["indexed"] / b["n"] * 100 if b["n"] else 0
        print(f"{sec:12} {b['n']:>8} {b['crawled']:>8} {b['indexed']:>8}"
              f" {pct:>9.0f}%")
    t = last["total"]
    pct = t["indexed"] / t["n"] * 100 if t["n"] else 0
    print(f"{'ALL':12} {t['n']:>8} {t['crawled']:>8} {t['indexed']:>8}"
          f" {pct:>9.0f}%")

    if last.get("canaries"):
        print(f"\n{'key page':28} status")
        for path, r in last["canaries"].items():
            mark = "indexed" if r["verdict"] == "PASS" else r["coverage"][:40]
            print(f"{path:28} {mark}")

    if len(hist) > 1:
        print(f"\ntrend, indexed share of the same sample:")
        for h in hist[-12:]:
            t = h["total"]
            p = t["indexed"] / t["n"] * 100 if t["n"] else 0
            bar = "#" * int(p / 2)
            print(f"  {h['at'][:16]}  {p:>5.0f}%  {bar}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-section", type=int, default=8,
                    help="urls to inspect per section (8 x 8 = 64 per run)")
    ap.add_argument("--pause", type=float, default=0.4,
                    help="seconds between calls, the limit is 600/minute")
    ap.add_argument("--history", action="store_true",
                    help="print the trend without calling the API")
    a = ap.parse_args()
    show(None if a.history else run(a.per_section, a.pause))
