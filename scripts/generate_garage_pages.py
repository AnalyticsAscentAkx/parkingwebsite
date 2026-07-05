#!/usr/bin/env python3
"""
Generate static garage detail pages from garages.json (built by rdw_tariff_sync.py).

Outputs:
  ../garage/<slug>.html   one page per garage (ParkingFacility + FAQ JSON-LD)
  ../garage/index.html    directory of all garages, grouped by city
  garage-urls.txt         URL list for sitemap maintenance

Usage: python3 generate_garage_pages.py
"""
import json
import math
from datetime import date
from pathlib import Path

SITE = "https://parkingnetherlands.com"
TODAY = date.today().isoformat()
YEAR = date.today().year

CITY_LABEL = {
    "amsterdam": "Amsterdam", "rotterdam": "Rotterdam", "the-hague": "The Hague",
    "utrecht": "Utrecht", "eindhoven": "Eindhoven", "groningen": "Groningen",
    "maastricht": "Maastricht", "leiden": "Leiden", "haarlem": "Haarlem",
    "breda": "Breda", "delft": "Delft", "nijmegen": "Nijmegen",
    "tilburg": "Tilburg", "zwolle": "Zwolle",
}

HEAD_FONTS = """<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/site.css">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='8' fill='%230B1120'/><text x='16' y='23' text-anchor='middle' font-size='20' font-weight='bold' fill='white' font-family='sans-serif'>P</text></svg>">"""

NAV = """<nav class="nav"><div class="nav-in">
<a href="/" class="logo"><div class="logo-mark"></div><span class="logo-text">Parking Netherlands</span></a>
<ul class="nav-links" id="navLinks">
  <li class="has-drop"><a href="/all-cities">Cities</a>
    <div class="drop">
      <a href="/amsterdam">Amsterdam</a><a href="/rotterdam">Rotterdam</a><a href="/the-hague">The Hague</a><a href="/utrecht">Utrecht</a><a href="/eindhoven">Eindhoven</a>
      <div class="drop-div"></div>
      <a href="/groningen">Groningen</a><a href="/haarlem">Haarlem</a><a href="/leiden">Leiden</a><a href="/delft">Delft</a><a href="/maastricht">Maastricht</a><a href="/breda">Breda</a>
      <div class="drop-div"></div>
      <a href="/all-cities">All cities →</a>
    </div>
  </li>
  <li><a href="/search">Search</a></li>
  <li><a href="/map">Map</a></li>
  <li><a href="/schiphol">Schiphol</a></li>
  <li class="has-drop"><a href="/free-parking">Guides</a>
    <div class="drop">
      <a href="/free-parking">Free parking</a><a href="/street-parking">Street parking</a><a href="/long-term-parking">Long-term parking</a><a href="/parking-tips-netherlands">Parking tips</a><a href="/ev-parking">EV charging</a><a href="/parking-apps">Parking apps</a><a href="/parking-fines">Fines guide</a>
      <div class="drop-div"></div>
      <a href="/about">About this site</a>
    </div>
  </li>
  <li><a href="/blog">Blog</a></li>
  <li><a href="https://www.paypal.com/qrcodes/managed/f2e1981d-0f0e-43ca-862f-4393ef678450?utm_source=consweb_more" class="nav-cta" target="_blank" rel="noopener">Support</a></li>
</ul>
<button class="menu-btn" onclick="document.getElementById('navLinks').classList.toggle('open')" aria-label="Menu">☰</button>
</div></nav>"""

