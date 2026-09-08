#!/usr/bin/env python3
"""
Deterministic generator for /parking-<city>-centraal POI landing pages.

Reproduces the hand-built template (Amsterdam/Rotterdam/Utrecht Centraal) from
real RDW garage data so the daily job can publish a new page with zero LLM
variance - safe to auto-push. Nothing here invents prices: every tariff comes
from the garage pages' JSON-LD, and P+R facts come from targets.json.

Usage:
  python3 generate_poi_page.py --next        # build the first unbuilt target
  python3 generate_poi_page.py <target_key>  # build a specific target
  python3 generate_poi_page.py --list        # show queue + built status

On success it writes <slug>.html, updates _redirects and sitemap.xml, adds a
reciprocal link on the parent city page, and `git add`s everything. It does NOT
commit or push - run_daily.sh does that.
"""
import glob
import json
import math
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
TARGETS = json.loads((HERE / "targets.json").read_text("utf-8"))

# --- garage data ------------------------------------------------------------
def _hav(a, b):
    R = 6371000
    la1, lo1, la2, lo2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))


def parse_garages(city_slug, coords, limit=7):
    """Closest `limit` real garages to `coords`, with official 2026 tariffs."""
    out = []
    for f in glob.glob(str(REPO / "garage" / f"*{city_slug}*.html")):
        t = Path(f).read_text("utf-8")
        m = re.search(r'<script type="application/ld\+json">(\[.*?\])</script>', t, re.S)
        if not m:
            continue
        try:
            data = json.loads(m.group(1))
        except Exception:
            continue
        pf = next((x for x in data if x.get("@type") == "ParkingFacility"), None)
        if not pf or "geo" not in pf:
            continue
        md = re.search(r'costs €([\d.]+) for 1 hour.*?€([\d.]+) for 24 hours', t)
        if not md:
            continue                        # no reliable price -> skip
        p1, p24 = float(md.group(1)), float(md.group(2))
        # anomaly guards: coach/flat-fee garages (e.g. €41/hr, or 1h == 24h)
        if p1 <= 0 or p1 > 15 or abs(p1 - p24) < 0.01:
            continue
        d = _hav(coords, (pf["geo"]["latitude"], pf["geo"]["longitude"]))
        slug = Path(f).stem
        name = re.sub(r'^(Garage|Parkeergarage)\s+', '', pf["name"]).strip()
        out.append({"dist": round(d), "name": pf["name"], "short": name,
                    "p1": p1, "p24": p24,
                    "cap": pf.get("maximumAttendeeCapacity", ""), "slug": slug})
    out.sort(key=lambda r: r["dist"])
    return out[:limit]


def _walk(m):
    mins = max(1, round(m / 80))
    dist = f"{m} m" if m < 1000 else f"{m / 1000:.1f} km"
    return f"~{mins} min ({dist})"


def _eur(v):
    return f"€{v:.0f}" if abs(v - round(v)) < 0.01 else f"€{v:.2f}"


