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
CSS_VERSION = "20260929d"
SITE_CSS = f'<link rel="stylesheet" href="/site.css?v={CSS_VERSION}">'

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

NAV_RE = re.compile(r"<nav\b.*?</nav>", re.S)
FOOTER_RE = re.compile(r"<footer\b.*?</footer>", re.S)
SHARED_LINK_RE = re.compile(r'\s*<link[^>]+href="/?shared\.css"[^>]*>', re.I)
SITE_LINK_RE = re.compile(r'<link[^>]+href="/?site\.css(?:\?[^"]*)?"[^>]*>', re.I)
FONT_LINK_RE = re.compile(r'\s*<link[^>]+fonts\.googleapis\.com/css2[^>]*>', re.I)
PRECONNECT_RE = re.compile(r'\s*<link rel="preconnect" href="https://fonts\.g[^"]+"[^>]*>', re.I)
IMPORT_FONT_RE = re.compile(r'@import\s+url\([^)]*fonts\.googleapis[^)]*\);?', re.I)


def page_url(path: Path) -> str:
    rel = path.relative_to(ROOT).as_posix()
    if rel == "index.html":
        return "/"
    if rel.endswith("/index.html"):
        return "/" + rel[: -len("index.html")]
    return "/" + rel[: -len(".html")]


# Pages whose main content already is the search box do not get the sticky bar.
NO_NAV_SEARCH = {"/", "/search"}
NAV_SEARCH_RE = re.compile(r'\s*<form class="nav-search".*?</form>', re.S)


def nav_for(url: str) -> str:
    """Mark the nav item that owns this page as active; drop the search bar where redundant."""
    nav = NAV_SEARCH_RE.sub("", NAV) if url in NO_NAV_SEARCH else NAV
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
    if FOOTER_RE.search(html):
        # replace the last footer only
        last = list(FOOTER_RE.finditer(html))[-1]
        html = html[: last.start()] + FOOTER + html[last.end():]
    else:
        html = html.replace("</body>", FOOTER + "\n</body>", 1)

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