FOOTER = f"""<footer class="footer"><div class="wrap">
  <div class="foot-grid">
    <div class="foot-brand">
      <a href="/" class="logo"><div class="logo-mark"></div><span class="logo-text">Parking Netherlands</span></a>
      <p>Independent parking comparison for the Netherlands. Official data, no bookings pushed, no paywall.</p>
      <div class="credit">Built &amp; maintained by <a href="https://analyticascent.com" target="_blank" rel="noopener">Analytics Ascent</a></div>
    </div>
    <div class="foot-col"><h4>Cities</h4><a href="/amsterdam">Amsterdam</a><a href="/rotterdam">Rotterdam</a><a href="/the-hague">The Hague</a><a href="/utrecht">Utrecht</a><a href="/schiphol">Schiphol</a><a href="/all-cities">All cities</a></div>
    <div class="foot-col"><h4>Tools</h4><a href="/search">Parking search</a><a href="/map">Interactive map</a><a href="/garage/">Garage directory</a><a href="/blog">Blog</a></div>
    <div class="foot-col"><h4>Guides</h4><a href="/free-parking">Free parking</a><a href="/parking-apps">Parking apps</a><a href="/parking-fines">Fines guide</a><a href="/ev-parking">EV parking</a><a href="/about">About</a></div>
  </div>
  <div class="foot-bottom">
    <span>© {YEAR} Parking Netherlands — an <a href="https://analyticascent.com" target="_blank" rel="noopener" style="color:var(--sig)">Analytics Ascent</a> project</span>
    <span class="foot-pill">DATA: RDW OPEN DATA · CC0</span>
    <span>Not affiliated with any municipality</span>
  </div>
</div></footer>"""


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def haversine(a, b):
    r = 6371
    dla = math.radians(b["lat"] - a["lat"])
    dlo = math.radians(b["lng"] - a["lng"])
    x = math.sin(dla / 2) ** 2 + math.cos(math.radians(a["lat"])) * math.cos(math.radians(b["lat"])) * math.sin(dlo / 2) ** 2
    return 2 * r * math.asin(math.sqrt(x))


def eur(v):
    return f"€{v:,.2f}"


def short_name(g):
    n = g["name"]
    return n.rsplit(" (", 1)[0]