# --- page sections ----------------------------------------------------------
NAV = '''<nav class="nav"><div class="nav-in">
<a href="/" class="logo"><div class="lm">P</div><span class="lt">Parking Netherlands</span></a>
<ul class="nl">
  <li class="has-drop"><a href="/all-cities">Cities ▾</a>
    <div class="drop">
      <a href="/amsterdam">Amsterdam</a><a href="/rotterdam">Rotterdam</a><a href="/the-hague">The Hague</a><a href="/utrecht">Utrecht</a><a href="/eindhoven">Eindhoven</a>
      <div class="drop-div"></div>
      <a href="/groningen">Groningen</a><a href="/haarlem">Haarlem</a><a href="/leiden">Leiden</a><a href="/delft">Delft</a><a href="/maastricht">Maastricht</a><a href="/breda">Breda</a>
      <div class="drop-div"></div>
      <a href="/nijmegen">Nijmegen</a><a href="/tilburg">Tilburg</a><a href="/zwolle">Zwolle</a>
      <div class="drop-div"></div>
      <a href="/all-cities">All Cities →</a>
    </div>
  </li>
  <li><a href="/search">Search \U0001f50d</a></li>
  <li><a href="/map">Map \U0001f5fa️</a></li>
  <li><a href="/schiphol">Schiphol ✈</a></li>
  <li class="has-drop"><a href="/free-parking">Guides ▾</a>
    <div class="drop">
      <a href="/free-parking">\U0001f193 Free Parking</a><a href="/street-parking">\U0001f6e3️ Street Parking</a><a href="/long-term-parking">\U0001f550 Long-Term Parking</a><a href="/parking-tips-netherlands">\U0001f4a1 Parking Tips</a><a href="/ev-parking">⚡ EV Charging</a><a href="/parking-apps">\U0001f4f1 Parking Apps</a><a href="/parking-fines">⚠️ Fines Guide</a>
      <div class="drop-div"></div>
      <a href="/parkbee">\U0001f17f️ ParkBee Guide</a><a href="/belgium-parking">\U0001f1e7\U0001f1ea Belgium Parking</a>
      <div class="drop-div"></div>
      <a href="/about">About this site</a>
    </div>
  </li>
  <li><a href="/blog">Blog</a></li>
  <li><a href="https://www.paypal.com/qrcodes/managed/f2e1981d-0f0e-43ca-862f-4393ef678450?utm_source=consweb_more" class="cb" target="_blank">\U0001f499 Support</a></li>
</ul>
<button class="mt" onclick="toggleMenu()" aria-label="Menu">☰</button>
</div></nav>'''

FOOTER = '''<footer class="footer"><div class="ct">
<div class="fg">
<div class="fb2"><a href="/" class="logo"><div class="lm">P</div><span class="lt">Parking Netherlands</span></a><p>Independent parking comparison. Helping tourists, expats, and locals park smarter across the Netherlands.</p><div class="fbu">Built &amp; maintained by <a href="https://analyticascent.com" target="_blank">Analytics Ascent</a></div></div>
<div class="fc"><h4>Major Cities</h4><a href="/amsterdam">Amsterdam</a><a href="/rotterdam">Rotterdam</a><a href="/the-hague">The Hague</a><a href="/utrecht">Utrecht</a><a href="/eindhoven">Eindhoven</a><a href="/schiphol">Schiphol ✈</a></div>
<div class="fc"><h4>More Cities</h4><a href="/haarlem">Haarlem</a><a href="/leiden">Leiden</a><a href="/delft">Delft</a><a href="/groningen">Groningen</a><a href="/maastricht">Maastricht</a><a href="/breda">Breda</a><a href="/nijmegen">Nijmegen</a><a href="/tilburg">Tilburg</a><a href="/zwolle">Zwolle</a></div>
<div class="fc"><h4>Guides</h4><a href="/parking-apps">Parking Apps</a><a href="/parking-fines">Fines Guide</a><a href="/free-parking">Free Parking</a><a href="/street-parking">Street Parking</a><a href="/long-term-parking">Long-Term Parking</a><a href="/parking-tips-netherlands">Parking Tips</a><a href="/ev-parking">EV Parking</a><a href="/about">About</a></div>
</div>
<div class="fbo"><span>© 2026 Parking Netherlands - An <a href="https://analyticascent.com" target="_blank" style="color:var(--or)">Analytics Ascent</a> project</span><span class="ff">\U0001f193 100% free</span><span>Not affiliated with any municipality</span></div>
</div></footer>'''


def _garage_rows(garages):
    rows = []
    for g in garages:
        rows.append(
            f'<tr><td><strong><a href="/garage/{g["slug"]}" '
            f'style="color:var(--ink);text-decoration:none">{g["short"]}</a></strong></td>'
            f'<td>{_walk(g["dist"])}</td>'
            f'<td class="tp">{_eur(g["p1"])}/hr</td>'
            f'<td class="tp">{_eur(g["p24"])}</td>'
            f'<td>{g["cap"]}</td></tr>')
    return "\n".join(rows)


