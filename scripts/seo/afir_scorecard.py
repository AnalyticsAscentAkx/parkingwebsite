#!/usr/bin/env python3
"""
AFIR data scorecard: how much of the Dutch charge point register meets the EU
data obligation, nationally and per operator.

Regulation (EU) 2023/1804 (AFIR) article 20 and Implementing Regulation (EU)
2025/655 oblige operators to publish static and dynamic data through the
National Access Point from 14 April 2026. The OCPI "NAP Data Extension 1.0"
(EVRoaming Foundation with NDW, 24 September 2026) maps every obligation onto a
field of the OCPI feed that NDW publishes. This script reads that feed and
counts, field by field, what is actually there.

Outputs
  afir-scorecard.html                     the page
  data/afir-scorecard-2026.json / .csv    national + per-operator figures (CC BY 4.0)
  img/articles/afir-coverage.png          chart: national coverage per obligation
  img/articles/afir-operators.png         chart: card payment per operator

Usage: python3 scripts/seo/afir_scorecard.py [--cache DIR] [--offline]
Feed cache is per day; the daily job refreshes it.
"""
import csv, gzip, io, json, os, sys, datetime, collections, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITE = "https://parkingnetherlands.com"
TODAY = datetime.date.today().isoformat()
CACHE = Path(sys.argv[sys.argv.index("--cache") + 1]) if "--cache" in sys.argv else Path(os.environ.get("EV_CACHE", "/tmp/afir-cache"))
CACHE.mkdir(parents=True, exist_ok=True)
LOC_URL = "https://opendata.ndw.nu/charging_point_locations_ocpi.json.gz"
TAR_URL = "https://opendata.ndw.nu/charging_point_tariffs_ocpi.json.gz"
UA = {"User-Agent": "Mozilla/5.0 parkingnetherlands.com research"}
COBALT, ORANGE, INK, MUT, LINE = "#2337C6", "#EA580C", "#0B1120", "#64748B", "#E3E9F2"

# Obligations, in the order they appear on the page. level: point (EVSE) or site (Location).
# ref = row in the AFIR annex tables as used by the NAP extension.
OBLIGATIONS = [
    ("ad_hoc",     "Ad hoc price named",            "point", "F3",  "a tariff of type AD_HOC_PAYMENT attached to the connector"),
    ("tariff",     "Any tariff attached",            "point", "F3",  "connector tariff_ids resolves to a published tariff"),
    ("card",       "Bank card reader",               "point", "A20", "capabilities include CREDIT_CARD_PAYABLE, DEBIT_CARD_PAYABLE, PED_TERMINAL or CHIP_CARD_SUPPORT"),
    ("contactless","Contactless payment",            "point", "A21", "capabilities include CONTACTLESS_CARD_SUPPORT"),
    ("power",      "Point maximum power published",  "point", "B6",  "max_electric_power on at least one connector"),
    ("status",     "Operational status known",       "point", "F1",  "status is not UNKNOWN"),
    ("hours",      "Opening hours",                  "site",  "A14", "opening_times present on the location"),
    ("energy",     "Renewable share declared",       "site",  "B10", "energy_mix present on the location"),
    ("phone",      "Helpdesk telephone",             "site",  "A5",  "help_phone present on the location"),
    ("parking",    "Parking spaces and vehicle limits", "site", "A16 to A19", "parking_places present on the location"),
]
# Fields the extension adds. Zero today; the feed watch alerts when they appear.
NEW_FIELDS = [
    ("legal_name",     "Location.operator.legal_name", "A1",  "legal name next to the trading name"),
    ("region",         "Location.region",              "A10", "NUTS-1 region code"),
    ("services",       "Location.services",            "A4",  "on-site service support"),
    ("payment_brands", "EVSE.payment_brands",          "A23", "card brands accepted for ad hoc payment"),
    ("parking_places", "Location.parking_places",      "A16 to A19", "spaces, vehicle limits, disabled bays"),
    ("help_phone",     "Location.help_phone",          "A5",  "helpdesk telephone (existing field, now mandatory)"),
]
CARD_CAPS = {"CREDIT_CARD_PAYABLE", "DEBIT_CARD_PAYABLE", "PED_TERMINAL", "CHIP_CARD_SUPPORT"}

