#!/usr/bin/env python3
"""Dutch, German and French city pages built from data: the English page's
quick facts, P+R cards and street-zone table, the register's garages, the
charging figures, and templated prose with the city's own numbers.

  python3 scripts/i18n/build_cities.py            # nl de fr
Also adds hreflang links to the English city pages. Run apply_chrome.py after.
"""
import json, re, sys, statistics, datetime, html as H
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from i18n.strings import S, LANGS, PREFIX, city_name, city_url, garage_url, money, num, pct

ROOT = Path(__file__).resolve().parents[2]
SITE = "https://parkingnetherlands.com"
TODAY = datetime.date.today().isoformat(); YEAR = "2026"
CITY_LABEL = {"amsterdam": "Amsterdam", "rotterdam": "Rotterdam", "the-hague": "The Hague", "utrecht": "Utrecht", "eindhoven": "Eindhoven", "groningen": "Groningen",
              "maastricht": "Maastricht", "leiden": "Leiden", "haarlem": "Haarlem", "breda": "Breda", "delft": "Delft", "nijmegen": "Nijmegen", "tilburg": "Tilburg", "zwolle": "Zwolle"}
LAADPAAL = {"the-hague": "den-haag"}; EV_NAME = {"the-hague": "Den Haag"}
GARAGES = json.loads((ROOT / "scripts/garages.json").read_text("utf-8"))
CITIES_EV = {c["name"]: c for c in json.loads((ROOT / "ev-data/cities.json").read_text("utf-8"))}
ADOPTION = {r["name"]: r for r in json.loads((ROOT / "data/ev-adoption-2026.json").read_text("utf-8"))["municipalities"]}
def esc(s): return H.escape(str(s), quote=True)
def short(g): return g["name"].rsplit(" (", 1)[0]
def priced(g): return g.get("rate_hr") is not None
def is_free(g): return priced(g) and g["rate_hr"] == 0 and (g.get("rate_day") or 0) == 0
def is_anom(g): return priced(g) and not is_free(g) and (g["rate_hr"] > 15 or g["rate_hr"] == g["rate_day"] or (g["rate_3h"] or 0) > 45)

