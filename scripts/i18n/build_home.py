#!/usr/bin/env python3
"""Localized home pages: /nl/, /de/, /fr/. Each is the language's landing page,
built from the same live data as the English homepage, and the target the
language menu falls back to when a page has no exact translation.

  python3 scripts/i18n/build_home.py
Also writes the hreflang block into the English index.html. Run apply_chrome.py after.
"""
import json, glob, re, sys, statistics, datetime, html as H
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from i18n.strings import S, LANGS, PREFIX, city_name, city_url, money, num, pct

ROOT = Path(__file__).resolve().parents[2]
SITE = "https://parkingnetherlands.com"
TODAY = datetime.date.today().isoformat(); YEAR = "2026"
CITY_LABEL = {"amsterdam": "Amsterdam", "rotterdam": "Rotterdam", "the-hague": "The Hague", "utrecht": "Utrecht", "eindhoven": "Eindhoven", "groningen": "Groningen",
              "maastricht": "Maastricht", "leiden": "Leiden", "haarlem": "Haarlem", "breda": "Breda", "delft": "Delft", "nijmegen": "Nijmegen", "tilburg": "Tilburg", "zwolle": "Zwolle"}
FINES = {"en": "/parking-fines", "nl": "/nl/parkeerboete", "de": "/de/parkstrafe-niederlande", "fr": "/fr/amende-stationnement-pays-bas"}
def esc(s): return H.escape(str(s), quote=True)

def fit_desc(d, limit=158):
    """A snippet is cut by Google, not by us, and never mid-word."""
    d = d.strip()
    if len(d) <= limit: return d
    cut = d[:limit]
    stop = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    if stop > 80: return cut[:stop + 1]
    return cut[:cut.rfind(" ")].rstrip(" ,;:") + "."

# live figures from our own data
pts = stations = down = fast = 0; ppk = []
for f in glob.glob(str(ROOT / "ev-data/cells/*.json")):
    for r in json.load(open(f)):
        stations += 1; pts += r[6] or 0
        if (r[10] or 0) > 0: down += 1
        if r[8]: ppk.append(r[8])
        if (r[5] or 0) >= 150: fast += 1
MED = statistics.median(ppk); DOWN = down / stations * 100
G = json.loads((ROOT / "scripts/garages.json").read_text("utf-8"))
PAID = [g for g in G if g.get("rate_hr") not in (None, 0) and not (g["rate_hr"] > 15 or g["rate_hr"] == g["rate_day"])]
MED_HR = statistics.median(g["rate_hr"] for g in PAID); MED_DAY = statistics.median(g["rate_day"] for g in PAID)
EV = json.loads((ROOT / "data/ev-adoption-2026.json").read_text("utf-8"))["national"]

# Numbers formatted once per language. Never post-process a whole sentence to
# fix a thousand separator: that is what turned every comma into a full stop.
def figures(lang):
    return dict(
        pts=num(lang, pts), stations=num(lang, stations), garages=str(len(G)),
        med=money(lang, MED), med_hr=money(lang, MED_HR), med_day=money(lang, MED_DAY),
        down=pct(lang, DOWN, 1), fast=num(lang, fast), evs=num(lang, EV["electric"]),
        growth=pct(lang, EV["growth_pct"], 1), share=pct(lang, EV["electric_share_private_cbs"], 1),
        per100=(f"{EV['points_per_100_ev']:.1f}" if lang == "en" else f"{EV['points_per_100_ev']:.1f}".replace(".", ",")),
    )

N = {lang: figures(lang) for lang in ("nl", "de", "fr")}
_nl, _de, _fr = N["nl"], N["de"], N["fr"]

