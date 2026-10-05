#!/usr/bin/env python3
"""Daily QA pass over the live site.

Written after a day in which three separate faults were live at once and none
of them announced itself:

  * ev.css and ev.js were referenced by two pages and returned 404, because
    the files were never committed. Both pages served HTTP 200 the whole time
    while rendering unstyled with no map.
  * The mobile menu painted over its own close button, so a tap to dismiss it
    hit a nav link and navigated the visitor away instead.
  * Four commits sat pushed but undeployed, so fixes that looked shipped were
    not live at all.

Every check here exists because something in that list would have been caught
by it. The last one is the reason for the deploy-integrity check: a green
test run against a stale deployment is worse than no test run.

It tests the LIVE site by default, because that is what visitors get. Pass
--base http://127.0.0.1:8899 to test a local server instead.

Usage:
  python3 audit.py                 # sample pass, what the daily job runs
  python3 audit.py --full          # parse every page, slow
  python3 audit.py --sample 200
"""
import argparse
import concurrent.futures as cf
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OUT = REPO / "data" / "qa"
BASE = "https://parkingnetherlands.com"
UA = "parkingnetherlands-qa/1.0 (+site owner self-test)"
TIMEOUT = 25

# House style the owner has asked for repeatedly. Both read as machine-written
# and both have had to be stripped from the site once already.
DASHES = re.compile(r"[–—]")
# U+2600-U+27BF is Miscellaneous Symbols and Dingbats, which holds plenty of
# legitimate interface glyphs: the hamburger icon, ticks, crosses, arrows. The
# first run flagged 56 pages for the menu button alone. Allow the ones the
# design system actually uses and flag the rest, which are true emoji blocks.
UI_GLYPHS = ("\u2630\u2713\u2714\u2715\u2716\u2717\u2718\u2605\u2606"
             "\u25b6\u25c0\u25cf\u2022\u2192\u2190")
# The first version of this started at U+1F300 and missed every emoji that
# was actually on the site: the squared letters live in the Enclosed
# Alphanumeric Supplement at U+1F100 (P in a box, FREE in a box, the
# regional-indicator flags) and the clock faces sit in Miscellaneous
# Technical at U+23F0. Fifty-two of them survived a run that reported no
# findings at all. The ranges below cover the pictographic blocks from
# U+1F000 up, plus the two low blocks that actually bit us, plus the
# variation selector that trails an emoji presentation form.
EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF"      # pictographs, flags, enclosed letters
    "\u2300-\u23FF"               # clocks, stopwatches, misc technical
    "\u2600-\u27BF"               # misc symbols and dingbats
    "\u2B00-\u2BFF"               # arrows and stars
    "\uFE0F]"                     # emoji variation selector
)


def emoji_in(text):
    """True emoji only, interface glyphs allowed."""
    return [c for c in EMOJI.findall(text) if c not in UI_GLYPHS]


def encode(url):
    """Percent-encode the parts urllib refuses to send.

    Several pages link to /search?q=P+R RAI Amsterdam with real spaces in the
    query. A browser encodes those silently; urllib raises, which the first
    run reported as status 0 and looked like 5 dead links that were fine.
    """
    sp = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((
        sp.scheme, sp.netloc,
        urllib.parse.quote(sp.path, safe="/%:@&=+$,~"),
        urllib.parse.quote(sp.query, safe="/?:@&=+$,~"),
        ""))


def fetch(url, method="GET"):
    """Return (status, body, seconds). Never raises."""
    req = urllib.request.Request(encode(url), method=method,
                                 headers={"User-Agent": UA})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read().decode("utf-8", "replace") if method == "GET" else ""
            return r.status, body, time.time() - t0
    except urllib.error.HTTPError as e:
        return e.code, "", time.time() - t0
    except Exception as e:
        return 0, str(e)[:120], time.time() - t0


