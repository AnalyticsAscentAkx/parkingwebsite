#!/usr/bin/env python3
"""Build /park-and-ride: every P+R site in the register, and what it really costs.

This page exists in its current form because the first version of it was wrong.

The RDW national parking register carries a tariff for each P+R site. For the
Amsterdam sites it says 1.00 euro, for one hour, three hours and twenty-four
hours alike. The municipality's own page says 6.00 euro per 24 hours if you
arrive after ten in the morning and 13.00 for the first 24 hours if you arrive
before it, and the reduced rate only applies if you check in and out on public
transport with an OV-chipkaart. The register figure appears to be the rate
Amsterdam charged years ago. It is still being published today.

We repeated that 1.00 euro across the site because the register said so and we
did not check it against the city. That is the whole lesson: a national
register is a source, not an authority, and a conditional municipal scheme does
not fit in a single number.

So this build will not print a price it has not seen on a municipal page. Rates
live in VERIFIED below with the URL they came from and the date someone looked.
A city without an entry gets its sites, capacities and links, and the honest
statement that we have not checked its tariff yet. No price, no saving, no
estimate dressed up as a fact.

Usage:
  python3 park_and_ride.py
  python3 park_and_ride.py --dry-run
"""
import argparse
import json
import re
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SITE = "https://parkingnetherlands.com"
YEAR = 2026

