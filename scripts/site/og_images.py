#!/usr/bin/env python3
"""Social preview images, one per page that gets shared.

Every page used to share the same generic og-image.png, so a city guide, an
operator fault page and the homepage all looked identical in WhatsApp, LinkedIn
and Reddit. This draws a 1200x630 card per page: the page's own headline, its
description, and for city and operator pages the three numbers that matter.

  python3 scripts/site/og_images.py          # writes og/<slug>.png + og/index.json

apply_chrome.py reads og/index.json and points each page's og:image at its card.
Runs in the daily job before the chrome pass. Pillow only, system Arial, no
network. About 130 images, a few seconds.
"""
import html as H, json, re, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "og"
W, HGT = 1200, 630
COBALT, ORANGE, INK, WHITE, SOFT = (35, 55, 198), (234, 88, 12), (11, 17, 32), (255, 255, 255), (205, 213, 245)
FONT_B = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_R = "/System/Library/Fonts/Supplemental/Arial.ttf"
BRAND = {"en": "Charge + Park · The Netherlands", "nl": "Charge + Park · Nederland", "de": "Charge + Park · Niederlande", "fr": "Charge + Park · Pays-Bas"}

def font(path, size):
    try: return ImageFont.truetype(path, size)
    except OSError: return ImageFont.load_default()

def text_of(frag): return H.unescape(re.sub(r"<[^>]+>", "", frag)).strip()

def lang_of(rel):
    m = re.match(r"^(nl|de|fr)/", rel)
    return m.group(1) if m else "en"

def page_url(rel):
    if rel == "index.html": return "/"
    if rel.endswith("/index.html"): return "/" + rel[:-len("index.html")]
    return "/" + rel[:-5]

def slug_of(url):
    s = url.strip("/").replace("/", "_") or "index"
    return s

def wrap(draw, txt, f, maxw):
    words, lines, cur = txt.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=f) <= maxw: cur = t
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines

def stats_for(rel, t):
    """Up to three (value, label) pairs the card can lead with."""
    if re.match(r"^[a-z-]+\.html$", rel) and '<div class="qbl">' in t:
        tiles = re.findall(r'<div class="qbl">([^<]*)</div><div class="qbv[^"]*">([^<]*)</div>', t)
        return [(H.unescape(v), H.unescape(l)) for l, v in tiles[:3]]
    if '<div class="ea-stat">' in t:
        tiles = re.findall(r'<div class="ea-stat"><b>([^<]*)</b><span>([^<]*)</span>', t)
        return [(H.unescape(v), H.unescape(l)) for v, l in tiles[:3]]
    if rel.endswith("-storing.html"):
        m = re.search(r'content="(\d+) van de ([\d.]+) openbare (.+?)-laadpunten staan nu als buiten gebruik gemeld, ([\d,]+%) tegen ([\d,]+%) landelijk', t)
        if m: return [(m.group(4), "buiten gebruik"), (m.group(5), "landelijk"), (m.group(2), "laadpunten")]
    if rel.startswith("laadpaal-"):
        m = re.search(r'content="(\d+) openbare laadlocaties en (\d+) laadpunten.*?Mediaan (€\d+,\d+) per kWh, ([\d,]+%) buiten gebruik', t)
        if m: return [(m.group(2), "laadpunten"), (m.group(3), "mediaan per kWh"), (m.group(4), "buiten gebruik")]
    return []

