#!/usr/bin/env python3
"""Offline site checks: one check per fault we have actually shipped.

Every time a fault reaches the live site (or nearly does), add a check here
that would have caught it, with the date and what happened. The daily run
calls this before the commit; a HARD finding blocks the publish, a WARN is
logged only.

    python3 scripts/qa/site_check.py            # all checks, exit 1 on HARD
    python3 scripts/qa/site_check.py --list     # what is checked and why

Reads the working tree only: no network, runs in a second or two.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITE = "https://parkingnetherlands.com"
NOINDEX = re.compile(r'<meta[^>]+name="robots"[^>]+noindex', re.I)
# Pages that are noindex on purpose. Anything else carrying the tag is a fault.
NOINDEX_OK = {"404.html", "offline.html", "privacy.html", "embed/charging.html",
              "outreach/medium-source.html"}
SKIP_DIRS = {"scripts", "node_modules", ".git"}

CHECKS = []


def check(found, why):
    """Register a check with the date the fault was found and what it did."""
    def wrap(fn):
        CHECKS.append((fn, found, why))
        return fn
    return wrap


def pages():
    for p in ROOT.rglob("*.html"):
        if not SKIP_DIRS.intersection(p.relative_to(ROOT).parts):
            yield p


def url_to_file(u):
    path = u[len(SITE):].strip("/")
    if not path:
        return ROOT / "index.html"
    for cand in (ROOT / f"{path}.html", ROOT / path / "index.html", ROOT / path):
        if cand.is_file():
            return cand
    return None


def sitemap_urls():
    return re.findall(r"<loc>([^<]+)</loc>", (ROOT / "sitemap.xml").read_text("utf-8"))


@check("2026-11-09", "/offline (noindex) was in sitemap.xml; Search Console emailed "
       "'Excluded by noindex'")
def sitemap_noindex():
    out = []
    for u in sitemap_urls():
        f = url_to_file(u)
        if f and NOINDEX.search(f.read_text("utf-8", "ignore")[:4000]):
            out.append(("HARD", u, "in sitemap but the page is noindex"))
    return out


@check("2026-11-09", "a page turning noindex by accident drops out of Google silently")
def unexpected_noindex():
    out = []
    for p in pages():
        rel = p.relative_to(ROOT).as_posix()
        if rel not in NOINDEX_OK and NOINDEX.search(p.read_text("utf-8", "ignore")[:4000]):
            out.append(("HARD", rel, "noindex tag on a page not in the noindex allowlist"))
    return out


@check("2026-11-09", "a sitemap URL with no page behind it is a submitted 404")
def sitemap_missing_file():
    redirects = (ROOT / "_redirects").read_text("utf-8") if (ROOT / "_redirects").exists() else ""
    sources = {line.split()[0].rstrip("/") for line in redirects.splitlines()
               if line.strip() and not line.startswith("#")}
    out = []
    for u in sitemap_urls():
        if url_to_file(u) is None:
            path = "/" + u[len(SITE):].strip("/")
            kind = "redirects elsewhere" if path.rstrip("/") in sources else "has no file"
            out.append(("HARD", u, f"in sitemap but {kind}"))
    return out


@check("2026-11-09", "the map priced a 2 hour stop by default and drivers read the total "
       "as the hourly price (Overamstel, 2026-10-28)")
def default_stop_one_hour():
    out = []
    for f in ("ev-map.js", "ev.js"):
        src = (ROOT / f).read_text("utf-8")
        if "7200000" in src:
            out.append(("HARD", f, "a 2 hour (7200000 ms) default stop is back"))
    for f in ("index.html", "search.html", "ev-charging.html", "embed/charging.html"):
        if "a 2 h stop" in (ROOT / f).read_text("utf-8"):
            out.append(("HARD", f, "page text still says the estimate assumes a 2 h stop"))
    return out


@check("2026-10-18", "a JS fix shipped without a version bump never reached returning "
       "visitors (cached ?v=)")
def asset_versions_agree():
    out = []
    for asset in ("ev-map.js", "ev-map.css", "site.css"):
        seen = {}
        for p in pages():
            for v in re.findall(r"/" + re.escape(asset) + r"\?v=([0-9a-z]+)", p.read_text("utf-8", "ignore")):
                seen.setdefault(v, []).append(p.relative_to(ROOT).as_posix())
        if len(seen) > 1:
            parts = ", ".join(f"v={v} on {len(fs)} pages (e.g. {fs[0]})" for v, fs in seen.items())
            out.append(("WARN", asset, f"pages load different versions: {parts}"))
    return out


@check("2026-11-09", "the daily commit carried a model co-author line; no model "
       "attribution in commits")
def no_model_attribution():
    out = []
    for f in (ROOT / "scripts").rglob("*.sh"):
        if re.search(r"Co-Authored-By:\s*Claude", f.read_text("utf-8", "ignore"), re.I):
            out.append(("HARD", f.relative_to(ROOT).as_posix(), "writes a model co-author line into commits"))
    return out


def _age_days(stamp):
    from datetime import datetime, timezone
    return (datetime.now(timezone.utc) - datetime.fromisoformat(stamp)).total_seconds() / 86400


@check("2026-11-09", "charging tariffs were never refreshed after 2026-09-28: every map "
       "price was six weeks old (no job called 'evlayer.cli tariffs')")
def ev_data_fresh():
    import json
    meta = json.loads((ROOT / "ev-data" / "meta.json").read_text("utf-8"))
    out = []
    for key, limit in (("generated", 2), ("locations_fetched", 2), ("tariffs_fetched", 3)):
        if key not in meta:
            continue   # older exports carry only "generated"
        if not meta[key]:
            out.append(("WARN", f"ev-data {key}", "never fetched"))
        elif _age_days(meta[key]) > limit:
            out.append(("WARN", f"ev-data {key}", f"{_age_days(meta[key]):.0f} days old (limit {limit})"))
    return out


@check("2026-11-09", "TotalEnergies dropped from 8,926 to 14 stations in the NDW feed "
       "on 2026-11-08; nothing noticed")
def operator_vanished():
    import json
    ops = json.loads((ROOT / "ev-data" / "meta.json").read_text("utf-8")).get("operators") or {}
    return [("WARN", name or "(no operator)", f"only {live:,} of {total:,} stations in the feed in the last 2 days")
            for name, (live, total) in ops.items() if live < total * 0.5]


@check("2026-09-28", "em dashes read as machine-written; removed site-wide, must not return")
def no_em_dashes():
    hits = [p.relative_to(ROOT).as_posix() for p in pages() if "—" in p.read_text("utf-8", "ignore")]
    return [("WARN", f"{len(hits)} pages", f"em dash found, e.g. {', '.join(hits[:3])}")] if hits else []


def main():
    if "--list" in sys.argv:
        for fn, found, why in CHECKS:
            print(f"{fn.__name__:<24} {found}  {why}")
        return 0
    hard = 0
    for fn, found, why in CHECKS:
        res = fn()
        status = "ok" if not res else ("FAIL" if any(s == "HARD" for s, _, _ in res) else "warn")
        print(f"{status:<4} {fn.__name__} ({len(res)})")
        for sev, where, msg in res[:15]:
            print(f"     {sev} {where}: {msg}")
        if len(res) > 15:
            print(f"     ... {len(res) - 15} more")
        hard += sum(1 for s, _, _ in res if s == "HARD")
    print(f"site_check: {hard} hard finding(s)")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