def _pr_cards(prs):
    cards = []
    for i, p in enumerate(prs):
        tag = '<span class="pk-tag">Our #1 Pick</span>' if i == 0 else ''
        cls = "pk best" if i == 0 else "pk"
        cards.append(
            f'<div class="{cls}">{tag}'
            f'<div class="pk-n">{p["name"]}</div><div class="pk-t">{p["sub"]}</div>'
            f'<div class="pk-r"><span class="l">24-hour rate</span><span class="v c">{p["rate"]}</span></div>'
            f'<div class="pk-r"><span class="l">To {p.get("to_label","station")}</span><span class="v">{p["to"]}</span></div>'
            f'<div class="pk-d"><div class="pk-di">{p["note"]}</div><div class="pk-di">Check in/out on OV-chipkaart</div></div></div>')
    return "".join(cards)


def _pr_map_js(prs):
    pts = ",\n     ".join(
        f'{{name:"{p["name"]}",lat:{p["coords"][0]},lng:{p["coords"][1]}}}'
        for p in prs)
    return pts


def _faq(station, closest, cheapest, prrate):
    qa = [
        (f"How much is parking near {station}?",
         f"Garages within walking distance of {station} range from {_eur(cheapest['p1'])} to "
         f"{_eur(closest['p1'])} per hour in 2026. The closest, {closest['name']}, is {_eur(closest['p1'])}/hr "
         f"and {_eur(closest['p24'])}/day. The cheapest walkable garage, {cheapest['name']}, is "
         f"{_eur(cheapest['p1'])}/hr. P+R on the outskirts is {prrate}/24hr including transit."),
        (f"Where is the closest parking garage to {station}?",
         f"{closest['name']} is the closest, about {closest['dist']} metres "
         f"({max(1, round(closest['dist']/80))}-minute walk) from the station, at {_eur(closest['p1'])}/hr "
         f"and {_eur(closest['p24'])} for 24 hours."),
        (f"What is the cheapest parking near {station}?",
         f"{cheapest['name']} at {_eur(cheapest['p1'])}/hr and {_eur(cheapest['p24'])}/24hr is the cheapest "
         f"garage within walking distance. For all-day parking, outer P+R at {prrate}/24hr including the "
         f"bus, tram or metro in is cheaper still."),
        (f"Can I park at {station} overnight?",
         f"Yes. Nearby garages are open 24 hours; a full day runs about {_eur(closest['p24'])} at the closest. "
         f"For multi-day stays, P+R at {prrate}/24hr is cheaper."),
    ]
    faq_json = json.dumps({"@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [{"@type": "Question", "name": q,
            "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in qa]},
        ensure_ascii=False)
    faq_html = "\n".join(
        f'<div class="faq-item"><button class="faq-q" onclick="this.parentElement.classList.toggle(\'open\')">'
        f'{q} <span class="t">+</span></button><div class="faq-a"><p>{a}</p></div></div>'
        for q, a in qa)
    return faq_json, faq_html


def render(target):
    slug = target["slug"]
    station = target["station"]
    city = target["city_name"]
    city_slug = target["city_slug"]
    lat, lng = target["coords"]
    garages = parse_garages(target["garage_slug"], target["coords"])
    if len(garages) < 3:
        raise SystemExit(f"[skip] only {len(garages)} usable garages for {slug}; not enough for a page.")
    closest = garages[0]
    cheapest = min(garages, key=lambda g: g["p1"])
    prs = target["pr"]
    prrate = target.get("pr_rate", prs[0]["rate"].split("/")[0])
    url = f"https://parkingnetherlands.com/{slug}"

    faq_json, faq_html = _faq(station, closest, cheapest, prrate)
    breadcrumb = json.dumps({"@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": "https://parkingnetherlands.com/"},
            {"@type": "ListItem", "position": 2, "name": f"Parking {city}", "item": f"https://parkingnetherlands.com/{city_slug}"},
            {"@type": "ListItem", "position": 3, "name": station, "item": url}]}, ensure_ascii=False)

    desc = (f"Parking near {station} 2026. Closest garage {_eur(closest['p1'])}/hr "
            f"({closest['dist']} m walk); cheapest walkable {_eur(cheapest['p1'])}/hr. "
            f"Ranked garage list plus P+R from {prrate}/24hr.")
    title = f"Parking near {station} 2026 - Closest Garages, Prices & P+R"

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2889604222343187" crossorigin="anonymous"></script>
<meta charset="UTF-8">
    <link rel="icon" href="/favicon.ico" sizes="any"><link rel="icon" type="image/svg+xml" href="/favicon.svg"><link rel="apple-touch-icon" href="/apple-touch-icon.png"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{url}">
