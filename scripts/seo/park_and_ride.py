#!/usr/bin/env python3
"""Build /park-and-ride: every P+R site in the register, and what using one saves.

The demand this site actually receives is "goedkoop parkeren amsterdam" and
"guenstig parken amsterdam". Cheap parking. The cheapest parking in the country
by a wide margin is park and ride, and there was no page about it: 68 P+R sites
sat in the data, each linked exactly once from a 25-item list on its city page,
where nobody looking for cheap parking would ever find them.

The number that makes the case is the gap. A day in a median Amsterdam garage
costs 92 euro at register tariffs. P+R Sloterdijk is 1 euro for 24 hours. No
amount of shopping between garages gets near that, which is the opposite of
what the rest of the site spends its time helping people do.

Two sources, because the two numbers come from different places:

  garages.json                    68 sites flagged is_pr, with capacity,
                                  EV points and coordinates, from the RDW
                                  national parking register
  parking-price-index-2026.json   the median 24 hour garage tariff per city,
                                  already published on /parking-price-index

The P+R day rate is the one thing neither source has. Municipalities set it
themselves and it is not in the register, so it is written out below with the
city page it came from, and the build refuses to run if the two ever disagree.

Usage:
  python3 park_and_ride.py
  python3 park_and_ride.py --dry-run
"""
import argparse
import json
import re
import statistics
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SITE = "https://parkingnetherlands.com"
YEAR = 2026

# Municipal P+R day rates. Not in the national register: each municipality
# publishes its own. Every one of these is already stated on the city page
# named beside it, and check_rates() below re-reads those pages and aborts the
# build on any disagreement, so the two can never quietly drift apart.
PR_RATE = {
    "amsterdam": (1.00, "amsterdam.html"),
    "breda": (2.00, "breda.html"),
    "delft": (2.50, "delft.html"),
    "eindhoven": (3.00, "eindhoven.html"),
    "groningen": (2.00, "groningen.html"),
    "haarlem": (3.00, "haarlem.html"),
    "leiden": (5.00, "leiden.html"),
    "maastricht": (4.00, "maastricht.html"),
    "nijmegen": (2.50, "nijmegen.html"),
    "rotterdam": (2.50, "rotterdam.html"),
    "the-hague": (2.00, "the-hague.html"),
    "tilburg": (2.00, "tilburg.html"),
    "utrecht": (5.00, "utrecht.html"),
}

CITY_NAME = {
    "amsterdam": "Amsterdam", "breda": "Breda", "delft": "Delft",
    "eindhoven": "Eindhoven", "groningen": "Groningen", "haarlem": "Haarlem",
    "leiden": "Leiden", "maastricht": "Maastricht", "nijmegen": "Nijmegen",
    "rotterdam": "Rotterdam", "the-hague": "The Hague", "tilburg": "Tilburg",
    "utrecht": "Utrecht",
}


