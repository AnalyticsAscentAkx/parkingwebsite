#!/usr/bin/env python3
"""RSS feed at /feed.xml: today's charge point status plus the most recently
updated pages, so feed readers, aggregators and retrieval pipelines that
subscribe to feeds have something to subscribe to.

  python3 scripts/site/feed.py

Items are deterministic from the sitemap and the pages themselves, so a daily
run only changes the feed when the site changed. Garage pages are excluded:
1,292 of them share one lastmod and would drown everything else.
"""
import html as H, json, re, sys, datetime, email.utils
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITE = "https://parkingnetherlands.com"
MAX_ITEMS = 30

def rfc822(day):
    dt = datetime.datetime.strptime(day, "%Y-%m-%d").replace(hour=6, tzinfo=datetime.timezone.utc)
    return email.utils.format_datetime(dt)

def esc(s): return H.escape(s, quote=False)

def page_meta(url):
    rel = "index.html" if url == "/" else (url.strip("/") + ("/index.html" if url.endswith("/") else ".html"))
    p = ROOT / rel
    if not p.exists(): return None
    t = p.read_text("utf-8", errors="ignore")
    title = re.search(r"<title>(.*?)</title>", t, re.S)
    desc = re.search(r'<meta name="description" content="([^"]*)"', t)
    return {"title": H.unescape(re.sub(r"\s+", " ", title.group(1))).strip() if title else url,
            "desc": H.unescape(desc.group(1)) if desc else ""}

def status_item():
    meta = json.loads((ROOT / "ev-data/meta.json").read_text("utf-8"))
    day = meta["generated"][:10]
    ev = (ROOT / "ev-charging.html").read_text("utf-8", errors="ignore")
    m = re.search(r'content="[^"]*?Median price EUR ([\d.]+)/kWh, ([\d.]+)% out of order now', ev)
    med, down = (m.group(1), m.group(2)) if m else ("n/a", "n/a")
    title = f"Charge point status {day}: {down}% of {meta['stations']:,} public charge points out of order, median EUR {med}/kWh"
    desc = (f"National charge point register snapshot {meta['generated'][:16].replace('T', ' ')} UTC. {meta['stations']:,} public charge points, "
            f"{down}% reported out of order, median price EUR {med} per kWh before parking. Live map with parking priced for your stop at {SITE}/ev-charging.")
    return {"title": title, "link": f"{SITE}/ev-charging", "guid": f"{SITE}/ev-charging#status-{day}", "day": day, "desc": desc}

def main():
    sm = (ROOT / "sitemap.xml").read_text("utf-8")
    entries = re.findall(r"<loc>([^<]+)</loc>\s*<lastmod>([^<]+)</lastmod>", sm)
    rows = []
    for loc, day in entries:
        url = loc.replace(SITE, "") or "/"
        if "/garage/" in url and not url.endswith("/garage/"): continue
        rows.append((day, url))
    rows.sort(key=lambda r: (r[0], r[1]), reverse=True)
    items = [status_item()]
    for day, url in rows:
        if len(items) >= MAX_ITEMS: break
        meta = page_meta(url)
        if not meta: continue
        items.append({"title": meta["title"], "link": SITE + url, "guid": SITE + url, "day": day, "desc": meta["desc"]})
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">', "<channel>",
           "<title>Charge + Park, The Netherlands</title>", f"<link>{SITE}/</link>",
           "<description>Every public EV charger and every register-listed parking garage in the Netherlands, priced for your stop. Daily charge point status and updated guides.</description>",
           "<language>en</language>", f'<atom:link href="{SITE}/feed.xml" rel="self" type="application/rss+xml"/>',
           f"<lastBuildDate>{rfc822(items[0]['day'])}</lastBuildDate>"]
    for it in items:
        out += ["<item>", f"<title>{esc(it['title'])}</title>", f"<link>{it['link']}</link>",
                f'<guid isPermaLink="false">{esc(it["guid"])}</guid>', f"<pubDate>{rfc822(it['day'])}</pubDate>",
                f"<description>{esc(it['desc'])}</description>", "</item>"]
    out += ["</channel>", "</rss>", ""]
    (ROOT / "feed.xml").write_text("\n".join(out), "utf-8")
    print(f"feed: {len(items)} items -> feed.xml")
    return 0

if __name__ == "__main__":
    sys.exit(main())
