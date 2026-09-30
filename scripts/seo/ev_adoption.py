#!/usr/bin/env python3
"""
Builds the EV adoption pages: /ev-adoption (EN) and /elektrische-autos-per-gemeente (NL),
plus /ev-data/gemeenten-ev.json (choropleth GeoJSON) and /data/ev-adoption-2026.{csv,json}.

Sources (all open, keyless):
  CBS maatwerk 2026/16  share of electric cars per municipality, 1 Jan 2026 (national vehicle register)
  CBS 85237NED          national car fleet by fuel per 1 January
  CBS 70072ned          population and private cars per municipality
  PDOK CBS gebiedsindelingen 2026  municipality polygons
  ev-data/cells/*.json  this site's charge point register extract (NDW / DOT-NL)

Usage: python3 scripts/seo/ev_adoption.py [--cache DIR]
"""
import json, csv, glob, math, os, re, sys, datetime, urllib.request, collections
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
SITE = "https://parkingnetherlands.com"
TODAY = datetime.date.today().isoformat()
CACHE = Path(sys.argv[sys.argv.index("--cache") + 1]) if "--cache" in sys.argv else Path(os.environ.get("EV_CACHE", "/tmp/ev-adoption-cache"))
CACHE.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 parkingnetherlands.com research", "Accept": "application/json"}

def fetch(url, name, binary=False):
    p = CACHE / name
    if p.exists(): return p.read_bytes() if binary else p.read_text("utf-8")
    req = urllib.request.Request(url, headers=UA)
    data = urllib.request.urlopen(req, timeout=180).read()
    p.write_bytes(data)
    return data if binary else data.decode("utf-8")

# ----------------------------------------------------------------- inputs
def cbs_share():
    import openpyxl, io
    raw = fetch("https://www.cbs.nl/-/media/_excel/2026/16/personenauto_aandeel_elektrisch.xlsx", "cbs_ev.xlsx", binary=True)
    ws = openpyxl.load_workbook(io.BytesIO(raw), data_only=True)["Tabel 1"]
    out, total = {}, None
    for r in ws.iter_rows(min_row=4, values_only=True):
        r = [c for c in r if c is not None]
        if len(r) >= 2 and isinstance(r[1], (int, float)):
            if str(r[0]).strip().lower() == "totaal": total = r[1]
            else: out[str(r[0]).strip()] = r[1]
    return total, out

def national_fleet():
    rows = json.loads(fetch("https://opendata.cbs.nl/ODataApi/odata/85237NED/TypedDataSet?$format=json&$filter=Bouwjaar%20eq%20%27T001378%27", "fleet.json"))["value"]
    return [{"year": int(r["Perioden"][:4]), "cars": r["Totaal_14"], "electric": r["Elektriciteit_18"], "petrol": r["Benzine_15"],
             "diesel": r["Diesel_16"], "company": r["OpNaamBedrijf_22"], "private": r["ParticulierenTotaal_23"]} for r in rows]

def kerncijfers():
    out = {}
    for p in ("2026JJ00", "2025JJ00"):
        url = ("https://opendata.cbs.nl/ODataApi/odata/70072ned/TypedDataSet?$format=json&$select=RegioS,Perioden,TotaleBevolking_1,PersonenautoS_171,PersonenautoSParticulieren_173"
               "&$filter=startswith(RegioS,%27GM%27)%20and%20Perioden%20eq%20%27" + p + "%27")
        for r in json.loads(fetch(url, f"kern_{p}.json"))["value"]:
            d = out.setdefault(r["RegioS"].strip(), {})
            for f, n in (("TotaleBevolking_1", "pop"), ("PersonenautoS_171", "cars"), ("PersonenautoSParticulieren_173", "private_cars")):
                if r.get(f) is not None and n not in d: d[n] = r[f]
    return out

def municipalities():
    return json.loads(fetch("https://service.pdok.nl/cbs/gebiedsindelingen/2026/wfs/v1_0?request=GetFeature&service=WFS&version=2.0.0&typeName=gemeente_gegeneraliseerd&outputFormat=json&srsName=EPSG:4326", "gem_2026.json"))["features"]

def chargers_by_municipality(features):
    from shapely.geometry import shape, Point
    from shapely.strtree import STRtree
    polys = [shape(f["geometry"]) for f in features]; codes = [f["properties"]["statcode"] for f in features]
    tree = STRtree(polys)
    agg = collections.defaultdict(lambda: {"stations": 0, "points": 0, "fast": 0, "down": 0})
    for f in glob.glob(str(ROOT / "ev-data/cells/*.json")):
        for r in json.load(open(f)):
            idx = tree.query(Point(r[4], r[3]), predicate="within")
            if len(idx) == 0: continue
            a = agg[codes[idx[0]]]
            a["stations"] += 1; a["points"] += r[6] or 0; a["fast"] += 1 if (r[5] or 0) >= 150 else 0; a["down"] += r[10] or 0
    return agg

DISPLAY = {"'s-Gravenhage": "Den Haag", "Laren (NH.)": "Laren", "Bergen (NH.)": "Bergen (Noord-Holland)", "Bergen (L.)": "Bergen (Limburg)",
           "Hengelo (O.)": "Hengelo", "Middelburg (Z.)": "Middelburg", "Rijswijk (ZH.)": "Rijswijk", "Stein (L.)": "Stein", "Beek (L.)": "Beek",
           "Groningen (gemeente)": "Groningen", "Utrecht (gemeente)": "Utrecht", "Súdwest-Fryslân": "Súdwest-Fryslân"}
def norm(s): return re.sub(r"\s+", " ", s.lower().replace("\u2019", "'").replace("\u02bc", "'").strip())

