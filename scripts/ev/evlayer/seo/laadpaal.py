"""Dutch per-city and per-operator pages, generated from the database.

  laadpaal-{stad}.html       "laadpaal Utrecht": counts, price per kWh by
                             operator, faults by operator, fast chargers,
                             charging + parking, map link, FAQ
  {operator}-storing.html    "Fastned storing": fault rate now, by city,
                             against the national figure; grows into a
                             30-day record as the collector accrues

Every number comes from a query below, so a re-run after the daily rollup
refreshes the pages. Copy is Dutch; the English site never had these.
Licence rules apply: credit NDW / DOT-NL, never name RDW (the parking
register is "het Nationaal Parkeer Register").
"""
import json
import re
from datetime import date
from pathlib import Path

from .. import config, db

CITY_LIMIT = 40
OPERATOR_LIMIT = 24
TODAY = date.today()
MONTHS_NL = ["januari", "februari", "maart", "april", "mei", "juni", "juli",
             "augustus", "september", "oktober", "november", "december"]
DATE_NL = f"{TODAY.day} {MONTHS_NL[TODAY.month - 1]} {TODAY.year}"
EN_CITY_PAGES = {"amsterdam", "rotterdam", "den-haag", "utrecht", "eindhoven", "groningen", "haarlem",
                 "leiden", "delft", "maastricht", "breda", "nijmegen", "tilburg", "zwolle"}
EN_SLUG = {"den-haag": "the-hague"}


def slug(s: str) -> str:
    s = s.lower().replace("'s-", "s-").replace("'", "")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def eur(v, dec=2):
    return ("€" + f"{float(v):,.{dec}f}").replace(",", "X").replace(".", ",").replace("X", ".")


def pct(v):
    return f"{float(v):.1f}".replace(".", ",") + "%"


NP = '<span style="color:var(--mut)">niet gepubliceerd</span>'


def esc(s):
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ---------------------------------------------------------------- queries
def national() -> dict:
    return db.one("""
      SELECT COUNT(DISTINCT s.station_id)::int AS stations,
             COUNT(DISTINCT e.evse_id)::int AS points,
             ROUND(100.0 * COUNT(DISTINCT e.evse_id) FILTER (WHERE e.status_current IN ('OUTOFORDER','INOPERATIVE'))
                   / NULLIF(COUNT(DISTINCT e.evse_id), 0), 1) AS fault_pct,
             (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY price_per_kwh) FROM cpo_tariff WHERE price_per_kwh IS NOT NULL) AS med_kwh
      FROM station s JOIN evse e ON e.station_id = s.station_id
      WHERE s.access_type = 'FreePublic'""")


def cities():
    return db.query("""
      SELECT s.city, COUNT(DISTINCT s.station_id)::int AS stations, COUNT(DISTINCT e.evse_id)::int AS points,
             ROUND(100.0 * COUNT(DISTINCT e.evse_id) FILTER (WHERE e.status_current IN ('OUTOFORDER','INOPERATIVE'))
                   / NULLIF(COUNT(DISTINCT e.evse_id), 0), 1) AS fault_pct,
             COUNT(DISTINCT s.station_id) FILTER (WHERE c.max_power_kw >= 50)::int AS fast,
             COUNT(DISTINCT s.station_id) FILTER (WHERE c.max_power_kw >= 150)::int AS hubs,
             AVG(s.lat) AS lat, AVG(s.lon) AS lon
      FROM station s JOIN evse e ON e.station_id = s.station_id
      JOIN connector c ON c.evse_id = e.evse_id
      WHERE s.access_type = 'FreePublic' AND s.city IS NOT NULL
      GROUP BY s.city ORDER BY stations DESC LIMIT %s""", (CITY_LIMIT,))