# Only what has been read on the municipality's own page. Each entry is
# (headline rate text, full conditions, source url, date checked).
# Adding a city means opening its page and reading it, not copying ours.
VERIFIED = {
    "amsterdam": {
        "headline": "€6.00 per 24 hours",
        "detail": (
            "€6.00 per 24 hours if you enter after 10:00, or €13.00 for the first "
            "24 hours if you enter before 10:00 and €6.00 per 24 hours after that, up to "
            "96 hours. The reduced rate only applies if you check in and out on public "
            "transport with an OV-chipkaart or a paper GVB card. Paying with OVpay, a bank "
            "card or a phone does not qualify and you lose the discount. Public transport "
            "fares are separate."),
        "url": "https://www.amsterdam.nl/parkeren/parkeren-reizen/plaatsen-binnen-stad/pr-sloterdijk/",
        "checked": "2026-10-05",
    },
    "rotterdam": {
        "headline": "free for 24 hours with onward public transport",
        "detail": (
            "Free for up to 24 hours at P+R Kralingse Zoom if you travel on by public or "
            "shared transport using an OV-chipkaart. Without that it is €0.50 per 18 "
            "minutes, €17.00 a day. Beyond 24 hours the rate is €0.50 per 13 minutes "
            "to a maximum of €23.00 a day. Other Rotterdam P+R sites differ: P+R "
            "Alexander is around €1.77 an hour to a daily maximum of €18.00."),
        "url": "https://www.rotterdam.nl/pr-kralingse-zoom",
        "checked": "2026-10-05",
    },
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


def clean_name(n, city):
    n = re.sub(r"\s*\((?:" + re.escape(CITY_NAME.get(city, city)) + r")\)\s*$",
               "", n or "", flags=re.I)
    return n.strip()


def build():
    garages = json.loads((ROOT / "scripts" / "garages.json").read_text())
    index = json.loads((ROOT / "data" / f"parking-price-index-{YEAR}.json").read_text())
    med = {c["slug"]: c.get("median_24h_eur") for c in index["cities"]}
    med_vals = sorted(v for v in med.values() if v)
    med_of_med = statistics.median(med_vals)

    pr = [g for g in garages if g.get("is_pr")]
    by_city = {}
    for g in pr:
        by_city.setdefault(g["city"], []).append(g)

    rows = []
    for slug, sites in by_city.items():
        if slug not in CITY_NAME:
            continue
        rows.append({
            "slug": slug, "city": CITY_NAME[slug], "sites": sites,
            "n": len(sites),
            "spaces": sum(s.get("capacity") or 0 for s in sites),
            "median24": med.get(slug),
            "v": VERIFIED.get(slug),
        })
    rows.sort(key=lambda r: (r["v"] is None, -r["n"]))

    n_sites = sum(r["n"] for r in rows)
    n_spaces = sum(r["spaces"] for r in rows)
    n_ver = sum(1 for r in rows if r["v"])

    trs = []
    for r in rows:
        rate = (f'{esc(r["v"]["headline"])}' if r["v"]
                else '<span style="color:var(--mut)">not verified yet</span>')
        src = (f'<a href="{esc(r["v"]["url"])}" rel="nofollow noopener" target="_blank">'
               f'municipality, {r["v"]["checked"]}</a>' if r["v"] else "–")
        trs.append(
            f'<tr id="{r["slug"]}"><td><a href="/{r["slug"]}">{esc(r["city"])}</a></td>'
            f'<td class="num">{r["n"]}</td><td class="num">{r["spaces"]:,}</td>'
            f'<td>{rate}</td>'
            f'<td class="price">{eur(r["median24"]) if r["median24"] else "n/a"}</td>'
            f'<td style="font-size:12.5px">{src}</td></tr>')
    table = ('<div class="tbl-wrap"><table>\n<thead><tr><th>City</th><th>P+R sites</th>'
             '<th>Spaces</th><th>P+R tariff</th><th>Median garage per 24 h</th>'
             '<th>Source</th></tr></thead>\n<tbody>' + "\n".join(trs) + "</tbody></table></div>")

    secs = []
    for r in rows:
        items = []
        for s in sorted(r["sites"], key=lambda x: -(x.get("capacity") or 0)):
            cap = f'{s["capacity"]:,} spaces' if s.get("capacity") else "capacity not listed"
            ev = f' · {s["ev_points"]} charge points' if s.get("ev_points") else ""
            items.append(f'<li><a href="/garage/{s["slug"]}">'
                         f'{esc(clean_name(s.get("name"), r["slug"]))}</a>'
                         f'<span>{cap}{ev}</span></li>')
        if r["v"]:
            note = (f'<p><b>{esc(r["v"]["headline"])}.</b> {esc(r["v"]["detail"])} '
                    f'Checked on the <a href="{esc(r["v"]["url"])}" rel="nofollow noopener" '
                    f'target="_blank">municipal page</a> on {r["v"]["checked"]}.</p>')
        else:
            note = ('<p>We have not yet checked this city’s P+R tariff against the '
                    'municipality, so we are not quoting one. The register’s figure for '
                    'P+R sites has already proved wrong for Amsterdam, and we would rather '
                    'say nothing than repeat it. The sites and capacities below are from the '
                    'register and are reliable.</p>')
        secs.append(
            f'<h3 id="pr-{r["slug"]}">{esc(r["city"])}: {r["n"]} P+R '
            f'{"site" if r["n"] == 1 else "sites"}</h3>{note}'
            f'<ul class="glist">{"".join(items)}</ul>')

    faqs = [
        ("What is P+R parking in the Netherlands?",
         "P+R, park and ride, is a car park on the edge of a city with a direct public "
         "transport link into the centre. Municipalities subsidise it so that drivers leave "
         "the car outside the centre, and nearly all of them make the low rate conditional "
         "on actually travelling on by public transport."),
        ("How much does P+R cost?",
         "It depends on the city and on whether you use public transport, and the two Dutch "
         "schemes we have checked work differently from each other. Amsterdam charges €6.00 "
         "per 24 hours when you arrive after 10:00, and €13.00 for the first 24 hours when "
         "you arrive earlier. Rotterdam's Kralingse Zoom is free for 24 hours if you travel on "
         "with an OV-chipkaart, and €17.00 a day if you do not."),
        ("Is the price in the national parking register correct?",
         "For P+R sites, not always. The register lists every Amsterdam P+R at €1.00 for "
         "one hour, three hours and a full day alike, which was the city's rate some years "
         "ago and is not what you pay now. We treat the register as authoritative for where "
         "the sites are and how big they are, and we check tariffs against the municipality."),
        ("Do I have to use public transport to get the cheap rate?",
         "In both cities we have checked, yes, and the mechanism matters. Amsterdam requires "
         "a check-in and check-out on an OV-chipkaart or paper GVB card; paying with OVpay, a "
         "bank card or a phone does not count and the discount is lost. Rotterdam requires "
         "onward travel on an OV-chipkaart for the free period. Read the sign at the barrier."),
        ("Is P+R still cheaper than a city garage?",
         f"Generally yes, by a wide margin, but less than the register would suggest. A day in "
         f"a Dutch city garage has a median of {eur(med_of_med)} and reaches {eur(max(med_vals))} "
         f"in Amsterdam. Against Amsterdam's {eur(6)} P+R rate that is still a saving of around "
         f"{eur(max(med_vals) - 6)} before fares, rather than the {eur(max(med_vals) - 1)} the "
         f"register's figure would imply."),
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
            f"{len(rows)} cities, with tariffs checked against the municipality rather than "
            f"copied from the register.")

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2889604222343187" crossorigin="anonymous"></script>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Park and Ride Netherlands {YEAR}: All {n_sites} P+R Sites and Real Prices</title>
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
table td a{{color:var(--ink);text-decoration:none;font-weight:600}}
.cite{{font-size:13px;color:var(--mut);line-height:1.6}}
.corr{{background:var(--sig-soft);border-radius:var(--r-lg);padding:18px 20px;margin:22px 0}}
.corr b{{color:var(--ink)}}
.corr p{{font-size:14.5px;margin:0}}
</style>
</head>
<body>
<main class="pi-wrap">
<header class="pi-hero">
<h1>Park and ride in the Netherlands</h1>
<p class="lead">All {n_sites} P+R sites in the national parking register, {n_spaces:,} spaces
across {len(rows)} cities, with what each one actually costs where we have been able to check
it against the municipality.</p>
</header>

<div class="corr">
<p><b>A correction, and why this page is careful.</b> An earlier version of this page said
Amsterdam P+R costs {eur(1)} for 24 hours, because that is what the national parking register
says for every Amsterdam P+R site. The city charges {eur(6)}, or {eur(13)} if you arrive before
10:00, and only with an OV-chipkaart check-in. The register figure is years out of date and
still being published. We have removed every price on this page that we have not read on a
municipal page ourselves, and {n_ver} of {len(rows)} cities are verified so far.</p>
</div>

<div class="pi-stats">
<div class="pi-stat"><b>{n_sites}</b><span>P+R sites in the register</span></div>
<div class="pi-stat"><b>{n_spaces:,}</b><span>spaces across {len(rows)} cities</span></div>
<div class="pi-stat"><b>{n_ver}</b><span>cities with a verified tariff</span></div>
<div class="pi-stat"><b>{eur(med_of_med)}</b><span>median city garage, 24 hours</span></div>
</div>

<p>Park and ride is still the cheapest way to leave a car near a Dutch city, and the gap is
large enough that it survives being measured honestly. What it is not is a single national
price. Amsterdam charges a flat {eur(6)} a day with the discount; Rotterdam gives you the first
24 hours free if you travel on by tram or metro, and {eur(17)} if you do not. Those are two
different schemes, and the only reliable way to know which one you are standing in is the sign
at the barrier.</p>

<p>Nearly every scheme ties the low rate to actually using public transport, usually through a
check-in and check-out on an OV-chipkaart. Miss that step and you pay the ordinary daily rate,
which in Amsterdam is several times higher. The fare into town is on top in every city we
checked.</p>

<h2>What P+R costs, by city</h2>
{table}
<p class="cite">The tariff column is only filled where we have read the figure on the
municipality's own page, and the date we read it is in the source column. Where it is blank we
have not checked yet and are not guessing. Sites and capacities throughout are from the RDW
national parking register, which is reliable for those. The garage column is the median 24 hour
drive-in tariff of every register-listed garage in that city, the same figure published on the
<a href="/parking-price-index">Netherlands Parking Price Index</a>.</p>

<h2>Every P+R site, by city</h2>
{"".join(secs)}

<h2>How this was put together, and what is wrong with it</h2>
<p class="cite">Locations, names and capacities: the RDW national parking register, the source
behind every garage page here. Tariffs: read individually on each municipality's own page, with
the date recorded. Median garage tariffs: {index.get('register_snapshot', 'register snapshot')},
{sum(c.get('priced', 0) for c in index['cities'])} priced facilities.</p>
<p class="cite">The known weakness is coverage: {len(rows) - n_ver} of {len(rows)} cities still
have no verified tariff here, and those sections say so rather than showing a number. The
register's own tariff field is not used for P+R anywhere on this page, because it is
demonstrably wrong for Amsterdam and we have no reason to assume Amsterdam is the only one.
Rates change. The figure at the barrier wins. If you find one of these wrong, the contact
address is on the <a href="/about">about page</a> and it gets fixed the same week.</p>

<h2>Common questions</h2>
<div class="fq">{faq_html}</div>

<p style="margin-top:32px">Next: price a specific stop on the <a href="/map">garage and P+R map</a>,
check the <a href="/free-parking">places that cost nothing at all</a>, or see
<a href="/parking-price-index">how the cities compare on garage rates</a>.</p>
</main>
</body>
</html>
"""
    return page, n_sites, n_spaces, len(rows), n_ver


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    page, n_sites, n_spaces, n_cities, n_ver = build()
    print(f"  {n_sites} P+R sites, {n_spaces:,} spaces, {n_cities} cities")
    print(f"  cities with a tariff verified against the municipality: {n_ver}")
    print(f"  cities quoting no price at all: {n_cities - n_ver}")
    if a.dry_run:
        print("  dry run, nothing written")
        return 0
    out = ROOT / "park-and-ride.html"
    out.write_text(page, "utf-8")
    print(f"-> {out} ({len(page):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
