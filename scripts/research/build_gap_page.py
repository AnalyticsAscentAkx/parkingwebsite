#!/usr/bin/env python3
"""Build /charging-gap from the model output.

Reads charging-gap-summary.json and renders the page. The hexagon layer is
served as a separate file and fetched by the map, so the HTML stays small.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SUM = ROOT / "data" / "research" / "charging-gap-summary.json"
OUT = ROOT / "charging-gap.html"
SITE = "https://parkingnetherlands.com"


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def main():
    d = json.loads(SUM.read_text())
    sweep = d.get("sweep", [])
    worst = [w for w in d["worst"] if w["dep"] >= 50][:25]

    sweep_rows = "".join(
        f'<tr><td class="num">{s["catchment_m"]:,} m</td>'
        f'<td class="num">{s["short"]}</td>'
        f'<td class="num">{s["zero"]}</td>'
        f'<td class="num">{s["median"]}</td>'
        f'<td class="num">{s["p10"]}</td></tr>' for s in sweep)

    worst_rows = "".join(
        f'<tr><td>{esc(w["city"])}</td>'
        f'<td class="num">{w["pop"]:,}</td>'
        f'<td class="num">{w["dep"]:,}</td>'
        f'<td class="num">{w["per"]}</td>'
        f'<td class="num">{w["kw"]:,}</td>'
        f'<td class="num">{w["flats"]}%</td></tr>' for w in worst)

    lo = min(s["short"] for s in sweep) if sweep else d["short_hexes"]
    hi = max(s["short"] for s in sweep) if sweep else d["short_hexes"]

    faqs = [
        ("Does the Netherlands have enough public charging?",
         f"Nationally, comfortably. There is {d['national_kw']/1e6:.2f} GW of publicly "
         f"accessible charging power for about {d['national_ev']:,} electric cars, which is "
         f"{d['national_kw_per_ev']} kW each against the 1.3 kW per battery electric vehicle "
         f"that EU regulation 2023/1804 requires. That is more than twice the legal floor. "
         f"The shortage, where it exists, is local."),
        ("Which places fall short?",
         f"Between {lo} and {hi} neighbourhoods of roughly 1,400, depending on how far you "
         f"assume somebody will walk to charge. At a one kilometre catchment it is "
         f"{d['short_hexes']}, home to {d['short_people']:,} people. The full range is "
         f"published on this page rather than a single number, because the choice of walking "
         f"distance moves the answer more than anything else in the model."),
        ("How much would it cost to close the gap?",
         f"About {d['short_total_kw']/1000:.1f} MW of additional public charging power, which "
         f"is a few dozen fast chargers or a few hundred kerbside points. The national total "
         f"is small because the problem is concentrated: most of the country is far above the "
         f"line and a short list of neighbourhoods is below it."),
        ("Why measure per flat-dweller rather than per electric car?",
         "Because roughly four fifths of charging happens at home, and a household with a "
         "driveway barely touches the public network. The demand public infrastructure has to "
         "carry comes from people who cannot charge where they sleep. The closest thing open "
         "data supports is electric cars owned by households in multi-family housing, which "
         "makes every figure here a lower bound: a terraced street with no driveway counts as "
         "served when it is not."),
        ("Is this the same as the official forecasts?",
         "No, and it is not a substitute for them. ElaadNL and the Nationale Agenda "
         "Laadinfrastructuur already forecast charging demand per neighbourhood, with real "
         "charging transaction data this model does not have. What is not published anywhere "
         "we could find is the AFIR power test applied below national level and mapped, which "
         "is what this is."),
    ]
    faq_html = "".join(
        f'<div class="fqi"><button class="fqq">{esc(q)}<span class="fqt">+</span></button>'
        f'<div class="fqa"><p>{esc(a)}</p></div></div>' for q, a in faqs)

    ld = [
        {"@context": "https://schema.org", "@type": "FAQPage",
         "mainEntity": [{"@type": "Question", "name": q,
                         "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faqs]},
        {"@context": "https://schema.org", "@type": "Dataset",
         "name": "Dutch public charging accessibility by neighbourhood, 2026",
         "description": ("Public charging power reachable on foot per electric car without "
                         "home charging, for every two-kilometre hexagon in the Netherlands, "
                         "measured against the AFIR 1.3 kW per BEV standard."),
         "url": f"{SITE}/charging-gap",
         "license": "https://creativecommons.org/licenses/by/4.0/",
         "creator": {"@type": "Organization", "name": "Analytics Ascent"},
         "distribution": [
             {"@type": "DataDownload", "encodingFormat": "text/csv",
              "contentUrl": f"{SITE}/data/research/charging-gap-2026.csv"},
             {"@type": "DataDownload", "encodingFormat": "application/geo+json",
              "contentUrl": f"{SITE}/data/research/charging-gap-hexes.json"}]},
    ]
    ld_json = json.dumps(ld, ensure_ascii=False).replace("</", "<\\/")

    desc = (f"Public charging power reachable per electric car without a driveway, mapped for "
            f"every 2 km hexagon in the Netherlands. Nationally {d['national_kw_per_ev']} kW "
            f"per EV against the EU's 1.3. Between {lo} and {hi} neighbourhoods fall short.")

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2889604222343187" crossorigin="anonymous"></script>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Where Dutch Charging Still Falls Short: A Neighbourhood Map</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{SITE}/charging-gap">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<link rel="stylesheet" href="/site.css">
<link rel="icon" href="/favicon.ico?v=2" sizes="any"><link rel="icon" type="image/svg+xml" href="/favicon.svg?v=2">
<meta property="og:type" content="article">
<meta property="og:url" content="{SITE}/charging-gap">
<meta property="og:title" content="Where Dutch charging still falls short">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:image" content="{SITE}/og-image.png">
<meta name="robots" content="index, follow">
<meta name="author" content="Analytics Ascent">
<script type="application/ld+json">{ld_json}</script>
<style>
.cg{{max-width:1080px;margin:0 auto;padding:0 24px}}
.cg-hero{{padding:44px 0 6px}}
.cg-hero h1{{font-size:clamp(1.9rem,4vw,2.9rem);font-weight:800;letter-spacing:-.03em;line-height:1.1;color:var(--ink);margin:10px 0 12px}}
.cg-hero .lead{{font-size:17px;color:var(--mut);max-width:780px;line-height:1.6}}
.cg-stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:26px 0}}
.cg-stat{{background:#fff;border:1px solid var(--line);border-radius:var(--r-lg);padding:16px 18px;box-shadow:var(--sh)}}
.cg-stat b{{display:block;font-size:26px;font-weight:800;letter-spacing:-.03em;color:var(--ink);font-variant-numeric:tabular-nums}}
.cg-stat span{{font-size:12.5px;color:var(--mut)}}
.cg h2{{font-size:1.35rem;font-weight:800;letter-spacing:-.02em;color:var(--ink);margin:40px 0 12px}}
.cg h3{{font-size:1.05rem;font-weight:700;color:var(--ink);margin:26px 0 6px}}
.cg p{{line-height:1.65}}
.cg ul{{line-height:1.7;padding-left:20px}}
.cg li{{margin-bottom:8px}}
#cgmap{{height:clamp(420px,66vh,720px);border-radius:var(--r-lg);border:1px solid var(--line);
  background:#eef1f6;margin:8px 0 10px}}
.cg-legend{{display:flex;flex-wrap:wrap;gap:14px;font-size:12.5px;color:var(--mut);margin-bottom:6px}}
.cg-legend i{{width:13px;height:13px;border-radius:3px;display:inline-block;margin-right:6px;vertical-align:-2px}}
.cg-controls{{display:flex;gap:16px;flex-wrap:wrap;align-items:center;font-size:13.5px;margin:10px 0 2px}}
.cg-controls label{{display:flex;gap:7px;align-items:center;cursor:pointer}}
.cite{{font-size:13px;color:var(--mut);line-height:1.6}}
.warnbox{{background:var(--sig-soft);border-radius:var(--r-lg);padding:18px 20px;margin:22px 0}}
.warnbox p{{font-size:14.5px;margin:0 0 8px}}
.warnbox p:last-child{{margin:0}}
table td,table th{{white-space:nowrap}}
.leaflet-popup-content{{font:13.5px/1.5 var(--f);margin:12px 14px}}
.leaflet-popup-content b{{font-size:14.5px}}
.leaflet-popup-content dl{{display:grid;grid-template-columns:auto auto;gap:3px 12px;margin:8px 0 0}}
.leaflet-popup-content dt{{color:var(--mut)}}
.leaflet-popup-content dd{{margin:0;text-align:right;font-variant-numeric:tabular-nums;font-weight:600}}
</style>
</head>
<body>
<main class="cg">
<header class="cg-hero">
<h1>Where Dutch charging still falls short</h1>
<p class="lead">The Netherlands has more than twice the public charging power the EU requires.
That is a national average, and national averages are the wrong instrument for a question
about places. This is the same test applied to every two-kilometre hexagon in the country.</p>
</header>

<div class="cg-stats">
<div class="cg-stat"><b>{d['national_kw']/1e6:.2f} GW</b><span>public charging power in the register</span></div>
<div class="cg-stat"><b>{d['national_kw_per_ev']} kW</b><span>per electric car, against the EU's 1.3</span></div>
<div class="cg-stat"><b>{d['short_hexes']}</b><span>neighbourhoods below the line, of {d['hexes_with_demand']:,}</span></div>
<div class="cg-stat"><b>{d['short_total_kw']/1000:.1f} MW</b><span>would close every one of them</span></div>
</div>

<p>EU regulation 2023/1804, the Alternative Fuels Infrastructure Regulation, obliges member
states to provide at least 1.3 kW of publicly accessible charging power for every registered
battery electric car. It is checked per country. The Netherlands passes it at
{d['national_kw_per_ev']} kW per car and is not close to failing.</p>

<p>Underneath that, provision is not even. The map below asks the regulation's own question of
every neighbourhood: how much charging power can somebody actually reach on foot, per electric
car in that neighbourhood that has nowhere private to plug in.</p>

<h2>The map</h2>
<div class="cg-controls">
  <label><input type="checkbox" id="cgOnlyShort"> Show only the neighbourhoods below 1.3 kW</label>
  <span class="cite">Click any hexagon for its numbers.</span>
</div>
<div class="cg-legend">
  <span><i style="background:#C2410C"></i>nothing reachable</span>
  <span><i style="background:#EA580C"></i>below 1.3 kW</span>
  <span><i style="background:#FDBA74"></i>1.3 to 3</span>
  <span><i style="background:#93C5FD"></i>3 to 7</span>
  <span><i style="background:#3B82F6"></i>7 to 15</span>
  <span><i style="background:#2337C6"></i>15 and above</span>
</div>
<div id="cgmap"></div>
<p class="cite">Hexagons are 2 km across, about 3.5 km&sup2;. Only those with at least fifty
electric cars without home charging are shaded; the rest are too small a sample for a ratio to
mean anything. Colour is kilowatts of public charging reachable within one kilometre, shared
between everyone who can reach it, per electric car without a driveway.</p>

<h2>The number that moves the most is the one nobody measures</h2>
<p>How far will somebody walk to charge a car overnight? Nothing in the open data answers that,
and the answer changes the headline more than any other choice in this model. So here is the
whole curve rather than the single figure that makes the best story.</p>
<div class="tbl-wrap"><table>
<thead><tr><th>Assumed walking distance</th><th>Neighbourhoods below 1.3 kW</th>
<th>With nothing reachable</th><th>Median kW per car</th><th>Worst tenth</th></tr></thead>
<tbody>{sweep_rows}</tbody></table></div>
<p>At six hundred metres, seventy neighbourhoods fall short. At two kilometres, eight do. The
honest reading is the part that does not move: the median neighbourhood sits between 5.8 and
8.1 kW per car without home charging, four to six times the legal floor, whichever distance you
pick. The country is well supplied. A short, specific list of places is not, and which places
they are barely changes even though how many does.</p>

<h2>The neighbourhoods furthest below the line</h2>
<div class="tbl-wrap"><table>
<thead><tr><th>Municipality</th><th>Residents</th><th>EVs without home charging</th>
<th>kW reachable per car</th><th>kW inside the hexagon</th><th>Flats</th></tr></thead>
<tbody>{worst_rows}</tbody></table></div>
<p class="cite">Several of these have a good deal of charging inside them and still score
badly, which is the method working rather than failing: a charger is shared with everyone who
can walk to it, so a hexagon sitting next to a dense neighbourhood is competing for the same
posts. The column that matters is what a resident can reach, not what happens to stand on
their side of a line.</p>

<h2>How it is built</h2>
<p>Four inputs, three of them observed and one modelled, and the modelled one is named as such
every time it is used.</p>
<ul>
<li><b>Charging supply.</b> {d['national_kw']:,.0f} kW across about 80,000 public charging
locations from the national charge point register, the same source behind our
<a href="/ev-charging">charger map</a>.</li>
<li><b>Cars per neighbourhood.</b> CBS wijken en buurten 2024, observed, 14,668 neighbourhoods.</li>
<li><b>Electric share per municipality.</b> CBS fleet statistics, observed, as published on our
<a href="/ev-adoption">EV adoption page</a>.</li>
<li><b>Electric cars per neighbourhood.</b> Cars times the municipal electric share.
<b>Modelled.</b> CBS does not publish electric cars at neighbourhood level.</li>
<li><b>Cars without home charging.</b> The above times the share of dwellings that are flats,
also from CBS. <b>Modelled</b>, and deliberately conservative.</li>
</ul>
<p>Accessibility is two-step floating catchment area, the standard method in the charging
desert literature, which shares each charger between everyone who can reach it instead of
assigning it to whichever polygon it happens to stand in.</p>

<div class="warnbox">
<p><b>Three things this got wrong before it got them right.</b></p>
<p>The first version counted only chargers inside each hexagon and announced that the worst
place in the Netherlands was a Groningen neighbourhood with no charging at all. It has
sixty-one chargers within two kilometres and the nearest is 1.08 km away. The hexagon was
measuring its own edges. That is what the catchment method fixed.</p>
<p>The second version measured distance from the middle of each hexagon, which puts everyone
living on the rim up to a kilometre from where they actually are. Demand now sits at
neighbourhood centroids, which are a few hundred metres across rather than two kilometres.</p>
<p>The third was a sensitivity sweep that returned an identical answer at every walking
distance, which looked like reassuring robustness and was a bug: the catchment was frozen at
import and never changed. The real spread is in the table above, and it is wide.</p>
<p>Each was found by checking one specific claim against the world rather than by reading the
code. We publish them because a model nobody has tried to break is not evidence.</p>
</div>

<h2>What this does not tell you</h2>
<ul>
<li>Electric cars per neighbourhood are estimated, not counted.</li>
<li>Flats are a proxy for having nowhere to charge, not a measurement of it. A terraced street
without driveways reads as well served here.</li>
<li>Power is not availability. Whether a post is occupied when you arrive is not published by
anyone, so nothing here accounts for it.</li>
<li>AFIR sets a national target. Applying it to a neighbourhood is our interpretation, not the
regulation's, and the regulation would not recognise it.</li>
<li>Only charging where people live is modelled. Workplace, motorway and destination charging
answer different questions.</li>
</ul>

<h2>Common questions</h2>
<div class="fq">{faq_html}</div>

<h2>Take the data</h2>
<p>Both files are free to reuse with attribution.
<a href="/data/research/charging-gap-2026.csv">CSV, one row per hexagon</a> and
<a href="/data/research/charging-gap-hexes.json">GeoJSON with the geometry</a>. The code that
builds them is in the repository, and if you find a fourth mistake we would like to hear about
it: the address is on the <a href="/about">about page</a>.</p>
<p class="cite">Sources: RDW national parking register and the national charge point register
for supply; CBS wijken en buurten 2024 and CBS fleet statistics for demand; Regulation (EU)
2023/1804 Article 3 for the 1.3 kW standard. Method after the two-step floating catchment area
literature on charging access and charging deserts. Generated {d['generated']}.</p>
</main>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
(function () {{
  var map = L.map('cgmap', {{ preferCanvas: true, scrollWheelZoom: false }})
    .setView([52.15, 5.4], 8);
  L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    maxZoom: 17, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }}).addTo(map);
  map.once('focus', function () {{ map.scrollWheelZoom.enable(); }});

  /* Bands, not a continuous ramp. A ramp invites the eye to read precision
     that a modelled denominator cannot support. */
  function colour(v) {{
    if (v <= 0) return '#C2410C';
    if (v < 1.3) return '#EA580C';
    if (v < 3) return '#FDBA74';
    if (v < 7) return '#93C5FD';
    if (v < 15) return '#3B82F6';
    return '#2337C6';
  }}
  var layer = null, data = null, onlyShort = false;

  function style(f) {{
    var p = f.properties;
    return {{ fillColor: colour(p.per), fillOpacity: .72, color: '#fff',
              weight: .4, opacity: .5 }};
  }}
  function keep(f) {{
    var p = f.properties;
    if (p.dep < 50) return false;         // too small for a ratio to mean anything
    return onlyShort ? p.per < 1.3 : true;
  }}
  function popup(f, l) {{
    var p = f.properties;
    l.bindPopup(
      '<b>' + (p.city || 'Unnamed area') + '</b>' +
      '<dl>' +
      '<dt>Reachable per car without home charging</dt><dd>' + p.per.toFixed(2) + ' kW</dd>' +
      '<dt>EU minimum</dt><dd>1.30 kW</dd>' +
      '<dt>Residents</dt><dd>' + p.pop.toLocaleString() + '</dd>' +
      '<dt>Electric cars (modelled)</dt><dd>' + p.ev.toLocaleString() + '</dd>' +
      '<dt>Of those, in flats</dt><dd>' + p.dep.toLocaleString() + '</dd>' +
      '<dt>Charging power inside</dt><dd>' + p.kw.toLocaleString() + ' kW</dd>' +
      '<dt>Dwellings that are flats</dt><dd>' + p.flats + '%</dd>' +
      '</dl>');
  }}
  function draw() {{
    if (layer) map.removeLayer(layer);
    layer = L.geoJSON(data, {{ style: style, filter: keep, onEachFeature: popup }}).addTo(map);
  }}

  fetch('/data/research/charging-gap-hexes.json')
    .then(function (r) {{ return r.json(); }})
    .then(function (j) {{ data = j; draw(); }})
    .catch(function () {{
      document.getElementById('cgmap').innerHTML =
        '<p style="padding:20px;color:#555">The map data could not be loaded. ' +
        'The figures in the tables below are unaffected.</p>';
    }});

  var cb = document.getElementById('cgOnlyShort');
  if (cb) cb.addEventListener('change', function () {{
    onlyShort = cb.checked;
    if (data) draw();
  }});
}})();
</script>
</body>
</html>
"""
    OUT.write_text(page, "utf-8")
    print(f"-> {OUT} ({len(page):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