def city_operators(city):
    return db.query("""
      SELECT s.cpo, COUNT(DISTINCT s.station_id)::int AS stations, COUNT(DISTINCT e.evse_id)::int AS points,
             ROUND(100.0 * COUNT(DISTINCT e.evse_id) FILTER (WHERE e.status_current IN ('OUTOFORDER','INOPERATIVE'))
                   / NULLIF(COUNT(DISTINCT e.evse_id), 0), 1) AS fault_pct,
             (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY t.price_per_kwh)
                FROM station s2 JOIN evse e2 ON e2.station_id = s2.station_id
                JOIN connector c2 ON c2.evse_id = e2.evse_id
                JOIN LATERAL unnest(c2.tariff_ids) tid ON true JOIN cpo_tariff t ON t.tariff_id = tid
               WHERE s2.city = s.city AND s2.cpo = s.cpo AND t.price_per_kwh IS NOT NULL) AS med_kwh
      FROM station s JOIN evse e ON e.station_id = s.station_id
      WHERE s.access_type = 'FreePublic' AND s.city = %s AND s.cpo IS NOT NULL AND s.cpo <> ''
      GROUP BY s.city, s.cpo ORDER BY stations DESC LIMIT 8""", (city,))


def city_hubs(city):
    return db.query("""
      SELECT s.name, s.cpo, s.address, MAX(c.max_power_kw)::int AS kw, COUNT(DISTINCT e.evse_id)::int AS points
      FROM station s JOIN evse e ON e.station_id = s.station_id JOIN connector c ON c.evse_id = e.evse_id
      WHERE s.access_type = 'FreePublic' AND s.city = %s
      GROUP BY s.station_id HAVING MAX(c.max_power_kw) >= 50 AND MAX(c.max_power_kw) <= 1000
      ORDER BY kw DESC, points DESC LIMIT 8""", (city,))


def city_parking(city):
    return db.one("""
      SELECT COUNT(DISTINCT s.station_id)::int AS in_zone,
             (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY t.price_per_hour)
                FROM station_parking_link l2 JOIN station s2 ON s2.station_id = l2.station_id
                JOIN parking_tariff t ON t.area_id = l2.area_id AND t.day_of_week = 3
                  AND t.start_min <= 840 AND t.end_min > 840
               WHERE s2.city = %s AND t.price_per_hour > 0 AND t.price_per_hour < 20) AS med_hour
      FROM station s JOIN station_parking_link l ON l.station_id = s.station_id
      WHERE s.city = %s""", (city, city))


def operators():
    return db.query("""
      SELECT s.cpo, COUNT(DISTINCT s.station_id)::int AS stations, COUNT(DISTINCT e.evse_id)::int AS points,
             COUNT(DISTINCT e.evse_id) FILTER (WHERE e.status_current IN ('OUTOFORDER','INOPERATIVE'))::int AS down,
             ROUND(100.0 * COUNT(DISTINCT e.evse_id) FILTER (WHERE e.status_current IN ('OUTOFORDER','INOPERATIVE'))
                   / NULLIF(COUNT(DISTINCT e.evse_id), 0), 1) AS fault_pct,
             ROUND(100.0 * COUNT(DISTINCT e.evse_id) FILTER (WHERE e.status_current IS NULL OR e.status_current = 'UNKNOWN')
                   / NULLIF(COUNT(DISTINCT e.evse_id), 0), 1) AS unknown_pct,
             COUNT(DISTINCT s.city)::int AS cities
      FROM station s JOIN evse e ON e.station_id = s.station_id
      WHERE s.access_type = 'FreePublic' AND s.cpo IS NOT NULL AND s.cpo <> ''
      GROUP BY s.cpo HAVING COUNT(DISTINCT s.station_id) >= 40 ORDER BY points DESC LIMIT %s""", (OPERATOR_LIMIT,))


def operator_cities(cpo):
    return db.query("""
      SELECT s.city, COUNT(DISTINCT e.evse_id)::int AS points,
             COUNT(DISTINCT e.evse_id) FILTER (WHERE e.status_current IN ('OUTOFORDER','INOPERATIVE'))::int AS down
      FROM station s JOIN evse e ON e.station_id = s.station_id
      WHERE s.access_type = 'FreePublic' AND s.cpo = %s AND s.city IS NOT NULL
      GROUP BY s.city HAVING COUNT(DISTINCT e.evse_id) >= 40 ORDER BY down DESC, points DESC LIMIT 10""", (cpo,))


def history_days():
    return db.one("SELECT COUNT(DISTINCT day) AS d FROM reliability_daily")["d"] or 0


def operator_uptime(cpo):
    r = db.one("""
      SELECT ROUND(AVG(r.uptime_pct), 1) AS up, COUNT(DISTINCT r.day)::int AS days
      FROM reliability_daily r JOIN evse e ON e.evse_id = r.evse_id JOIN station s ON s.station_id = e.station_id
      WHERE s.cpo = %s AND r.day > current_date - 30""", (cpo,))
    return r if r and r["days"] else None