C = {
"nl": dict(title="Parkeren in {city} {year}: tarieven, garages en P+R", h1="Parkeren in {city}",
  desc="Parkeren in {city} in {year}: straattarief centrum {street}, goedkoopste garage {cheap}, P+R {pr}. Alle {n} geregistreerde garages met officiële tarieven, laadpalen en boetes.",
  q_street="Straat (centrum)", q_garage="Goedkoopste garage", q_pr="P+R (24 uur)", q_fine="Parkeerboete",
  intro="{city} heeft {n} garages en P+R-terreinen in het nationaal parkeerregister, waarvan {k} met een gepubliceerd tarief. Een betaalde garage kost hier mediaan {medh} per uur en {medd} per 24 uur; op straat in het centrum betaal je {street}. Deze pagina zet alle officiële cijfers op een rij, van het goedkoopste P+R-terrein tot de garage met laadpunten, zodat je voor vertrek weet wat een stop kost.",
  h_garages="Alle garages in {city}, gesorteerd op prijs", p_garages="Officiële dagtarieven uit het nationaal parkeerregister (stand {snap}): eerste uur, 3 uur en 24 uur. Gratis terreinen daarna, voorzieningen zonder gepubliceerd tarief onderaan. Klik op een garage voor de vergelijking met de rest van de stad, betaalde uren en alternatieven.",
  th_garage="Garage", th_1h="1 uur", th_3h="3 uur", th_24h="24 uur", th_cap="Plaatsen", th_ev="Laadpunten", free="gratis", none="geen tarief",
  h_pr="P+R: parkeren aan de rand, met het ov naar het centrum", p_pr="Voor een hele dag in het centrum is een P+R-terrein in {city} vrijwel altijd de goedkoopste keuze. Let op de voorwaarde: het lage tarief geldt meestal alleen met een ov-rit heen en terug op dezelfde dag.",
  r_rate="24-uurstarief", r_cap="Capaciteit", r_centre="Naar het centrum", r_daily="Dagtarief", r_hourly="Uurtarief",
  h_zones="Straatparkeren: zones en tarieven", p_zones="Straatparkeren in {city} werkt met zones. Het centrum is het duurst; buiten de betaalde uren is de straat gratis. Controleer altijd de zonecode op het bord naast je auto, niet die van een straat verderop.",
  th_zone="Zone", th_rate="Tarief per uur", th_hours="Betaalde uren", th_cost="Kosten 4 uur",
  h_ev="Laden in {city}", p_ev="{pts} publieke laadpunten op {locs} locaties, mediaan {kwh} per kWh vóór parkeerkosten, {down} van de locaties meldt nu een storing, {fast} snellaadlocaties van 150 kW of meer. {share} van de particuliere auto's in {city} rijdt elektrisch, met {per100} publieke laadpunten per 100 EV's. Op de <a href=\"{maplink}\">laadpalenkaart</a> zie je per paal wat laden plus parkeren kost voor jouw stop; <a href=\"/laadpaal-{lp}\">laadpaal-{city_slug}</a> geeft prijzen en storingen per exploitant.",
  h_fine="Boete in {city}: wat het kost", p_fine="Niet betalen op straat levert in {city} een naheffingsaanslag op van maximaal €82,00 kosten plus één uur parkeergeld ({street}), dus {fine_total}. Fout parkeren (stoep, parkeerverbod, blauwe zone zonder schijf) is een Mulderboete van €130 plus €9 via het CJIB; een gehandicaptenparkeerplaats €400. Scanauto's controleren elk kenteken, ook buitenlandse. Lees <a href=\"{fines}\">de volledige boetegids</a> voor betalen en bezwaar.",
  h_faq="Veelgestelde vragen over parkeren in {city}",
  faq=[("Wat kost parkeren in {city}?", "Op straat in het centrum {street} per uur. In een garage mediaan {medh} per uur en {medd} per 24 uur; de goedkoopste geregistreerde garage rekent {cheapg} voor het eerste uur. Een P+R-terrein kost {pr} per 24 uur."),
       ("Waar parkeer ik het goedkoopst in {city}?", "Voor een hele dag: een P+R-terrein ({pr} per 24 uur) en verder met het ov. Voor een kort bezoek: {cheapname}, {cheapg} voor het eerste uur. Buiten de betaalde uren is straatparkeren gratis."),
       ("Hoeveel garages heeft {city}?", "Het nationaal parkeerregister vermeldt {n} garages en P+R-terreinen in {city}, waarvan {k} met een gepubliceerd tarief en {evg} met laadpunten."),
       ("Kan ik elektrisch laden in {city}?", "{city} heeft {pts} publieke laadpunten op {locs} locaties, mediaan {kwh} per kWh. {evg} garages hebben laadpunten. De laadpalenkaart toont per paal de prijs van laden plus parkeren."),
       ("Wat is de boete voor niet betalen in {city}?", "Maximaal €82,00 aan kosten plus één uur parkeergeld, in het centrum van {city} dus {fine_total}. Bezwaar binnen zes weken bij de gemeente.")],
  langs="Deze pagina in andere talen", src="Bronnen: nationaal parkeerregister (NPR, CC0), stand {snap}; nationaal laadpuntenregister (NDW / DOT-NL); CBS aandeel elektrische auto's 1 januari {year}; gemeentelijke straattarieven. Bijgewerkt {today}.",
),
"de": dict(title="Parken in {city} {year}: Gebühren, Parkhäuser und P+R", h1="Parken in {city}",
  desc="Parken in {city} {year}: Straßentarif Zentrum {street}, günstigstes Parkhaus {cheap}, P+R {pr}. Alle {n} registrierten Parkhäuser mit offiziellen Tarifen, Ladesäulen und Knöllchen.",
  q_street="Straße (Zentrum)", q_garage="Günstigstes Parkhaus", q_pr="P+R (24 Std.)", q_fine="Knöllchen",
  intro="{city} hat {n} Parkhäuser und P+R-Plätze im nationalen Parkregister, davon {k} mit veröffentlichtem Tarif. Ein bezahltes Parkhaus kostet hier im Median {medh} pro Stunde und {medd} pro 24 Stunden; auf der Straße im Zentrum zahlen Sie {street}. Diese Seite stellt alle offiziellen Zahlen zusammen, vom günstigsten P+R-Platz bis zum Parkhaus mit Ladepunkten, damit Sie vor der Abfahrt wissen, was ein Stopp kostet.",
  h_garages="Alle Parkhäuser in {city}, nach Preis sortiert", p_garages="Offizielle Tarife aus dem nationalen Parkregister (Stand {snap}): erste Stunde, 3 Stunden und 24 Stunden. Kostenlose Plätze danach, Einrichtungen ohne veröffentlichten Tarif am Ende. Klicken Sie ein Parkhaus an für den Vergleich mit der Stadt, gebührenpflichtige Zeiten und Alternativen.",
  th_garage="Parkhaus", th_1h="1 Std.", th_3h="3 Std.", th_24h="24 Std.", th_cap="Plätze", th_ev="Ladepunkte", free="kostenlos", none="kein Tarif",
  h_pr="P+R: am Rand parken, mit Bus und Bahn ins Zentrum", p_pr="Für einen ganzen Tag im Zentrum ist ein P+R-Platz in {city} fast immer die günstigste Wahl. Beachten Sie die Bedingung: der niedrige Tarif gilt meist nur mit einer Fahrt im Nahverkehr hin und zurück am selben Tag.",
  r_rate="24-Stunden-Tarif", r_cap="Stellplätze", r_centre="Ins Zentrum", r_daily="Tagestarif", r_hourly="Stundentarif",
  h_zones="Straßenparken: Zonen und Tarife", p_zones="Straßenparken in {city} ist in Zonen geregelt. Das Zentrum ist am teuersten; außerhalb der gebührenpflichtigen Zeiten ist die Straße kostenlos. Prüfen Sie immer den Zonencode auf dem Schild neben Ihrem Auto, nicht den einer Straße weiter.",
  th_zone="Zone", th_rate="Tarif pro Stunde", th_hours="Gebührenpflichtig", th_cost="Kosten 4 Std.",
  h_ev="Laden in {city}", p_ev="{pts} öffentliche Ladepunkte an {locs} Standorten, im Median {kwh} pro kWh vor Parkgebühren, {down} der Standorte melden derzeit eine Störung, {fast} Schnellladestandorte ab 150 kW. {share} der privaten Pkw in {city} fahren elektrisch, bei {per100} öffentlichen Ladepunkten je 100 E-Autos. Die <a href=\"{maplink}\">Ladekarte</a> zeigt je Säule, was Laden plus Parken für Ihren Stopp kostet.",
  h_fine="Knöllchen in {city}: was es kostet", p_fine="Nicht bezahltes Straßenparken bringt in {city} einen Nachforderungsbescheid (naheffingsaanslag) von höchstens 82,00 € Kosten plus einer Stunde Parkgebühr ({street}), also {fine_total}. Falschparken (Gehweg, Parkverbot, blaue Zone ohne Parkscheibe) ist ein Bußgeld von 130 € plus 9 € über das CJIB; ein Behindertenparkplatz 400 €. Scan-Fahrzeuge erfassen jedes Kennzeichen, auch deutsche, und Bußgelder werden in Deutschland vollstreckt. <a href=\"{fines}\">Der vollständige Ratgeber</a> erklärt Zahlung und Einspruch.",
  h_faq="Häufige Fragen zum Parken in {city}",
  faq=[("Was kostet Parken in {city}?", "Auf der Straße im Zentrum {street} pro Stunde. Im Parkhaus im Median {medh} pro Stunde und {medd} pro 24 Stunden; das günstigste registrierte Parkhaus verlangt {cheapg} für die erste Stunde. Ein P+R-Platz kostet {pr} pro 24 Stunden."),
       ("Wo parke ich in {city} am günstigsten?", "Für einen ganzen Tag: ein P+R-Platz ({pr} pro 24 Stunden) und weiter mit dem Nahverkehr. Für einen kurzen Besuch: {cheapname}, {cheapg} für die erste Stunde. Außerhalb der gebührenpflichtigen Zeiten ist Straßenparken kostenlos."),
       ("Wie viele Parkhäuser hat {city}?", "Das nationale Parkregister führt {n} Parkhäuser und P+R-Plätze in {city}, davon {k} mit veröffentlichtem Tarif und {evg} mit Ladepunkten."),
       ("Kann ich in {city} elektrisch laden?", "{city} hat {pts} öffentliche Ladepunkte an {locs} Standorten, im Median {kwh} pro kWh. {evg} Parkhäuser haben Ladepunkte. Die Ladekarte zeigt je Säule den Preis für Laden plus Parken."),
       ("Was kostet ein Knöllchen in {city} mit deutschem Kennzeichen?", "Höchstens 82,00 € Kosten plus eine Stunde Parkgebühr, im Zentrum von {city} also {fine_total}. Für Bußgelder über 70 € übernimmt das Bundesamt für Justiz die Vollstreckung in Deutschland. Einspruch innerhalb von sechs Wochen.")],
  langs="Diese Seite in anderen Sprachen", src="Quellen: nationales Parkregister (NPR, CC0), Stand {snap}; nationales Ladesäulenregister (NDW / DOT-NL); CBS Anteil E-Autos 1. Januar {year}; kommunale Straßentarife. Aktualisiert {today}.",
),
"fr": dict(title="Se garer à {city} {year} : tarifs, parkings et P+R", h1="Se garer à {city}",
  desc="Stationnement à {city} en {year} : tarif de rue au centre {street}, parking le moins cher {cheap}, P+R {pr}. Les {n} parkings enregistrés avec tarifs officiels, bornes de recharge et amendes.",
  q_street="Rue (centre)", q_garage="Parking le moins cher", q_pr="P+R (24 h)", q_fine="Amende",
  intro="{city} compte {n} parkings et parcs relais dans le registre national du stationnement, dont {k} avec un tarif publié. Un parking payant coûte ici en médiane {medh} par heure et {medd} par 24 heures ; dans la rue au centre, vous payez {street}. Cette page rassemble tous les chiffres officiels, du parc relais le moins cher au parking équipé de bornes, pour savoir avant de partir ce que coûte un arrêt.",
  h_garages="Tous les parkings de {city}, classés par prix", p_garages="Tarifs officiels du registre national du stationnement (état au {snap}) : première heure, 3 heures et 24 heures. Sites gratuits ensuite, sans tarif publié en fin de liste. Cliquez sur un parking pour la comparaison avec la ville, les heures payantes et les alternatives.",
  th_garage="Parking", th_1h="1 h", th_3h="3 h", th_24h="24 h", th_cap="Places", th_ev="Bornes", free="gratuit", none="pas de tarif",
  h_pr="P+R : se garer en périphérie, rejoindre le centre en transports", p_pr="Pour une journée entière au centre, un parc relais à {city} est presque toujours le choix le moins cher. Attention à la condition : le tarif réduit ne s'applique généralement qu'avec un aller-retour en transports le même jour.",
  r_rate="Tarif 24 heures", r_cap="Capacité", r_centre="Vers le centre", r_daily="Tarif journalier", r_hourly="Tarif horaire",
  h_zones="Stationnement en rue : zones et tarifs", p_zones="Le stationnement en rue à {city} fonctionne par zones. Le centre est le plus cher ; en dehors des heures payantes, la rue est gratuite. Vérifiez toujours le code de zone sur le panneau à côté de votre voiture, pas celui d'une rue plus loin.",
  th_zone="Zone", th_rate="Tarif horaire", th_hours="Heures payantes", th_cost="Coût 4 h",
  h_ev="Recharger à {city}", p_ev="{pts} points de charge publics sur {locs} sites, médiane {kwh} par kWh hors stationnement, {down} des sites signalent une panne en ce moment, {fast} sites de recharge rapide à 150 kW ou plus. {share} des voitures particulières de {city} sont électriques, pour {per100} points de charge publics par 100 VE. La <a href=\"{maplink}\">carte des bornes</a> indique pour chaque borne le coût de la recharge plus le stationnement pour votre arrêt.",
  h_fine="Amende à {city} : ce que ça coûte", p_fine="Ne pas payer dans la rue vaut à {city} un avis de redressement (naheffingsaanslag) de 82,00 € de frais au maximum plus une heure de stationnement ({street}), soit {fine_total}. Le stationnement interdit (trottoir, interdiction, zone bleue sans disque) est une amende de 130 € plus 9 € via le CJIB ; une place handicapé, 400 €. Les voitures-scanner lisent chaque plaque, y compris françaises ; Amsterdam pose désormais un sabot aux voitures françaises après deux avis impayés. <a href=\"{fines}\">Le guide complet</a> explique le paiement et le recours.",
  h_faq="Questions fréquentes sur le stationnement à {city}",
  faq=[("Combien coûte le stationnement à {city} ?", "Dans la rue au centre, {street} par heure. En parking, médiane {medh} par heure et {medd} par 24 heures ; le parking enregistré le moins cher demande {cheapg} la première heure. Un parc relais coûte {pr} par 24 heures."),
       ("Où se garer au moins cher à {city} ?", "Pour une journée entière : un parc relais ({pr} par 24 heures) puis les transports. Pour une courte visite : {cheapname}, {cheapg} la première heure. En dehors des heures payantes, la rue est gratuite."),
       ("Combien de parkings compte {city} ?", "Le registre national du stationnement recense {n} parkings et parcs relais à {city}, dont {k} avec un tarif publié et {evg} équipés de bornes de recharge."),
       ("Peut-on recharger une voiture électrique à {city} ?", "{city} compte {pts} points de charge publics sur {locs} sites, médiane {kwh} par kWh. {evg} parkings ont des bornes. La carte des bornes indique le prix de la recharge plus le stationnement."),
       ("Quelle amende pour une voiture française à {city} ?", "Au maximum 82,00 € de frais plus une heure de stationnement, soit {fine_total} au centre de {city}. Les amendes CJIB de plus de 70 € sont transmises aux autorités françaises ; les avis municipaux impayés mènent au sabot lors du prochain passage. Recours dans les six semaines.")],
  langs="Cette page dans d'autres langues", src="Sources : registre national du stationnement (NPR, CC0), état au {snap} ; registre national des bornes (NDW / DOT-NL) ; CBS part de voitures électriques au 1er janvier {year} ; tarifs municipaux de rue. Mis à jour le {today}.",
),
}
ROW_LABELS = {"24-hour rate": "r_rate", "Capacity": "r_cap", "To Centre": "r_centre", "Daily rate": "r_daily", "Hourly rate": "r_hourly", "Rate": "r_hourly"}