# ----------------------------------------------------------------- build
def build():
    total_share, share = cbs_share()
    fleet = national_fleet(); kern = kerncijfers(); feats = municipalities(); chg = chargers_by_municipality(feats)
    share_n = {norm(k): v for k, v in share.items()}
    # CBS writes "Utrecht (gemeente)" where the boundary file writes "Utrecht"
    for k, v in share.items():
        if k.endswith("(gemeente)"): share_n.setdefault(norm(k[: -len("(gemeente)")]), v)
    rows, unmatched = [], []
    from shapely.geometry import shape, mapping
    geo = {"type": "FeatureCollection", "features": []}
    for f in feats:
        p = f["properties"]; code, name = p["statcode"], p["statnaam"]
        s = share_n.get(norm(name))
        if s is None:
            # CBS drops the province suffix in some names
            s = share_n.get(norm(re.sub(r"\s*\(.*\)$", "", name)))
        if s is None: unmatched.append(name); continue
        k = kern.get(code, {}); c = chg.get(code, {"stations": 0, "points": 0, "fast": 0, "down": 0})
        ev_est = round(s / 100 * k["private_cars"]) if k.get("private_cars") else None
        disp = next((v for k, v in DISPLAY.items() if norm(k) == norm(name)), name)
        row = {"code": code, "name": disp, "share": round(s, 1), "pop": k.get("pop"), "private_cars": k.get("private_cars"),
               "ev_estimate": ev_est, "stations": c["stations"], "charge_points": c["points"], "fast_hubs": c["fast"],
               "points_per_100_ev": round(c["points"] / ev_est * 100, 1) if ev_est else None,
               "points_per_1000_res": round(c["points"] / k["pop"] * 1000, 1) if k.get("pop") else None}
        rows.append(row)
        g = shape(f["geometry"]).simplify(0.0015, preserve_topology=True)
        gm = mapping(g)
        def rnd(o):
            if isinstance(o, (list, tuple)): return [rnd(x) for x in o]
            if isinstance(o, float): return round(o, 4)
            return o
        gm["coordinates"] = rnd(gm["coordinates"])
        geo["features"].append({"type": "Feature", "geometry": gm, "properties": {"c": code, "n": row["name"], "s": row["share"], "e": ev_est, "p": c["points"], "r": row["points_per_100_ev"], "pop": k.get("pop")}})
    if unmatched: print("unmatched municipalities:", unmatched)
    rows.sort(key=lambda r: -r["share"])
    for i, r in enumerate(rows): r["rank_share"] = i + 1

    (ROOT / "ev-data").mkdir(exist_ok=True); (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "ev-data/gemeenten-ev.json").write_text(json.dumps(geo, ensure_ascii=False, separators=(",", ":")), "utf-8")
    cols = ["rank_share", "code", "name", "share", "pop", "private_cars", "ev_estimate", "stations", "charge_points", "fast_hubs", "points_per_100_ev", "points_per_1000_res"]
    with open(ROOT / "data/ev-adoption-2026.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); [w.writerow({c: r[c] for c in cols}) for r in rows]
    nat = fleet[-1]; prev = fleet[-2]
    national = {"year": nat["year"], "cars": nat["cars"], "electric": nat["electric"], "electric_share_all": round(nat["electric"] / nat["cars"] * 100, 1),
                "electric_share_private_cbs": round(total_share, 1), "growth_abs": nat["electric"] - prev["electric"], "growth_pct": round((nat["electric"] / prev["electric"] - 1) * 100, 1),
                "diesel": nat["diesel"], "petrol": nat["petrol"], "charge_points": sum(r["charge_points"] for r in rows), "stations": sum(r["stations"] for r in rows),
                "ev_estimate_private": sum(r["ev_estimate"] or 0 for r in rows)}
    national["points_per_100_ev"] = round(national["charge_points"] / national["ev_estimate_private"] * 100, 1)
    (ROOT / "data/ev-adoption-2026.json").write_text(json.dumps({"name": "EV adoption per municipality, Netherlands 2026", "published": TODAY, "license": "https://creativecommons.org/licenses/by/4.0/",
        "source": SITE + "/ev-adoption", "national": national, "fleet_by_year": fleet, "municipalities": rows}, ensure_ascii=False, indent=1), "utf-8")
    return rows, fleet, national, total_share

# ----------------------------------------------------------------- pages
def eur(v): return f"{v:,.0f}"
def pct(v): return f"{v:.1f}%"
def esc(s): return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

CSS = """
.ea-wrap{max-width:1080px;margin:0 auto;padding:0 24px}
.ea-hero{padding:44px 0 10px}
.ea-hero h1{font-size:clamp(1.9rem,4vw,2.9rem);font-weight:800;letter-spacing:-.03em;line-height:1.1;color:var(--ink);margin:10px 0 12px}
.ea-hero .lead{font-size:17px;color:var(--mut);max-width:780px;line-height:1.6}
.ea-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:28px 0}
.ea-stat{background:#fff;border:1px solid var(--line);border-radius:var(--r-lg);padding:16px 18px;box-shadow:var(--sh)}
.ea-stat b{display:block;font-size:26px;font-weight:800;letter-spacing:-.03em;color:var(--ink);font-variant-numeric:tabular-nums}
.ea-stat span{font-size:12.5px;color:var(--mut)}
.ea-wrap h2{font-size:1.35rem;font-weight:800;letter-spacing:-.02em;color:var(--ink);margin:40px 0 12px}
.ea-wrap p{line-height:1.65}
#eamap{height:560px;border-radius:var(--r-lg);border:1px solid var(--line);box-shadow:var(--sh);background:#EEF2F7}
.ea-ctl{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:14px 0}
.ea-ctl button{font:inherit;font-size:13px;font-weight:700;padding:8px 14px;border-radius:100px;border:1px solid var(--line);background:#fff;color:var(--ink);cursor:pointer}
.ea-ctl button[aria-pressed=true]{background:var(--sig);border-color:var(--sig);color:#fff}
.ea-legend{display:flex;gap:4px;align-items:center;font-size:12px;color:var(--mut);margin-left:auto}
.ea-legend i{display:inline-block;width:22px;height:10px;border-radius:2px}
.ea-info{position:absolute;z-index:500;right:12px;top:12px;background:#fff;border:1px solid var(--line);border-radius:var(--r);padding:10px 12px;font-size:13px;box-shadow:var(--sh);min-width:200px;max-width:260px}
.ea-info b{display:block;font-size:14px;margin-bottom:4px}
.ea-info small{color:var(--mut)}
.ea-maprel{position:relative}
table td,table th{white-space:nowrap}
.faq-item{border:1px solid var(--line);border-radius:var(--r);background:#fff;padding:12px 16px;margin:8px 0}
.faq-item summary{font-weight:700;cursor:pointer}
.faq-item p{margin:10px 0 0;color:var(--mut)}
pre.cite{white-space:pre-wrap;background:#fff;border:1px solid var(--line);border-radius:var(--r);padding:14px;font-size:13px;font-family:var(--f-mono);color:var(--ink)}
.ea-two{display:grid;grid-template-columns:1fr 1fr;gap:20px}
@media(max-width:760px){.ea-two{grid-template-columns:1fr}#eamap{height:440px}.ea-info{position:static;margin-top:10px;max-width:none}}
"""

def page(lang, rows, fleet, nat, total_share):
    en = lang == "en"
    top = rows[:15]; bottom = rows[-15:][::-1]
    big = sorted([r for r in rows if (r["pop"] or 0) >= 100000], key=lambda r: -(r["pop"] or 0))
    dense = [r for r in rows if (r["ev_estimate"] or 0) >= 2000 and r["points_per_100_ev"] is not None]
    most_pts = sorted(dense, key=lambda r: -r["points_per_100_ev"])[:10]
    least_pts = sorted(dense, key=lambda r: r["points_per_100_ev"])[:10]
    t1, tl = rows[0], rows[-1]
    ams = next(r for r in rows if r["name"] == "Amsterdam"); dh = next(r for r in rows if r["name"] == "Den Haag"); rot = next(r for r in rows if r["name"] == "Rotterdam"); utr = next(r for r in rows if r["name"] == "Utrecht")
    yr0 = fleet[0]; yr = fleet[-1]
    url = SITE + ("/ev-adoption" if en else "/elektrische-autos-per-gemeente")
    alt = SITE + ("/elektrische-autos-per-gemeente" if en else "/ev-adoption")

    def T(en_s, nl_s): return en_s if en else nl_s
    def num(v): return f"{v:,.0f}".replace(",", "." if not en else ",") if v is not None else "n/a"
    def pc(v): return (f"{v:.1f}%" if en else f"{v:.1f}%".replace(".", ",")) if v is not None else "n/a"
    def dec(v): return (f"{v:.1f}" if en else f"{v:.1f}".replace(".", ",")) if v is not None else "n/a"
    def link(r): return f'<a href="/laadpaal-{slug(r["name"])}" hreflang="nl">{esc(r["name"])}</a>' if (ROOT / f'laadpaal-{slug(r["name"])}.html').exists() else esc(r["name"])

    def tbl(rs, cols):
        head = "".join(f"<th>{h}</th>" for h, _ in cols)
        NUM = ' class="num"'
        body = "".join("<tr>" + "".join("<td" + (NUM if i else "") + ">" + str(fn(r)) + "</td>" for i, (_, fn) in enumerate(cols)) + "</tr>" for r in rs)
        return f'<div class="tbl-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'

    share_cols = [(T("Municipality", "Gemeente"), link), (T("EV share of private cars", "Aandeel elektrisch (particulier)"), lambda r: pc(r["share"])),
                  (T("Estimated EVs", "Geschat aantal EV's"), lambda r: num(r["ev_estimate"])), (T("Public charge points", "Publieke laadpunten"), lambda r: num(r["charge_points"])),
                  (T("Points per 100 EVs", "Laadpunten per 100 EV's"), lambda r: dec(r["points_per_100_ev"]))]
    fleet_cols = [(T("1 January", "1 januari"), lambda r: str(r["year"])), (T("Cars", "Personenauto's"), lambda r: num(r["cars"])), (T("Electric drive", "Elektrisch"), lambda r: num(r["electric"])),
                  (T("Share", "Aandeel"), lambda r: pc(r["electric"] / r["cars"] * 100)), (T("Diesel", "Diesel"), lambda r: num(r["diesel"])), (T("Petrol", "Benzine"), lambda r: num(r["petrol"]))]

    title = T(f"Electric Cars per Municipality, Netherlands {yr['year']}: EV Share Map", f"Elektrische auto's per gemeente {yr['year']}: kaart, aandeel en laadpunten")
    desc = T(f"{pc(total_share)} of private cars in the Netherlands are electric on 1 January {yr['year']}, from {pc(t1['share'])} in {t1['name']} to {pc(tl['share'])} in {tl['name']}. Map of all 342 municipalities with public charge points per 100 EVs. CBS data, free CSV.",
             f"Op 1 januari {yr['year']} is {pc(total_share)} van de particuliere personenauto's elektrisch, van {pc(t1['share'])} in {t1['name']} tot {pc(tl['share'])} in {tl['name']}. Kaart van alle 342 gemeenten met laadpunten per 100 EV's. CBS-cijfers, gratis CSV.")[:158]
    h1 = T(f"Electric cars per municipality, {yr['year']}", f"Elektrische auto's per gemeente, {yr['year']}")

    faq = [
        (T(f"Which Dutch municipality has the most electric cars?", "Welke gemeente heeft het hoogste aandeel elektrische auto's?"),
         T(f"By share of private cars, {t1['name']} leads with {pc(t1['share'])} on 1 January {yr['year']}, followed by {rows[1]['name']} ({pc(rows[1]['share'])}) and {rows[2]['name']} ({pc(rows[2]['share'])}). In absolute numbers Amsterdam has the most, with an estimated {num(ams['ev_estimate'])} electric cars registered to private owners.",
           f"Naar aandeel van de particuliere personenauto's staat {t1['name']} bovenaan met {pc(t1['share'])} op 1 januari {yr['year']}, gevolgd door {rows[1]['name']} ({pc(rows[1]['share'])}) en {rows[2]['name']} ({pc(rows[2]['share'])}). In absolute aantallen heeft Amsterdam de meeste, naar schatting {num(ams['ev_estimate'])} elektrische auto's op naam van particulieren.")),
        (T("How many electric cars are there in the Netherlands?", "Hoeveel elektrische auto's zijn er in Nederland?"),
         T(f"On 1 January {yr['year']} the national vehicle register held {num(yr['electric'])} passenger cars with electric drive as main fuel, {pc(nat['electric_share_all'])} of all {num(yr['cars'])} cars and including hybrids and plug-in hybrids under the CBS definition. That is {num(nat['growth_abs'])} more than a year earlier, a rise of {pc(nat['growth_pct'])}.",
           f"Op 1 januari {yr['year']} stonden er {num(yr['electric'])} personenauto's met elektriciteit als hoofdbrandstof in het nationale kentekenregister, {pc(nat['electric_share_all'])} van alle {num(yr['cars'])} auto's, inclusief hybrides en plug-in hybrides volgens de CBS-definitie. Dat is {num(nat['growth_abs'])} meer dan een jaar eerder, een stijging van {pc(nat['growth_pct'])}.")),
        (T("Where is public charging most crowded?", "Waar is het drukst bij de publieke laadpaal?"),
         T(f"Among municipalities with at least 2,000 electric cars, {least_pts[0]['name']} has the fewest public charge points per 100 EVs ({dec(least_pts[0]['points_per_100_ev'])}) and {most_pts[0]['name']} the most ({dec(most_pts[0]['points_per_100_ev'])}). The national figure is {dec(nat['points_per_100_ev'])}. Low numbers usually mean owners charge at home on a driveway; high numbers mean on-street parking with municipal charging programmes.",
           f"Van de gemeenten met minstens 2.000 elektrische auto's heeft {least_pts[0]['name']} de minste publieke laadpunten per 100 EV's ({dec(least_pts[0]['points_per_100_ev'])}) en {most_pts[0]['name']} de meeste ({dec(most_pts[0]['points_per_100_ev'])}). Landelijk is het {dec(nat['points_per_100_ev'])}. Lage cijfers betekenen meestal dat bewoners op eigen oprit laden; hoge cijfers horen bij straatparkeren met een gemeentelijk laadprogramma.")),
        (T("Where do these numbers come from?", "Waar komen deze cijfers vandaan?"),
         T("The share per municipality is a CBS publication based on the national vehicle register, counting private cars insured in the previous year. Population and private-car counts come from CBS regional key figures. Charge points are this site's own extract of the national charge point register, assigned to municipalities by location. The CSV is free under CC BY 4.0.",
           "Het aandeel per gemeente is een CBS-publicatie op basis van het nationale kentekenregister, geteld over particuliere auto's die het voorgaande jaar verzekerd waren. Inwoners en particuliere auto's komen uit de regionale kerncijfers van het CBS. Laadpunten zijn het eigen uittreksel van deze site uit het nationale laadpuntenregister, per locatie aan een gemeente toegekend. De CSV is vrij te gebruiken onder CC BY 4.0.")),
    ]
    ld = [
        {"@context": "https://schema.org", "@type": "Dataset", "name": T(f"EV adoption per municipality, Netherlands {yr['year']}", f"Elektrische auto's per gemeente, Nederland {yr['year']}"),
         "description": desc, "url": url, "sameAs": SITE + "/data/ev-adoption-2026.json", "license": "https://creativecommons.org/licenses/by/4.0/", "isAccessibleForFree": True,
         "keywords": ["electric vehicles", "EV adoption", "Netherlands", "elektrische auto's per gemeente", "laadpunten", "CBS", "kentekenregister"], "inLanguage": lang,
         "creator": {"@type": "Organization", "name": "Analytics Ascent", "url": "https://analyticascent.com"}, "publisher": {"@type": "Organization", "name": "Parking Netherlands", "url": SITE},
         "temporalCoverage": str(yr["year"]), "dateModified": TODAY, "datePublished": TODAY, "spatialCoverage": {"@type": "Place", "name": "Netherlands"},
         "variableMeasured": ["share", "ev_estimate", "charge_points", "points_per_100_ev", "points_per_1000_res"],
         "isBasedOn": [{"@type": "Dataset", "name": "CBS: Aandeel elektrische personenauto's per gemeente, 1 januari 2026", "url": "https://www.cbs.nl/nl-nl/maatwerk/2026/16/aandeel-elektrische-personenauto-s-per-gemeente-1-1-2026"},
                       {"@type": "Dataset", "name": "CBS 85237NED Personenauto's actief; voertuigkenmerken", "url": "https://opendata.cbs.nl/statline/#/CBS/nl/dataset/85237NED"},
                       {"@type": "Dataset", "name": "CBS 70072ned Regionale kerncijfers Nederland", "url": "https://opendata.cbs.nl/statline/#/CBS/nl/dataset/70072ned"}],
         "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": SITE + "/data/ev-adoption-2026.csv"}, {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": SITE + "/data/ev-adoption-2026.json"}]},
        {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [{"@type": "ListItem", "position": 1, "name": "Home", "item": SITE + "/"}, {"@type": "ListItem", "position": 2, "name": h1, "item": url}]},
        {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]},
    ]
    faq_html = "".join(f'<details class="faq-item"><summary>{esc(q)}</summary><p>{esc(a)}</p></details>' for q, a in faq)
    cite = T(f"Parking Netherlands ({yr['year']}). Electric cars per municipality, Netherlands {yr['year']}: EV share and public charge points per 100 EVs for 342 municipalities. {url}",
             f"Parking Netherlands ({yr['year']}). Elektrische auto's per gemeente, Nederland {yr['year']}: aandeel elektrisch en publieke laadpunten per 100 EV's voor 342 gemeenten. {url}")

    if en:
        body = f"""
  <h2>What the map shows</h2>
  <p>Every municipality is coloured by the share of privately owned cars that run on electric drive on 1 January {yr['year']}, the CBS count from the national vehicle register. Switch the view to see public charge points per 100 electric cars, which is this site's own calculation from {num(nat['stations'])} charging locations placed inside the municipal boundaries. Tap a municipality for its figures; the Dutch charger pages for the larger towns are linked in the tables below.</p>

  <h2>Where electric ownership is highest, and lowest</h2>
  <p>The national share for private cars is {pc(total_share)}. The spread between municipalities is more than threefold: {t1['name']} sits at {pc(t1['share'])}, {rows[1]['name']} at {pc(rows[1]['share'])} and {rows[2]['name']} at {pc(rows[2]['share'])}, while {tl['name']} closes the list at {pc(tl['share'])}, with {rows[-2]['name']} ({pc(rows[-2]['share'])}) and {rows[-3]['name']} ({pc(rows[-3]['share'])}) just above it. The top of the ranking is the commuter belt around Amsterdam, Utrecht and The Hague: small, high-income municipalities with driveways and a short drive to a large employer. The bottom is rural Friesland, Overijssel and the Bible belt, where cars are older, distances longer and incomes lower. The pattern is consistent with what the CBS itself reports, that electric cars first reach the households that can charge at home and buy new.</p>
  {tbl(top, share_cols)}
  <p style="margin-top:14px"><strong>The fifteen lowest shares.</strong></p>
  {tbl(bottom, share_cols)}

  <h2>The big cities: many cars, more chargers</h2>
  <p>The four largest cities hold the largest fleets in absolute terms. Amsterdam has an estimated {num(ams['ev_estimate'])} private electric cars at a share of {pc(ams['share'])}, Rotterdam {num(rot['ev_estimate'])} at {pc(rot['share'])}, The Hague {num(dh['ev_estimate'])} at {pc(dh['share'])} and Utrecht {num(utr['ev_estimate'])} at {pc(utr['share'])}. Their shares sit close to the national average, yet their public charging density is far above it: The Hague offers {dec(dh['points_per_100_ev'])} public charge points per 100 EVs and Rotterdam {dec(rot['points_per_100_ev'])}, against {dec(nat['points_per_100_ev'])} nationally. That is the mirror image of the villa municipalities: where nobody has a driveway, the municipality has to put the charger on the street, and the Dutch cities have done so at scale.</p>
  {tbl(big, [(T("City", "Stad"), link), ("Residents", lambda r: num(r["pop"])), ("EV share", lambda r: pc(r["share"])), ("Estimated EVs", lambda r: num(r["ev_estimate"])), ("Public charge points", lambda r: num(r["charge_points"])), ("Points per 100 EVs", lambda r: dec(r["points_per_100_ev"])), ("Fast hubs 150 kW+", lambda r: num(r["fast_hubs"]))])}

  <h2>Where public charging is thin, and where it is generous</h2>
  <p>Among the {len(dense)} municipalities with at least 2,000 electric cars, the number of public charge points per 100 EVs runs from {dec(least_pts[0]['points_per_100_ev'])} in {least_pts[0]['name']} to {dec(most_pts[0]['points_per_100_ev'])} in {most_pts[0]['name']}. A low figure is not automatically a problem: in {least_pts[0]['name']} and {least_pts[1]['name']} most owners charge on their own driveway. It does matter for visitors. If you drive into one of the thin municipalities without a full battery, plan the charge before you arrive, or pick the P+R or garage with charge points from the <a href="/ev-charging">charger map</a>. In the generous municipalities the risk is the opposite one: plenty of posts, but each on a paid parking spot, so the parking tariff can exceed the electricity. The charger map prices both together.</p>
  <div class="ea-two">
    <div><p><strong>Fewest public charge points per 100 EVs</strong> (2,000+ EVs)</p>{tbl(least_pts, share_cols[:1] + share_cols[2:])}</div>
    <div><p><strong>Most public charge points per 100 EVs</strong> (2,000+ EVs)</p>{tbl(most_pts, share_cols[:1] + share_cols[2:])}</div>
  </div>

  <h2>The national fleet since {yr0['year']}</h2>
  <p>The register counted {num(yr['electric'])} cars with electric drive on 1 January {yr['year']}, {pc(nat['electric_share_all'])} of all {num(yr['cars'])} passenger cars, up {num(nat['growth_abs'])} or {pc(nat['growth_pct'])} in a year. Diesel has fallen from {num(yr0['diesel'])} cars in {yr0['year']} to {num(yr['diesel'])}. The all-cars share is higher than the private-car share on the map because company and lease cars, {num(yr['company'])} of them, electrify faster than private ones. The CBS definition of electric drive includes hybrids and plug-in hybrids alongside battery-only cars, so the battery-only fleet is smaller than the headline.</p>
  {tbl(fleet, fleet_cols)}

  <h2 id="method">Methodology</h2>
  <p>Share per municipality: CBS custom table "Aandeel elektrische personenauto's per gemeente, 1 januari 2026", which counts passenger cars registered to natural persons that were insured during the previous year and excludes dealer stock, from the national vehicle register. Estimated EVs: that share applied to the CBS count of private passenger cars per municipality from the regional key figures (latest available year), rounded; treat it as an estimate within a few percent. Residents: CBS, 1 January 2026. Charge points: this site's extract of the national charge point register (NDW / DOT-NL), {num(nat['stations'])} locations with {num(nat['charge_points'])} charge points, each assigned to the municipality whose 2026 boundary contains it; private and semi-public posts are not included. Municipal boundaries: CBS via PDOK, generalised. Boundary changes between the CBS table and the register extract can shift a few dozen posts at municipal edges. The CSV and JSON carry every figure on this page under CC BY 4.0.</p>

  <h2>Cite or reuse</h2>
  <pre class="cite">{esc(cite)}</pre>
  <p><a class="btn btn-primary btn-sm" href="/data/ev-adoption-2026.csv" download>Download CSV</a> <a class="btn btn-ghost btn-sm" href="/data/ev-adoption-2026.json">JSON</a> <a class="btn btn-ghost btn-sm" href="/ev-data/gemeenten-ev.json">GeoJSON</a></p>

  <h2>Questions</h2>
  {faq_html}
  <p style="font-size:12.5px;color:var(--mut);margin:30px 0 60px">Published {TODAY} by <a href="/about">Analytics Ascent</a>. Sources: CBS (national vehicle register), NDW / DOT-NL charge point register, CBS/PDOK boundaries. Nederlandse versie: <a href="/elektrische-autos-per-gemeente" hreflang="nl">elektrische auto's per gemeente</a>. Related: <a href="/ev-charging">live charger map</a>, <a href="/laadpalen" hreflang="nl">laadpalen per stad</a>, <a href="/parking-price-index">parking price index</a>.</p>"""
    else:
        body = f"""
  <h2>Wat de kaart laat zien</h2>
  <p>Elke gemeente is gekleurd naar het aandeel particuliere personenauto's dat op 1 januari {yr['year']} elektrisch rijdt, zoals het CBS dat uit het nationale kentekenregister telt. Zet de kaart om naar publieke laadpunten per 100 elektrische auto's: een eigen berekening van deze site op basis van {num(nat['stations'])} laadlocaties, per gemeentegrens toegekend. Tik op een gemeente voor de cijfers; de laadpaalpagina's van de grotere steden staan in de tabellen gelinkt.</p>

  <h2>Waar het aandeel het hoogst is, en het laagst</h2>
  <p>Landelijk is {pc(total_share)} van de particuliere auto's elektrisch. Tussen gemeenten zit meer dan een factor drie: {t1['name']} staat op {pc(t1['share'])}, {rows[1]['name']} op {pc(rows[1]['share'])} en {rows[2]['name']} op {pc(rows[2]['share'])}, terwijl {tl['name']} de lijst sluit met {pc(tl['share'])}, net onder {rows[-2]['name']} ({pc(rows[-2]['share'])}) en {rows[-3]['name']} ({pc(rows[-3]['share'])}). De top is de forensengordel rond Amsterdam, Utrecht en Den Haag: kleine gemeenten met hoge inkomens, een oprit en een korte rit naar een grote werkgever. De onderkant ligt in landelijk Friesland, Overijssel en de Bijbelgordel, met oudere auto's, langere afstanden en lagere inkomens. Het beeld sluit aan bij wat het CBS zelf meldt: de elektrische auto komt eerst bij huishoudens die thuis kunnen laden en nieuw kopen.</p>
  {tbl(top, share_cols)}
  <p style="margin-top:14px"><strong>De vijftien laagste aandelen.</strong></p>
  {tbl(bottom, share_cols)}

  <h2>De grote steden: veel auto's, nog meer laadpunten</h2>
  <p>De vier grote steden hebben in absolute aantallen de grootste vloten. Amsterdam telt naar schatting {num(ams['ev_estimate'])} particuliere elektrische auto's bij een aandeel van {pc(ams['share'])}, Rotterdam {num(rot['ev_estimate'])} bij {pc(rot['share'])}, Den Haag {num(dh['ev_estimate'])} bij {pc(dh['share'])} en Utrecht {num(utr['ev_estimate'])} bij {pc(utr['share'])}. Hun aandelen liggen dicht bij het landelijk gemiddelde, maar hun publieke laaddichtheid ligt er ver boven: Den Haag heeft {dec(dh['points_per_100_ev'])} publieke laadpunten per 100 EV's en Rotterdam {dec(rot['points_per_100_ev'])}, tegen {dec(nat['points_per_100_ev'])} landelijk. Dat is het spiegelbeeld van de villagemeenten: waar niemand een oprit heeft, moet de gemeente de laadpaal op straat zetten, en de grote steden hebben dat op schaal gedaan.</p>
  {tbl(big, [("Stad", link), ("Inwoners", lambda r: num(r["pop"])), ("Aandeel elektrisch", lambda r: pc(r["share"])), ("Geschat aantal EV's", lambda r: num(r["ev_estimate"])), ("Publieke laadpunten", lambda r: num(r["charge_points"])), ("Per 100 EV's", lambda r: dec(r["points_per_100_ev"])), ("Snellaadhubs 150 kW+", lambda r: num(r["fast_hubs"]))])}

  <h2>Waar publiek laden schaars is, en waar ruim</h2>
  <p>Van de {len(dense)} gemeenten met minstens 2.000 elektrische auto's loopt het aantal publieke laadpunten per 100 EV's van {dec(least_pts[0]['points_per_100_ev'])} in {least_pts[0]['name']} tot {dec(most_pts[0]['points_per_100_ev'])} in {most_pts[0]['name']}. Een laag cijfer is niet automatisch een probleem: in {least_pts[0]['name']} en {least_pts[1]['name']} laadt het gros van de eigenaren op de eigen oprit. Voor bezoekers telt het wel. Wie met een lege accu een van de schaarse gemeenten inrijdt, plant de laadbeurt beter vooraf, of kiest de P+R of garage met laadpunten op de <a href="/laadpalen">laadpalenkaart</a>. In de ruime gemeenten is het risico omgekeerd: palen genoeg, maar elk op een betaald parkeervak, zodat het parkeertarief de stroom kan overtreffen. De kaart rekent beide bij elkaar.</p>
  <div class="ea-two">
    <div><p><strong>Minste publieke laadpunten per 100 EV's</strong> (2.000+ EV's)</p>{tbl(least_pts, share_cols[:1] + share_cols[2:])}</div>
    <div><p><strong>Meeste publieke laadpunten per 100 EV's</strong> (2.000+ EV's)</p>{tbl(most_pts, share_cols[:1] + share_cols[2:])}</div>
  </div>

  <h2>Het wagenpark sinds {yr0['year']}</h2>
  <p>Het register telde op 1 januari {yr['year']} {num(yr['electric'])} personenauto's met elektrische aandrijving, {pc(nat['electric_share_all'])} van alle {num(yr['cars'])} personenauto's, {num(nat['growth_abs'])} of {pc(nat['growth_pct'])} meer dan een jaar eerder. Diesel daalde van {num(yr0['diesel'])} auto's in {yr0['year']} naar {num(yr['diesel'])}. Het aandeel over alle auto's ligt hoger dan het particuliere aandeel op de kaart, omdat zakelijke en leaseauto's, {num(yr['company'])} stuks, sneller elektrificeren dan particuliere. De CBS-definitie van elektrisch omvat naast volledig elektrische auto's ook hybrides en plug-in hybrides; de volledig elektrische vloot is dus kleiner dan het kopcijfer.</p>
  {tbl(fleet, fleet_cols)}

  <h2 id="method">Methode</h2>
  <p>Aandeel per gemeente: CBS-maatwerktabel "Aandeel elektrische personenauto's per gemeente, 1 januari 2026", geteld over personenauto's op naam van natuurlijke personen die het voorgaande jaar verzekerd waren, zonder bedrijfsvoorraad, uit het nationale kentekenregister. Geschat aantal EV's: dat aandeel toegepast op het CBS-aantal particuliere personenauto's per gemeente uit de regionale kerncijfers (laatst beschikbare jaar), afgerond; een schatting met een marge van enkele procenten. Inwoners: CBS, 1 januari 2026. Laadpunten: het uittreksel van deze site uit het nationale laadpuntenregister (NDW / DOT-NL), {num(nat['stations'])} locaties met {num(nat['charge_points'])} laadpunten, elk toegekend aan de gemeente waarvan de grens van 2026 de locatie omvat; private en semipublieke palen tellen niet mee. Gemeentegrenzen: CBS via PDOK, gegeneraliseerd. Grenswijzigingen tussen de CBS-tabel en het registeruittreksel kunnen aan gemeentegrenzen enkele tientallen palen verschuiven. De CSV en JSON bevatten elk cijfer van deze pagina onder CC BY 4.0.</p>

  <h2>Citeren of hergebruiken</h2>
  <pre class="cite">{esc(cite)}</pre>
  <p><a class="btn btn-primary btn-sm" href="/data/ev-adoption-2026.csv" download>Download CSV</a> <a class="btn btn-ghost btn-sm" href="/data/ev-adoption-2026.json">JSON</a> <a class="btn btn-ghost btn-sm" href="/ev-data/gemeenten-ev.json">GeoJSON</a></p>

  <h2>Vragen</h2>
  {faq_html}
  <p style="font-size:12.5px;color:var(--mut);margin:30px 0 60px">Gepubliceerd {TODAY} door <a href="/about">Analytics Ascent</a>. Bronnen: CBS (nationaal kentekenregister), NDW / DOT-NL laadpuntenregister, CBS/PDOK-grenzen. English version: <a href="/ev-adoption" hreflang="en">electric cars per municipality</a>. Zie ook: <a href="/laadpalen">laadpalen per stad</a>, <a href="/ev-charging" hreflang="en">live charger map</a>, <a href="/parking-price-index" hreflang="en">parking price index</a>.</p>"""

    lead = T(f"How electric each Dutch municipality's cars are on 1 January {yr['year']}, counted by the CBS from the national vehicle register, set against the public charge points this site tracks. 342 municipalities, one map, free data.",
             f"Hoe elektrisch het wagenpark van elke Nederlandse gemeente is op 1 januari {yr['year']}, door het CBS geteld uit het nationale kentekenregister, afgezet tegen de publieke laadpunten die deze site volgt. 342 gemeenten, één kaart, vrije data.")
    stats = [(pc(total_share), T("of private cars electric, national", "van de particuliere auto's elektrisch")), (num(yr['electric']), T(f"cars with electric drive, 1 Jan {yr['year']}", f"auto's met elektrische aandrijving, 1 jan {yr['year']}")),
             ("+" + pc(nat['growth_pct']), T("growth in one year", "groei in één jaar")), (t1['name'], T(f"highest share, {pc(t1['share'])}", f"hoogste aandeel, {pc(t1['share'])}")),
             (tl['name'], T(f"lowest share, {pc(tl['share'])}", f"laagste aandeel, {pc(tl['share'])}")), (dec(nat['points_per_100_ev']), T("public charge points per 100 EVs", "publieke laadpunten per 100 EV's"))]
    stats_html = "".join(f'<div class="ea-stat"><b>{esc(a)}</b><span>{esc(b)}</span></div>' for a, b in stats)
    ld_json = json.dumps(ld, ensure_ascii=False).replace("</", "<\\/")
    labels = json.dumps({"share": T("EV share of private cars", "Aandeel elektrisch (particulier)"), "ratio": T("Public charge points per 100 EVs", "Publieke laadpunten per 100 EV's"),
                         "evs": T("Estimated EVs", "Geschat aantal EV's"), "points": T("Public charge points", "Publieke laadpunten"), "pop": T("Residents", "Inwoners"), "na": T("no data", "geen data"),
                         "hint": T("Hover or tap a municipality", "Beweeg over of tik op een gemeente"), "lang": lang}, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2889604222343187" crossorigin="anonymous"></script>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{url}">
<link rel="alternate" hreflang="en" href="{SITE}/ev-adoption">
<link rel="alternate" hreflang="nl" href="{SITE}/elektrische-autos-per-gemeente">
<link rel="alternate" hreflang="x-default" href="{SITE}/ev-adoption">
<link rel="stylesheet" href="/site.css">
<link rel="icon" href="/favicon.ico?v=2" sizes="any"><link rel="icon" type="image/svg+xml" href="/favicon.svg?v=2">
<meta property="og:type" content="article">
<meta property="og:url" content="{url}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:image" content="{SITE}/og-image.png">
<meta name="robots" content="index, follow">
<meta name="author" content="Analytics Ascent">
<link rel="alternate" type="text/csv" href="/data/ev-adoption-2026.csv" title="{esc(title)} (CSV)">
<script type="application/ld+json">{ld_json}</script>
<style>{CSS}</style>
</head>
<body>
<div class="ea-wrap">
  <header class="ea-hero">
    <div class="crumb" style="font-size:13px;color:var(--mut)"><a href="/" style="color:var(--mut);text-decoration:none">Home</a> / {esc(h1)}</div>
    <h1>{esc(h1)}</h1>
    <p class="lead">{esc(lead)}</p>
  </header>
  <div class="ea-stats">{stats_html}</div>
  <div class="ea-ctl" role="group" aria-label="{T('Map metric', 'Kaartmaat')}">
    <button type="button" data-metric="share" aria-pressed="true">{T('EV share', 'Aandeel elektrisch')}</button>
    <button type="button" data-metric="ratio" aria-pressed="false">{T('Charge points per 100 EVs', 'Laadpunten per 100 EV&#39;s')}</button>
    <div class="ea-legend" id="eaLegend"></div>
  </div>
  <div class="ea-maprel"><div id="eamap" role="img" aria-label="{esc(h1)}"></div><div class="ea-info" id="eaInfo"><b>{T('Netherlands', 'Nederland')}</b>{esc(pc(total_share))} {T('of private cars electric', 'van de particuliere auto&#39;s elektrisch')}<br><small>{T('Hover or tap a municipality', 'Beweeg over of tik op een gemeente')}</small></div></div>
  {body}
</div>
<script>window.EA_LABELS={labels};</script>
<script src="/ev-adoption.js?v={TODAY.replace('-', '')}" defer></script>
</body>
</html>"""

def slug(name):
    s = name.lower().replace("'", "").replace("’", "")
    s = re.sub(r"[àáâä]", "a", s); s = re.sub(r"[èéêë]", "e", s); s = re.sub(r"[ïíî]", "i", s); s = re.sub(r"[óôö]", "o", s); s = re.sub(r"[úûü]", "u", s)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")

JS = r"""
/* Choropleth of EV share and public charge points per 100 EVs, per municipality. */
(function () {
  var L_ = window.EA_LABELS || {};
  var el = document.getElementById('eamap'); if (!el) return;
  var metric = 'share', geo = null, layer = null, map = null;
  var RAMP = ['#E8ECFA', '#BFC9F2', '#8E9EE8', '#5F73DC', '#3A4FD0', '#2337C6', '#16247F'];
  var BREAKS = { share: [10, 12, 14, 16, 18, 21, 24], ratio: [1, 2, 3, 4, 6, 8, 12] };
  function fmt(v, m) { if (v == null) return L_.na; var s = (m === 'share' ? v.toFixed(1) + '%' : v.toFixed(1)); return L_.lang === 'nl' ? s.replace('.', ',') : s; }
  function fmtInt(v) { return v == null ? L_.na : v.toLocaleString(L_.lang === 'nl' ? 'nl-NL' : 'en-GB'); }
  function color(v, m) { if (v == null) return '#F3F5F9'; var b = BREAKS[m], i = 0; while (i < b.length && v >= b[i]) i++; return RAMP[Math.min(i, RAMP.length - 1)]; }
  function style(f) { var v = metric === 'share' ? f.properties.s : f.properties.r; return { fillColor: color(v, metric), weight: 0.6, color: '#fff', fillOpacity: 0.9 }; }
  function legend() {
    var b = BREAKS[metric], h = '<span>' + (L_[metric]) + '</span>';
    h += '<i style="background:' + RAMP[0] + '" title="&lt; ' + b[0] + '"></i>';
    for (var i = 0; i < b.length; i++) h += '<i style="background:' + RAMP[Math.min(i + 1, RAMP.length - 1)] + '" title="' + b[i] + (b[i + 1] ? ' to ' + b[i + 1] : '+') + '"></i>';
    h += '<span>' + fmt(b[0], metric) + ' to ' + fmt(b[b.length - 1], metric) + '+</span>';
    document.getElementById('eaLegend').innerHTML = h;
  }
  function info(p) {
    var box = document.getElementById('eaInfo');
    if (!p) { box.innerHTML = '<b>' + (L_.lang === 'nl' ? 'Nederland' : 'Netherlands') + '</b><small>' + L_.hint + '</small>'; return; }
    box.innerHTML = '<b>' + p.n + '</b>' + L_.share + ': <strong>' + fmt(p.s, 'share') + '</strong><br>' + L_.evs + ': ' + fmtInt(p.e) + '<br>' + L_.points + ': ' + fmtInt(p.p) + '<br>' + L_.ratio + ': <strong>' + fmt(p.r, 'ratio') + '</strong><br><small>' + L_.pop + ': ' + fmtInt(p.pop) + '</small>';
  }
  function draw() {
    if (layer) map.removeLayer(layer);
    layer = L.geoJSON(geo, { style: style, onEachFeature: function (f, l) {
      l.on('mouseover', function () { l.setStyle({ weight: 2, color: '#0B1120' }); l.bringToFront(); info(f.properties); });
      l.on('mouseout', function () { layer.resetStyle(l); });
      l.on('click', function () { info(f.properties); if (window.track) window.track('ev_adoption_select', { municipality: f.properties.n, metric: metric }); });
    } }).addTo(map);
    legend();
  }
  function boot() {
    map = L.map('eamap', { scrollWheelZoom: false, zoomSnap: 0.25 }).setView([52.2, 5.3], 7);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/light_nolabels/{z}/{x}/{y}{r}.png', { attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; CARTO · CBS/PDOK · charge points: NDW / DOT-NL', maxZoom: 12 }).addTo(map);
    fetch('/ev-data/gemeenten-ev.json').then(function (r) { return r.json(); }).then(function (g) { geo = g; draw(); map.fitBounds(layer.getBounds(), { padding: [6, 6] }); });
    Array.prototype.forEach.call(document.querySelectorAll('.ea-ctl button'), function (b) {
      b.onclick = function () {
        metric = b.dataset.metric;
        Array.prototype.forEach.call(document.querySelectorAll('.ea-ctl button'), function (x) { x.setAttribute('aria-pressed', x === b ? 'true' : 'false'); });
        if (geo) draw();
        if (window.track) window.track('ev_adoption_metric', { metric: metric });
      };
    });
  }
  var css = document.createElement('link'); css.rel = 'stylesheet'; css.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'; document.head.appendChild(css);
  var js = document.createElement('script'); js.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'; js.onload = boot; document.head.appendChild(js);
})();
"""

if __name__ == "__main__":
    rows, fleet, nat, total_share = build()
    (ROOT / "ev-adoption.js").write_text(JS.strip() + "\n", "utf-8")
    (ROOT / "ev-adoption.html").write_text(page("en", rows, fleet, nat, total_share), "utf-8")
    (ROOT / "elektrische-autos-per-gemeente.html").write_text(page("nl", rows, fleet, nat, total_share), "utf-8")
    print(f"built: {len(rows)} municipalities; national {nat}")