def garage_page(g, nearby):
    city = CITY_LABEL[g["city"]]
    name = short_name(g)
    has_rate = g.get("rate_hr") is not None
    is_free = has_rate and g["rate_hr"] == 0 and g.get("rate_day") == 0

    if is_free:
        price_line = f"{name} in {city} is free to use according to the national parking register."
    elif has_rate:
        price_line = (f"Parking at {name} in {city} costs {eur(g['rate_hr'])} for 1 hour, "
                      f"{eur(g['rate_3h'])} for 3 hours and {eur(g['rate_day'])} for 24 hours "
                      f"(official {YEAR} drive-in tariff).")
    else:
        price_line = (f"{name} is a registered parking facility in {city}; its operator does not "
                      f"publish tariffs in the national parking register — check signage on arrival.")

    desc = price_line[:158]

    # --- JSON-LD ---
    facility = {
        "@context": "https://schema.org",
        "@type": "ParkingFacility",
        "name": name,
        "url": f"{SITE}/garage/{g['slug']}",
        "geo": {"@type": "GeoCoordinates", "latitude": g["lat"], "longitude": g["lng"]},
        "address": {"@type": "PostalAddress", "addressLocality": city, "addressCountry": "NL"},
        "publicAccess": True,
        "isAccessibleForFree": bool(is_free),
    }
    if g.get("capacity"):
        facility["maximumAttendeeCapacity"] = g["capacity"]
    feats = []
    if g.get("ev_points"):
        feats.append({"@type": "LocationFeatureSpecification", "name": "EV charging points", "value": g["ev_points"]})
    if g.get("max_height_cm"):
        feats.append({"@type": "LocationFeatureSpecification", "name": "Maximum vehicle height", "value": f"{g['max_height_cm']/100:.2f} m"})
    if feats:
        facility["amenityFeature"] = feats
    if has_rate and not is_free:
        facility["priceRange"] = f"{eur(g['rate_hr'])}/hour"

    breadcrumb = {
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE + "/"},
            {"@type": "ListItem", "position": 2, "name": f"Parking {city}", "item": f"{SITE}/{g['city']}"},
            {"@type": "ListItem", "position": 3, "name": name, "item": f"{SITE}/garage/{g['slug']}"},
        ],
    }
    faq = {
        "@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [{
            "@type": "Question",
            "name": f"How much does parking cost at {name} in {city}?",
            "acceptedAnswer": {"@type": "Answer", "text": price_line},
        }, {
            "@type": "Question",
            "name": f"Where is {name} located?",
            "acceptedAnswer": {"@type": "Answer", "text":
                f"{name} is in {city}, Netherlands, at coordinates {g['lat']:.5f}, {g['lng']:.5f}."
                + (f" The facility has approximately {g['capacity']} parking spaces." if g.get("capacity") else "")},
        }],
    }
    jsonld = json.dumps([facility, breadcrumb, faq], ensure_ascii=False)

    # --- tariff table / facts ---
    rows = ""
    if has_rate and not is_free:
        r30 = min(g["rate_hr"], g["rate_hr"] * 0.5 if g["rate_hr"] else 0)
        rows = f"""<div class="tbl-wrap"><table>
<thead><tr><th>Stay</th><th>Official tariff</th><th>Effective per hour</th></tr></thead>
<tbody>
<tr><td>1 hour</td><td class="price">{eur(g['rate_hr'])}</td><td class="price">{eur(g['rate_hr'])}</td></tr>
<tr><td>3 hours</td><td class="price">{eur(g['rate_3h'])}</td><td class="price">{eur(g['rate_3h']/3)}</td></tr>
<tr><td>24 hours</td><td class="price">{eur(g['rate_day'])}</td><td class="price">{eur(g['rate_day']/24)}</td></tr>
</tbody></table></div>
<p style="font-size:12.5px;color:var(--mut);margin-top:10px">Drive-in rates computed from the RDW/NPR tariff table for a weekday stay. Operators may offer cheaper pre-booked online rates or apply day caps not encoded in the register.</p>"""
    elif is_free:
        rows = '<p><span class="badge badge-ok">Free parking</span> — the national register lists a €0.00 tariff for this facility.</p>'
    else:
        rows = '<p><span class="badge badge-line">Tariff not published</span> — this operator does not publish rates in the national register. Check signage on arrival, or compare nearby garages below.</p>'

    facts = ""
    if g.get("capacity"):
        facts += f'<tr><td>Capacity</td><td class="num">{g["capacity"]} spaces</td></tr>'
    if g.get("ev_points") is not None:
        facts += f'<tr><td>EV charging points</td><td class="num">{g["ev_points"] or "none listed"}</td></tr>'
    if g.get("max_height_cm"):
        facts += f'<tr><td>Max vehicle height</td><td class="num">{g["max_height_cm"]/100:.2f} m</td></tr>'
    facts += f'<tr><td>Type</td><td>{"P+R (park and ride)" if g.get("is_pr") else "Parking garage / lot"}</td></tr>'
    facts += f'<tr><td>Coordinates</td><td class="num">{g["lat"]:.5f}, {g["lng"]:.5f}</td></tr>'
    facts += f'<tr><td>NPR area code</td><td class="num">{g["areaid"]}</td></tr>'

    nearby_html = "".join(
        f'<tr><td><a href="/garage/{n["slug"]}" style="font-weight:600;color:var(--ink);text-decoration:none">{esc(short_name(n))}</a></td>'
        f'<td class="num">{n["_dist"]*1000:.0f} m</td>'
        f'<td class="price">{eur(n["rate_hr"]) + "/h" if n.get("rate_hr") else "—"}</td></tr>'
        for n in nearby)

    calc = ""
    if has_rate and not is_free:
        calc = f"""<div class="card card-pad" style="margin-top:22px">
  <div class="eyebrow" style="margin-bottom:10px">Cost calculator</div>
  <label for="dur" style="font-size:14px;font-weight:600">Stay duration: <span id="durL" class="num">3 h</span></label>
  <input type="range" id="dur" min="1" max="48" value="3" step="1" style="width:100%;margin:12px 0;accent-color:var(--sig)">
  <div style="font-size:15px">Estimated cost: <span id="durC" class="num" style="font-size:22px;font-weight:600;color:var(--ink)">{eur(g['rate_3h'])}</span></div>
</div>
<script>
(function(){{
  var h1={g['rate_hr']},h3={g['rate_3h']},d1={g['rate_day']};
  function cost(h){{var m=h*60;function u(m){{if(m<=60)return h1*Math.max(m/60,.5);if(m<=180)return h1+(h3-h1)*(m-60)/120;return h3+(d1-h3)*(m-180)/1260;}}
  if(m<=1440)return u(m);var d=Math.floor(m/1440),r=m%1440;return d*d1+Math.min(u(r),d1);}}
  var s=document.getElementById('dur');
  s.addEventListener('input',function(){{document.getElementById('durL').textContent=s.value+' h';
  document.getElementById('durC').textContent='€'+cost(+s.value).toFixed(2);}});
}})();
</script>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2889604222343187" crossorigin="anonymous"></script>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(name)} Parking — Rates, Capacity &amp; Info ({city} {YEAR})</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{SITE}/garage/{g['slug']}">
{HEAD_FONTS}
<meta property="og:type" content="place">
<meta property="og:url" content="{SITE}/garage/{g['slug']}">
<meta property="og:title" content="{esc(name)} — Parking Rates &amp; Info ({city})">
<meta property="og:description" content="{esc(desc)}">
<meta name="robots" content="index, follow">
<meta property="og:image" content="https://parkingnetherlands.com/og-image.png">
<script type="application/ld+json">{jsonld}</script>
<style>
.gwrap{{max-width:860px;margin:0 auto;padding:0 24px}}
.crumb{{font-size:13px;color:var(--mut);padding:18px 0 0}}
.crumb a{{color:var(--mut);text-decoration:none}}.crumb a:hover{{color:var(--ink)}}
.ghead h1{{font-size:clamp(1.6rem,3vw,2.2rem);font-weight:800;letter-spacing:-.03em;color:var(--ink);line-height:1.15;margin:10px 0 8px}}
.ghead .sub{{color:var(--mut);font-size:15px;margin-bottom:18px}}
#gmap{{height:300px;border-radius:var(--r-lg);border:1px solid var(--line);margin:26px 0;box-shadow:var(--sh)}}
h2{{font-size:1.25rem;font-weight:800;letter-spacing:-.02em;color:var(--ink);margin:34px 0 14px}}
</style>
</head>
<body>
{NAV}
<div class="gwrap">
  <div class="crumb"><a href="/">Home</a> / <a href="/{g['city']}">Parking {city}</a> / {esc(name)}</div>
  <header class="ghead">
    <h1>{esc(name)}</h1>
    <p class="sub">{'P+R site' if g.get('is_pr') else 'Parking facility'} in {city} · official RDW-registered location {'· <span class="badge badge-pr">P+R</span>' if g.get('is_pr') else ''}</p>
    <div style="display:flex;gap:10px;flex-wrap:wrap">
      <a class="btn btn-primary btn-sm" target="_blank" rel="noopener" href="https://www.google.com/maps/dir/?api=1&destination={g['lat']},{g['lng']}">Directions</a>
      <a class="btn btn-ghost btn-sm" href="/search?q={esc(name)} {city}&lat={g['lat']}&lng={g['lng']}">Compare nearby</a>
      <a class="btn btn-ghost btn-sm" href="/{g['city']}">{city} parking guide</a>
      {f'<a class="btn btn-dark btn-sm" target="_blank" rel="noopener nofollow" href="{g["op_url"]}">Operator website ↗</a>' if g.get("op_url") else ''}
    </div>
  </header>

  <h2>Parking rates</h2>
  <p style="font-size:15px;margin-bottom:14px">{esc(price_line)}</p>
  {rows}
  {calc}

  <h2>Facility details</h2>
  <div class="tbl-wrap"><table><tbody>{facts}</tbody></table></div>

  <div id="gmap"></div>

  <h2>Nearby alternatives</h2>
  <div class="tbl-wrap"><table>
  <thead><tr><th>Garage</th><th>Distance</th><th>Rate</th></tr></thead>
  <tbody>{nearby_html}</tbody></table></div>

  <p style="font-size:12.5px;color:var(--mut);margin:26px 0 60px">
    Source: <a href="https://opendata.rdw.nl" rel="noopener" target="_blank" style="color:var(--mut)">RDW Open Data (NPR)</a>, CC0 licence · Page generated {TODAY} ·
    Found an error? <a href="/about" style="color:var(--mut)">Let us know</a>.
  </p>
</div>
{FOOTER}
<script>
(function(){{
  function init(){{
    var css=document.createElement('link');css.rel='stylesheet';css.href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';document.head.appendChild(css);
    var js=document.createElement('script');js.src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
    js.onload=function(){{
      var map=L.map('gmap',{{scrollWheelZoom:false}}).setView([{g['lat']},{g['lng']}],15);
      L.tileLayer('https://{{s}}.basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}{{r}}.png',{{attribution:'© OSM © CARTO',maxZoom:18}}).addTo(map);
      L.marker([{g['lat']},{g['lng']}]).addTo(map).bindPopup({json.dumps(esc(name))}).openPopup();
    }};
    document.head.appendChild(js);
  }}
  if('IntersectionObserver' in window){{
    var o=new IntersectionObserver(function(e){{if(e[0].isIntersecting){{init();o.disconnect();}}}},{{rootMargin:'250px'}});
    o.observe(document.getElementById('gmap'));
  }} else init();
}})();
</script>
</body>
</html>"""


