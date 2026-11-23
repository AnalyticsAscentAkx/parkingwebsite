#!/usr/bin/env python3
"""Date each page by when its own content last changed, not when the file did.

The sitemap lastmod used to be the file's last git commit, and the daily run
stamped today on every staged page. A nav, footer or CSS-version change
rewrites all 1,476 pages, so on 2026-11-09 1,434 URLs got the same lastmod and
IndexNow was sent 1,468 "changed" URLs. A lastmod that moves for every page at
once tells a crawler nothing, and Google stops using it to pick what to fetch:
/ev-charging and /about had sat in "Discovered / unknown" for eight weeks.

The fingerprint is the visible text of the page with <head>, <nav>, <footer>,
<script>, <style> and the language line removed. The date only moves when that
text changes. State lives in scripts/seo/content_dates.json (/scripts/ is not
served): {url: [fingerprint, date]}.

    python3 scripts/seo/content_dates.py seed   # one-off: date every page from git history
"""
import hashlib
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "scripts" / "seo" / "content_dates.json"

STRIP = [re.compile(p, re.S | re.I) for p in (
    r"<head\b.*?</head>", r"<nav\b.*?</nav>", r"<footer\b.*?</footer>",
    r"<script\b.*?</script>", r"<style\b.*?</style>", r"<!--.*?-->",
    r'<p class="site-langs">.*?</p>',
)]
UPDATED = re.compile(r"(updated|bijgewerkt|aktualisiert|mise? à jour)( le)? \d{4}-\d{2}-\d{2}", re.I)


def fingerprint(html: str) -> str:
    for rx in STRIP:
        html = rx.sub(" ", html)
    # keep link targets: a changed href is a content change
    html = re.sub(r'<a\b[^>]*href="([^"]*)"[^>]*>', r" \1 ", html)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    # "Page updated 2026-11-09" is the generator's run date, rewritten on all
    # 1,296 garage pages every day; it is not a change to what the page says
    text = UPDATED.sub("", text)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def load():
    return json.loads(STATE.read_text("utf-8")) if STATE.exists() else {}


def save(state):
    STATE.write_text(json.dumps(state, indent=0, sort_keys=True) + "\n", "utf-8")


def lastmod(state, url, path, today):
    """The page's content date; records today when the content has changed."""
    fp = fingerprint(path.read_text("utf-8", "ignore"))
    old = state.get(url)
    if old and old[0] == fp:
        return old[1]
    state[url] = [fp, today]
    return today


def _git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout


def seed_one(rel):
    """Date of the oldest commit whose content still matches today's file."""
    cur = fingerprint((ROOT / rel).read_text("utf-8", "ignore"))
    date = None
    for line in _git("log", "--format=%H %cs", "--", rel).splitlines():
        sha, d = line.split()
        blob = _git("show", f"{sha}:{rel}")
        if not blob or fingerprint(blob) != cur:
            break
        date = d
    return cur, date


def seed(url_paths, today):
    """url_paths: {url: Path}. Pages with no matching commit get today."""
    state = {}
    items = list(url_paths.items())
    with ThreadPoolExecutor(8) as ex:
        res = ex.map(lambda kv: seed_one(kv[1].relative_to(ROOT).as_posix()), items)
        for (url, _), (fp, d) in zip(items, res):
            state[url] = [fp, d or today]
    save(state)
    return state


if __name__ == "__main__" and sys.argv[1:] == ["seed"]:
    sys.path.insert(0, str(Path(__file__).parent))
    import enrich_site
    enrich_site.do_sitemap(reseed=True)
