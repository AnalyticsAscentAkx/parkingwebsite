#!/usr/bin/env python3
"""Tell every search engine about pages that changed, however they changed.

The daily publish pinged IndexNow only for the pages it rebuilt itself, so a
page that arrived through a merged pull request (a new translation, a new
guide) was never submitted anywhere. This reads the sitemap, takes every URL
whose lastmod is within the last --days days and that has not been submitted
since that lastmod, checks it answers 200 on the live site, and then:

  1. IndexNow (api.indexnow.org shares with Bing, Yandex, Seznam, Naver, Yep;
     Bing's index also feeds ChatGPT search and Copilot)
  2. Google: resubmits sitemap.xml through the Search Console API (Google
     ignores IndexNow and has no "request indexing" API for normal pages)

State lives in scripts/daily/index_submitted.json (not served: /scripts/ is
closed). Rerunnable: a URL is sent again only when its lastmod moves.

    python3 scripts/seo/submit_index.py --dry-run
    python3 scripts/seo/submit_index.py --days 2
"""
import argparse
import json
import re
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITE = "https://parkingnetherlands.com"
STATE = ROOT / "scripts" / "daily" / "index_submitted.json"
KEYF = ROOT / "scripts" / "daily" / "indexnow_key.txt"


def changed_urls(days):
    sm = (ROOT / "sitemap.xml").read_text("utf-8")
    since = (date.today() - timedelta(days=days)).isoformat()
    out = {}
    for loc, lastmod in re.findall(r"<loc>([^<]+)</loc>\s*<lastmod>([^<]+)</lastmod>", sm):
        if lastmod[:10] >= since:
            out[loc] = lastmod[:10]
    return out


def status(url):
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "parkingnetherlands-index-check"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except Exception as e:
        return getattr(e, "code", 0)


def indexnow(urls):
    key = KEYF.read_text().strip()
    body = json.dumps({"host": "parkingnetherlands.com", "key": key,
                       "keyLocation": f"{SITE}/{key}.txt", "urlList": urls}).encode()
    req = urllib.request.Request("https://api.indexnow.org/indexnow", data=body, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except Exception as e:
        return getattr(e, "code", 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=2)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    todo = {u: m for u, m in changed_urls(a.days).items() if state.get(u) != m}
    print(f"index: {len(todo)} changed URL(s) not yet submitted (lastmod within {a.days} days)")
    if not todo:
        return 0
    with ThreadPoolExecutor(max_workers=8) as ex:          # polite: 8 at a time
        codes = dict(zip(todo, ex.map(status, todo)))
    live = [u for u in todo if codes[u] == 200]
    for u in todo:
        if codes[u] != 200:
            print(f"  WARN not live ({codes[u]}): {u}")
    print(f"  {len(live)} live, e.g. {live[:3]}")
    if a.dry_run or not live:
        return 0

    rc = indexnow(live[:10000]) if KEYF.exists() else "no key"
    print(f"  IndexNow HTTP {rc} for {len(live)} URL(s)")
    gpy = ROOT / "scripts" / "gsc_agent" / ".venv" / "bin" / "python"
    g = subprocess.run([str(gpy if gpy.exists() else sys.executable),
                        str(ROOT / "scripts" / "gsc_agent" / "submit_sitemap.py")],
                       capture_output=True, text=True)
    print("  " + (g.stdout.strip() or g.stderr.strip()[-200:]))
    if rc in (200, 202):
        state.update({u: todo[u] for u in live})
        STATE.write_text(json.dumps(state, indent=0, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