def parse_en(slug):
    t = (ROOT / f"{slug}.html").read_text("utf-8")
    qb = re.findall(r'<div class="qb"><div class="qbl">([^<]*)</div><div class="qbv[^"]*">([^<]*)', t)
    prs = []
    for m in re.finditer(r'<div class="pk[^"]*">(.*?)</div>\s*(?=<div class="pk|</div>\s*</div></section>)', t, re.S):
        b = m.group(1)
        n = re.search(r'<div class="pk-n">([^<]*)', b); ty = re.search(r'<div class="pk-t">([^<]*)', b)
        rows = re.findall(r'<div class="pk-r"><span class="l">([^<]*)</span><span class="v[^"]*">([^<]*)', b)
        if n: prs.append((H.unescape(n.group(1)), H.unescape(ty.group(1)) if ty else "", [(H.unescape(a), H.unescape(v)) for a, v in rows]))
    zones = []
    zsec = re.search(r'parking zones &amp; rates</h2>.*?<table>(.*?)</table>', t, re.S)
    if zsec:
        head = [re.sub(r"<[^>]+>", "", h).strip().lower() for h in re.findall(r"<th>(.*?)</th>", zsec.group(1), re.S)]
        for tr in re.findall(r"<tr>(.*?)</tr>", zsec.group(1), re.S):
            cells = [H.unescape(re.sub(r"<[^>]+>", "", c).strip()) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            if len(cells) == len(head) and cells: zones.append(dict(zip(head, cells)))
    return qb, prs, zones

def ev_numbers(slug):
    lp = ROOT / f"laadpaal-{LAADPAAL.get(slug, slug)}.html"
    if not lp.exists(): return None
    d = re.search(r'<meta name="description" content="([^"]*)"', lp.read_text("utf-8")).group(1)
    m = re.search(r"(\d+) openbare laadlocaties en (\d+) laadpunten.*?Mediaan €(\d+,\d+) per kWh, (\d+,\d+)% buiten gebruik, (\d+) snellaadlocaties", d)
    if not m: return None
    return dict(locs=int(m.group(1)), pts=int(m.group(2)), kwh=float(m.group(3).replace(",", ".")), down=float(m.group(4).replace(",", ".")), fast=int(m.group(5)))

def build(lang, slug):
    T = C[lang]; G = S[lang]; en = CITY_LABEL[slug]; cname = city_name(lang, en); M = lambda v: money(lang, v)
    qb, prs, zones = parse_en(slug)
    qv = {k.strip(): v.strip() for k, v in qb}
    street_txt = qv.get("Street (Centre)", ""); street = float(re.search(r"[\d.]+", street_txt).group(0)) if re.search(r"[\d.]+", street_txt) else None
    pr_txt = qv.get("P+R (24hr)", ""); cheap_txt = qv.get("Cheapest Garage", "")
    def loc_money_txt(txt):
        m = re.search(r"€([\d.]+)", txt)
        if not m: return txt
        v = float(m.group(1)); rest = txt[m.end():]
        rest = rest.replace("/hr", {"nl": "/uur", "de": "/Std.", "fr": "/h"}[lang])
        return M(v) + rest
    gs = [g for g in GARAGES if g["city"] == slug]; paid = [g for g in gs if priced(g) and not is_free(g) and not is_anom(g)]
    medh = statistics.median(g["rate_hr"] for g in paid) if paid else None; medd = statistics.median(g["rate_day"] for g in paid) if paid else None
    cheapest = min([g for g in paid if g["rate_hr"] > 0], key=lambda g: (g["rate_3h"], g["rate_day"])) if paid else None
    evg = sum(1 for g in gs if (g.get("ev_points") or 0) > 0)
    ev = ev_numbers(slug); a = ADOPTION.get(EV_NAME.get(slug, en), {}); cc = CITIES_EV.get(EV_NAME.get(slug, en)) or CITIES_EV.get(en)
    fines_page = {"nl": "/nl/parkeerboete", "de": "/de/parkstrafe-niederlande", "fr": "/fr/amende-stationnement-pays-bas"}[lang]
    if not (ROOT / (fines_page.strip("/") + ".html")).exists(): fines_page = "/parking-fines"
    ctx = dict(city=cname, year=YEAR, n=len(gs), k=sum(1 for g in gs if priced(g)), medh=M(medh) if medh else "n/a", medd=M(medd) if medd else "n/a",
               street=loc_money_txt(street_txt) if street_txt else "n/a", cheap=loc_money_txt(cheap_txt) if cheap_txt else "n/a", pr=loc_money_txt(pr_txt) if pr_txt else "n/a",
               cheapg=M(cheapest["rate_hr"]) if cheapest else "n/a", cheapname=short(cheapest) if cheapest else "n/a", evg=evg, snap=SNAP, today=TODAY,
               fine_total=M(82 + street) if street else "n/a", fines=fines_page, lp=LAADPAAL.get(slug, slug), city_slug=LAADPAAL.get(slug, slug),
               pts=num(lang, ev["pts"]) if ev else "n/a", locs=num(lang, ev["locs"]) if ev else "n/a", kwh=M(ev["kwh"]) if ev else "n/a", down=pct(lang, ev["down"], 1) if ev else "n/a", fast=ev["fast"] if ev else "n/a",
               share=pct(lang, a["share"], 1) if a.get("share") else "n/a", per100=(f"{a['points_per_100_ev']:.1f}".replace(".", ",") if lang != "en" else f"{a['points_per_100_ev']:.1f}") if a.get("points_per_100_ev") else "n/a",
               maplink=f"/ev-charging?lat={cc['lat']}&lng={cc['lon']}&zoom=13" if cc else "/ev-charging")
    F = lambda key: T[key].format(**ctx)
    def gkey(g): return (0, g["rate_hr"], g["rate_day"]) if priced(g) and not is_free(g) else (1, 0, 0) if is_free(g) else (2, 0, 0)
    PR_BADGE = ' <em style="font-style:normal;font-size:10.5px;font-weight:700;color:var(--sig)">P+R</em>'
    def grow(g):
        name_cell = '<td><a href="' + garage_url(lang, g["slug"]) + '" style="font-weight:600;color:var(--ink);text-decoration:none">' + esc(short(g)) + '</a>' + (PR_BADGE if g.get("is_pr") else "") + '</td>'
        if priced(g) and not is_free(g):
            price_cells = '<td class="price">' + M(g["rate_hr"]) + '</td><td class="price">' + M(g["rate_3h"]) + '</td><td class="price">' + M(g["rate_day"]) + '</td>'
        else:
            price_cells = '<td colspan="3" style="color:var(--mut)">' + (T["free"] if is_free(g) else T["none"]) + '</td>'
        tail = '<td class="num">' + (num(lang, g["capacity"]) if g.get("capacity") else "-") + '</td><td class="num">' + str(g.get("ev_points") or "-") + '</td>'
        return "<tr>" + name_cell + price_cells + tail + "</tr>"
    grows = "".join(grow(g) for g in sorted(gs, key=gkey))
    pr_html = ""
    if prs:
        cards = "".join('<div class="card card-pad" style="padding:18px 20px"><div style="font-weight:800;font-size:16px;margin-bottom:2px">' + esc(n) + '</div><div style="font-size:12.5px;color:var(--mut);margin-bottom:10px">' + esc(ty.replace("Park + Ride", "P+R")) + '</div>'
                        + "".join(f'<div style="display:flex;justify-content:space-between;font-size:13.5px;padding:5px 0;border-top:1px solid var(--line-soft)"><span style="color:var(--mut)">{esc(T.get(ROW_LABELS.get(l, ""), l))}</span><b class="num">{esc(loc_money_txt(v))}</b></div>' for l, v in rows) + '</div>' for n, ty, rows in prs)
        pr_html = f'<h2>{F("h_pr")}</h2><p>{F("p_pr")}</p><div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin:14px 0">{cards}</div>'
    zone_html = ""
    if zones:
        def pick(z, words):
            for k, v in z.items():
                if any(w in k for w in words): return v
            return ""
        zrows = "".join(f'<tr><td><strong>{esc(pick(z, ["zone"]))}</strong></td><td class="price">{esc(loc_money_txt(pick(z, ["rate"])))}</td><td>{esc(pick(z, ["hour", "paid"]))}</td><td class="price">{esc(loc_money_txt(pick(z, ["cost"])))}</td></tr>' for z in zones if pick(z, ["zone"]))
        zone_html = f'<h2>{F("h_zones")}</h2><p>{F("p_zones")}</p><div class="tbl-wrap"><table><thead><tr><th>{T["th_zone"]}</th><th>{T["th_rate"]}</th><th>{T["th_hours"]}</th><th>{T["th_cost"]}</th></tr></thead><tbody>{zrows}</tbody></table></div>'
    ev_html = f'<h2>{F("h_ev")}</h2><p>{F("p_ev")}</p>' if ev else ""
    faqs = [(q.format(**ctx), re.sub(r"<[^>]+>", "", an.format(**ctx))) for q, an in T["faq"]]
    faq_html = "".join(f'<details class="faq-item"><summary>{esc(q)}</summary><p>{esc(an)}</p></details>' for q, an in faqs)
    url = SITE + city_url(lang, slug)
    alts = "".join(f'<link rel="alternate" hreflang="{l}" href="{SITE}{city_url(l, slug)}">' for l in LANGS) + f'<link rel="alternate" hreflang="x-default" href="{SITE}{city_url("en", slug)}">'
    other = " · ".join(f'<a href="{city_url(l, slug)}" hreflang="{l}" lang="{l}">{S[l]["lang_name"]}</a>' for l in LANGS if l != lang)
    ld = [{"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [{"@type": "ListItem", "position": 1, "name": G["home"], "item": SITE + "/"}, {"@type": "ListItem", "position": 2, "name": F("h1"), "item": url}]},
          {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": an}} for q, an in faqs]}]
    ld_json = json.dumps(ld, ensure_ascii=False).replace("</", "<\\/")
    tiles = "".join(f'<div class="ea-stat"><b>{esc(v)}</b><span>{esc(l)}</span></div>' for l, v in ((T["q_street"], ctx["street"]), (T["q_garage"], ctx["cheap"]), (T["q_pr"], ctx["pr"]), (T["q_fine"], ctx["fine_total"])))
    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2889604222343187" crossorigin="anonymous"></script>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(F("title"))}</title>
<meta name="description" content="{esc(F("desc")[:158])}">
<link rel="canonical" href="{url}">
{alts}
<link rel="stylesheet" href="/site.css">
<link rel="icon" href="/favicon.ico?v=2" sizes="any"><link rel="icon" type="image/svg+xml" href="/favicon.svg?v=2">
<meta property="og:type" content="article"><meta property="og:url" content="{url}"><meta property="og:title" content="{esc(F("title"))}"><meta property="og:description" content="{esc(F("desc")[:158])}"><meta property="og:image" content="{SITE}/og-image.png">
<meta name="robots" content="index, follow"><meta name="author" content="Analytics Ascent">
<script type="application/ld+json">{ld_json}</script>
<style>
.cw{{max-width:1080px;margin:0 auto;padding:0 24px}}
.ch{{padding:44px 0 10px}}.ch h1{{font-size:clamp(1.9rem,4vw,2.9rem);font-weight:800;letter-spacing:-.03em;line-height:1.1;color:var(--ink);margin:10px 0 12px}}
.ch .lead{{font-size:16.5px;color:var(--mut);max-width:820px;line-height:1.65}}
.ea-stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:24px 0}}
.ea-stat{{background:#fff;border:1px solid var(--line);border-radius:var(--r-lg);padding:16px 18px;box-shadow:var(--sh)}}
.ea-stat b{{display:block;font-size:24px;font-weight:800;letter-spacing:-.03em;color:var(--ink);font-variant-numeric:tabular-nums}}.ea-stat span{{font-size:12.5px;color:var(--mut)}}
.cw h2{{font-size:1.4rem;font-weight:800;letter-spacing:-.02em;color:var(--ink);margin:40px 0 12px}}.cw p{{line-height:1.65}}
.faq-item{{border:1px solid var(--line);border-radius:var(--r);background:#fff;padding:12px 16px;margin:8px 0}}.faq-item summary{{font-weight:700;cursor:pointer}}.faq-item p{{margin:10px 0 0;color:var(--mut)}}
.clangs{{font-size:13.5px;color:var(--mut);margin:26px 0 0}}.clangs a{{color:var(--sig);font-weight:600;text-decoration:none}}
</style>
</head>
<body>
<div class="cw">
<header class="ch">
  <div class="crumb" style="font-size:13px;color:var(--mut)"><a href="/" style="color:var(--mut);text-decoration:none">{G["home"]}</a> / {esc(F("h1"))}</div>
  <h1>{esc(F("h1"))}</h1>
  <p class="lead">{F("intro")}</p>
</header>
<div class="ea-stats">{tiles}</div>
<h2>{F("h_garages")}</h2><p>{F("p_garages")}</p>
<div class="tbl-wrap"><table><thead><tr><th>{T["th_garage"]}</th><th>{T["th_1h"]}</th><th>{T["th_3h"]}</th><th>{T["th_24h"]}</th><th>{T["th_cap"]}</th><th>{T["th_ev"]}</th></tr></thead><tbody>{grows}</tbody></table></div>
{pr_html}
{zone_html}
{ev_html}
<h2>{F("h_fine")}</h2><p>{F("p_fine")}</p>
<h2>{F("h_faq")}</h2>
{faq_html}
<p class="clangs">{T["langs"]}: {other}</p>
<p style="font-size:12.5px;color:var(--mut);margin:16px 0 60px">{F("src")}</p>
</div>
</body>
</html>"""

def patch_en_hreflang(slug):
    p = ROOT / f"{slug}.html"; t = p.read_text("utf-8")
    alts = "".join(f'<link rel="alternate" hreflang="{l}" href="{SITE}{city_url(l, slug)}">' for l in LANGS) + f'<link rel="alternate" hreflang="x-default" href="{SITE}{city_url("en", slug)}">'
    block = f"<!-- hreflang:start -->{alts}<!-- hreflang:end -->"
    if "<!-- hreflang:start -->" in t: t = re.sub(r"<!-- hreflang:start -->.*?<!-- hreflang:end -->", block, t, flags=re.S)
    else: t = re.sub(r'(<link rel="canonical"[^>]*>)', lambda m: m.group(1) + "\n" + block, t, count=1)
    p.write_text(t, "utf-8")

import subprocess
def git_date(path):
    out = subprocess.run(["git", "log", "-1", "--format=%cs", "--", str(path)], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", str(path)], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return TODAY if dirty or not out else out
SNAP = git_date(ROOT / "scripts/garages.json")

if __name__ == "__main__":
    langs = [a for a in sys.argv[1:] if a in ("nl", "de", "fr")] or ["nl", "de", "fr"]
    for lang in langs:
        (ROOT / lang).mkdir(exist_ok=True)
        for slug in CITY_LABEL:
            (ROOT / (city_url(lang, slug).strip("/") + ".html")).write_text(build(lang, slug), "utf-8")
        print(lang, "14 city pages")
    for slug in CITY_LABEL: patch_en_hreflang(slug)
    print("hreflang added to 14 English city pages")