<link rel="stylesheet" href="shared.css">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script type="application/ld+json">{faq_json}</script>
<script type="application/ld+json">{breadcrumb}</script>
    <meta property="og:type" content="website">
    <meta property="og:title" content="Parking near {station} 2026 - Closest Garages &amp; P+R">
    <meta property="og:url" content="{url}">
    <meta property="og:description" content="{desc}">
    <meta property="og:site_name" content="Parking Netherlands">
    <meta property="og:locale" content="en_NL">
    <meta name="twitter:title" content="Parking near {station} 2026 - Closest Garages &amp; P+R">
    <meta name="twitter:description" content="{desc}">
    <meta name="robots" content="index, follow">
    <meta name="author" content="Analytics Ascent">
    <meta name="geo.region" content="{target['geo_region']}">
    <meta name="geo.placename" content="{station}">
<meta property="og:image" content="https://parkingnetherlands.com/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
</head>
<body>
{NAV}
<div class="bc-bar"><div class="ct bc-in"><a href="/">Home</a> → <a href="/{city_slug}">{city}</a> → <strong>{station}</strong></div></div>
<div class="ph"><div class="ct">
<h1>Parking near <em>{station}</em> - 2026</h1>
<p class="sub">The complete guide to parking at {station}. Every close garage ranked by walking distance and real 2026 price, plus the P+R alternative from {prrate}/24hr.</p>
<div class="qs">
<div class="qb"><div class="qbl">Closest Garage</div><div class="qbv">{_eur(closest['p1'])}/hr</div></div>
<div class="qb"><div class="qbl">Cheapest Nearby</div><div class="qbv c">{_eur(cheapest['p1'])}/hr</div></div>
<div class="qb"><div class="qbl">Closest 24hr</div><div class="qbv">{_eur(closest['p24'])}</div></div>
<div class="qb"><div class="qbl">P+R (24hr)</div><div class="qbv c">{prrate}</div></div>
</div></div></div>

<section class="sec sec-wm"><div class="ct">
<div class="sl">Interactive Map</div>
<h2 class="st">Garages &amp; P+R around {station}</h2>
<p class="ss">The blue pin is the station. Orange pins are official RDW garages; dark pins are the P+R sites that connect into the centre.</p>
<div class="mw"><div id="cMap" class="mc"></div></div>
<div class="ml">
<div class="mli"><div class="mld" style="background:#2337C6"></div> {station}</div>
<div class="mli"><div class="mld" style="background:var(--or)"></div> Garages (RDW)</div>
<div class="mli"><div class="mld" style="background:#0A1628"></div> P+R</div>
</div></div></section>

<div class="ad-wrap w"><div class="ad">- Advertisement -</div></div>

<section class="sec sec-wm"><div class="ct">
<div class="sl">Parking Garages</div>
<h2 class="st">Garages near {station}, closest first</h2>
<p class="ss">Walking distance measured from the station. Prices are the official 2026 drive-in tariffs from the RDW register. Pre-booking through an app often saves 10-20%.</p>
<div class="tw"><table>
<thead><tr><th>Garage</th><th>Walk to station</th><th>Per Hour</th><th>Per Day (24h)</th><th>Spaces</th></tr></thead>
<tbody>
{_garage_rows(garages)}
</tbody>
</table></div>
<p class="ss" style="margin-top:14px">Need an exact price for your arrival and departure times? The <a href="/search?q={station.replace(' ','%20')}&lat={lat}&lng={lng}" style="color:var(--or);font-weight:600">parking search</a> computes the cost of your specific stay at every garage within reach.</p>
</div></section>

