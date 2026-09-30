#!/usr/bin/env python3
"""Stamp the one canonical nav, footer and stylesheet onto every page.

The site grew two generations of markup (a 2025 "shared.css" family with an
emoji nav, and the 2026 "site.css" design system), and even inside the newer
family the nav drifted page by page. This script is the single source of truth
for site chrome:

    scripts/site/nav.html      the header, exactly as every page must carry it
    scripts/site/footer.html   the footer, likewise
    site.css                   the only stylesheet a page links

Run it after adding or regenerating any page. It is idempotent and only
rewrites files whose content actually changes.

    python3 scripts/site/apply_chrome.py            # apply
    python3 scripts/site/apply_chrome.py --check    # exit 1 if anything drifted
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAV = (ROOT / "scripts/site/nav.html").read_text("utf-8").strip()
FOOTER = (ROOT / "scripts/site/footer.html").read_text("utf-8").strip()

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">\n'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
         '<link href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600;700;800'
         '&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">')
# Bump the version whenever site.css changes in a way older pages depend on;
# Cloudflare and browsers cache the old file otherwise.
CSS_VERSION = "20261001c"
SITE_CSS = (f'<link rel="stylesheet" href="/site.css?v={CSS_VERSION}">\n<script src="/analytics.js?v={CSS_VERSION}" defer></script>'
            f'\n<script src="/site.js?v={CSS_VERSION}" defer></script>'
            f'\n<script src="/affiliates.js?v={CSS_VERSION}" defer></script>')

# Colours from the retired palette, mapped onto the design system. These
# survive in inline styles and Leaflet marker code on the older pages.
HEX_MAP = {
    "#0A1628": "#0B1120",   # legacy navy        -> ink
    "#0F2240": "#101A30",   # legacy navy-2      -> ink-2
    "#FF6B2C": "#EA580C",   # legacy orange      -> signal orange
    "#E85A1F": "#C2410C",   # legacy orange dark -> signal hover
    "#FF9A5C": "#4159E8",   # legacy logo tint   -> cobalt tint
    "#00C9A7": "#059669",   # legacy teal (good) -> ok green
    "#FFDD00": "#EA580C",   # legacy yellow CTA  -> signal orange
}
HEX_RE = re.compile("|".join(re.escape(k) for k in HEX_MAP), re.I)

sys.path.insert(0, str(ROOT / "scripts"))
from i18n.strings import CHROME, HREF, city_url, LANGS  # noqa: E402
CITY_SLUGS = ["amsterdam","rotterdam","the-hague","utrecht","eindhoven","groningen","maastricht","leiden","haarlem","breda","delft","nijmegen","tilburg","zwolle"]

def lang_of(url: str) -> str:
    m = re.match(r"^/(nl|de|fr)(/|$)", url)
    return m.group(1) if m else "en"

_LOC_CACHE = {}
LANG_LINK_RE = re.compile(r'<a\b[^>]*\bdata-lang="([a-z]{2})"[^>]*>.*?</a>', re.S)

def localize(html: str, lang: str) -> str:
    """Chrome in the page's language: links written for one language only are
    dropped elsewhere, labels come from the table, and city links point at the
    localized city pages where they exist."""
    key = (lang, hash(html))
    if key in _LOC_CACHE: return _LOC_CACHE[key]
    # a link tagged for another language has no business on this page
    out = LANG_LINK_RE.sub(lambda m: m.group(0) if m.group(1) == lang else "", html)
    if lang == "en":
        _LOC_CACHE[key] = out
        return out
    for en, loc in sorted(CHROME[lang].items(), key=lambda kv: -len(kv[0])):
        out = out.replace(">" + en + "<", ">" + loc + "<")
    for slug in CITY_SLUGS:
        target = city_url(lang, slug)
        if (ROOT / (target.strip("/") + ".html")).exists():
            out = re.sub(r'href="/' + re.escape(slug) + '"', 'href="' + target + '"', out)
    for en, loc in HREF.get(lang, {}).items():
        if (ROOT / (loc.split("#")[0].strip("/") + ".html")).exists():
            out = out.replace('href="' + en + '"', 'href="' + loc + '"')
    out = out.replace('<a href="/" class="logo">', '<a href="/' + lang + '/" class="logo">') if (ROOT / lang / "index.html").exists() else out
    _LOC_CACHE[key] = out
    return out

NAV_RE = re.compile(r"<nav\b.*?</nav>", re.S)
FOOTER_RE = re.compile(r"<footer\b.*?</footer>", re.S)
SHARED_LINK_RE = re.compile(r'\s*<link[^>]+href="/?shared\.css"[^>]*>', re.I)
SITE_LINK_RE = re.compile(r'<link[^>]+href="/?site\.css(?:\?[^"]*)?"[^>]*>(?:\s*<script src="/analytics\.js[^>]*></script>)?(?:\s*<script src="/site\.js[^>]*></script>)?(?:\s*<script src="/affiliates\.js[^>]*></script>)?', re.I)
FONT_LINK_RE = re.compile(r'\s*<link[^>]+fonts\.googleapis\.com/css2[^>]*>', re.I)
PRECONNECT_RE = re.compile(r'\s*<link rel="preconnect" href="https://fonts\.g[^"]+"[^>]*>', re.I)
IMPORT_FONT_RE = re.compile(r'@import\s+url\([^)]*fonts\.googleapis[^)]*\);?', re.I)



# French typography puts a space before ? ! ; : and inside guillemets. A plain
# space lets the browser break the line there, which strands the punctuation on
# the next line, so French pages get a no-break space instead. Text and the few
# attributes a reader sees are touched; script and style blocks never are.
_FR_BEFORE = re.compile(r"[ \u202f\u2009]([?!;:\u00bb])")
_FR_AFTER = re.compile(r"(\u00ab)[ \u202f\u2009]")
_FR_ATTR = re.compile(r'((?:content|placeholder|title|aria-label|alt)=")([^"]*)(")')
_TEXT_NODE = re.compile(r">([^<>]*)<")
_SKIP_BLOCK = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.S | re.I)


def _fr(text: str) -> str:
    return _FR_AFTER.sub("\u00ab\u00a0", _FR_BEFORE.sub("\u00a0\\1", text))


def french_spacing(html: str) -> str:
    out, last = [], 0
    for m in _SKIP_BLOCK.finditer(html):
        out.append(_fr_segment(html[last:m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(_fr_segment(html[last:]))
    return "".join(out)


def _fr_segment(seg: str) -> str:
    seg = _TEXT_NODE.sub(lambda m: ">" + _fr(m.group(1)) + "<", seg)
    return _FR_ATTR.sub(lambda m: m.group(1) + _fr(m.group(2)) + m.group(3), seg)

def page_url(path: Path) -> str:
    rel = path.relative_to(ROOT).as_posix()
    if rel == "index.html":
        return "/"
    if rel.endswith("/index.html"):
        return "/" + rel[: -len("index.html")]
    return "/" + rel[: -len(".html")]


# Pages whose main content already is the search box do not get the sticky bar.
NO_NAV_SEARCH = {"/", "/search", "/ev-charging"}
NAV_SEARCH_RE = re.compile(r'\s*<form class="nav-search".*?</form>', re.S)


def nav_for(url: str) -> str:
    """Mark the nav item that owns this page as active; drop the search bar where redundant."""
    nav = NAV_SEARCH_RE.sub("", NAV) if url in NO_NAV_SEARCH else NAV
    nav = localize(nav, lang_of(url))
    out = []
    parts = re.split(r"(?=<li)", nav)
    # A direct top-level item wins over a dropdown that also lists the page.
    def is_direct(li):
        hrefs = re.findall(r'href="([^"]+)"', li)
        return hrefs[:1] == [url] or (li.startswith('<li class="nav-pair"') and url in hrefs)
    direct = any(is_direct(li) for li in parts if li.startswith("<li"))
    marked = False
    for li in parts:
        if li.startswith("<li"):
            hrefs = re.findall(r'href="([^"]+)"', li)
            own = is_direct(li) or (not direct and li.startswith('<li class="has-drop"') and url in hrefs)
            if own and not marked:
                marked = True
                if li.startswith('<li class="nav-pair"'):
                    li = li.replace('<li class="nav-pair">', '<li class="nav-pair active">', 1)
                    li = li.replace('href="' + url + '" class="nav-find', 'href="' + url + '" class="nav-find is-on', 1)
                else:
                    li = (li.replace('<li class="has-drop">', '<li class="has-drop active">', 1)
                          if li.startswith('<li class="has-drop">') else li.replace("<li>", '<li class="active">', 1))
        out.append(li)
    return "".join(out)


def apply(html: str, url: str) -> str:
    # 1. chrome
    html, n = NAV_RE.subn(lambda m: nav_for(url), html, count=1)
    if n == 0:
        html = html.replace("<body>", "<body>\n" + nav_for(url), 1)
    footer = localize(FOOTER, lang_of(url))
    if FOOTER_RE.search(html):
        # replace the last footer only
        last = list(FOOTER_RE.finditer(html))[-1]
        html = html[: last.start()] + footer + html[last.end():]
    else:
        html = html.replace("</body>", footer + "\n</body>", 1)

    # 2. one stylesheet, one font stack
    head_end = html.find("</head>")
    head, body = html[:head_end], html[head_end:]
    head = SHARED_LINK_RE.sub("", head)
    head = IMPORT_FONT_RE.sub("", head)
    head = PRECONNECT_RE.sub("", head)
    head = FONT_LINK_RE.sub("", head)
    if SITE_LINK_RE.search(head):
        head = SITE_LINK_RE.sub(FONTS + "\n" + SITE_CSS, head, count=1)
    else:
        # put it right after the canonical link when there is one, else at the end of head
        m = re.search(r'<link rel="canonical"[^>]*>', head)
        ins = FONTS + "\n" + SITE_CSS
        head = (head[: m.end()] + "\n" + ins + head[m.end():]) if m else head + "\n" + ins + "\n"
    html = head + body

    # 3. retire the old palette wherever it was hard-coded
    html = HEX_RE.sub(lambda m: HEX_MAP[m.group(0).upper()], html)

    # 4. French punctuation must not wrap onto the next line
    if lang_of(url) == "fr":
        html = french_spacing(html)
    return html


def main() -> int:
    check = "--check" in sys.argv
    pages = sorted(p for p in ROOT.rglob("*.html")
                   if ".git" not in p.parts and "scripts" not in p.parts and "node_modules" not in p.parts)
    changed = []
    for p in pages:
        src = p.read_text("utf-8", errors="surrogateescape")
        out = apply(src, page_url(p))
        if out != src:
            changed.append(p.relative_to(ROOT).as_posix())
            if not check:
                p.write_text(out, "utf-8", errors="surrogateescape")
    verb = "would change" if check else "updated"
    print(f"chrome: {len(pages)} pages scanned, {len(changed)} {verb}")
    for c in changed[:20]:
        print("  ", c)
    if len(changed) > 20:
        print(f"   ... and {len(changed) - 20} more")
    return 1 if (check and changed) else 0


if __name__ == "__main__":
    sys.exit(main())