# --------------------------------------------------------------- template
HEAD = """<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="https://parkingnetherlands.com/{path}">
{alternates}
<meta property="og:title" content="{title}"><meta property="og:description" content="{desc}"><meta property="og:type" content="article"><meta property="og:locale" content="nl_NL"><meta property="og:image" content="https://parkingnetherlands.com/og-image.png"><meta property="og:url" content="https://parkingnetherlands.com/{path}">
<meta name="robots" content="index, follow">
<link rel="stylesheet" href="/site.css">
<link rel="icon" href="/favicon.ico" sizes="any"><link rel="icon" type="image/svg+xml" href="/favicon.svg"><link rel="apple-touch-icon" href="/apple-touch-icon.png">
<script type="application/ld+json">{ld}</script>
</head>
<body>
"""

FOOT = """
</body>
</html>
"""


def ld_breadcrumb(items):
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": n, "item": "https://parkingnetherlands.com" + u}
        for i, (n, u) in enumerate(items)]}


def ld_faq(qa):
    return {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in qa]}


def faq_html(qa):
    return "".join(
        f'<div class="fqi"><button class="fqq" type="button" onclick="this.parentElement.classList.toggle(\'open\')">{esc(q)}<span class="fqt">+</span></button>'
        f'<div class="fqa"><p>{esc(a)}</p></div></div>' for q, a in qa)