<div class="ad-wrap wm"><div class="ad">- Advertisement -</div></div>

<section class="sec sec-w"><div class="ct">
<div class="sl">Best Value</div>
<h2 class="st">P+R into the centre from {prrate}/24hr</h2>
<p class="ss">Park on the outskirts and ride public transport in. You must tap in and out with an OV-chipkaart to get the cheap rate.</p>
<div class="pg">{_pr_cards(prs)}</div>
<p class="ss" style="margin-top:16px">See the full <a href="/{city_slug}" style="color:var(--or);font-weight:600">{city} parking guide</a> for every P+R site, street zone and free-parking tip.</p>
</div></section>

<div class="ad-wrap wm"><div class="ad">- Advertisement -</div></div>

<section class="sec sec-w"><div class="ct prose"><h2>Parking at {station} - the full picture</h2>
<p>Garages around {station} span <strong>{_eur(cheapest['p1'])} to {_eur(closest['p1'])} per hour</strong> in 2026, and the walk from the cheapest to the closest is short enough that it always pays to check both. The closest garage, <strong>{closest['name']}</strong>, is about a {max(1, round(closest['dist']/80))}-minute walk at {_eur(closest['p1'])}/hr and {_eur(closest['p24'])} for a full day.</p>
<h3>Cheapest vs closest</h3>
<p>If price matters more than a few minutes on foot, <strong>{cheapest['name']}</strong> is the value pick at {_eur(cheapest['p1'])}/hr and {_eur(cheapest['p24'])}/24hr. For a short visit the convenience of the closest garage usually wins; for a full day the cheaper garages and P+R pull well ahead.</p>
<h3>When P+R makes sense</h3>
<p>For all-day or multi-day parking, {city}'s Park and Ride is the value play at {prrate} for 24 hours including the ride into the centre. You tap in and out on an OV-chipkaart. That undercuts the central garages once you are staying a full day, and it keeps the car out of the busy centre entirely.</p></div></section>

<section class="sec sec-wm"><div class="ct">
<div class="sl">FAQ</div>
<h2 class="st">{station} parking questions</h2>
<div style="max-width:760px">
{faq_html}
</div>
</div></section>

<section class="sec sec-wm2"><div class="ct">
<div class="sc"><div><h2>Did we save you money?</h2><p>This site is 100% free. No paywalls. If our tips helped, a small tip keeps the rates updated.</p><img src="/paypal-qr.png" alt="Scan to support via PayPal" style="width:110px;height:110px;display:block;margin:12px 0;border-radius:8px"></div>
<a href="https://www.paypal.com/qrcodes/managed/f2e1981d-0f0e-43ca-862f-4393ef678450?utm_source=consweb_more" target="_blank" rel="noopener" class="bc">\U0001f499 Support via PayPal</a></div>
</div></section>
<div class="ad-wrap cr"><div class="ad">- Advertisement -</div></div>

<section class="share-section">
  <h3>Found this useful? Share it</h3>
  <p>Help other drivers find cheap parking near {station}.</p>
  <div class="share-row">
    <a href="https://www.facebook.com/sharer/sharer.php?u={url}" target="_blank" rel="noopener" aria-label="Share on Facebook">Facebook</a>
    <a href="https://twitter.com/intent/tweet?url={url}&text=Parking%20near%20{station.replace(' ','%20')}%202026" target="_blank" rel="noopener" aria-label="Share on X (Twitter)">X · Twitter</a>
    <a href="https://wa.me/?text={url}" target="_blank" rel="noopener" aria-label="Share on WhatsApp">WhatsApp</a>
    <a href="https://www.linkedin.com/sharing/share-offsite/?url={url}" target="_blank" rel="noopener" aria-label="Share on LinkedIn">LinkedIn</a>
    <a href="mailto:?subject=Parking%20near%20{station.replace(' ','%20')}&body={url}" aria-label="Share via email">Email</a>
  </div>