# ----------------------------------------------------------------- feed
def fetch(url, name):
    p = CACHE / f"{name}-{TODAY}.json.gz"
    if not p.exists():
        if "--offline" in sys.argv:
            olds = sorted(CACHE.glob(f"{name}-*.json.gz"))
            if not olds: raise SystemExit(f"offline and no cached {name}")
            p = olds[-1]
        else:
            req = urllib.request.Request(url, headers=UA)
            p.write_bytes(urllib.request.urlopen(req, timeout=300).read())
    with gzip.open(p, "rb") as fh:
        d = json.load(fh)
    return d if isinstance(d, list) else d.get("data", d)

def load_feed():
    return fetch(LOC_URL, "locations"), fetch(TAR_URL, "tariffs")

# ----------------------------------------------------------------- analysis
def nonempty(v):
    return v not in (None, [], {}, "")

def analyse(L, T):
    tar = {}
    for t in T:
        comps = {(pc.get("type") or "").upper() for el in t.get("elements") or [] for pc in el.get("price_components") or []}
        tar[t["id"]] = {"adhoc": (t.get("type") or "").upper() == "AD_HOC_PAYMENT", "idle": "PARKING_TIME" in comps}
    nat = collections.Counter()
    ops = collections.defaultdict(collections.Counter)
    fields = {"location": collections.Counter(), "evse": collections.Counter(), "connector": collections.Counter(), "tariff": collections.Counter(),
              "capability": collections.Counter(), "status": collections.Counter(), "tariff_type": collections.Counter(), "price_component": collections.Counter()}
    for t in T:
        fields["tariff"].update(k for k, v in t.items() if nonempty(v))
        fields["tariff_type"][(t.get("type") or "none")] += 1
        for el in t.get("elements") or []:
            fields["price_component"].update((pc.get("type") or "?") for pc in el.get("price_components") or [])
    for l in L:
        fields["location"].update(k for k, v in l.items() if nonempty(v))
        op = (l.get("operator") or {}).get("name") or l.get("party_id") or "unknown"
        op = op.strip()
        site = {"hours": nonempty(l.get("opening_times")), "energy": nonempty(l.get("energy_mix")),
                "phone": nonempty(l.get("help_phone")), "parking": nonempty(l.get("parking_places"))}
        for e in l.get("evses") or []:
            fields["evse"].update(k for k, v in e.items() if nonempty(v))
            st = e.get("status") or "UNKNOWN"
            fields["status"][st] += 1
            caps = set(e.get("capabilities") or [])
            fields["capability"].update(caps)
            conns = e.get("connectors") or []
            for c in conns:
                fields["connector"].update(k for k, v in c.items() if nonempty(v))
            if st in ("REMOVED", "PLANNED"): continue
            tids = [tid for c in conns for tid in (c.get("tariff_ids") or []) if tid in tar]
            m = {"ad_hoc": any(tar[t]["adhoc"] for t in tids), "tariff": bool(tids),
                 "card": bool(caps & CARD_CAPS), "contactless": "CONTACTLESS_CARD_SUPPORT" in caps,
                 "power": any(nonempty(c.get("max_electric_power")) for c in conns), "status": st != "UNKNOWN",
                 "idle": any(tar[t]["idle"] for t in tids)}
            m.update(site)
            for ctr in (nat, ops[op]):
                ctr["points"] += 1
                for k, v in m.items():
                    if v: ctr[k] += 1
    return nat, ops, fields

def pct(ctr, k):
    return round(100.0 * ctr[k] / ctr["points"], 1) if ctr["points"] else 0.0

def op_rows(ops, min_points=500):
    rows = []
    for name, c in ops.items():
        if c["points"] < min_points: continue
        r = {"operator": name, "points": c["points"]}
        for k, *_ in OBLIGATIONS: r[k] = pct(c, k)
        r["idle"] = pct(c, "idle")
        r["met"] = sum(1 for k, *_ in OBLIGATIONS if r[k] >= 90.0)
        rows.append(r)
    rows.sort(key=lambda r: -r["points"])
    return rows