T = {
"nl": dict(
  title=f"Parkeren en laden in Nederland {YEAR}: wat kost jouw stop?",
  h1="Wat kost jouw stop echt?",
  rot=["Laden.", "Parkeren.", "Allebei, samen geprijsd.", "Laden."],
  desc="Vergelijk parkeertarieven, garages en P+R in Nederlandse steden. Vind laadpalen en bereken wat laden en parkeren samen kosten.",
  lead=f"Elke publieke laadpaal en elke geregistreerde garage in Nederland, geprijsd voor precies jouw stop: de stroom, het parkeren onder de paal, en het goedkoopste alternatief op loopafstand. Gebouwd voor de {_nl['evs']} elektrische auto's op Nederlands kenteken, en voor iedereen die gewoon een plek zoekt.",
  tag=f"Live · {_nl['stations']} laadlocaties · {len(G)} garages · open data",
  seg_ev="Laden + parkeren", seg_park="Alleen parkeren",
  ph_ev="Waar ga je heen? Adres, locatie of plaats", ph_park="Waar wil je parkeren? Adres, locatie of plaats",
  cta="Prijs mijn stop", near="Goedkoopste stop in de buurt",
  stats=[(_nl['pts'], "publieke laadpunten, live status uit het nationale register"),
         (_nl['med'], "mediaan per kWh, met het parkeren eronder meegerekend"),
         (str(len(G)), "geregistreerde garages en P+R met officiële tarieven"),
         ("€0", "wat deze site jou kost")],
  h_why="Waarvoor mensen hier komen",
  cards=[("Laden onderweg", "Prijs een laadbeurt en het parkeren eronder", f"{_nl['stations']} publieke laadlocaties met live status, de prijs per kWh en het parkeertarief voor de tijd dat je er staat. Filter op slagboom, pinbetaling en snelladen.", "/ev-charging", "Open de laadpalenkaart"),
         ("Laden per stad", "Laadpalen, prijzen en storingen per stad", "Per Nederlandse stad: hoeveel publieke palen, wat de mediaan per kWh kost, welke exploitanten nu storingen melden en waar de snellaadhubs staan. Elk half uur bijgewerkt.", "/laadpalen", "Kies een stad"),
         ("Waar laden schaars is", "Elektrische auto's en laadpunten per gemeente", f"{_nl['share']} van de particuliere auto's is elektrisch, van 28% tot 8% per gemeente. Zie waar het publieke net ruim is en waar je beter opgeladen aankomt.", "/elektrische-autos-per-gemeente", "Bekijk de kaart"),
         ("Alleen parkeren", "Garages en P+R, geprijsd voor jouw parkeerduur", f"{len(G)} geregistreerde garages en P+R-terreinen in 14 steden met officiële dagtarieven, plus elke straatzone. Voor een hele dag bespaart een P+R meestal €30 of meer tegenover een garage in het centrum.", "/search", "Vergelijk parkeerprijzen")],
  h_cities="Kies je stad",
  p_cities="Elke stad rekent anders. Per stad: alle geregistreerde garages op prijs gesorteerd, de P+R-terreinen, de straatzones, de laadpalen en wat een boete kost.",
  h_numbers="Laden in Nederland, in cijfers",
  numbers=[f"Het nationale laadpuntenregister telt {_nl['stations']} publieke laadlocaties met {_nl['pts']} laadpunten, en deze site leest elk half uur hun status. Op dit moment meldt {_nl['down']} van de locaties minstens één punt buiten gebruik. De mediaanprijs is {_nl['med']} per kWh, maar het verschil tussen exploitanten is groot: dezelfde 20 kWh kost de helft of het dubbele, afhankelijk van wiens paal je kiest. {_nl['fast']} locaties leveren 150 kW of meer.",
           f"Het wagenpark groeit sneller dan het net: {_nl['evs']} auto's met elektrische aandrijving op 1 januari {YEAR}, {_nl['growth']} meer dan een jaar eerder, tegenover ongeveer {_nl['per100']} publieke laadpunten per 100 particuliere EV's.",
           f"Wat een stop kost is zelden alleen de stroom. De meeste palen staan op een betaald parkeervak, dus twee uur laden in een centrum kost bovenop de kWh een parkeertarief dat het laden kan overtreffen. Daarom telt elke prijs op deze site beide bij elkaar op voor precies de tijd die je invult. Een betaalde garage kost mediaan {_nl['med_hr']} per uur en {_nl['med_day']} per 24 uur."],
  h_fines="Een boete gehad?",
  p_fines="Er bestaat niet één parkeerboete: een naheffingsaanslag van de gemeente is iets anders dan een Mulderboete van het CJIB, met andere bedragen, termijnen en bezwaarwegen. De gids legt uit welke brief je hebt, wat die kost per stad en per dag vertraging, en hoe je bezwaar maakt met een voorbeeldbrief.",
  fines_cta="Naar de boetegids", langs="Deze pagina in andere talen",
  src=f"Bronnen: nationaal parkeerregister (NPR, CC0), nationaal laadpuntenregister (NDW / DOT-NL), CBS. Bijgewerkt {TODAY}."),

"de": dict(
  title=f"Parken und Laden in den Niederlanden {YEAR}: was kostet Ihr Stopp?",
  h1="Was kostet Ihr Stopp wirklich?",
  rot=["Laden.", "Parken.", "Beides, zusammen gerechnet.", "Laden."],
  desc="Parkgebühren, Parkhäuser und P+R in niederländischen Städten vergleichen. Ladesäulen finden und berechnen, was Laden und Parken zusammen kosten.",
  lead=f"Jede öffentliche Ladesäule und jedes registrierte Parkhaus in den Niederlanden, mit dem Preis für genau Ihren Stopp: der Strom, das Parken unter der Säule und die günstigste Alternative in Gehweite. Gebaut für die {_de['evs']} Elektroautos mit niederländischem Kennzeichen, und für alle anderen, die einfach einen Platz brauchen.",
  tag=f"Live · {_de['stations']} Ladestandorte · {len(G)} Parkhäuser · offene Daten",
  seg_ev="Laden + Parken", seg_park="Nur Parken",
  ph_ev="Wohin fahren Sie? Adresse, Ort oder Stadt", ph_park="Wo möchten Sie parken? Adresse, Ort oder Stadt",
  cta="Stopp berechnen", near="Günstigster Stopp in der Nähe",
  stats=[(_de['pts'], "öffentliche Ladepunkte, Live-Status aus dem nationalen Register"),
         (_de['med'], "Median pro kWh, mit dem Parken darunter gerechnet"),
         (str(len(G)), "registrierte Parkhäuser und P+R mit offiziellen Tarifen"),
         ("0 €", "was Sie diese Seite kostet")],
  h_why="Weshalb Menschen hierherkommen",
  cards=[("Laden unterwegs", "Ladevorgang und Parken darunter berechnen", f"{_de['stations']} öffentliche Ladestandorte mit Live-Status, dem Preis pro kWh und der Parkgebühr für die Zeit, die Sie dort stehen. Filter für Schranke, Kartenzahlung und Schnellladen.", "/ev-charging", "Ladekarte öffnen"),
         ("Laden nach Stadt", "Ladesäulen, Preise und Störungen je Stadt", "Für jede niederländische Stadt: wie viele öffentliche Säulen, was die kWh im Median kostet, welche Betreiber gerade Störungen melden und wo die Schnellladehubs stehen. Halbstündlich aktualisiert.", "/laadpalen", "Stadt wählen"),
         ("Wo Laden knapp ist", "E-Autos und Ladepunkte je Gemeinde", f"{_de['share']} der privaten Pkw fahren elektrisch, je nach Gemeinde zwischen 28% und 8%. Sehen Sie, wo das öffentliche Netz großzügig ist und wo Sie besser geladen ankommen.", "/ev-adoption", "Karte ansehen"),
         ("Nur Parken", "Parkhäuser und P+R, für Ihre Parkdauer berechnet", f"{len(G)} registrierte Parkhäuser und P+R-Plätze in 14 Städten mit offiziellen Tarifen, dazu jede Straßenzone. Für einen ganzen Tag spart ein P+R meist 30 € oder mehr gegenüber einem Parkhaus im Zentrum.", "/search", "Parkpreise vergleichen")],
  h_cities="Ihre Stadt wählen",
  p_cities="Jede Stadt rechnet anders. Je Stadt: alle registrierten Parkhäuser nach Preis, die P+R-Plätze, die Straßenzonen, die Ladesäulen und was ein Knöllchen kostet.",
  h_numbers="Laden in den Niederlanden, in Zahlen",
  numbers=[f"Das nationale Ladesäulenregister führt {_de['stations']} öffentliche Ladestandorte mit {_de['pts']} Ladepunkten, und diese Seite liest halbstündlich ihren Status. Derzeit meldet {_de['down']} der Standorte mindestens einen Punkt außer Betrieb. Der Medianpreis liegt bei {_de['med']} pro kWh, doch die Spanne zwischen Betreibern ist groß: dieselben 20 kWh kosten die Hälfte oder das Doppelte, je nachdem, wessen Säule Sie wählen. {_de['fast']} Standorte liefern 150 kW oder mehr.",
           f"Die Flotte wächst schneller als das Netz: {_de['evs']} Autos mit Elektroantrieb am 1. Januar {YEAR}, {_de['growth']} mehr als ein Jahr zuvor, bei rund {_de['per100']} öffentlichen Ladepunkten je 100 privaten E-Autos.",
           f"Was ein Stopp kostet, ist selten nur der Strom. Die meisten Säulen stehen auf einem gebührenpflichtigen Parkplatz, also kommt zu zwei Stunden Laden im Zentrum eine Parkgebühr, die den Strom übersteigen kann. Deshalb zählt jeder Preis auf dieser Seite beides zusammen, für genau die Zeit, die Sie eingeben. Ein bezahltes Parkhaus kostet im Median {_de['med_hr']} pro Stunde und {_de['med_day']} pro 24 Stunden."],
  h_fines="Ein Knöllchen bekommen?",
  p_fines="Es gibt nicht ein niederländisches Knöllchen: der kommunale Nachforderungsbescheid ist etwas anderes als ein CJIB-Bußgeld, mit anderen Beträgen, Fristen und Einspruchswegen. Der Ratgeber erklärt, welcher Brief bei Ihnen liegt, was er je Stadt und Tag Verzug kostet, ob er ein deutsches Kennzeichen erreicht und wie Sie mit einer Vorlage Einspruch einlegen.",
  fines_cta="Zum Knöllchen-Ratgeber", langs="Diese Seite in anderen Sprachen",
  src=f"Quellen: nationales Parkregister (NPR, CC0), nationales Ladesäulenregister (NDW / DOT-NL), CBS. Aktualisiert {TODAY}."),

"fr": dict(
  title=f"Stationnement et recharge aux Pays-Bas {YEAR} : quel prix ?",
  h1="Combien coûte vraiment votre arrêt ?",
  rot=["Recharge.", "Stationnement.", "Les deux, prix total.", "Recharge."],
  desc="Comparez les tarifs de stationnement, parkings et P+R des villes néerlandaises. Trouvez les bornes et calculez le coût total de votre arrêt.",
  lead=f"Chaque borne publique et chaque parking enregistré aux Pays-Bas, au prix exact de votre arrêt : l'électricité, le stationnement sous la borne et l'alternative la moins chère à pied. Conçu pour les {_fr['evs']} voitures électriques immatriculées aux Pays-Bas, et pour tous ceux qui cherchent simplement une place.",
  tag=f"En direct · {_fr['stations']} sites de recharge · {len(G)} parkings · données ouvertes",
  seg_ev="Recharge + stationnement", seg_park="Stationnement seul",
  ph_ev="Où allez-vous\u00a0? Adresse, lieu ou ville", ph_park="Où voulez-vous vous garer\u00a0? Adresse, lieu ou ville",
  cta="Calculer mon arrêt", near="Arrêt le moins cher à proximité",
  stats=[(_fr['pts'], "points de charge publics, état en direct du registre national"),
         (_fr['med'], "médiane par kWh, stationnement compris"),
         (str(len(G)), "parkings et P+R enregistrés aux tarifs officiels"),
         ("0 €", "ce que ce site vous coûte")],
  h_why="Pourquoi les gens viennent ici",
  cards=[("Recharge en route", "Calculer une recharge et le stationnement dessous", f"{_fr['stations']} sites de recharge publics avec état en direct, le prix par kWh et le tarif de stationnement pour la durée de l'arrêt. Filtres barrière, paiement par carte et recharge rapide.", "/ev-charging", "Ouvrir la carte des bornes"),
         ("Recharge par ville", "Bornes, prix et pannes par ville", "Pour chaque ville néerlandaise : combien de bornes publiques, la médiane par kWh, quels opérateurs signalent des pannes en ce moment et où sont les sites de recharge rapide. Mis à jour toutes les demi-heures.", "/laadpalen", "Choisir une ville"),
         ("Où la recharge manque", "Voitures électriques et bornes par commune", f"{_fr['share']} des voitures particulières sont électriques, de 28% à 8% selon la commune. Voyez où le réseau public est généreux et où mieux vaut arriver chargé.", "/ev-adoption", "Voir la carte"),
         ("Stationnement seul", "Parkings et P+R, au prix de votre durée", f"{len(G)} parkings et parcs relais enregistrés dans 14 villes aux tarifs officiels, plus chaque zone de rue. Pour une journée entière, un parc relais économise généralement 30 € ou plus par rapport à un parking du centre.", "/search", "Comparer les prix")],
  h_cities="Choisissez votre ville",
  p_cities="Chaque ville applique ses propres tarifs. Par ville : tous les parkings enregistrés classés par prix, les parcs relais, les zones de rue, les bornes et le coût d'une amende.",
  h_numbers="La recharge aux Pays-Bas, en chiffres",
  numbers=[f"Le registre national des bornes recense {_fr['stations']} sites de recharge publics et {_fr['pts']} points de charge, et ce site lit leur état toutes les demi-heures. Actuellement {_fr['down']} des sites signalent au moins un point hors service. Le prix médian est de {_fr['med']} par kWh, mais l'écart entre opérateurs est large : les mêmes 20 kWh coûtent la moitié ou le double selon la borne choisie. {_fr['fast']} sites délivrent 150 kW ou plus.",
           f"Le parc grandit plus vite que le réseau : {_fr['evs']} voitures à motorisation électrique au 1er janvier {YEAR}, {_fr['growth']} de plus qu'un an plus tôt, pour environ {_fr['per100']} points de charge publics pour 100 véhicules électriques particuliers.",
           f"Le coût d'un arrêt, ce n'est presque jamais que l'électricité. La plupart des bornes sont sur une place payante : deux heures de recharge au centre ajoutent un tarif de stationnement qui peut dépasser la recharge. C'est pourquoi chaque prix de ce site additionne les deux, pour la durée exacte que vous saisissez. Un parking payant coûte en médiane {_fr['med_hr']} par heure et {_fr['med_day']} par 24 heures."],
  h_fines="Vous avez reçu une amende ?",
  p_fines="Il n'existe pas une amende de stationnement néerlandaise : l'avis communal n'est pas l'amende du CJIB, et les montants, délais et recours diffèrent. Le guide explique quelle lettre vous avez, ce qu'elle coûte selon la ville et le retard, si elle atteint une plaque française, et comment contester avec un modèle.",
  fines_cta="Voir le guide des amendes", langs="Cette page dans d'autres langues",
  src=f"Sources : registre national du stationnement (NPR, CC0), registre national des bornes (NDW / DOT-NL), CBS. Mis à jour le {TODAY}."),
}