def esc(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def eur(v):
    return f"€{v:,.2f}"


def visible(path):
    t = Path(path).read_text(errors="ignore")
    t = re.sub(r'(?s)<(script|style)[^>]*>.*?</\1>', " ", t)
    return re.sub(r"<[^>]+>", " ", t)


def check_rates():
    """Refuse to publish a rate the city page itself does not agree with."""
    bad = []
    for slug, (rate, page) in PR_RATE.items():
        p = ROOT / page
        if not p.is_file():
            bad.append(f"{slug}: {page} is missing")
            continue
        v = visible(p)
        found = {float(m.group(1).replace(",", "."))
                 for m in re.finditer(r"P\+R[^.€]{0,40}?€\s?([\d]+(?:[.,]\d{1,2})?)", v, re.I)}
        if rate not in found:
            bad.append(f"{slug}: script says {rate}, {page} says {sorted(found) or 'nothing'}")
    if bad:
        for b in bad:
            print("  RATE MISMATCH:", b, file=sys.stderr)
        sys.exit("refusing to build with rates the city pages contradict")
    print(f"  rates cross-checked against {len(PR_RATE)} city pages: all agree")


def clean_name(n, city):
    """Site names repeat the city in brackets, which reads badly in a list
    that is already grouped by city."""
    n = re.sub(r"\s*\((?:" + re.escape(CITY_NAME.get(city, city)) + r")\)\s*$", "", n or "", flags=re.I)
    return n.strip()


def build():
    garages = json.loads((ROOT / "scripts" / "garages.json").read_text())
    index = json.loads((ROOT / "data" / f"parking-price-index-{YEAR}.json").read_text())
    med = {c["slug"]: c.get("median_24h_eur") for c in index["cities"]}

    pr = [g for g in garages if g.get("is_pr")]
    by_city = {}
    for g in pr:
        by_city.setdefault(g["city"], []).append(g)

    rows = []
    for slug, sites in by_city.items():
        if slug not in PR_RATE:
            continue
        rate = PR_RATE[slug][0]
        spaces = sum(s.get("capacity") or 0 for s in sites)
        m = med.get(slug)
        rows.append({
            "slug": slug, "city": CITY_NAME.get(slug, slug.title()),
            "sites": sites, "n": len(sites), "spaces": spaces,
            "rate": rate, "median24": m,
            "saving": (m - rate) if m else None,
        })
    rows.sort(key=lambda r: -(r["saving"] or 0))
    med_vals = sorted(v for v in med.values() if v)
    med_of_med = statistics.median(med_vals)

    n_sites = sum(r["n"] for r in rows)
    n_spaces = sum(r["spaces"] for r in rows)
    n_ev = sum((s.get("ev_points") or 0) for r in rows for s in r["sites"])
    best = rows[0]
    cheapest = min(rows, key=lambda r: r["rate"])

    # ---- main table
    trs = []
    for r in rows:
        trs.append(
            f'<tr id="{r["slug"]}"><td><a href="/{r["slug"]}">{esc(r["city"])}</a></td>'
            f'<td class="num">{r["n"]}</td>'
            f'<td class="num">{r["spaces"]:,}</td>'
            f'<td class="price">{eur(r["rate"])}</td>'
            f'<td class="price">{eur(r["median24"]) if r["median24"] else "n/a"}</td>'
            f'<td class="price"><strong>{eur(r["saving"]) if r["saving"] else "n/a"}</strong></td></tr>')
    table = ('<div class="tbl-wrap"><table>\n<thead><tr><th>City</th><th>P+R sites</th>'
             '<th>Spaces</th><th>P+R per 24 h</th><th>Median garage per 24 h</th>'
             '<th>Parking saved</th></tr></thead>\n<tbody>' + "\n".join(trs) + "</tbody></table></div>")

    # ---- per city lists, which is what gives each P+R page a real parent
    secs = []
    for r in rows:
        items = []
        for s in sorted(r["sites"], key=lambda x: -(x.get("capacity") or 0)):
            cap = f'{s["capacity"]:,} spaces' if s.get("capacity") else "capacity not listed"
            ev = f' · {s["ev_points"]} charge points' if s.get("ev_points") else ""
            items.append(f'<li><a href="/garage/{s["slug"]}">{esc(clean_name(s.get("name"), r["slug"]))}</a>'
                         f'<span>{cap}{ev}</span></li>')
        secs.append(
            f'<h3 id="pr-{r["slug"]}">{esc(r["city"])}: {r["n"]} P+R '
            f'{"site" if r["n"] == 1 else "sites"}, {eur(r["rate"])} per 24 hours</h3>'
            f'<p>Against a median {eur(r["median24"])} for 24 hours in a '
            f'{esc(r["city"])} garage, a day on P+R leaves {eur(r["saving"])} in your '
            f'pocket before you have paid a fare. Full city rates are on the '
            f'<a href="/{r["slug"]}">{esc(r["city"])} parking page</a>.</p>'
            f'<ul class="glist">{"".join(items)}</ul>')

    faqs = [
        ("What is P+R parking in the Netherlands?",
         "P+R, short for park and ride, is a car park on the edge of a city with a direct "
         "public transport link into the centre. The municipality subsidises the parking so "
         "that drivers leave the car outside the centre, which is why a day costs between "
         f"{eur(cheapest['rate'])} and {eur(max(r['rate'] for r in rows))} instead of the "
         f"{eur(med_of_med)} a typical city garage charges for the same day."),
        ("How much does P+R parking cost?",
         f"Between {eur(cheapest['rate'])} and {eur(max(r['rate'] for r in rows))} for 24 hours, "
         f"depending on the city. {cheapest['city']} is the cheapest at {eur(cheapest['rate'])}. "
         "The rate is set by the municipality rather than the operator, so every site in a "
         "city normally charges the same. Public transport into the centre is extra."),
        ("Do I have to use public transport to get the P+R rate?",
         "In most cities yes. The low rate is conditional on checking in and out on public "
         "transport with an OV-chipkaart, usually at least twice, and in Amsterdam the "
         "discount is removed entirely if you do not. Without it you pay the ordinary daily "
         "tariff, which can be several times higher. Check the sign at the barrier."),
        ("Is P+R cheaper than a garage?",
         f"In every city here, substantially. The largest gap is {best['city']}, where a "
         f"median garage day is {eur(best['median24'])} and P+R is {eur(best['rate'])}, a "
         f"difference of {eur(best['saving'])}. Even after two return fares the saving holds "
         "for any stay longer than about an hour."),
        ("Where are the P+R car parks?",
         f"There are {n_sites} in the national parking register across {len(rows)} cities, "
         f"{n_spaces:,} spaces in total. They are listed by city on this page, and every one "
         "of them is on the map with its live position and the tariff for the ground it sits on."),
    ]
    faq_html = "".join(
        f'<div class="fqi"><button class="fqq">{esc(q)}<span class="fqt">+</span></button>'
        f'<div class="fqa"><p>{esc(a)}</p></div></div>' for q, a in faqs)

    ld = [
        {"@context": "https://schema.org", "@type": "FAQPage",
         "mainEntity": [{"@type": "Question", "name": q,
                         "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faqs]},
        {"@context": "https://schema.org", "@type": "ItemList",
         "name": f"Park and ride sites in the Netherlands {YEAR}",
         "numberOfItems": n_sites,
         "itemListElement": [
             {"@type": "ListItem", "position": i + 1,
              "url": f"{SITE}/garage/{s['slug']}",
              "name": clean_name(s.get("name"), r["slug"])}
             for i, (r, s) in enumerate((r, s) for r in rows for s in r["sites"])]},
        {"@context": "https://schema.org", "@type": "BreadcrumbList",
         "itemListElement": [
             {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE},
             {"@type": "ListItem", "position": 2, "name": "Park and Ride",
              "item": f"{SITE}/park-and-ride"}]},
    ]
    ld_json = json.dumps(ld, ensure_ascii=False).replace("</", "<\\/")

    desc = (f"All {n_sites} park and ride sites in the Netherlands, {n_spaces:,} spaces across "
            f"{len(rows)} cities. From {eur(cheapest['rate'])} per 24 hours against a median "
            f"garage day of {eur(best['median24'])}.")

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2889604222343187" crossorigin="anonymous"></script>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Park and Ride Netherlands {YEAR}: All {n_sites} P+R Sites and Prices</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{SITE}/park-and-ride">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/site.css">
<link rel="icon" href="/favicon.ico?v=2" sizes="any"><link rel="icon" type="image/svg+xml" href="/favicon.svg?v=2">
<meta property="og:type" content="article">
<meta property="og:url" content="{SITE}/park-and-ride">
<meta property="og:title" content="Park and Ride Netherlands {YEAR}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:image" content="{SITE}/og-image.png">
<meta name="robots" content="index, follow">
<meta name="author" content="Analytics Ascent">
<script type="application/ld+json">{ld_json}</script>
<style>
.pi-wrap{{max-width:1080px;margin:0 auto;padding:0 24px}}
.pi-hero{{padding:44px 0 10px}}
.pi-hero h1{{font-size:clamp(1.9rem,4vw,2.9rem);font-weight:800;letter-spacing:-.03em;line-height:1.1;color:var(--ink);margin:10px 0 12px}}
.pi-hero .lead{{font-size:17px;color:var(--mut);max-width:760px;line-height:1.6}}
.pi-stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:28px 0}}
.pi-stat{{background:#fff;border:1px solid var(--line);border-radius:var(--r-lg);padding:16px 18px;box-shadow:var(--sh)}}
.pi-stat b{{display:block;font-size:26px;font-weight:800;letter-spacing:-.03em;color:var(--ink);font-variant-numeric:tabular-nums}}
.pi-stat span{{font-size:12.5px;color:var(--mut)}}
.pi-wrap h2{{font-size:1.35rem;font-weight:800;letter-spacing:-.02em;color:var(--ink);margin:40px 0 12px}}
.pi-wrap h3{{font-size:1.05rem;font-weight:700;color:var(--ink);margin:28px 0 6px}}
.pi-wrap p{{line-height:1.65}}
table td,table th{{white-space:nowrap}}
table td a{{color:var(--ink);text-decoration:none;font-weight:600}}
.cite{{font-size:13px;color:var(--mut);line-height:1.6}}
</style>
</head>
<body>
<main class="pi-wrap">
<header class="pi-hero">
<h1>Park and ride in the Netherlands</h1>
<p class="lead">Every P+R site in the national parking register, what each city charges for
24 hours, and what that saves against parking the same day in a garage. {n_sites} sites,
{n_spaces:,} spaces, {len(rows)} cities.</p>
</header>

<div class="pi-stats">
<div class="pi-stat"><b>{n_sites}</b><span>P+R sites in the register</span></div>
<div class="pi-stat"><b>{n_spaces:,}</b><span>spaces across {len(rows)} cities</span></div>
<div class="pi-stat"><b>{eur(cheapest['rate'])}</b><span>cheapest 24 hours, in {esc(cheapest['city'])}</span></div>
<div class="pi-stat"><b>{eur(best['saving'])}</b><span>biggest daily saving, in {esc(best['city'])}</span></div>
</div>

<p>The rest of this site exists to help you find a cheaper garage. This page is about the
option that beats all of them. A day in a city garage, taking the median of every
register-listed tariff in each city, runs from {eur(min(med_vals))} in the cheapest city to
{eur(max(med_vals))} in Amsterdam, with {eur(med_of_med)} in the middle. Leaving the car on the
edge of the same city costs between {eur(cheapest['rate'])} and
{eur(max(r['rate'] for r in rows))}, because the municipality would rather you did, and pays
for the difference.</p>

<p>The catch is real and worth stating plainly. In most cities the low rate only applies if
you actually check in and out on public transport, and the fare is on top. For one person
that is a few euro return. The saving still holds comfortably, but it is not the whole number
in the last column.</p>

<h2>What P+R costs, and what it saves, by city</h2>
{table}
<p class="cite">Sorted by the saving. The P+R rate is the municipal scheme rate for the city.
The garage figure is the median 24 hour drive-in tariff of every register-listed garage in that
city, the same number published on the
<a href="/parking-price-index">Netherlands Parking Price Index</a>. Public transport is not
included in either column.</p>

<h2>Every P+R site, by city</h2>
<p>Capacities come from the register and are blank where the operator has not filed one.
Each site links to its own page with the exact location, height limit and access hours.</p>
{"".join(secs)}

<h2>How this was put together</h2>
<p class="cite">P+R sites and capacities: the RDW national parking register, the same source
behind every garage page on this site. Median garage tariffs: {index.get('register_snapshot', 'register snapshot')},
{sum(c.get('priced', 0) for c in index['cities'])} priced facilities. P+R day rates are set by
each municipality and are not in the register, so they are taken from the city pages here and
the build fails if the two disagree. Rates change; the figure at the barrier wins. If you find
one of these wrong, the contact address is on the <a href="/about">about page</a> and it gets
fixed the same week.</p>

<h2>Common questions</h2>
<div class="fq">{faq_html}</div>

<p style="margin-top:32px">Next: price a specific stop on the <a href="/map">garage and P+R map</a>,
check the <a href="/free-parking">places that cost nothing at all</a>, or see
<a href="/parking-price-index">how the cities compare on garage rates</a>.</p>
</main>
</body>
</html>
"""
    build.rows = rows
    return page, n_sites, n_spaces, len(rows), best


PR_START = "<!-- pr-link:start -->"
PR_END = "<!-- pr-link:end -->"


def inject_city_blocks(rows):
    """Give every city page a route into the P+R page carrying its own figures.

    A block repeated verbatim across thirteen pages is boilerplate and reads
    like it. Each one here states that city's own site count, rate and saving,
    so the page says something only that page can say.
    """
    n = 0
    for r in rows:
        f = ROOT / f"{r['slug']}.html"
        if not f.is_file():
            continue
        t = f.read_text()
        block = (
            f'{PR_START}\n<section class="sec"><div class="wrap">'
            f'<h2>Park and ride in {esc(r["city"])}</h2>'
            f'<p>{esc(r["city"])} has {r["n"]} park and ride '
            f'{"site" if r["n"] == 1 else "sites"} in the national register, '
            f'{r["spaces"]:,} spaces between them, at {eur(r["rate"])} for 24 hours. '
            f'A day in a median {esc(r["city"])} garage is {eur(r["median24"])}, so the '
            f'car costs {eur(r["saving"])} less before you add a fare. The low rate '
            f'normally depends on checking in and out on public transport.</p>'
            f'<p>All {r["n"]} are listed with capacities on the '
            f'<a href="/park-and-ride#pr-{r["slug"]}">national park and ride page</a>, '
            f'alongside the other twelve cities.</p>'
            f'</div></section>\n{PR_END}'
        )
        if PR_START in t:
            i, j = t.index(PR_START), t.index(PR_END) + len(PR_END)
            t = t[:i] + block + t[j:]
        else:
            anchor = "<!-- free-link:start -->"
            if anchor in t:
                t = t.replace(anchor, block + "\n" + anchor, 1)
            else:
                continue
        f.write_text(t, "utf-8")
        n += 1
    print(f"  city pages given a P+R block: {n}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    check_rates()
    page, n_sites, n_spaces, n_cities, best = build()
    print(f"  {n_sites} P+R sites, {n_spaces:,} spaces, {n_cities} cities")
    print(f"  biggest saving: {best['city']} at {eur(best['saving'])} a day")
    if a.dry_run:
        print("  dry run, nothing written")
        return 0
    out = ROOT / "park-and-ride.html"
    out.write_text(page, "utf-8")
    inject_city_blocks(build.rows)
    print(f"-> {out} ({len(page):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