# ----------------------------------------------------------------- charts
def charts(nat, rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": LINE, "axes.labelcolor": INK, "xtick.color": MUT, "ytick.color": INK})
    out = ROOT / "img/articles"; out.mkdir(parents=True, exist_ok=True)

    labels = [f"{lab}  ({ref})" for _, lab, _, ref, _ in OBLIGATIONS][::-1]
    vals = [pct(nat, k) for k, *_ in OBLIGATIONS][::-1]
    fig, ax = plt.subplots(figsize=(10, 5.6), dpi=160)
    bars = ax.barh(labels, vals, color=[COBALT if v >= 90 else ORANGE for v in vals], height=0.62)
    for b, v in zip(bars, vals):
        ax.text(min(v, 100) + 1.2, b.get_y() + b.get_height() / 2, f"{v:.1f}%", va="center", color=INK, fontsize=10)
    ax.axvline(90, color=MUT, lw=1, ls=":"); ax.text(90.5, len(vals) - 0.45, "90% line", color=MUT, fontsize=9)
    ax.set_xlim(0, 112); ax.set_xlabel("Share of active public charge points in the register, %")
    ax.set_title("Dutch charge point register against the AFIR data obligations", loc="left", fontsize=12.5, color=INK, pad=12)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    fig.text(0.01, 0.01, "Source: NDW charging_point_locations_ocpi + tariffs, read against OCPI NAP Data Extension 1.0. parkingnetherlands.com/afir-scorecard", color=MUT, fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(out / "afir-coverage.png"); plt.close(fig)

    top = rows[:15][::-1]
    fig, ax = plt.subplots(figsize=(10, 6.4), dpi=160)
    y = range(len(top)); h = 0.38
    ax.barh([i + h / 2 for i in y], [r["card"] for r in top], height=h, color=COBALT, label="Bank card reader (A20)")
    ax.barh([i - h / 2 for i in y], [r["ad_hoc"] for r in top], height=h, color=ORANGE, label="Ad hoc price typed (F3)")
    ax.set_yticks(list(y)); ax.set_yticklabels([f'{r["operator"]}  ({r["points"]:,} pts)' for r in top])
    for i, r in enumerate(top):
        ax.text(r["card"] + 1, i + h / 2, f'{r["card"]:.0f}%', va="center", fontsize=9, color=INK)
        ax.text(r["ad_hoc"] + 1, i - h / 2, f'{r["ad_hoc"]:.0f}%', va="center", fontsize=9, color=INK)
    ax.set_xlim(0, 112); ax.set_xlabel("Share of the operator's active charge points, %")
    ax.set_title("Card reader and ad hoc price declared per operator, fifteen largest networks", loc="left", fontsize=12.5, color=INK, pad=12)
    ax.legend(loc="lower right", frameon=False)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    fig.text(0.01, 0.01, f"Source: NDW register snapshot {TODAY}. parkingnetherlands.com/afir-scorecard", color=MUT, fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(out / "afir-operators.png"); plt.close(fig)

# ----------------------------------------------------------------- page
def n(x): return f"{x:,}"
def esc(s): return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def render(nat, rows, fields, n_loc, n_tar):
    P = nat["points"]
    f = {k: pct(nat, k) for k, *_ in OBLIGATIONS}
    adhoc_tariffs = fields["tariff_type"].get("AD_HOC_PAYMENT", 0)
    untyped = fields["tariff_type"].get("none", 0)
    unknown = fields["status"].get("UNKNOWN", 0)
    idle = pct(nat, "idle")
    met_all = sum(1 for k in f if f[k] >= 90)
    best = sorted(rows, key=lambda r: (-r["met"], -r["card"]))[:3]
    worst_card = sorted([r for r in rows if r["points"] >= 2000], key=lambda r: r["card"])[:3]

    def fieldrow(k, lab, lvl, ref, how):
        v = f[k]; cls = "ok" if v >= 90 else "no"
        return f'<tr><td>{esc(lab)}</td><td class="num">{ref}</td><td>{"charge point" if lvl=="point" else "location"}</td><td class="num {cls}">{v:.1f}%</td><td class="how">{esc(how)}</td></tr>'
    obl_rows = "\n".join(fieldrow(*o) for o in OBLIGATIONS)

    def oprow(r):
        cells = "".join(f'<td class="num {"ok" if r[k] >= 90 else "no"}">{r[k]:.0f}</td>' for k, *_ in OBLIGATIONS)
        return f'<tr><td>{esc(r["operator"])}</td><td class="num">{n(r["points"])}</td>{cells}<td class="num"><b>{r["met"]}</b></td></tr>'
    op_html = "\n".join(oprow(r) for r in rows[:25])
    heads = "".join(f'<th title="{esc(lab)}">{ref}</th>' for _, lab, _, ref, _ in OBLIGATIONS)

    newrows = "\n".join(
        f'<tr><td><code>{esc(fld)}</code></td><td class="num">{ref}</td><td>{esc(what)}</td><td class="num">{n(fields["location"].get(fld.split(".")[-1], 0) if fld.startswith("Location") else fields["evse"].get(fld.split(".")[-1], 0))}</td></tr>'
        for _, fld, ref, what in NEW_FIELDS)

    faq = [
        ("What is AFIR and what does it oblige charge point operators to publish?",
         f"Regulation (EU) 2023/1804, the Alternative Fuels Infrastructure Regulation, article 20, obliges operators of publicly accessible charge points to make static and dynamic data available free of charge through the national access point. Static data covers the operator, location, opening hours, payment options, connectors and power; dynamic data covers operational status, availability and the ad hoc price. The implementing regulation 2025/655 fixes the fields and makes the obligation apply from 14 April 2026, static data within 24 hours of a change and dynamic data within one minute."),
        ("Does the Dutch register meet the AFIR data obligation?",
         f"Not on the data it publishes today. Of the ten obligations checked here, {met_all} are met for at least 90% of the {n(P)} active public charge points in the NDW feed. The ad hoc price, the one figure a driver without a subscription needs, is typed as such on {n(adhoc_tariffs)} of {n(n_tar)} tariffs. A bank card reader is declared on {f['card']:.1f}% of points and contactless payment on {f['contactless']:.1f}%."),
        ("Where does the data come from?",
         "From the two OCPI files that NDW, the Dutch national access point, publishes as open data: charging_point_locations_ocpi.json.gz and charging_point_tariffs_ocpi.json.gz. Each field is read the way the OCPI NAP Data Extension 1.0 (EVRoaming Foundation and NDW, 24 September 2026) maps it to the AFIR annex. The snapshot date is printed on the page and the figures are rebuilt daily."),
        ("Why does the card payment share look low when many chargers take cards?",
         "The scorecard counts what the operator declares in the register, not what is on the post. If a charge point has a card terminal and the operator has not set the capability flag, the register says there is none. Under AFIR the register is the source other services are meant to read, so an undeclared terminal is a compliance gap even when the hardware exists."),
    ]
    faq_html = "\n".join(f'<details class="faq"><summary>{esc(q)}</summary><p>{esc(a)}</p></details>' for q, a in faq)
    faq_ld = {"@context": "https://schema.org", "@type": "FAQPage",
              "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}
    dataset_ld = {"@context": "https://schema.org", "@type": "Dataset",
                  "name": "AFIR data scorecard for the Dutch charge point register",
                  "description": f"Share of active public charge points in the Dutch national register (NDW) that publish each data element required by EU regulation 2023/1804, nationally and per operator. Snapshot {TODAY}.",
                  "url": f"{SITE}/afir-scorecard", "license": "https://creativecommons.org/licenses/by/4.0/",
                  "creator": {"@type": "Organization", "name": "Analytics Ascent", "url": SITE},
                  "temporalCoverage": TODAY, "spatialCoverage": "Netherlands",
                  "isBasedOn": ["https://opendata.ndw.nu/charging_point_locations_ocpi.json.gz", "https://opendata.ndw.nu/charging_point_tariffs_ocpi.json.gz", "https://evroaming.org/wp-content/uploads/2026/09/OCPI-nap-extension-1.0.pdf"],
                  "distribution": [{"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f"{SITE}/data/afir-scorecard-2026.json"},
                                   {"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{SITE}/data/afir-scorecard-2026.csv"}]}
    crumb_ld = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE + "/"},
        {"@type": "ListItem", "position": 2, "name": "Charging", "item": SITE + "/ev-charging"},
        {"@type": "ListItem", "position": 3, "name": "AFIR scorecard", "item": SITE + "/afir-scorecard"}]}
    title = "AFIR Scorecard: What the Dutch Charge Point Register Actually Publishes"
    desc = (f"EU law has required an ad hoc price and payment data at every public charge point since April 2026. The Dutch register names one on {n(adhoc_tariffs)} of {n(n_tar)} tariffs "
            f"and a card reader on {f['card']:.0f}% of points. Field by field, per operator, rebuilt daily.")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{SITE}/afir-scorecard">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/site.css?v=20261007a">
<script src="/analytics.js?v=20261007a" defer></script>
<script src="/site.js?v=20261007a" defer></script>
<link rel="icon" href="/favicon.ico?v=2" sizes="any"><link rel="icon" type="image/svg+xml" href="/favicon.svg?v=2">
<meta property="og:type" content="article">
<meta property="og:url" content="{SITE}/afir-scorecard">
<meta property="og:title" content="AFIR scorecard: what the Dutch charge point register publishes">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:image" content="{SITE}/img/articles/afir-coverage.png">
<meta name="robots" content="index, follow">
<meta name="author" content="Analytics Ascent">
<script type="application/ld+json">{json.dumps([dataset_ld, faq_ld, crumb_ld], ensure_ascii=False)}</script>
<style>
.cg{{max-width:1080px;margin:0 auto;padding:0 24px}}
.cg-hero{{padding:44px 0 6px}}
.cg-hero h1{{font-size:clamp(1.9rem,4vw,2.9rem);font-weight:800;letter-spacing:-.03em;line-height:1.1;color:var(--ink);margin:10px 0 12px}}
.cg-hero .lead{{font-size:17px;color:var(--mut);max-width:780px;line-height:1.6}}
.crumb{{font-size:13px;color:var(--mut)}}.crumb a{{color:var(--mut)}}
.cg-stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:26px 0}}
.cg-stat{{background:#fff;border:1px solid var(--line);border-radius:var(--r-lg);padding:16px 18px;box-shadow:var(--sh)}}
.cg-stat b{{display:block;font-size:26px;font-weight:800;letter-spacing:-.03em;color:var(--ink);font-variant-numeric:tabular-nums}}
.cg-stat span{{font-size:12.5px;color:var(--mut)}}
.cg h2{{font-size:1.35rem;font-weight:800;letter-spacing:-.02em;color:var(--ink);margin:40px 0 12px}}
.cg h3{{font-size:1.05rem;font-weight:700;color:var(--ink);margin:26px 0 6px}}
.cg p{{line-height:1.65;max-width:780px}}
.cg ul,.cg ol{{line-height:1.7;padding-left:20px;max-width:780px}}
.cg li{{margin-bottom:8px}}
.cg figure{{margin:18px 0 26px}}.cg figure img{{width:100%;height:auto;border:1px solid var(--line);border-radius:var(--r-lg);background:#fff}}
.cap{{font-size:13px;color:var(--mut);line-height:1.6;margin:8px 0 0}}
.tbl-wrap{{margin:14px 0 8px}}
table{{width:100%;border-collapse:collapse;font-size:13.5px}}
th,td{{padding:8px 10px;border-bottom:1px solid var(--line-soft);text-align:left;vertical-align:top}}
th{{font-size:12px;color:var(--mut);font-weight:600;text-transform:uppercase;letter-spacing:.04em;white-space:nowrap}}
td.num,th.num{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
td.ok{{color:#168A68;font-weight:600}}td.no{{color:#B45309;font-weight:600}}
td.how{{color:var(--mut);font-size:12.5px;min-width:260px}}
.ops td,.ops th{{padding:6px 7px}}.ops td:first-child{{white-space:nowrap}}
.cite{{font-size:13px;color:var(--mut);line-height:1.6}}
.warnbox{{background:var(--sig-soft);border-radius:var(--r-lg);padding:18px 20px;margin:22px 0;max-width:780px}}
.warnbox p{{font-size:14.5px;margin:0 0 8px}}.warnbox p:last-child{{margin:0}}
details.faq{{border-bottom:1px solid var(--line-soft);padding:10px 0;max-width:780px}}
details.faq summary{{font-weight:700;cursor:pointer;color:var(--ink)}}details.faq p{{margin:8px 0 0;color:var(--mut)}}
code{{font-family:var(--f-mono);font-size:12.5px;background:var(--line-soft);padding:1px 5px;border-radius:4px}}
</style>
</head>
<body>
<main class="cg">
<header class="cg-hero">
<div class="crumb"><a href="/">Home</a> › <a href="/ev-charging">Charging</a> › AFIR scorecard</div>
<h1>AFIR scorecard: what the Dutch charge point register actually publishes</h1>
<p class="lead">Since 14 April 2026, EU law has required every public charge point operator to publish its prices, payment options, power and live status through the national access point. The Netherlands wrote the OCPI mapping for that obligation. This page reads the Dutch register against it, field by field and operator by operator, every day.</p>
<p class="cite">Register snapshot {TODAY}. {n(n_loc)} locations, {n(P)} active public charge points, {n(n_tar)} tariffs. Rebuilt daily from the NDW open data feed.</p>
</header>

<div class="cg-stats">
<div class="cg-stat"><b>{n(adhoc_tariffs)}</b><span>of {n(n_tar)} tariffs typed as the ad hoc price AFIR requires</span></div>
<div class="cg-stat"><b>{f['card']:.0f}%</b><span>of charge points declare a bank card reader</span></div>
<div class="cg-stat"><b>{f['contactless']:.1f}%</b><span>declare contactless payment</span></div>
<div class="cg-stat"><b>{met_all} of 10</b><span>obligations met for at least 90% of points</span></div>
</div>

<p>Regulation (EU) 2023/1804, the Alternative Fuels Infrastructure Regulation, is mostly known for its hardware rules: a 1.3 kW of public charging power per electric car, fast chargers every 60 km on the core network. Article 20 is the part nobody reads. It obliges every operator of a publicly accessible charge point to make a fixed list of data available, free of charge, through the national access point, so that any app or map can show a driver the price, the payment options and whether the post is working before they get there. Implementing Regulation (EU) 2025/655 fixed the field list and the deadline: 14 April 2026, static data updated within 24 hours of a change, dynamic data within one minute.</p>

<p>On 24 September 2026 the EVRoaming Foundation and NDW, the Dutch national access point, published the <a href="https://evroaming.org/wp-content/uploads/2026/09/OCPI-nap-extension-1.0.pdf">OCPI NAP Data Extension 1.0</a>. It maps each AFIR data element onto a field of the OCPI feed that NDW already publishes as open data, and makes a number of previously optional fields mandatory. That gives an outsider something rare: a published rulebook and the file it applies to, both open. This page compares the two.</p>

<h2>Ten obligations, one register</h2>
<p>Each row is one data element the regulation requires. The share is the proportion of active public charge points in the register (status not REMOVED or PLANNED) whose operator has filled in the corresponding OCPI field. Location-level elements are counted per charge point at that location, so a large site with no opening hours weighs more than a single post.</p>
<figure>
<img src="/img/articles/afir-coverage.png?d={TODAY}" alt="Horizontal bar chart: share of Dutch public charge points publishing each AFIR data element, {TODAY}" width="1600" height="896" loading="lazy">
<p class="cap">Figure 1. Share of active public charge points in the Dutch register that carry each AFIR data element. Cobalt bars meet the 90% line, orange bars do not. Source: NDW OCPI feed, {TODAY}.</p>
</figure>
<div class="tbl-wrap"><table>
<thead><tr><th>Obligation</th><th class="num">AFIR row</th><th>Level</th><th class="num">Share</th><th>How it is read</th></tr></thead>
<tbody>
{obl_rows}
</tbody></table></div>
<p class="cite">AFIR row numbers follow Annex tables A (static, station level), B (static, charge point level) and F (dynamic) of Implementing Regulation 2025/655, as used in the NAP extension.</p>

<h2>The ad hoc price is the gap that matters</h2>
<p>A driver without a subscription has one question at the post: what will this cost me? AFIR row F3 answers it with the ad hoc price, in national currency, including every component. OCPI carries that as a tariff of type AD_HOC_PAYMENT attached to the connector. The Dutch feed contains {n(n_tar)} tariffs. {n(adhoc_tariffs)} of them are typed AD_HOC_PAYMENT. {n(untyped)} have no type at all, which means the register cannot say whether the price it holds is the one a walk-up driver pays or a contract rate for one roaming partner.</p>
<p>That is not a missing-data problem at the edges. The tariff is attached for {f['tariff']:.1f}% of points, so the operators do publish a price; they do not say which price it is. The NAP extension makes the type field mandatory and requires the AD_HOC_PAYMENT tariff to be resolvable from every connector. On the day NDW enforces that, this number moves, and this page will show it.</p>

<h2>Payment: declared on paper, not in the register</h2>
<p>AFIR requires every public charge point to accept ad hoc payment, and from 2024 every new point of 50 kW or more to take bank cards, by reader or contactless. The register has fields for both. Across the country a bank card reader is declared on {f['card']:.1f}% of points and contactless on {f['contactless']:.1f}%. Anyone who has tapped a card on a Dutch fast charger knows the hardware share is higher than that. The gap is in the declaration, and under AFIR the declaration is what every navigation app is supposed to read.</p>
<figure>
<img src="/img/articles/afir-operators.png?d={TODAY}" alt="Grouped bar chart: share of charge points with a declared bank card reader and a typed ad hoc price, fifteen largest Dutch operators, {TODAY}" width="1600" height="1024" loading="lazy">
<p class="cap">Figure 2. Bank card reader (cobalt) and ad hoc price typed on the tariff (orange) as declared in the register, fifteen largest operators by active charge points. Contactless is below 1% for every operator and is not drawn. Source: NDW OCPI feed, {TODAY}.</p>
</figure>

<h2>Operator scorecard</h2>
<p>Operators with at least 500 active public charge points, ranked by size. Each cell is the share of the operator's points that carry the element; green is 90% or more. The last column counts the elements an operator meets at the 90% line. {esc(best[0]['operator'])} leads with {best[0]['met']} of ten{(", " + esc(best[1]['operator']) + " and " + esc(best[2]['operator']) + " follow with " + str(best[1]['met']) + " and " + str(best[2]['met'])) if len(best) > 2 else ""}.</p>
<div class="tbl-wrap"><table class="ops">
<thead><tr><th>Operator</th><th class="num">Points</th>{heads}<th class="num">Met</th></tr></thead>
<tbody>
{op_html}
</tbody></table></div>
<p class="cite">Column headers are AFIR rows: F3 ad hoc price typed, F3 any tariff attached, A20 bank card reader, A21 contactless, B6 point power, F1 status known, A14 opening hours, B10 renewable share, A5 helpdesk phone, A16 to A19 parking spaces. Hover a header for the name. The full table for every operator is in the CSV below.</p>

<h2>Fields the extension adds, and whether they have arrived</h2>
<p>The extension defines new fields and promotes existing optional ones to mandatory. None of the new ones is populated in the feed yet; the count below is checked daily and the page updates on the day the first operator fills one in.</p>
<div class="tbl-wrap"><table>
<thead><tr><th>Field</th><th class="num">AFIR row</th><th>Carries</th><th class="num">Populated today</th></tr></thead>
<tbody>
{newrows}
</tbody></table></div>

<h2>Three things the register does say</h2>
<ul>
<li><b>Status.</b> {n(unknown)} charge points report status UNKNOWN, which the extension maps to non-operational. For {f['status']:.1f}% of points the operator does say whether the post works, and this site's <a href="/ev-charging">map</a> and operator pages have tracked that status every 30 minutes since September 2026.</li>
<li><b>Power.</b> Point maximum power is published for {f['power']:.1f}% of points. For the rest it has to be derived from voltage and current, which the extension explicitly allows (row B6) and which the map does.</li>
<li><b>Idle fees.</b> {idle:.1f}% of points carry a PARKING_TIME price component, the operator's own fee for staying plugged in after charging. That is separate from the municipal parking tariff under the post, which <a href="/blog/charging-stop-costs">adds 38% to a city-centre stop</a> and which no register field carries at all.</li>
</ul>

<div class="warnbox">
<p><b>What this scorecard is not.</b> It measures what operators declare in the national register, not what is installed on the street. A terminal that exists but is not flagged counts as absent, because under AFIR the register is the source every other service is meant to read. It also does not test update latency; a field can be present and stale.</p>
</div>

<h2>Method</h2>
<ol>
<li>Download the two OCPI files NDW publishes: <code>charging_point_locations_ocpi.json.gz</code> and <code>charging_point_tariffs_ocpi.json.gz</code>.</li>
<li>Keep every EVSE whose status is not REMOVED or PLANNED. The register also carries non-public points; the NDW feed is the public set.</li>
<li>Read each AFIR element from the OCPI field the NAP extension names for it (table above). A field counts as present when it is non-empty; a tariff counts as ad hoc when its <code>type</code> is AD_HOC_PAYMENT; a point counts as card payable when its capabilities include any of CREDIT_CARD_PAYABLE, DEBIT_CARD_PAYABLE, PED_TERMINAL or CHIP_CARD_SUPPORT.</li>
<li>Attribute the operator from <code>operator.name</code>, falling back to the OCPI party id. Trading names are used as published; an operator that appears under two names is two rows.</li>
<li>Rebuild daily. The snapshot date is in the page and the data files.</li>
</ol>
<p><b>Open data.</b> <a href="/data/afir-scorecard-2026.json">afir-scorecard-2026.json</a> and <a href="/data/afir-scorecard-2026.csv">afir-scorecard-2026.csv</a>, CC BY 4.0. Cite as "Parking Netherlands (Analytics Ascent), AFIR scorecard, {TODAY}". The feed history behind the status figures is in the <a href="https://github.com/AnalyticsAscentAkx/parking-netherlands-open-data">open data repository</a>.</p>

<h2>Questions</h2>
{faq_html}

<h2>Related</h2>
<ul>
<li><a href="/charging-gap">Where Dutch charging still falls short</a>: the 1.3 kW per car test applied to every 2 km neighbourhood.</li>
<li><a href="/blog/charging-stop-costs">Parking is 38% of an EV charging stop</a>: the two registers joined for 14 city centres.</li>
<li><a href="/ev-charging">Price my stop</a>: every public charger with the parking tariff under it, live status, one total.</li>
</ul>
<p class="cite">Sources: Regulation (EU) 2023/1804; Commission Implementing Regulation (EU) 2025/655; EVRoaming Foundation and NDW, OCPI NAP Data Extension 1.0, 24 September 2026; NDW open data, charging point locations and tariffs (OCPI 2.2.1), snapshot {TODAY}.</p>
</main>
</body>
</html>
"""
    return html

# ----------------------------------------------------------------- data files
def write_data(nat, rows, fields, n_loc, n_tar):
    d = ROOT / "data"; d.mkdir(exist_ok=True)
    nat_out = {"points": nat["points"], **{k: pct(nat, k) for k, *_ in OBLIGATIONS}, "idle_fee": pct(nat, "idle")}
    out = {"snapshot": TODAY, "source": [LOC_URL, TAR_URL], "licence": "CC BY 4.0", "page": f"{SITE}/afir-scorecard",
           "locations": n_loc, "tariffs": n_tar,
           "obligations": [{"key": k, "label": lab, "level": lvl, "afir_row": ref, "read_as": how} for k, lab, lvl, ref, how in OBLIGATIONS],
           "national": nat_out, "operators": rows,
           "fields": {k: dict(v) for k, v in fields.items()}}
    (d / "afir-scorecard-2026.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
    with (d / "afir-scorecard-2026.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["operator", "points"] + [k for k, *_ in OBLIGATIONS] + ["idle_fee", "met_of_10", "snapshot"])
        for r in rows:
            w.writerow([r["operator"], r["points"]] + [r[k] for k, *_ in OBLIGATIONS] + [r["idle"], r["met"], TODAY])
    return out

def main():
    L, T = load_feed()
    nat, ops, fields = analyse(L, T)
    rows = op_rows(ops)
    charts(nat, rows)
    write_data(nat, rows, fields, len(L), len(T))
    (ROOT / "afir-scorecard.html").write_text(render(nat, rows, fields, len(L), len(T)), "utf-8")
    print(f"afir-scorecard: {nat['points']:,} points, {len(rows)} operators >= 500 pts, ad hoc typed {fields['tariff_type'].get('AD_HOC_PAYMENT', 0)}, card {pct(nat, 'card')}%, contactless {pct(nat, 'contactless')}%")

if __name__ == "__main__":
    main()