def page(lang):
    t = T[lang]; url = SITE + "/" + lang + "/"
    alts = "".join(f'<link rel="alternate" hreflang="{l}" href="{SITE}{"/" if l == "en" else "/" + l + "/"}">' for l in LANGS) + f'<link rel="alternate" hreflang="x-default" href="{SITE}/">'
    other = " · ".join(f'<a href="{"/" if l == "en" else "/" + l + "/"}" hreflang="{l}" lang="{l}">{S[l]["lang_name"]}</a>' for l in LANGS if l != lang)
    stats = "".join(f'<div class="hstat"><div class="n">{esc(a)}</div><div class="l">{esc(b)}</div></div>' for a, b in t["stats"])
    cards = "".join(f'<a class="card intent is-ev" href="{u}"><span class="k">{esc(k)}</span><h3>{esc(h)}</h3><p>{esc(p)}</p><span class="go">{esc(c)}</span></a>' for k, h, p, u, c in t["cards"])
    cities = "".join(f'<a href="{city_url(lang, s)}">{esc(city_name(lang, n))}</a>' for s, n in CITY_LABEL.items())
    nums = "".join(f"<p>{esc(p)}</p>" for p in t["numbers"])
    ld = [{"@context": "https://schema.org", "@type": "WebSite", "name": "Charge + Park", "url": url, "inLanguage": lang,
           "publisher": {"@type": "Organization", "name": "Parking Netherlands", "url": SITE}},
          {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [{"@type": "ListItem", "position": 1, "name": S[lang]["home"], "item": url}]}]
    ld_json = json.dumps(ld, ensure_ascii=False).replace("</", "<\\/")
    rot_json = json.dumps(t["rot"], ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2889604222343187" crossorigin="anonymous"></script>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="icon" href="/favicon.ico?v=2" sizes="any"><link rel="icon" type="image/svg+xml" href="/favicon.svg?v=2"><link rel="apple-touch-icon" href="/apple-touch-icon.png?v=2">
<title>{esc(t["title"])}</title>
<meta name="description" content="{esc(fit_desc(t["desc"]))}">
<link rel="canonical" href="{url}">
{alts}
<link rel="stylesheet" href="/site.css">
<meta property="og:type" content="website"><meta property="og:url" content="{url}"><meta property="og:title" content="{esc(t["title"])}"><meta property="og:description" content="{esc(fit_desc(t["desc"]))}"><meta property="og:image" content="{SITE}/og-image.png">
<meta name="robots" content="index, follow"><meta name="author" content="Analytics Ascent">
<script type="application/ld+json">{ld_json}</script>
<style>
.lh{{background:var(--paper-2);border-bottom:1px solid var(--line)}}
.lh-in{{max-width:var(--max);margin:0 auto;padding:54px 24px 40px}}
.lh .tag{{display:inline-flex;align-items:center;gap:8px;font-family:var(--f-mono);font-size:11px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--mut);border:1px solid var(--line);background:#fff;padding:7px 14px;border-radius:100px;margin-bottom:22px}}
.lh .tag i{{width:7px;height:7px;border-radius:50%;background:var(--ok);display:inline-block}}
.lh h1{{font-size:clamp(2.1rem,4.6vw,3.3rem);font-weight:800;letter-spacing:-.035em;line-height:1.07;color:var(--ink);margin:0 0 14px;max-width:820px}}
.lh .sub{{font-size:17px;color:var(--mut);line-height:1.6;max-width:760px;margin:0 0 22px}}
.hero-seg{{display:inline-flex;background:#fff;border:1px solid var(--line);border-radius:100px;padding:3px;margin:0 0 12px;box-shadow:var(--sh)}}
.hero-seg button{{font:inherit;font-size:13px;font-weight:700;color:var(--mut);background:transparent;border:0;border-radius:100px;padding:7px 14px;cursor:pointer}}
.hero-seg button[aria-pressed=true]{{background:var(--sig);color:#fff}}
.lh-search{{display:flex;gap:8px;max-width:620px;background:#fff;border:1px solid var(--line);border-radius:100px;padding:6px 6px 6px 18px;box-shadow:var(--sh)}}
.lh-search input{{flex:1;border:0;background:none;font:inherit;font-size:15px;color:var(--ink);outline:none;min-width:0}}
.lh-near{{display:inline-block;margin-top:12px;font-size:13.5px;font-weight:600;color:var(--sig);background:none;border:1px solid var(--line);border-radius:100px;padding:8px 16px;cursor:pointer}}
.hero-stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:0;margin-top:34px;border-top:1px solid var(--line)}}
.hstat{{padding:18px 20px 0;border-right:1px solid var(--line)}}.hstat:last-child{{border-right:0}}
.hstat .n{{font-size:26px;font-weight:800;letter-spacing:-.03em;color:var(--ink);font-variant-numeric:tabular-nums}}
.hstat .l{{font-size:12.5px;color:var(--mut);line-height:1.5;margin-top:4px}}
.lw{{max-width:var(--max);margin:0 auto;padding:0 24px}}
.lw h2{{font-size:1.5rem;font-weight:800;letter-spacing:-.025em;color:var(--ink);margin:52px 0 14px}}
.lw p{{line-height:1.7;font-size:15.5px}}
.intent-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}}
.intent{{display:flex;flex-direction:column;gap:8px;padding:22px;text-decoration:none;color:var(--ink)}}
.intent .k{{font-family:var(--f-mono);font-size:10.5px;font-weight:600;text-transform:uppercase;letter-spacing:.12em;color:var(--ok)}}
.intent h3{{font-size:17px;font-weight:800;letter-spacing:-.02em;margin:0;line-height:1.25}}
.intent p{{font-size:13.5px;color:var(--mut);margin:0;line-height:1.55;flex:1}}
.intent .go{{font-size:13px;font-weight:700;color:var(--ok)}}
.citylinks{{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 0}}
.citylinks a{{font-size:14px;font-weight:600;color:var(--ink);text-decoration:none;background:#fff;border:1px solid var(--line);border-radius:100px;padding:8px 16px}}
.citylinks a:hover{{border-color:var(--sig);color:var(--sig)}}
.finebox{{background:#fff;border:1px solid var(--line);border-radius:var(--r-lg);padding:24px;box-shadow:var(--sh);margin-top:14px}}
.glangs{{font-size:13.5px;color:var(--mut);margin:34px 0 0}}.glangs a{{color:var(--sig);font-weight:600;text-decoration:none}}
@media(max-width:900px){{.intent-grid{{grid-template-columns:1fr 1fr}}.hstat{{border-right:0;border-bottom:1px solid var(--line);padding-bottom:16px}}}}
@media(max-width:560px){{.intent-grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<header class="lh"><div class="lh-in">
  <div class="tag"><i></i> {esc(t["tag"])}</div>
  <h1>{esc(t["h1"])} <span class="sig rotator" id="heroRot" aria-live="off">{esc(t["rot"][0])}</span></h1>
  <p class="sub">{esc(t["lead"])}</p>
  <div class="hero-seg" role="group"><button type="button" data-m="chargers" aria-pressed="true">{esc(t["seg_ev"])}</button><button type="button" data-m="parking" aria-pressed="false">{esc(t["seg_park"])}</button></div>
  <form class="lh-search" id="heroForm" data-m="chargers" onsubmit="event.preventDefault();var v=document.getElementById('heroQ').value.trim();var m=this.dataset.m;if(v)location.href=(m==='parking'?'/search?q=':'/ev-charging?q=')+encodeURIComponent(v);">
    <input type="text" id="heroQ" placeholder="{esc(t["ph_ev"])}" autocomplete="off">
    <button type="submit" class="btn btn-primary">{esc(t["cta"])}</button>
  </form>
  <button type="button" class="lh-near" onclick="var b=this;b.disabled=true;navigator.geolocation?navigator.geolocation.getCurrentPosition(function(p){{location.href='/ev-charging?lat='+p.coords.latitude.toFixed(5)+'&lng='+p.coords.longitude.toFixed(5)+'&q=Near+me'}},function(){{location.href='/ev-charging'}},{{timeout:8000}}):location.href='/ev-charging'">{esc(t["near"])}</button>
  <div class="hero-stats">{stats}</div>
</div></header>
<div class="lw">
  <h2>{esc(t["h_why"])}</h2>
  <div class="intent-grid">{cards}</div>
  <h2>{esc(t["h_cities"])}</h2>
  <p>{esc(t["p_cities"])}</p>
  <div class="citylinks">{cities}</div>
  <h2>{esc(t["h_numbers"])}</h2>
  {nums}
  <h2>{esc(t["h_fines"])}</h2>
  <div class="finebox"><p style="margin-top:0">{esc(t["p_fines"])}</p><a class="btn btn-primary btn-sm" href="{FINES[lang]}">{esc(t["fines_cta"])}</a></div>
  <p class="glangs">{esc(t["langs"])}: {other}</p>
  <p style="font-size:12.5px;color:var(--mut);margin:14px 0 60px">{esc(t["src"])}</p>
</div>
<script>(function(){{
var el=document.getElementById('heroRot'),words={rot_json},i=0;
if(el&&!(window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches)){{
  setInterval(function(){{el.classList.add('is-out');setTimeout(function(){{i=(i+1)%words.length;el.textContent=words[i];el.classList.remove('is-out');el.classList.add('is-in');setTimeout(function(){{el.classList.remove('is-in')}},400)}},320)}},2600);
}}
var f=document.getElementById('heroForm');var PH={{chargers:{json.dumps(t["ph_ev"])},parking:{json.dumps(t["ph_park"])}}};
Array.prototype.forEach.call(document.querySelectorAll('.hero-seg button'),function(b){{b.onclick=function(){{f.dataset.m=b.dataset.m;Array.prototype.forEach.call(document.querySelectorAll('.hero-seg button'),function(x){{x.setAttribute('aria-pressed',x===b?'true':'false')}});document.getElementById('heroQ').placeholder=PH[b.dataset.m];}}}});}})();</script>
</body>
</html>"""

if __name__ == "__main__":
    for lang in ("nl", "de", "fr"):
        (ROOT / lang).mkdir(exist_ok=True)
        (ROOT / lang / "index.html").write_text(page(lang), "utf-8")
        print(f"/{lang}/ home page")
    p = ROOT / "index.html"; t = p.read_text("utf-8")
    alts = "".join(f'<link rel="alternate" hreflang="{l}" href="{SITE}{"/" if l == "en" else "/" + l + "/"}">' for l in LANGS) + f'<link rel="alternate" hreflang="x-default" href="{SITE}/">'
    block = f"<!-- hreflang:start -->{alts}<!-- hreflang:end -->"
    if "<!-- hreflang:start -->" in t: t = re.sub(r"<!-- hreflang:start -->.*?<!-- hreflang:end -->", block, t, flags=re.S)
    else: t = re.sub(r'(<link rel="canonical"[^>]*>)', lambda m: m.group(1) + "\n" + block, t, count=1)
    p.write_text(t, "utf-8"); print("hreflang added to the English homepage")