class Page(HTMLParser):
    """Pull out only what the checks need. A real parser beats regex here
    because attribute order and quoting vary across the generators."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = None
        self._in_title = False
        self.desc = None
        self.canonical = None
        self.robots = None
        self.h1 = []
        self.h1_count = 0      # start tags, NOT text fragments: an <em>
                               # inside an h1 splits handle_data into three
                               # and made every styled heading look duplicated
        self._in_h1 = False
        self.assets = []       # css, js, img the page depends on
        self.links = []        # internal hrefs
        self.hreflang = []     # (lang, href)
        self.jsonld = []
        self._in_ld = False
        self.imgs_no_alt = 0
        self.text = []
        self._skip = 0         # inside script/style, text is not visible
        self.has_nav = False
        self.has_footer = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "h1":
            self._in_h1 = True
            self.h1_count += 1
        elif tag in ("script", "style"):
            self._skip += 1
            if a.get("type") == "application/ld+json":
                self._in_ld = True
            if tag == "script" and a.get("src"):
                self.assets.append(a["src"])
        elif tag == "meta":
            n = (a.get("name") or "").lower()
            if n == "description":
                self.desc = a.get("content", "")
            elif n == "robots":
                self.robots = a.get("content", "")
        elif tag == "link":
            rel = (a.get("rel") or "").lower()
            if "canonical" in rel:
                self.canonical = a.get("href")
            elif "alternate" in rel and a.get("hreflang"):
                self.hreflang.append((a["hreflang"], a.get("href", "")))
            elif "stylesheet" in rel and a.get("href"):
                self.assets.append(a["href"])
        elif tag == "img":
            if a.get("src"):
                self.assets.append(a["src"])
            if not (a.get("alt") or "").strip() and a.get("alt") is None:
                self.imgs_no_alt += 1
        elif tag == "a" and a.get("href"):
            self.links.append(a["href"])
        elif tag == "nav":
            self.has_nav = True
        elif tag == "footer":
            self.has_footer = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "h1":
            self._in_h1 = False
        elif tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
            self._in_ld = False

    def handle_data(self, d):
        if self._in_title:
            self.title = (self.title or "") + d
        if self._in_h1:
            self.h1.append(d.strip())
        if self._in_ld:
            self.jsonld.append(d)
        if not self._skip:
            self.text.append(d)


def norm(href, page_url):
    """Absolute, same-host, fragment-stripped, or None if external."""
    if not href or href.startswith(("mailto:", "tel:", "javascript:", "data:", "#")):
        return None
    if href.startswith("//"):
        href = "https:" + href
    if href.startswith("http"):
        return href.split("#")[0] if href.startswith(BASE) else None
    if href.startswith("/"):
        return BASE + href.split("#")[0]
    base = page_url.rsplit("/", 1)[0]
    return (base + "/" + href).split("#")[0]


def sitemap_urls():
    st, body, _ = fetch(f"{BASE}/sitemap.xml")
    if st != 200:
        return []
    return re.findall(r"<loc>([^<]+)</loc>", body)


def stratify(urls, n):
    """Spread the sample across sections so one big section cannot hide a
    fault in a small one. Deterministic per day, and the offset rotates so
    consecutive days cover different pages."""
    day = datetime.now(timezone.utc).toordinal()
    groups = defaultdict(list)
    for u in urls:
        p = u.replace(BASE, "") or "/"
        if "/garage/" in p:
            k = p.split("/")[1] if p.startswith("/nl/") or p.startswith("/de/") \
                or p.startswith("/fr/") else "en"
            k += " garages"
        elif p.startswith(("/nl/", "/de/", "/fr/")):
            k = p.split("/")[1] + " pages"
        else:
            k = "en pages"
        groups[k].append(u)
    per = max(1, n // max(1, len(groups)))
    out = []
    for k in sorted(groups):
        g = sorted(groups[k])
        off = day % max(1, len(g))
        out += [g[(off + i) % len(g)] for i in range(min(per, len(g)))]
    return out


def recheck(bad, method="HEAD"):
    """Re-test failures one at a time before believing them.

    The concurrent sweep runs 12 to 16 requests at once and Cloudflare
    sometimes drops one, which surfaces as status 0. The first scheduled run
    reported 22 dead pages that were all serving 200 when asked politely.
    A daily report that cries wolf teaches the reader to ignore it, so a
    failure only counts if it fails again on its own, with a pause.
    """
    confirmed = []
    for url, st in bad:
        time.sleep(0.4)
        st2, _, _ = fetch(url, method)
        if st2 not in (200, 301, 302, 308):
            confirmed.append((url, st2 or st))
    return confirmed


def check_availability(urls, workers=16):
    """HEAD everything. Cheap, and it is the check that finds dead pages."""
    bad, slow = [], []
    with cf.ThreadPoolExecutor(workers) as ex:
        for url, (st, _, dt) in zip(urls, ex.map(lambda u: fetch(u, "HEAD"), urls)):
            if st != 200:
                bad.append((url, st))
            elif dt > 3.0:
                slow.append((url, round(dt, 1)))
    return bad, slow


def deploy_integrity():
    """Is what we committed actually what visitors are served?

    Four commits sat undeployed for over an hour while every local check
    passed. A QA run that does not verify this can report a clean site that
    nobody is being served.
    """
    issues = []
    ap = REPO / "scripts" / "site" / "apply_chrome.py"
    if not ap.is_file():
        return issues
    m = re.search(r'CSS_VERSION\s*=\s*"([^"]+)"', ap.read_text())
    if not m:
        return issues
    want = m.group(1)
    st, body, _ = fetch(BASE + "/")
    if st != 200:
        issues.append(("HARD", "homepage", f"homepage returned {st}"))
        return issues
    live = re.search(r"site\.css\?v=([0-9a-z]+)", body)
    live = live.group(1) if live else "none"
    if live != want:
        issues.append((
            "HARD", "deploy",
            f"live site serves asset version {live}, repo expects {want}: "
            f"the last commits are not deployed, so fixes are not live. "
            f"Read the BUILD LOG, not this check, for the reason: "
            f"dash.cloudflare.com -> Workers & Pages -> parking -> "
            f"Deployments -> Build history. On 2026-09-30 a single invalid "
            f"_redirects line (status 404, which static assets reject) failed "
            f"ten deploys in a row while this check could only see the symptom"))
    return issues


def check_page(url):
    """Everything that can be judged from one page's html."""
    out = []
    st, body, dt = fetch(url)
    if st != 200:
        return [("HARD", url, f"returned {st}")], None
    p = Page()
    try:
        p.feed(body)
    except Exception as e:
        return [("WARN", url, f"html did not parse: {e}")], None

    t = (p.title or "").strip()
    if not t:
        out.append(("HARD", url, "no <title>"))
    elif len(t) > 70:
        out.append(("WARN", url, f"title {len(t)} chars, Google cuts near 60"))

    d = (p.desc or "").strip()
    if not d:
        out.append(("WARN", url, "no meta description"))
    else:
        if len(d) > 165:
            out.append(("WARN", url, f"meta description {len(d)} chars"))
        # A description cut mid-word is a bug a reviewer caught once. But
        # plenty of good descriptions simply end without a full stop, so only
        # complain when the length is near a truncation limit AND it ends
        # unpunctuated, which is what an actual cut looks like.
        if len(d) >= 150 and not d.rstrip().endswith((".", "!", "?", "\u2026")):
            out.append(("WARN", url, f"description looks truncated at {len(d)}: ...{d[-30:]!r}"))

    if not p.canonical:
        out.append(("WARN", url, "no canonical"))
    if p.robots and "noindex" in p.robots and "/404" not in url:
        out.append(("HARD", url, f"robots meta says {p.robots}"))
    if p.h1_count == 0:
        out.append(("WARN", url, "no h1"))
    elif p.h1_count > 1:
        out.append(("WARN", url, f"{p.h1_count} h1 tags"))
    if not p.has_nav:
        out.append(("HARD", url, "no nav, chrome did not apply"))
    if not p.has_footer:
        out.append(("HARD", url, "no footer, chrome did not apply"))

    for blob in p.jsonld:
        b = blob.strip()
        if not b:
            continue
        try:
            json.loads(b)
        except Exception as e:
            out.append(("HARD", url, f"JSON-LD does not parse: {str(e)[:60]}"))
            break

    visible = "".join(p.text)
    if DASHES.search(visible):
        n = len(DASHES.findall(visible))
        out.append(("WARN", url, f"{n} em/en dash(es) in visible text"))
    em = emoji_in(visible)
    if em:
        out.append(("WARN", url, f"emoji in visible text: {''.join(sorted(set(em)))[:12]}"))

    return out, p