</section>

{FOOTER}

<script src="rdw-data.js"></script>
<script src="shared.js"></script>
<script>
document.addEventListener('DOMContentLoaded',function(){{
  try{{
    var CEN=[{lat},{lng}];
    var map=initMap('cMap',CEN,14);
    addRDWMarkers(map,'{target['garage_slug']}');
    addMarker(map,{{name:'{station}',lat:CEN[0],lng:CEN[1]}},'#2337C6','C');
    [{_pr_map_js(prs)}
    ].forEach(function(p){{addMarker(map,p,'#0A1628','P');}});
  }}catch(e){{}}
}});
</script>
</body></html>
'''
    return html


# --- wiring -----------------------------------------------------------------
def wire_in(target, html):
    slug = target["slug"]
    page = REPO / f"{slug}.html"
    page.write_text(html, "utf-8")

    # _redirects (.html -> clean URL)
    rp = REPO / "_redirects"
    rt = rp.read_text("utf-8")
    line = f"/{slug}.html  /{slug}  301"
    if line not in rt:
        rt = rt.replace("# Redirect .html versions to clean URLs (301 permanent)\n",
                        f"# Redirect .html versions to clean URLs (301 permanent)\n{line}\n", 1)
        rp.write_text(rt, "utf-8")

    # sitemap.xml
    sp = REPO / "sitemap.xml"
    st = sp.read_text("utf-8")
    if f"/{slug}<" not in st and f"/{slug}</loc>" not in st:
        entry = (f'  <url><loc>https://parkingnetherlands.com/{slug}</loc>'
                 f'<lastmod>{date.today().isoformat()}</lastmod>'
                 f'<changefreq>weekly</changefreq><priority>0.8</priority></url>\n')
        st = st.replace("</urlset>", entry + "</urlset>", 1)
        sp.write_text(st, "utf-8")

    # reciprocal link on the parent city page (best-effort, idempotent)
    cp = REPO / f"{target['city_slug']}.html"
    if cp.exists():
        ct = cp.read_text("utf-8")
        if f"/{slug}" not in ct:
            anchor = f'Pre-booking saves 10-20%.'
            link = (f'{anchor} Heading to the station? See '
                    f'<a href="/{slug}" style="color:var(--or);font-weight:600">'
                    f'parking near {target["station"]}</a>.')
            if anchor in ct:
                ct = ct.replace(anchor, link, 1)
                cp.write_text(ct, "utf-8")

    # stage everything
    files = [str(page), str(rp), str(sp)]
    if cp.exists():
        files.append(str(cp))
    subprocess.run(["git", "-C", str(REPO), "add"] + files, check=False)
    return page


def next_unbuilt():
    for t in TARGETS:
        if not (REPO / f"{t['slug']}.html").exists():
            return t
    return None


def main(argv):
    if not argv or argv[0] == "--list":
        for t in TARGETS:
            built = (REPO / f"{t['slug']}.html").exists()
            print(f"  [{'x' if built else ' '}] {t['slug']}  ({t['station']})")
        return 0
    if argv[0] == "--next":
        t = next_unbuilt()
        if not t:
            print("[generate] queue empty - all targets built.")
            return 0
    else:
        t = next((x for x in TARGETS if x["slug"] == argv[0] or x.get("key") == argv[0]), None)
        if not t:
            print(f"[generate] unknown target: {argv[0]}")
            return 1
    if (REPO / f"{t['slug']}.html").exists():
        print(f"[generate] {t['slug']} already exists - nothing to do.")
        return 0
    html = render(t)
    page = wire_in(t, html)
    print(f"[generate] wrote {page.name} ({t['station']}) and wired _redirects/sitemap/city-link.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