def draw_card(title, desc, stats, lang, path):
    im = Image.new("RGB", (W, HGT), COBALT)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 10], fill=ORANGE)
    f_brand, f_title, f_desc, f_num, f_lab = font(FONT_B, 26), font(FONT_B, 60), font(FONT_R, 28), font(FONT_B, 52), font(FONT_R, 22)
    d.text((64, 44), BRAND.get(lang, BRAND["en"]), font=f_brand, fill=SOFT)
    y = 110
    tl = wrap(d, title, f_title, W - 128)[:3]
    if len(tl) == 3 and len(wrap(d, title, f_title, W - 128)) > 3: tl[2] = tl[2][:-1].rstrip() + "…"
    for line in tl:
        d.text((64, y), line, font=f_title, fill=WHITE); y += 70
    y += 10
    for line in wrap(d, desc, f_desc, W - 128)[:2]:
        d.text((64, y), line, font=f_desc, fill=SOFT); y += 38
    if stats:
        base = HGT - 150
        d.line([(64, base - 26), (W - 64, base - 26)], fill=(70, 92, 220), width=2)
        x = 64
        for v, l in stats[:3]:
            d.text((x, base), v, font=f_num, fill=WHITE)
            d.text((x, base + 62), l, font=f_lab, fill=SOFT)
            x += 360
    d.text((64, HGT - 48), "parkingnetherlands.com", font=f_brand, fill=ORANGE)
    im.save(path, "PNG", optimize=True)

def wanted():
    pages = ["index.html", "ev-charging.html", "search.html", "parking-fines.html", "parking-price-index.html", "park-and-ride.html",
             "ev-adoption.html", "charging-gap.html", "afir-scorecard.html", "garage/index.html", "laadpalen.html", "belgium-parking.html", "free-parking.html",
             "parking-apps.html", "street-parking.html", "long-term-parking.html", "ev-parking.html", "schiphol.html", "all-cities.html",
             "nl/index.html", "de/index.html", "fr/index.html", "nl/garage/index.html", "de/garage/index.html", "fr/garage/index.html"]
    cities = ["amsterdam", "rotterdam", "the-hague", "utrecht", "eindhoven", "groningen", "maastricht", "leiden", "haarlem", "breda", "delft", "nijmegen", "tilburg", "zwolle"]
    pages += [c + ".html" for c in cities]
    pages += sorted(p.relative_to(ROOT).as_posix() for p in ROOT.glob("nl/parkeren-*.html"))
    pages += sorted(p.relative_to(ROOT).as_posix() for p in ROOT.glob("de/parken-*.html"))
    pages += sorted(p.relative_to(ROOT).as_posix() for p in ROOT.glob("fr/stationnement-*.html"))
    pages += sorted(p.relative_to(ROOT).as_posix() for p in ROOT.glob("*-storing.html"))
    pages += sorted(p.relative_to(ROOT).as_posix() for p in ROOT.glob("laadpaal-*.html"))
    pages += sorted(p.relative_to(ROOT).as_posix() for p in ROOT.glob("parking-*-centraal.html"))
    pages += sorted(p.relative_to(ROOT).as_posix() for p in ROOT.glob("parking-*-station.html"))
    seen, out = set(), []
    for p in pages:
        if p not in seen and (ROOT / p).exists(): seen.add(p); out.append(p)
    return out

def main():
    OUT.mkdir(exist_ok=True)
    index, n = {}, 0
    for rel in wanted():
        t = (ROOT / rel).read_text("utf-8", errors="ignore")
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", t, re.S)
        title = text_of(h1.group(1)) if h1 else text_of(re.search(r"<title>(.*?)</title>", t, re.S).group(1))
        title = re.sub(r"\s+", " ", title)
        m = re.search(r'<meta name="description" content="([^"]*)"', t)
        desc = H.unescape(m.group(1)) if m else ""
        desc = re.split(r"(?<=[.!?])\s", desc)[0] if len(desc) > 150 else desc
        url = page_url(rel); slug = slug_of(url); path = OUT / f"{slug}.png"
        draw_card(title, desc, stats_for(rel, t), lang_of(rel), path)
        index[url] = f"/og/{slug}.png"; n += 1
    (OUT / "index.json").write_text(json.dumps(index, indent=0, sort_keys=True), "utf-8")
    print(f"og: {n} cards -> og/")
    return 0

if __name__ == "__main__":
    sys.exit(main())