def main():
    global BASE
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=80)
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--skip-availability", action="store_true")
    a = ap.parse_args()
    BASE = a.base.rstrip("/")

    started = datetime.now(timezone.utc)
    issues = []
    print(f"QA pass against {BASE}")

    issues += deploy_integrity()

    urls = sitemap_urls()
    if not urls:
        issues.append(("HARD", "sitemap.xml", "sitemap missing or unparseable"))
        urls = [BASE + "/"]
    print(f"  sitemap: {len(urls)} urls")

    if not a.skip_availability:
        bad, slow = check_availability(urls)
        bad = recheck(bad)
        for u, st in bad:
            issues.append(("HARD", u, f"in sitemap but returns {st}"))
        for u, s in slow[:10]:
            issues.append(("WARN", u, f"slow: {s}s"))
        print(f"  availability: {len(bad)} dead, {len(slow)} slow")

    pages = urls if a.full else stratify(urls, a.sample)
    print(f"  parsing {len(pages)} pages")
    parsed = {}
    with cf.ThreadPoolExecutor(10) as ex:
        for url, (iss, p) in zip(pages, ex.map(check_page, pages)):
            issues += iss
            if p:
                parsed[url] = p

    # Assets. This is the ev.css check: a page can be 200 and still broken
    # because the stylesheet it depends on is not there.
    assets = set()
    for url, p in parsed.items():
        for s in p.assets:
            n = norm(s.split("?")[0], url)
            if n:
                assets.add(n)
    if assets:
        alist = sorted(assets)
        abad = []
        with cf.ThreadPoolExecutor(12) as ex:
            for u, (st, _, _) in zip(alist, ex.map(lambda x: fetch(x, "HEAD"), alist)):
                if st != 200:
                    abad.append((u, st))
        for u, st in recheck(abad):
            issues.append(("HARD", u, f"referenced asset returns {st}"))
        print(f"  assets: {len(assets)} checked")

    # Internal links, deduped across the sample.
    links = set()
    for url, p in parsed.items():
        for h in p.links:
            n = norm(h, url)
            if n:
                links.add(n)
    if links:
        llist = sorted(links)
        lbad = []
        with cf.ThreadPoolExecutor(14) as ex:
            for u, (st, _, _) in zip(llist, ex.map(lambda x: fetch(x, "HEAD"), llist)):
                if st not in (200, 301, 302, 308):
                    lbad.append((u, st))
        for u, st in recheck(lbad):
            issues.append(("HARD", u, f"internal link target returns {st}"))
        print(f"  links: {len(links)} checked")

    # Duplicate titles across the sample.
    titles = Counter((p.title or "").strip() for p in parsed.values() if p.title)
    for t, n in titles.items():
        if n > 1 and t:
            issues.append(("WARN", "(several)", f"{n} pages share the title {t[:54]!r}"))

    # hreflang has to point both ways or Google ignores it.
    for url, p in parsed.items():
        if p.hreflang:
            langs = [l for l, _ in p.hreflang]
            if "x-default" not in langs and len(langs) > 1:
                issues.append(("WARN", url, "hreflang set without x-default"))

    hard = [i for i in issues if i[0] == "HARD"]
    warn = [i for i in issues if i[0] == "WARN"]

    OUT.mkdir(parents=True, exist_ok=True)
    stamp = started.isoformat(timespec="seconds")
    (OUT / "issues.json").write_text(json.dumps(
        {"at": stamp, "base": BASE, "pages_parsed": len(parsed),
         "hard": len(hard), "warn": len(warn),
         "issues": [{"level": l, "where": w, "what": m} for l, w, m in issues]},
        indent=1))

    lines = [f"# QA report {stamp}", "",
             f"Target {BASE}. {len(urls)} urls in sitemap, {len(parsed)} parsed.", "",
             f"**{len(hard)} hard, {len(warn)} warnings.**", ""]
    for name, group in (("Hard", hard), ("Warnings", warn)):
        if not group:
            continue
        lines += [f"## {name} ({len(group)})", ""]
        seen = Counter(m for _, _, m in group)
        shown = set()
        for lvl, where, msg in group:
            key = re.sub(r"\d+", "N", msg)
            if key in shown and seen[msg] > 3:
                continue
            shown.add(key)
            lines.append(f"- `{where.replace(BASE, '')}` {msg}")
        lines.append("")
    (OUT / "report.md").write_text("\n".join(lines))

    print(f"\n{len(hard)} hard, {len(warn)} warnings -> data/qa/report.md")
    for lvl, where, msg in hard[:15]:
        print(f"  HARD {where.replace(BASE,'')} {msg}")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