def index_page(garages):
    by_city = {}
    for g in garages:
        by_city.setdefault(g["city"], []).append(g)

    sections = ""
    for city in sorted(by_city, key=lambda c: -len(by_city[c])):
        gs = sorted(by_city[city], key=lambda g: (g.get("rate_hr") is None, g.get("rate_hr") or 0))
        pr_badge = ' <span class="badge badge-pr">P+R</span>'
        rows = "".join(
            f'<tr><td><a href="/garage/{g["slug"]}" style="font-weight:600;color:var(--ink);text-decoration:none">{esc(short_name(g))}</a>'
            f'{pr_badge if g.get("is_pr") else ""}</td>'
            f'<td class="price">{eur(g["rate_hr"]) + "/h" if g.get("rate_hr") else "—"}</td>'
            f'<td class="price">{eur(g["rate_day"]) if g.get("rate_day") is not None else "—"}</td>'
            f'<td class="num">{g.get("capacity") or "—"}</td></tr>'
            for g in gs)
        sections += f"""<h2 id="{city}" style="font-size:1.35rem;font-weight:800;letter-spacing:-.02em;color:var(--ink);margin:40px 0 14px">
<a href="/{city}" style="color:inherit;text-decoration:none">{CITY_LABEL[city]}</a> <span style="color:var(--mut-2);font-weight:500;font-size:.85em">· {len(gs)} locations</span></h2>
<div class="tbl-wrap"><table>
<thead><tr><th>Facility</th><th>1h rate</th><th>24h rate</th><th>Spaces</th></tr></thead>
<tbody>{rows}</tbody></table></div>"""

    jsonld = json.dumps({
        "@context": "https://schema.org", "@type": "CollectionPage",
        "name": "Parking Garage Directory Netherlands",
        "url": f"{SITE}/garage/",
        "description": f"Directory of {len(garages)} RDW-registered parking garages and P+R sites across {len(by_city)} Dutch cities with official tariffs.",
    }, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2889604222343187" crossorigin="anonymous"></script>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Parking Garage Directory Netherlands — {len(garages)} Garages, Official {YEAR} Rates</title>
<meta name="description" content="Every RDW-registered parking garage and P+R site in {len(by_city)} Dutch cities: official hourly and daily tariffs, capacity and EV charging points. Free and independent.">
<link rel="canonical" href="{SITE}/garage/">
{HEAD_FONTS}
<meta name="robots" content="index, follow">
<meta property="og:image" content="https://parkingnetherlands.com/og-image.png">
<script type="application/ld+json">{jsonld}</script>
</head>
<body>
{NAV}
<div class="wrap" style="max-width:960px;padding-bottom:60px">
  <header style="padding:44px 0 6px">
    <div class="eyebrow">Garage directory</div>
    <h1 style="font-size:clamp(1.7rem,3.2vw,2.4rem);font-weight:800;letter-spacing:-.03em;color:var(--ink);line-height:1.12">Every registered parking garage in the Netherlands</h1>
    <p style="color:var(--mut);font-size:15.5px;max-width:620px;margin-top:12px">{len(garages)} garages, lots and P+R sites across {len(by_city)} cities, straight from the RDW national parking register — with official drive-in tariffs where published. Prefer searching by address? Use the <a href="/search" style="color:var(--sig);font-weight:600">parking search</a>.</p>
  </header>
  {sections}
</div>
{FOOTER}
</body>
</html>"""


def main():
    here = Path(__file__).resolve().parent
    site = here.parent
    garages = json.loads((here / "garages.json").read_text())
    out = site / "garage"
    out.mkdir(exist_ok=True)

    urls = [f"{SITE}/garage/"]
    for g in garages:
        near = sorted((o for o in garages if o["slug"] != g["slug"]),
                      key=lambda o: haversine(g, o))[:5]
        for n in near:
            n["_dist"] = haversine(g, n)
        (out / f"{g['slug']}.html").write_text(garage_page(g, near), encoding="utf-8")
        urls.append(f"{SITE}/garage/{g['slug']}")

    (out / "index.html").write_text(index_page(garages), encoding="utf-8")
    (here / "garage-urls.txt").write_text("\n".join(urls) + "\n")
    print(f"wrote {len(garages)} garage pages + index -> {out}")


if __name__ == "__main__":
    main()