def city_page(c, nat, all_cities) -> tuple[str, str]:
    city = c["city"]; sl = slug(city); path = f"laadpaal-{sl}"
    ops = city_operators(city); hubs = city_hubs(city); park = city_parking(city)
    priced = [o for o in ops if o["med_kwh"] is not None]
    cheapest = min(priced, key=lambda o: o["med_kwh"]) if priced else None
    dearest = max(priced, key=lambda o: o["med_kwh"]) if priced else None
    med = sorted(float(o["med_kwh"]) for o in priced)
    med_city = med[len(med) // 2] if med else None
    fault_vs = ("hoger dan" if c["fault_pct"] and nat["fault_pct"] and float(c["fault_pct"]) > float(nat["fault_pct"])
                else "lager dan of gelijk aan")
    en = EN_SLUG.get(sl, sl)
    title = f"Laadpalen {city}: prijzen per kWh, storingen en snelladers ({TODAY.year})"
    desc = (f"{c['stations']:,} openbare laadlocaties en {c['points']:,} laadpunten in {city}. "
            f"Mediaan {eur(med_city) if med_city else 'n.b.'} per kWh, {pct(c['fault_pct'] or 0)} buiten gebruik, "
            f"{c['fast']} snellaadlocaties. Live kaart met prijs van laden én parkeren.").replace(",", ".") if False else (
            f"{c['stations']} openbare laadlocaties en {c['points']} laadpunten in {city}. "
            f"Mediaan {eur(med_city) if med_city else 'n.b.'} per kWh, {pct(c['fault_pct'] or 0)} buiten gebruik, "
            f"{c['fast']} snellaadlocaties. Live kaart met de prijs van laden én parkeren.")
    qa = [
        (f"Hoeveel laadpalen zijn er in {city}?",
         f"Het nationale laadpuntenregister telt {c['stations']} openbare laadlocaties met samen {c['points']} laadpunten in {city} (stand {DATE_NL})."),
        (f"Wat kost opladen in {city}?",
         (f"De mediaanprijs van de gepubliceerde tarieven in {city} is {eur(med_city)} per kWh. "
          f"Het goedkoopste grote netwerk is {cheapest['cpo']} ({eur(cheapest['med_kwh'])}/kWh), het duurste {dearest['cpo']} ({eur(dearest['med_kwh'])}/kWh)."
          if cheapest and dearest else "Niet elke exploitant publiceert een tarief; landelijk ligt de mediaan rond " + eur(nat["med_kwh"]) + " per kWh.")),
        (f"Hoeveel laadpalen in {city} zijn kapot?",
         f"Op dit moment melden exploitanten {pct(c['fault_pct'] or 0)} van de laadpunten in {city} als buiten gebruik; landelijk is dat {pct(nat['fault_pct'])}."),
        (f"Waar kan ik snelladen in {city}?",
         (f"Er zijn {c['fast']} locaties met 50 kW of meer, waarvan {c['hubs']} met 150 kW of meer. De snelste staan in de tabel op deze pagina."
          if c["fast"] else f"Het register kent geen openbare snellader (50 kW+) binnen {city}; de dichtstbijzijnde vind je op de kaart.")),
        (f"Moet ik betalen voor parkeren bij een laadpaal in {city}?",
         (f"{park['in_zone']} laadlocaties in {city} staan in een betaald-parkeren-zone; het mediane uurtarief daar is {eur(park['med_hour'])}. "
          "Buiten die zones betaal je alleen de stroom. De kaart rekent beide bij elkaar op voor jouw tijden."
          if park and park["in_zone"] and park["med_hour"] else
          f"Voor de meeste laadlocaties in {city} kent het Nationaal Parkeer Register geen betaald-parkeren-zone; daar betaal je alleen de stroom. Controleer altijd het bord ter plekke.")),
    ]
    ld = json.dumps([ld_breadcrumb([("Home", "/"), ("Laadpalen", "/ev-charging"), (city, "/" + path)]), ld_faq(qa)], ensure_ascii=False)
    rows_ops = "".join(
        f"<tr><td><strong>{esc(o['cpo'])}</strong></td><td class=\"num\">{o['stations']}</td><td class=\"num\">{o['points']}</td>"
        f"<td class=\"num\">{eur(o['med_kwh']) if o['med_kwh'] is not None else NP}</td>"
        f"<td class=\"num\">{pct(o['fault_pct'] or 0)}</td></tr>" for o in ops)
    rows_hubs = "".join(
        f"<tr><td><strong>{esc(h['name'])}</strong><br><span style=\"color:var(--mut);font-size:13px\">{esc(h['address'] or '')}</span></td>"
        f"<td>{esc(h['cpo'] or '')}</td><td class=\"num\">{h['kw']} kW</td><td class=\"num\">{h['points']}</td></tr>" for h in hubs)
    others = [x for x in all_cities if x["city"] != city][:12]
    links = "".join(f'<a href="/laadpaal-{slug(x["city"])}">{esc(x["city"])}</a>' for x in others)
    en_link = f'<a href="/{en}">Parkeren in {esc(city)} (Engels)</a>' if sl in EN_CITY_PAGES else ""
    body = f"""
<div class="bc-bar"><div class="ct bc-in"><a href="/">Home</a> → <a href="/ev-charging">Laadpalen</a> → <strong>{esc(city)}</strong></div></div>
<div class="ph"><div class="ct">
<span class="updated">Bijgewerkt {DATE_NL} · nationaal laadpuntenregister</span>
<h1>Laadpalen in <em>{esc(city)}</em>: prijzen, storingen en snelladers</h1>
<p class="sub">{c['stations']} openbare laadlocaties, {c['points']} laadpunten. Wat laden kost per exploitant, welk deel buiten gebruik is, waar je snel kunt laden en wat parkeren erbij doet.</p>
<div class="qs">
<div class="qb"><div class="qbl">Laadpunten</div><div class="qbv">{c['points']}</div></div>
<div class="qb"><div class="qbl">Mediaan per kWh</div><div class="qbv">{eur(med_city) if med_city else '–'}</div></div>
<div class="qb"><div class="qbl">Buiten gebruik</div><div class="qbv {'h' if c['fault_pct'] and float(c['fault_pct']) > 3 else 'c'}">{pct(c['fault_pct'] or 0)}</div></div>
<div class="qb"><div class="qbl">Snelladers 50 kW+</div><div class="qbv">{c['fast']}</div></div>
</div>
<p style="margin-top:18px"><a class="btn btn-primary" href="/ev-charging?q={esc(city)}&amp;lat={float(c['lat']):.4f}&amp;lng={float(c['lon']):.4f}&amp;zoom=13">Open de kaart van {esc(city)}</a></p>
</div></div>

<section class="sec"><div class="ct">
<div class="sl">Prijs per kWh</div>
<h2 class="st">Wat laden kost in {esc(city)}, per exploitant</h2>
<p class="ss">Mediaan van de tarieven die exploitanten in het register publiceren voor hun laadpunten in {esc(city)}. Landelijk ligt de mediaan op {eur(nat['med_kwh'])} per kWh. Laadpassen rekenen soms een opslag.</p>
<div class="tw"><table><thead><tr><th>Exploitant</th><th>Locaties</th><th>Laadpunten</th><th>Prijs per kWh</th><th>Buiten gebruik</th></tr></thead><tbody>{rows_ops}</tbody></table></div>
{f'<div class="abox" style="margin-top:18px"><p><strong>Goedkoopste laadpaal in {esc(city)}:</strong> {esc(cheapest["cpo"])} rekent {eur(cheapest["med_kwh"])} per kWh, {esc(dearest["cpo"])} {eur(dearest["med_kwh"])}. Bij 20 kWh scheelt dat {eur((float(dearest["med_kwh"]) - float(cheapest["med_kwh"])) * 20)} per laadbeurt.</p></div>' if cheapest and dearest and cheapest is not dearest else ''}
</div></section>

<section class="sec sec-alt"><div class="ct">
<div class="sl">Storingen</div>
<h2 class="st">Hoeveel laadpalen in {esc(city)} werken niet</h2>
<p class="ss">Exploitanten melden {pct(c['fault_pct'] or 0)} van de laadpunten in {esc(city)} als buiten gebruik ({fault_vs} het landelijke {pct(nat['fault_pct'])}). De tabel hierboven laat zien welke exploitant het verschil maakt. Wij leggen deze meldingen elk half uur vast; na dertig dagen verschijnt hier de betrouwbaarheid over de tijd.</p>
</div></section>

<section class="sec"><div class="ct">
<div class="sl">Snelladen</div>
<h2 class="st">Snelladers in {esc(city)}</h2>
{f'<p class="ss">{c["fast"]} locaties bieden 50 kW of meer; {c["hubs"]} halen 150 kW of meer. De snelste:</p><div class="tw"><table><thead><tr><th>Locatie</th><th>Exploitant</th><th>Vermogen</th><th>Punten</th></tr></thead><tbody>{rows_hubs}</tbody></table></div>' if hubs else f'<p class="ss">Het register kent geen openbare snellader van 50 kW of meer binnen {esc(city)}. Op de kaart zie je de dichtstbijzijnde snellaadhub langs de snelweg.</p>'}
</div></section>

<section class="sec sec-alt"><div class="ct">
<div class="sl">Laden + parkeren</div>
<h2 class="st">Wat een laadstop in {esc(city)} echt kost</h2>
<p class="ss">{(f"{park['in_zone']} laadlocaties in {esc(city)} staan in een betaald-parkeren-zone van het Nationaal Parkeer Register, met een mediaan uurtarief van {eur(park['med_hour'])} op een doordeweekse middag. Twee uur laden kost daar dus al gauw {eur(float(park['med_hour']) * 2)} aan parkeren bovenop de stroom." if park and park['in_zone'] and park['med_hour'] else f"Voor de meeste laadlocaties in {esc(city)} kent het Nationaal Parkeer Register geen betaald-parkeren-zone.")} De kaart rekent laden en parkeren bij elkaar op voor jouw aankomst- en vertrektijd.</p>
<p><a class="btn btn-dark" href="/ev-charging?q={esc(city)}&amp;lat={float(c['lat']):.4f}&amp;lng={float(c['lon']):.4f}&amp;zoom=13">Bereken jouw laadstop in {esc(city)}</a></p>
</div></section>

<section class="sec"><div class="ct">
<div class="sl">Veelgestelde vragen</div>
<h2 class="st">Laadpalen {esc(city)}</h2>
<div style="max-width:760px">{faq_html(qa)}</div>
</div></section>

<section class="sec sec-alt"><div class="ct">
<div class="sl">Andere steden</div>
<h2 class="st">Laadpalen per stad</h2>
<div class="ev-citylinks" style="margin-top:0">{links}{en_link}</div>
<p style="margin-top:22px;font-size:13px;color:var(--mut)">Laadpuntdata: NDW / DOT-NL, stand {DATE_NL}. Parkeertarieven uit het Nationaal Parkeer Register. Prijzen zijn de door exploitanten gepubliceerde ad-hoctarieven; je laadpas kan een opslag rekenen.</p>
</div></section>
"""
    html = HEAD.format(title=esc(title), desc=esc(desc), path=path, ld=ld, alternates="") + body + FOOT
    return path, html


def operator_page(o, nat) -> tuple[str, str]:
    cpo = o["cpo"]; sl = slug(cpo); path = f"{sl}-storing"
    cities_ = operator_cities(cpo); up = operator_uptime(cpo); days = history_days()
    vs = float(o["fault_pct"] or 0) / float(nat["fault_pct"]) if nat["fault_pct"] else None
    title = f"{cpo} storing: {pct(o['fault_pct'] or 0)} van de laadpunten buiten gebruik ({DATE_NL})"
    desc = (f"{o['down']} van de {o['points']} openbare {cpo}-laadpunten staan nu als buiten gebruik gemeld, "
            f"{pct(o['fault_pct'] or 0)} tegen {pct(nat['fault_pct'])} landelijk. Per stad, elk half uur bijgewerkt.")
    qa = [
        (f"Is er een storing bij {cpo}?",
         f"Op {DATE_NL} melden de exploitantsystemen {o['down']} van de {o['points']} openbare {cpo}-laadpunten in Nederland als buiten gebruik ({pct(o['fault_pct'] or 0)}). Een landelijke storing herken je aan een plotselinge sprong in dat getal; deze pagina wordt elk half uur ververst."),
        (f"Hoe betrouwbaar is {cpo} vergeleken met andere exploitanten?",
         f"Landelijk staat {pct(nat['fault_pct'])} van alle laadpunten als buiten gebruik. {cpo} zit daar {'boven' if vs and vs > 1.1 else 'onder' if vs and vs < 0.9 else 'rond'}."
         + (f" Over de afgelopen {up['days']} dagen was de gemeten beschikbaarheid {pct(up['up'])}." if up else " Zodra dertig dagen metingen binnen zijn, verschijnt hier de beschikbaarheid over de tijd.")),
        (f"Wat doe ik als een {cpo}-laadpaal niet werkt?",
         "Meld het bij de storingsdienst op de paal (telefoonnummer op de sticker) en kies op onze kaart een werkend punt in de buurt; de kaart toont de laatst gemelde status per laadpunt."),
    ]
    ld = json.dumps([ld_breadcrumb([("Home", "/"), ("Laadpalen", "/ev-charging"), (f"{cpo} storing", "/" + path)]), ld_faq(qa)], ensure_ascii=False)
    rows = "".join(
        f"<tr><td><a href=\"/laadpaal-{slug(x['city'])}\" style=\"color:var(--blue);font-weight:600;text-decoration:none\">{esc(x['city'])}</a></td>"
        f"<td class=\"num\">{x['points']}</td><td class=\"num\">{x['down']}</td><td class=\"num\">{pct(100.0 * x['down'] / x['points'])}</td></tr>" for x in cities_)
    body = f"""
<div class="bc-bar"><div class="ct bc-in"><a href="/">Home</a> → <a href="/ev-charging">Laadpalen</a> → <strong>{esc(cpo)} storing</strong></div></div>
<div class="ph"><div class="ct">
<span class="updated">Stand {DATE_NL} · elk half uur bijgewerkt</span>
<h1>{esc(cpo)} <em>storing</em>: {pct(o['fault_pct'] or 0)} van de laadpunten buiten gebruik</h1>
<p class="sub">{o['down']} van de {o['points']} openbare {esc(cpo)}-laadpunten in Nederland staan nu als buiten gebruik gemeld door de exploitant zelf. Landelijk gemiddelde: {pct(nat['fault_pct'])}.</p>
<div class="qs">
<div class="qb"><div class="qbl">Laadpunten</div><div class="qbv">{o['points']}</div></div>
<div class="qb"><div class="qbl">Buiten gebruik</div><div class="qbv {'h' if vs and vs > 1.1 else 'c'}">{o['down']}</div></div>
<div class="qb"><div class="qbl">Aandeel</div><div class="qbv {'h' if vs and vs > 1.1 else 'c'}">{pct(o['fault_pct'] or 0)}</div></div>
<div class="qb"><div class="qbl">Status onbekend</div><div class="qbv">{pct(o['unknown_pct'] or 0)}</div></div>
</div>
</div></div>

<section class="sec"><div class="ct">
<div class="sl">Per stad</div>
<h2 class="st">Waar {esc(cpo)}-laadpunten nu buiten gebruik zijn</h2>
<p class="ss">Steden met minstens veertig {esc(cpo)}-laadpunten, gesorteerd op het aantal storingsmeldingen.</p>
<div class="tw"><table><thead><tr><th>Stad</th><th>Laadpunten</th><th>Buiten gebruik</th><th>Aandeel</th></tr></thead><tbody>{rows}</tbody></table></div>
</div></section>

<section class="sec sec-alt"><div class="ct">
<div class="sl">Over de tijd</div>
<h2 class="st">Betrouwbaarheid van {esc(cpo)}</h2>
<p class="ss">{(f"Over de afgelopen {up['days']} dagen was de gemeten beschikbaarheid van {esc(cpo)}-laadpunten {pct(up['up'])}: het aandeel van de tijd dat een punt werkte of in gebruik was." if up else f"Wij leggen sinds {DATE_NL} elk half uur de status van elk laadpunt vast. Zodra dertig dagen binnen zijn, staat hier de beschikbaarheid van {esc(cpo)} over de tijd, per stad, iets wat geen enkele exploitant zelf publiceert.")}</p>
<p><a class="btn btn-dark" href="/ev-charging">Bekijk werkende laadpunten op de kaart</a></p>
</div></section>

<section class="sec"><div class="ct">
<div class="sl">Veelgestelde vragen</div>
<h2 class="st">{esc(cpo)} storingen</h2>
<div style="max-width:760px">{faq_html(qa)}</div>
<p style="margin-top:22px;font-size:13px;color:var(--mut)">Statusmeldingen: NDW / DOT-NL, zoals door de exploitant aangeleverd. Buiten gebruik = OUTOFORDER of INOPERATIVE in het register. Deze site is onafhankelijk en niet verbonden aan {esc(cpo)}.</p>
</div></section>
"""
    html = HEAD.format(title=esc(title), desc=esc(desc), path=path, ld=ld, alternates="") + body + FOOT
    return path, html


def hub_page(nat, cs, ops) -> tuple[str, str]:
    """/laadpalen: the Dutch front door to every city and operator page."""
    path = "laadpalen"
    title = f"Laadpalen in Nederland: prijzen, storingen en snelladers per stad ({TODAY.year})"
    desc = (f"{nat['stations']} openbare laadlocaties, {nat['points']} laadpunten, mediaan {eur(nat['med_kwh'])} per kWh, "
            f"{pct(nat['fault_pct'])} buiten gebruik. Per stad en per exploitant, elk half uur bijgewerkt, met de prijs van laden én parkeren.")
    qa = [
        ("Hoeveel openbare laadpalen zijn er in Nederland?",
         f"Het nationale laadpuntenregister telt {nat['stations']} openbare laadlocaties met {nat['points']} laadpunten (stand {DATE_NL}); locaties die exploitanten als niet-openbaar markeren zijn niet meegeteld."),
        ("Wat kost laden aan een openbare laadpaal?",
         f"De mediaan van de gepubliceerde tarieven is {eur(nat['med_kwh'])} per kWh; tussen exploitanten scheelt het tot zestig procent. Per stad staat het goedkoopste en duurste netwerk op de stadspagina."),
        ("Welke exploitant heeft de meeste storingen?",
         f"Landelijk staat {pct(nat['fault_pct'])} van de laadpunten als buiten gebruik gemeld. De storingspagina's per exploitant tonen het aandeel nu en, na dertig dagen meten, de beschikbaarheid over de tijd."),
    ]
    ld = json.dumps([ld_breadcrumb([("Home", "/"), ("Laadpalen", "/" + path)]), ld_faq(qa)], ensure_ascii=False)
    rows_c = "".join(
        f"<tr><td><a href=\"/laadpaal-{slug(c['city'])}\" style=\"color:var(--blue);font-weight:700;text-decoration:none\">{esc(c['city'])}</a></td>"
        f"<td class=\"num\">{c['stations']}</td><td class=\"num\">{c['points']}</td><td class=\"num\">{pct(c['fault_pct'] or 0)}</td><td class=\"num\">{c['fast']}</td></tr>" for c in cs)
    rows_o = "".join(
        f"<tr><td><a href=\"/{slug(o['cpo'])}-storing\" style=\"color:var(--blue);font-weight:700;text-decoration:none\">{esc(o['cpo'])}</a></td>"
        f"<td class=\"num\">{o['stations']}</td><td class=\"num\">{o['points']}</td><td class=\"num\">{o['down']}</td><td class=\"num\">{pct(o['fault_pct'] or 0)}</td></tr>" for o in ops)
    body = f"""
<div class="bc-bar"><div class="ct bc-in"><a href="/">Home</a> → <strong>Laadpalen</strong></div></div>
<div class="ph"><div class="ct">
<span class="updated">Stand {DATE_NL} · elk half uur bijgewerkt</span>
<h1>Laadpalen in Nederland: <em>prijzen, storingen en snelladers</em> per stad</h1>
<p class="sub">Alle {nat['stations']} openbare laadlocaties uit het nationale register, met wat laden kost per exploitant, welk deel buiten gebruik is en wat parkeren erbij doet. Kies een stad of een exploitant.</p>
<div class="qs">
<div class="qb"><div class="qbl">Laadlocaties</div><div class="qbv">{nat['stations']}</div></div>
<div class="qb"><div class="qbl">Laadpunten</div><div class="qbv">{nat['points']}</div></div>
<div class="qb"><div class="qbl">Mediaan per kWh</div><div class="qbv">{eur(nat['med_kwh'])}</div></div>
<div class="qb"><div class="qbl">Buiten gebruik</div><div class="qbv h">{pct(nat['fault_pct'])}</div></div>
</div>
<p style="margin-top:18px"><a class="btn btn-primary" href="/ev-charging">Open de laadkaart met parkeerprijzen</a></p>
</div></div>

<section class="sec"><div class="ct">
<div class="sl">Per stad</div>
<h2 class="st">Laadpalen per stad</h2>
<p class="ss">De {len(cs)} steden met de meeste laadpunten. Elke stadspagina toont de prijs per kWh per exploitant, de storingen, de snelladers en de parkeerkosten bij de paal.</p>
<div class="tw"><table><thead><tr><th>Stad</th><th>Locaties</th><th>Laadpunten</th><th>Buiten gebruik</th><th>Snelladers 50 kW+</th></tr></thead><tbody>{rows_c}</tbody></table></div>
</div></section>

<section class="sec sec-alt"><div class="ct">
<div class="sl">Per exploitant</div>
<h2 class="st">Storingen per exploitant</h2>
<p class="ss">Wat elke exploitant zelf meldt als buiten gebruik, nu. Na dertig dagen meten komt daar de beschikbaarheid over de tijd bij.</p>
<div class="tw"><table><thead><tr><th>Exploitant</th><th>Locaties</th><th>Laadpunten</th><th>Buiten gebruik</th><th>Aandeel</th></tr></thead><tbody>{rows_o}</tbody></table></div>
</div></section>

<section class="sec"><div class="ct">
<div class="sl">Veelgestelde vragen</div>
<h2 class="st">Laadpalen in Nederland</h2>
<div style="max-width:760px">{faq_html(qa)}</div>
<p style="margin-top:22px;font-size:13px;color:var(--mut)">Laadpuntdata: NDW / DOT-NL. Parkeertarieven uit het Nationaal Parkeer Register. <a href="/ev-charging" style="color:var(--blue)">English version: EV charging map</a>.</p>
</div></section>
"""
    alts='<link rel="alternate" hreflang="nl" href="https://parkingnetherlands.com/laadpalen">\n<link rel="alternate" hreflang="en" href="https://parkingnetherlands.com/ev-charging">\n<link rel="alternate" hreflang="x-default" href="https://parkingnetherlands.com/ev-charging">'
    return path, HEAD.format(title=esc(title), desc=esc(desc), path=path, ld=ld, alternates=alts) + body + FOOT


def build() -> dict:
    root: Path = config.SITE_ROOT
    nat = national()
    cs = cities()
    written = []
    for c in cs:
        path, html = city_page(c, nat, cs)
        (root / f"{path}.html").write_text(html, "utf-8")
        written.append(path)
    ops = operators()
    for o in ops:
        path, html = operator_page(o, nat)
        (root / f"{path}.html").write_text(html, "utf-8")
        written.append(path)
    path, html = hub_page(nat, cs, ops)
    (root / f"{path}.html").write_text(html, "utf-8")
    written.append(path)
    return {"pages": len(written), "paths": written}
