#!/usr/bin/env python3
"""
SEO enrichment pass. Idempotent: every block it inserts is wrapped in
<!-- x:start --> ... <!-- x:end --> markers and replaced on re-run.

  python3 scripts/seo/enrich_site.py            # run everything
  python3 scripts/seo/enrich_site.py garages    # only the garage pages
  python3 scripts/seo/enrich_site.py cities     # only the city garage lists
  python3 scripts/seo/enrich_site.py index      # only /parking-price-index + data files
  python3 scripts/seo/enrich_site.py sitemap    # only sitemap lastmod from git

What it adds
  garage/*.html   "How X compares in <city>" section with the garage's rank,
                  the city median at 1h/3h/24h, typical-stay costs, the cheapest
                  alternative within 1 km, a data-driven "best for" line, a Dutch
                  FAQ line, matching FAQPage JSON-LD, a shorter <title>, and an
                  honest data-snapshot date.
  <city>.html     a list linking every register-listed garage in that city.
  /parking-price-index  citable dataset page (schema.org Dataset) + CSV + JSON.
  sitemap.xml     per-URL <lastmod> from the file's last git commit.
"""
import json, math, re, statistics, subprocess, sys, datetime, html
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITE = "https://parkingnetherlands.com"
TODAY = datetime.date.today().isoformat()
YEAR = "2026"
CITY_LABEL = {
    "amsterdam": "Amsterdam", "rotterdam": "Rotterdam", "the-hague": "The Hague",
    "utrecht": "Utrecht", "eindhoven": "Eindhoven", "groningen": "Groningen",
    "maastricht": "Maastricht", "leiden": "Leiden", "haarlem": "Haarlem",
    "breda": "Breda", "delft": "Delft", "nijmegen": "Nijmegen",
    "tilburg": "Tilburg", "zwolle": "Zwolle",
}
GARAGES = json.loads((ROOT / "scripts/garages.json").read_text("utf-8"))

def git_date(path):
    out = subprocess.run(["git", "log", "-1", "--format=%cs", "--", str(path)],
                         cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return out or TODAY

DATA_DATE = git_date(ROOT / "scripts/garages.json")

def esc(s): return html.escape(str(s), quote=True)
def eur(v): return f"€{v:,.2f}"
def short_name(g): return g["name"].rsplit(" (", 1)[0]
def priced(g): return g.get("rate_hr") is not None
def is_free(g): return priced(g) and g["rate_hr"] == 0 and (g.get("rate_day") or 0) == 0
def is_anomalous(g):
    """Register rows that are not a normal hourly product: > €15 for the first hour, or a first hour priced like a full day."""
    return priced(g) and not is_free(g) and (g["rate_hr"] > 15 or g["rate_hr"] == g["rate_day"] or (g["rate_3h"] or 0) > 45)

def haversine(a, b):
    r = 6371
    dla = math.radians(b["lat"] - a["lat"]); dlo = math.radians(b["lng"] - a["lng"])
    x = math.sin(dla/2)**2 + math.cos(math.radians(a["lat"]))*math.cos(math.radians(b["lat"]))*math.sin(dlo/2)**2
    return 2*r*math.asin(math.sqrt(x))

def stepped_cost(g, hours):
    h1, h3, d1 = g["rate_hr"], g["rate_3h"], g["rate_day"]
    def u(m):
        if m <= 60: return h1*max(m/60, .5)
        if m <= 180: return h1 + (h3-h1)*(m-60)/120
        return h3 + (d1-h3)*(m-180)/1260
    m = hours*60
    if m <= 1440: return u(m)
    d, r = divmod(m, 1440)
    return d*d1 + min(u(r), d1)

def replace_block(html_text, key, block, anchor_re):
    """Replace an existing marked block, or insert before the first anchor match."""
    start, end = f"<!-- {key}:start -->", f"<!-- {key}:end -->"
    wrapped = f"{start}\n{block}\n{end}"
    if start in html_text and end in html_text:
        return re.sub(re.escape(start) + r".*?" + re.escape(end), lambda m: wrapped, html_text, count=1, flags=re.S)
    m = re.search(anchor_re, html_text, re.S)
    if not m:
        return None
    return html_text[:m.start()] + wrapped + "\n" + html_text[m.start():]

# ----------------------------------------------------------------- city stats
def city_stats():
    stats = {}
    for c in CITY_LABEL:
        gs = [g for g in GARAGES if g["city"] == c]
        pr = [g for g in gs if priced(g)]
        paid = [g for g in pr if not is_free(g) and not is_anomalous(g)]
        s = {"all": gs, "priced": pr, "paid": paid, "n": len(gs), "n_priced": len(pr),
             "free": [g for g in pr if is_free(g)], "pr": [g for g in gs if g.get("is_pr")],
             "ev_points": sum(g.get("ev_points") or 0 for g in gs),
             "capacity": sum(g.get("capacity") or 0 for g in gs)}
        if paid:
            s["med_hr"] = statistics.median(g["rate_hr"] for g in paid)
            s["med_3h"] = statistics.median(g["rate_3h"] for g in paid)
            s["med_day"] = statistics.median(g["rate_day"] for g in paid)
            pos_hr = [g for g in paid if g["rate_hr"] > 0] or paid
            s["cheapest"] = min(pos_hr, key=lambda g: (g["rate_3h"], g["rate_day"]))
            s["dearest"] = max(paid, key=lambda g: (g["rate_3h"], g["rate_day"]))
            s["cheapest_day"] = min(paid, key=lambda g: g["rate_day"])
            caps = [g["capacity"] for g in gs if g.get("capacity")]
            s["med_cap"] = statistics.median(caps) if caps else None
        stats[c] = s
    return stats

STATS = city_stats()

def ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1:'st',2:'nd',3:'rd'}.get(n % 10, 'th')}"

def pct(a, b):
    if not b: return None
    return (a-b)/b*100

def delta_cell(a, b):
    d = pct(a, b)
    if d is None: return "n/a"
    if abs(d) < 1: return "same as median"
    return f"{'+' if d > 0 else ''}{d:.0f}%"

# ------------------------------------------------------------ garage section
def compare_block(g):
    city, cname = g["city"], CITY_LABEL[g["city"]]
    s = STATS[city]; name = short_name(g)
    others = [o for o in s["all"] if o["slug"] != g["slug"]]
    for o in others: o["_d"] = haversine(g, o)
    near_paid = sorted([o for o in others if priced(o) and not is_free(o) and o["_d"] <= 1.0], key=lambda o: o["rate_3h"])
    idx_link = f'<a href="/parking-price-index#{city}">{cname} in the Netherlands Parking Price Index</a>'
    faq = []
    parts = [f"<h2>How {esc(name)} compares in {cname}</h2>"]

    if priced(g) and not is_free(g) and not is_anomalous(g) and s.get("med_hr") is not None:
        paid = s["paid"]; n = len(paid)
        rank = 1 + sum(1 for o in paid if o["rate_hr"] < g["rate_hr"])
        rank_day = 1 + sum(1 for o in paid if o["rate_day"] < g["rate_day"])
        d_hr = pct(g["rate_hr"], s["med_hr"]); d_day = pct(g["rate_day"], s["med_day"])
        pos = ("one of the cheapest" if rank <= max(1, math.ceil(n*0.25)) else
               "cheaper than most" if rank <= n/2 else
               "mid-priced" if rank <= math.ceil(n*0.75) else "one of the more expensive")
        def rel(d, what):
            if abs(d) < 1: return f"in line with the median for {what}"
            return f"{abs(d):.0f}% {'above' if d > 0 else 'below'} the median for {what}"
        lead = (f"At {eur(g['rate_hr'])} for the first hour, {esc(name)} ranks {ordinal(rank)} of {n} priced garages in {cname}, "
                f"which makes it {pos} options in the city. The {cname} median is {eur(s['med_hr'])} per hour and {eur(s['med_day'])} per 24 hours, "
                f"so this garage is {rel(d_hr, 'an hour')} and {rel(d_day, 'a full day')} (ranked {ordinal(rank_day)} of {n} on the day rate).")
        parts.append(f"<p>{lead} See {idx_link}.</p>")
        rows = "".join(
            f"<tr><td>{lab}</td><td class=\"price\">{eur(g[k])}</td><td class=\"price\">{eur(s[mk])}</td><td class=\"num\">{delta_cell(g[k], s[mk])}</td></tr>"
            for lab, k, mk in (("1 hour", "rate_hr", "med_hr"), ("3 hours", "rate_3h", "med_3h"), ("24 hours", "rate_day", "med_day")))
        parts.append(f'<div class="tbl-wrap"><table><thead><tr><th>Stay</th><th>{esc(name)}</th><th>{cname} median</th><th>Difference</th></tr></thead><tbody>{rows}</tbody></table></div>')
        typ = ", ".join(f"{h} hours {eur(stepped_cost(g, h))}" for h in (2, 4, 8))
        breakeven = g["rate_day"]/g["rate_hr"] if g["rate_hr"] else None
        be_txt = (f" The 24-hour rate equals about {breakeven:.0f} hours at the first-hour price, so a long day here is "
                  f"{'good value' if breakeven <= 8 else 'priced like the hourly rate' if breakeven <= 16 else 'expensive; look at a P+R site instead'}.") if breakeven else ""
        parts.append(f"<p>Typical weekday stays under the stepped tariff: {typ}.{be_txt}</p>")
        if near_paid:
            alt = near_paid[0]
            saving = stepped_cost(g, 3) - stepped_cost(alt, 3)
            if saving > 0.05:
                parts.append(f'<p>Cheapest alternative within 1 km: <a href="/garage/{alt["slug"]}">{esc(short_name(alt))}</a> at {alt["_d"]*1000:.0f} m, '
                             f'{eur(alt["rate_hr"])} per hour. Walking there saves {eur(saving)} on a 3-hour stay.</p>')
            else:
                parts.append(f'<p>No priced garage within 1 km beats {esc(name)} on a 3-hour stay. The nearest, '
                             f'<a href="/garage/{alt["slug"]}">{esc(short_name(alt))}</a> at {alt["_d"]*1000:.0f} m, charges {eur(alt["rate_3h"])} for 3 hours.</p>')
        else:
            parts.append(f"<p>There is no other priced garage within 1 km in the register, so {esc(name)} has little direct competition on price at this spot.</p>")
        best = []
        if rank <= max(1, math.ceil(n*0.25)): best.append(f"short stays: among the cheapest first-hour rates in {cname}")
        if g["rate_day"] <= s["med_day"]*0.8: best.append(f"full days: day rate {abs(d_day):.0f}% under the city median")
        if len(paid) < 5: best.append(f"note: only {n} garages in {cname} publish a tariff, so the city median is indicative")
        if (g.get("ev_points") or 0) >= 4: best.append(f"EV drivers: {g['ev_points']} charging points on site")
        if g.get("is_pr"): best.append("park and ride: leave the car here and take public transport into the centre")
        if (g.get("capacity") or 0) and s.get("med_cap") and g["capacity"] >= s["med_cap"]*1.5: best.append(f"busy days: {g['capacity']} spaces, well above the {cname} median of {s['med_cap']:.0f}")
        if g.get("max_height_cm") and g["max_height_cm"] < 200: best.append(f"cars only: the {g['max_height_cm']/100:.2f} m height limit rules out most vans and roof boxes")
        if not best: best.append(f"a typical {cname} garage on price; compare the alternatives above before you commit")
        parts.append("<p><strong>Best for</strong>: " + "; ".join(best) + ".</p>")
        faq.append((f"Is {name} cheap compared with other garages in {cname}?",
                    f"{name} charges {eur(g['rate_hr'])} for the first hour, ranked {ordinal(rank)} of {n} priced garages in {cname}. "
                    f"The city median is {eur(s['med_hr'])} per hour and {eur(s['med_day'])} per 24 hours; this garage is {rel(d_hr, 'an hour')}."))
        nl = (f"Parkeren bij {name} in {cname} kost {eur(g['rate_hr']).replace('.', ',')} voor het eerste uur, "
              f"{eur(g['rate_3h']).replace('.', ',')} voor 3 uur en {eur(g['rate_day']).replace('.', ',')} per 24 uur "
              f"(officieel dagtarief {YEAR} uit het nationaal parkeerregister). De mediaan in {cname} is {eur(s['med_hr']).replace('.', ',')} per uur.")
    elif is_free(g):
        parts.append(f"<p>The register lists {esc(name)} at €0.00, one of {len(s['free'])} free facilities among the {s['n']} register-listed garages and P+R sites in {cname}. "
                     + (f"A paid garage in {cname} costs a median {eur(s['med_hr'])} per hour and {eur(s['med_day'])} per day, so parking here and walking or taking transit in is the cheapest option in the city. " if s.get("med_hr") is not None else "")
                     + f"Free registers often hide a catch: a public-transport ticket condition, a maximum stay, or a barrier that closes at night. Check signage on arrival. See {idx_link}.</p>")
        faq.append((f"Is {name} really free?", f"The national parking register lists a €0.00 tariff for {name} in {cname}. Conditions such as a maximum stay or a transit-ticket requirement are not encoded in the register; check signage on arrival."))
        nl = f"Parkeren bij {name} in {cname} is volgens het nationaal parkeerregister gratis. Let op eventuele voorwaarden (maximale parkeerduur, OV-kaartje) op de borden ter plaatse."
    else:
        near_any = sorted([o for o in others if priced(o) and not is_free(o) and not is_anomalous(o)], key=lambda o: o["_d"])[:1]
        flat = is_anomalous(g) and g["rate_hr"] == g["rate_3h"] == g["rate_day"] and g["rate_hr"] <= 15
        med_txt = (f"Priced garages in {cname} charge a median {eur(s['med_hr'])} per hour and {eur(s['med_day'])} per 24 hours" if s.get("med_hr") is not None else "")
        if flat:
            txt = (f"{esc(name)} is a flat-fee facility: the register lists {eur(g['rate_hr'])} whether you stay one hour or 24. "
                   + (f"{med_txt}, so a whole day here costs {'less than' if g['rate_hr'] < s['med_hr'] else 'about the same as'} a single hour in a typical {cname} garage. " if med_txt else "")
                   + ("Flat P+R fees usually require a public-transport ticket for the group and a same-day exit; check the signage. " if g.get("is_pr") else "Flat fees usually come with a maximum stay; check the signage. "))
        elif is_anomalous(g):
            txt = (f"The register tariff for {esc(name)} ({eur(g['rate_hr'])} for the first hour, {eur(g['rate_day'])} for 24 hours) does not look like a normal hourly product; "
                   f"it is most likely a season, coach or event product, so we leave it out of the {cname} comparison. " + (med_txt + ". " if med_txt else ""))
        else:
            txt = (f"The operator of {esc(name)} does not publish a tariff in the national register, which is the case for {s['n']-s['n_priced']} of the {s['n']} register-listed facilities in {cname}. "
                   + (med_txt + "; treat that as your benchmark when you read the signage. " if med_txt else ""))
        if near_any:
            a = near_any[0]
            txt += f'The nearest garage with a published hourly tariff is <a href="/garage/{a["slug"]}">{esc(short_name(a))}</a> at {a["_d"]*1000:.0f} m, {eur(a["rate_hr"])} per hour and {eur(a["rate_day"])} per day. '
        txt += f"See {idx_link}."
        parts.append(f"<p>{txt}</p>")
        if flat:
            parts.append("<p><strong>Best for</strong>: " + ("park and ride: leave the car here for a flat fee and take public transport into the centre" if g.get("is_pr") else "full days at a flat fee") + ".</p>")
            faq.append((f"How much does a full day at {name} cost?", f"{name} in {cname} charges a flat {eur(g['rate_hr'])} for any stay up to 24 hours according to the national parking register. " + med_txt + "." if med_txt else f"{name} in {cname} charges a flat {eur(g['rate_hr'])} for any stay up to 24 hours."))
            nl = f"{name} in {cname} heeft een vast tarief van {eur(g['rate_hr']).replace('.', ',')} voor elke parkeerduur tot 24 uur (nationaal parkeerregister). " + ("Bij P+R geldt meestal een OV-voorwaarde; zie de borden." if g.get("is_pr") else "")
        else:
            faq.append((f"What do garages near {name} charge?",
                        (med_txt + "." if med_txt else f"{name} publishes no usable tariff in the register.")
                        + (f" The nearest priced garage is {short_name(near_any[0])} at {near_any[0]['_d']*1000:.0f} m, {eur(near_any[0]['rate_hr'])} per hour." if near_any else "")))
            nl = (f"Voor {name} in {cname} staat geen bruikbaar uurtarief in het nationaal parkeerregister. "
                  + (f"Betaalde garages in {cname} rekenen mediaan {eur(s['med_hr']).replace('.', ',')} per uur." if s.get("med_hr") is not None else ""))

    parts.append(f'<p lang="nl" style="font-size:14px;color:var(--mut);border-left:3px solid var(--line);padding-left:12px"><strong>In het Nederlands:</strong> {esc(nl)}</p>')
    faq.append((f"Wat kost parkeren bij {name} in {cname}?", nl))
    return "\n".join(parts), faq

TITLE_RE = re.compile(r"<title>(.*?) Parking - Rates, Capacity &amp; Info \(([A-Za-z -]+) (\d{4})\)</title>")
GEN_RE = re.compile(r"Page generated \d{4}-\d{2}-\d{2}")
SNAP_RE = re.compile(r"Register snapshot \d{4}-\d{2}-\d{2} · Page updated \d{4}-\d{2}-\d{2}")
LD_RE = re.compile(r'(<script type="application/ld\+json">)(.*?)(</script>)', re.S)

def update_faq_jsonld(text, faq):
    m = LD_RE.search(text)
    if not m: return text
    try: data = json.loads(m.group(2))
    except json.JSONDecodeError: return text
    if not isinstance(data, list): return text
    for node in data:
        if node.get("@type") == "FAQPage":
            keep = [q for q in node["mainEntity"] if not q.get("_seo")]
            for qn, an in faq:
                keep.append({"@type": "Question", "name": qn, "acceptedAnswer": {"@type": "Answer", "text": an}, "_seo": True})
            node["mainEntity"] = keep
    out = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return text[:m.start(2)] + out + text[m.end(2):]

def strip_seo_flags(text):
    return text.replace(', "_seo": true', "")

def do_garages():
    by_slug = {g["slug"]: g for g in GARAGES}
    n_done = n_skip = 0
    for p in sorted((ROOT / "garage").glob("*.html")):
        if p.name == "index.html": continue
        g = by_slug.get(p.stem)
        if not g: n_skip += 1; continue
        t = p.read_text("utf-8")
        block, faq = compare_block(g)
        new = replace_block(t, "compare", block, r'\s*<div id="gmap"></div>')
        if new is None: n_skip += 1; continue
        cname = CITY_LABEL[g["city"]]; name = short_name(g)
        new = TITLE_RE.sub(lambda m: f"<title>{m.group(1)}, {cname}: Parking Rates &amp; Info {YEAR}</title>", new, count=1)
        new = re.sub(r"<title>(.*?), " + re.escape(cname) + r": Parking Rates &amp; Info \d{4}</title>",
                     lambda m: f"<title>{m.group(1)}, {cname}: Parking Rates &amp; Info {YEAR}</title>", new, count=1)
        stamp = f"Register snapshot {DATA_DATE} · Page updated {TODAY}"
        new = GEN_RE.sub(stamp, new, count=1); new = SNAP_RE.sub(stamp, new, count=1)
        new = strip_seo_flags(update_faq_jsonld(new, faq))
        if new != t: p.write_text(new, "utf-8"); n_done += 1
    print(f"garages: {n_done} updated, {n_skip} skipped")

# ------------------------------------------------------------- city lists
def do_cities():
    for city, cname in CITY_LABEL.items():
        p = ROOT / f"{city}.html"
        if not p.exists(): print("  missing", p.name); continue
        s = STATS[city]
        def key(g): return (0, g["rate_hr"], g["rate_day"]) if priced(g) and not is_free(g) else (1, 0, 0) if is_free(g) else (2, 0, 0)
        items = []
        for g in sorted(s["all"], key=key):
            if priced(g) and not is_free(g): tag = f"{eur(g['rate_hr'])}/h · {eur(g['rate_day'])}/day"
            elif is_free(g): tag = "free"
            else: tag = "no published tariff"
            pr = ' <em>P+R</em>' if g.get("is_pr") else ""
            items.append(f'<li><a href="/garage/{g["slug"]}">{esc(short_name(g))}</a>{pr}<span>{tag}</span></li>')
        med = f" Median priced garage: {eur(s['med_hr'])} per hour, {eur(s['med_day'])} per 24 hours." if s.get("med_hr") is not None else ""
        block = (f'<div class="glist-wrap"><h3 class="glist-h">All {s["n"]} register-listed garages and P+R sites in {cname}</h3>'
                 f'<p class="glist-p">Official drive-in tariffs from the national parking register, snapshot {DATA_DATE}. Cheapest first; free sites, then facilities without a published tariff, last.{med} '
                 f'Compare cities in the <a href="/parking-price-index#{city}">Netherlands Parking Price Index</a>.</p>'
                 f'<ul class="glist{" glist-3" if len(items) > 30 else ""}">{"".join(items)}</ul></div>')
        t = p.read_text("utf-8")
        # anchor: end of the section whose heading mentions garages; else before the footer
        anchor = None
        for m in re.finditer(r"<section\b.*?</section>", t, re.S):
            sec = m.group(0)
            h = re.search(r"<h2[^>]*>(.*?)</h2>", sec, re.S)
            if h and re.search(r"garage", h.group(1), re.I) and "/garage/" not in sec.split("<!-- garage-list:start -->")[0][:0]:
                anchor = m
                break
        if "<!-- garage-list:start -->" in t:
            new = replace_block(t, "garage-list", block, r"$")
        elif anchor:
            end = anchor.end() - len("</section>")
            # step back over the closing ct div(s)
            close = t.rfind("</div>", anchor.start(), end)
            new = t[:close] + f"<!-- garage-list:start -->\n{block}\n<!-- garage-list:end -->\n" + t[close:]
        else:
            new = re.sub(r"(<footer\b)", f"<section class=\"sec sec-w\"><div class=\"ct\"><!-- garage-list:start -->\n{block}\n<!-- garage-list:end --></div></section>\n\\1", t, count=1)
        if new != t: p.write_text(new, "utf-8")
        print(f"  {city}: {len(items)} garages listed ({'in garage section' if anchor else 'before footer'})")

# ------------------------------------------------------------- price index
def do_index():
    rows = []
    for city, cname in CITY_LABEL.items():
        s = STATS[city]
        rows.append({
            "city": cname, "slug": city, "facilities": s["n"], "priced": len(s["paid"]), "free": len(s["free"]),
            "park_and_ride": len(s["pr"]), "capacity_listed": s["capacity"], "ev_points": s["ev_points"],
            "median_1h_eur": s.get("med_hr"), "median_3h_eur": s.get("med_3h"), "median_24h_eur": s.get("med_day"),
            "cheapest_garage": short_name(s["cheapest"]) if s.get("cheapest") else None,
            "cheapest_1h_eur": s["cheapest"]["rate_hr"] if s.get("cheapest") else None,
            "cheapest_3h_eur": s["cheapest"]["rate_3h"] if s.get("cheapest") else None,
            "cheapest_slug": s["cheapest"]["slug"] if s.get("cheapest") else None,
            "most_expensive_garage": short_name(s["dearest"]) if s.get("dearest") else None,
            "most_expensive_1h_eur": s["dearest"]["rate_hr"] if s.get("dearest") else None,
            "most_expensive_3h_eur": s["dearest"]["rate_3h"] if s.get("dearest") else None,
            "most_expensive_slug": s["dearest"]["slug"] if s.get("dearest") else None,
            "cheapest_day_garage": short_name(s["cheapest_day"]) if s.get("cheapest_day") else None,
            "cheapest_day_eur": s["cheapest_day"]["rate_day"] if s.get("cheapest_day") else None,
            "cheapest_day_slug": s["cheapest_day"]["slug"] if s.get("cheapest_day") else None,
        })
    MIN_N = 5
    ranked = sorted([r for r in rows if r["median_1h_eur"] is not None and r["priced"] >= MIN_N], key=lambda r: (-r["median_1h_eur"], -r["median_24h_eur"]))
    small = sorted([r for r in rows if r["median_1h_eur"] is not None and r["priced"] < MIN_N], key=lambda r: -r["median_1h_eur"])
    paid_all = [g for g in GARAGES if priced(g) and not is_free(g) and not is_anomalous(g)]
    nat = {"garages": len(GARAGES), "priced": len(paid_all), "cities": len(rows),
           "med_hr": statistics.median(g["rate_hr"] for g in paid_all), "med_day": statistics.median(g["rate_day"] for g in paid_all),
           "min_hr": min(g["rate_hr"] for g in paid_all if g["rate_hr"] > 0), "max_hr": max(g["rate_hr"] for g in paid_all),
           "pr": sum(1 for g in GARAGES if g.get("is_pr")), "ev": sum(g.get("ev_points") or 0 for g in GARAGES),
           "free": sum(1 for g in GARAGES if is_free(g))}
    top, low = ranked[0], ranked[-1]
    spread = top["median_1h_eur"]/low["median_1h_eur"]
    # data files
    (ROOT / "data").mkdir(exist_ok=True)
    cols = [k for k in rows[0] if not k.endswith("_slug")]
    csv_lines = [",".join(cols)] + [",".join("" if r[c] is None else (f'"{r[c]}"' if isinstance(r[c], str) and "," in r[c] else str(r[c])) for c in cols) for r in rows]
    (ROOT / "data/parking-price-index-2026.csv").write_text("\n".join(csv_lines) + "\n", "utf-8")
    (ROOT / "data/parking-price-index-2026.json").write_text(json.dumps({
        "name": f"Netherlands Parking Price Index {YEAR}", "source": f"{SITE}/parking-price-index", "license": "https://creativecommons.org/licenses/by/4.0/",
        "register_snapshot": DATA_DATE, "published": TODAY, "national": nat, "cities": rows}, ensure_ascii=False, indent=1), "utf-8")

    def cell(v, money=True): return "n/a" if v is None else (eur(v) if money else f"{v:,}")
    trs = "".join(
        f'<tr id="{r["slug"]}"><td class="num">{i+1}</td><td><a href="/{r["slug"]}" style="font-weight:600;color:var(--ink);text-decoration:none">{r["city"]}</a></td>'
        f'<td class="price">{cell(r["median_1h_eur"])}</td><td class="price">{cell(r["median_3h_eur"])}</td><td class="price">{cell(r["median_24h_eur"])}</td>'
        f'<td><a href="/garage/{r["cheapest_slug"]}">{esc(r["cheapest_garage"])}</a> <span class="num" style="color:var(--mut)">{cell(r["cheapest_3h_eur"])} for 3 h</span></td>'
        f'<td><a href="/garage/{r["most_expensive_slug"]}">{esc(r["most_expensive_garage"])}</a> <span class="num" style="color:var(--mut)">{cell(r["most_expensive_3h_eur"])} for 3 h</span></td>'
        f'<td class="num">{r["priced"]}/{r["facilities"]}</td><td class="num">{r["park_and_ride"]}</td><td class="num">{r["ev_points"]}</td></tr>'
        for i, r in enumerate(ranked))
    for r in small:
        trs += (f'<tr id="{r["slug"]}"><td class="num">-</td><td><a href="/{r["slug"]}">{r["city"]}</a> <span style="color:var(--mut);font-size:12px">small sample</span></td>'
                f'<td class="price">{cell(r["median_1h_eur"])}</td><td class="price">{cell(r["median_3h_eur"])}</td><td class="price">{cell(r["median_24h_eur"])}</td>'
                f'<td><a href="/garage/{r["cheapest_slug"]}">{esc(r["cheapest_garage"])}</a> <span class="num" style="color:var(--mut)">{cell(r["cheapest_3h_eur"])} for 3 h</span></td>'
                f'<td><a href="/garage/{r["most_expensive_slug"]}">{esc(r["most_expensive_garage"])}</a> <span class="num" style="color:var(--mut)">{cell(r["most_expensive_3h_eur"])} for 3 h</span></td>'
                f'<td class="num">{r["priced"]}/{r["facilities"]}</td><td class="num">{r["park_and_ride"]}</td><td class="num">{r["ev_points"]}</td></tr>')
    unranked = [r for r in rows if r["median_1h_eur"] is None]
    for r in unranked:
        trs += f'<tr id="{r["slug"]}"><td class="num">-</td><td><a href="/{r["slug"]}">{r["city"]}</a></td><td colspan="5" style="color:var(--mut)">fewer than 2 priced garages in the register</td><td class="num">{r["priced"]}/{r["facilities"]}</td><td class="num">{r["park_and_ride"]}</td><td class="num">{r["ev_points"]}</td></tr>'
    day_rows = "".join(
        f'<tr><td>{r["city"]}</td><td><a href="/garage/{r["cheapest_day_slug"]}">{esc(r["cheapest_day_garage"])}</a></td><td class="price">{cell(r["cheapest_day_eur"])}</td><td class="price">{cell(r["median_24h_eur"])}</td>'
        f'<td class="num">{(1-r["cheapest_day_eur"]/r["median_24h_eur"])*100:.0f}%</td></tr>'
        for r in sorted([r for r in rows if r.get("cheapest_day_eur") is not None], key=lambda r: r["cheapest_day_eur"]))
    faq = [
        (f"Which Dutch city has the most expensive garage parking in {YEAR}?",
         f"{top['city']}: the median register-listed garage charges {eur(top['median_1h_eur'])} for the first hour and {eur(top['median_24h_eur'])} for 24 hours, based on {top['priced']} priced garages."),
        (f"Which Dutch city has the cheapest garage parking in {YEAR}?",
         f"Of the {len(ranked)} cities with at least {MIN_N} priced garages, {low['city']} is cheapest at a median {eur(low['median_1h_eur'])} per hour and {eur(low['median_24h_eur'])} per 24 hours. {top['city']} is {spread:.1f} times more expensive per hour."),
        ("How is the Netherlands Parking Price Index calculated?",
         f"We take every garage and P+R site listed for {nat['cities']} cities in the national parking register (NPR, CC0 open data, snapshot {DATA_DATE}), compute the weekday drive-in tariff for 1, 3 and 24 hours from the register's stepped fare tables, and report the median per city across the {nat['priced']} facilities that publish a tariff. Free sites and unpriced facilities are counted but excluded from the medians."),
        ("Can I reuse this data?",
         f"Yes. The index is published under CC BY 4.0. Download the CSV or JSON, and credit 'Parking Netherlands Parking Price Index {YEAR}' with a link to {SITE}/parking-price-index."),
    ]
    ld = [
        {"@context": "https://schema.org", "@type": "Dataset", "name": f"Netherlands Parking Price Index {YEAR}",
         "description": f"Median garage parking tariffs (1 h, 3 h, 24 h) for {nat['cities']} Dutch cities, with the cheapest and most expensive register-listed garage per city, P+R counts and EV charging points. Derived from the national parking register (NPR) open data, snapshot {DATA_DATE}.",
         "url": f"{SITE}/parking-price-index", "sameAs": f"{SITE}/data/parking-price-index-2026.json",
         "license": "https://creativecommons.org/licenses/by/4.0/", "isAccessibleForFree": True,
         "keywords": ["parking", "parking tariffs", "Netherlands", "parkeertarieven", "parkeergarage", "open data", "P+R"],
         "creator": {"@type": "Organization", "name": "Analytics Ascent", "url": "https://analyticascent.com"},
         "publisher": {"@type": "Organization", "name": "Parking Netherlands", "url": SITE},
         "temporalCoverage": YEAR, "dateModified": TODAY, "datePublished": TODAY,
         "spatialCoverage": {"@type": "Place", "name": "Netherlands", "address": {"@type": "PostalAddress", "addressCountry": "NL"}},
         "variableMeasured": ["median_1h_eur", "median_3h_eur", "median_24h_eur", "facilities", "priced", "park_and_ride", "ev_points"],
         "isBasedOn": {"@type": "Dataset", "name": "Nationaal Parkeer Register (NPR) open data", "license": "https://creativecommons.org/publicdomain/zero/1.0/"},
         "distribution": [
             {"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{SITE}/data/parking-price-index-2026.csv"},
             {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f"{SITE}/data/parking-price-index-2026.json"}]},
        {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE + "/"},
            {"@type": "ListItem", "position": 2, "name": "Parking Price Index", "item": f"{SITE}/parking-price-index"}]},
        {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]},
    ]
    faq_html = "".join(f"<details class=\"faq-item\"><summary>{esc(q)}</summary><p>{esc(a)}</p></details>" for q, a in faq)
    cite = f"Parking Netherlands ({YEAR}). Netherlands Parking Price Index {YEAR}: median garage tariffs in {nat['cities']} cities from national parking register data. {SITE}/parking-price-index"
    embed = esc(f'<a href="{SITE}/parking-price-index">Netherlands Parking Price Index {YEAR}</a>: {top["city"]} is the most expensive Dutch city for garage parking at a median {eur(top["median_1h_eur"])}/hour; {low["city"]} the cheapest at {eur(low["median_1h_eur"])}/hour (Parking Netherlands, national register data).')
    desc = f"Median garage parking rates in {nat['cities']} Dutch cities from {nat['priced']} register-listed tariffs: {top['city']} {eur(top['median_1h_eur'])}/h tops the index, {low['city']} {eur(low['median_1h_eur'])}/h is cheapest. Free CSV, CC BY."
    desc = desc[:158]
    ld_json = json.dumps(ld, ensure_ascii=False).replace("</", "<\\/")
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2889604222343187" crossorigin="anonymous"></script>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Netherlands Parking Price Index {YEAR}: Garage Rates by City</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{SITE}/parking-price-index">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/site.css">
<link rel="icon" href="/favicon.ico?v=2" sizes="any"><link rel="icon" type="image/svg+xml" href="/favicon.svg?v=2">
<meta property="og:type" content="article">
<meta property="og:url" content="{SITE}/parking-price-index">
<meta property="og:title" content="Netherlands Parking Price Index {YEAR}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:image" content="{SITE}/og-image.png">
<meta name="robots" content="index, follow">
<meta name="author" content="Analytics Ascent">
<link rel="alternate" type="text/csv" href="/data/parking-price-index-2026.csv" title="Netherlands Parking Price Index {YEAR} (CSV)">
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
h2{{font-size:1.35rem;font-weight:800;letter-spacing:-.02em;color:var(--ink);margin:40px 0 12px}}
.pi-wrap p{{line-height:1.65}}
table td,table th{{white-space:nowrap}}
table td a{{color:var(--ink);text-decoration:none;font-weight:600}}
.faq-item{{border:1px solid var(--line);border-radius:var(--r);background:#fff;padding:12px 16px;margin:8px 0}}
.faq-item summary{{font-weight:700;cursor:pointer}}
.faq-item p{{margin:10px 0 0;color:var(--mut)}}
pre.cite{{white-space:pre-wrap;background:#fff;border:1px solid var(--line);border-radius:var(--r);padding:14px;font-size:13px;font-family:var(--f-mono);color:var(--ink)}}
.pi-dl a{{margin-right:10px}}
</style>
</head>
<body>
<div class="pi-wrap">
  <header class="pi-hero">
    <div class="crumb" style="font-size:13px;color:var(--mut)"><a href="/" style="color:var(--mut);text-decoration:none">Home</a> / Parking Price Index</div>
    <h1>Netherlands Parking Price Index {YEAR}</h1>
    <p class="lead">What a garage really costs in each Dutch city, computed from every tariff in the national parking register rather than a handful of operator websites. {nat['cities']} cities, {nat['garages']} facilities, {nat['priced']} published tariffs. Open data, CC BY 4.0, free to cite.</p>
    <div class="pi-dl" style="margin-top:14px"><a class="btn btn-primary btn-sm" href="/data/parking-price-index-2026.csv" download>Download CSV</a><a class="btn btn-ghost btn-sm" href="/data/parking-price-index-2026.json">JSON</a><a class="btn btn-ghost btn-sm" href="#method">Methodology</a></div>
  </header>

  <div class="pi-stats">
    <div class="pi-stat"><b>{eur(nat['med_hr'])}</b><span>national median, first hour</span></div>
    <div class="pi-stat"><b>{eur(nat['med_day'])}</b><span>national median, 24 hours</span></div>
    <div class="pi-stat"><b>{top['city']}</b><span>most expensive city, {eur(top['median_1h_eur'])}/h median</span></div>
    <div class="pi-stat"><b>{low['city']}</b><span>cheapest city, {eur(low['median_1h_eur'])}/h median</span></div>
    <div class="pi-stat"><b>{spread:.1f}x</b><span>spread between the two</span></div>
    <div class="pi-stat"><b>{nat['pr']}</b><span>P+R sites in the register</span></div>
  </div>

  <h2 id="table">City ranking by median first-hour garage tariff</h2>
  <p>Medians are taken over the garages that publish a tariff in the register; a city is ranked only when at least five do. The cheapest and most expensive garage in each city are chosen on a 3-hour stay, the most common visit, so a facility with a free first hour and a steep second one does not win on a technicality. Click through to check the stepped tariff for your own stay length.</p>
  <div class="tbl-wrap"><table>
  <thead><tr><th>#</th><th>City</th><th>Median 1 h</th><th>Median 3 h</th><th>Median 24 h</th><th>Cheapest garage (3 h stay)</th><th>Most expensive (3 h stay)</th><th>Priced / listed</th><th>P+R</th><th>EV points</th></tr></thead>
  <tbody>{trs}</tbody></table></div>

  <h2>Cheapest day rate per city</h2>
  <p>For a full day, the spread inside a city is often bigger than the spread between cities. The cheapest published 24-hour rate in each city, against that city's median.</p>
  <div class="tbl-wrap"><table>
  <thead><tr><th>City</th><th>Cheapest 24 h garage</th><th>24 h rate</th><th>City median 24 h</th><th>Saving vs median</th></tr></thead>
  <tbody>{day_rows}</tbody></table></div>

  <h2>What the numbers say</h2>
  <p>{top['city']} garages cost a median {eur(top['median_1h_eur'])} for the first hour and {eur(top['median_24h_eur'])} for a day, {spread:.1f} times the hourly median of {low['city']} ({eur(low['median_1h_eur'])}). Across all {nat['priced']} priced facilities the first hour runs from {eur(nat['min_hr'])} to {eur(nat['max_hr'])}, so the choice of garage inside a city matters more than the choice of city. {nat['free']} register-listed facilities are free, almost all of them park-and-ride sites on the edge of town, and {nat['pr']} facilities are flagged as P+R. The register lists {nat['ev']:,} EV charging points across these garages.</p>
  <p>Every figure on this page is a weekday drive-in tariff. Pre-booked online rates, evening caps and resident discounts are not in the register and are not counted. That makes the index a fair comparison of the list price, and a ceiling on what a visitor pays.</p>

  <h2 id="method">Methodology</h2>
  <p>Source: the national parking register (NPR), published as CC0 open data. Snapshot {DATA_DATE}. For every facility we join the register's area, regulation, time-window and stepped-fare tables and compute the cost of a 1-hour, 3-hour and 24-hour weekday stay starting at 10:00. A city's median is taken over facilities with a computed tariff above zero. Cities with fewer than five priced facilities are shown with their figures but not ranked, because a median of two or three tariffs is not a city-level statistic. Capacity and EV points come from the register's specifications table. Anomalies (tariffs above €15 per hour, or a 1-hour price equal to the 24-hour price, which usually marks a coach or flat-fee product) are excluded. The garage pages linked from the table show the underlying tariff for each facility. Report an error via the <a href="/about#contact">contact page</a>.</p>

  <h2>Cite or embed</h2>
  <p>The index is CC BY 4.0. Copy the citation, or the one-line summary with a link.</p>
  <pre class="cite">{esc(cite)}</pre>
  <pre class="cite">{embed}</pre>

  <h2>Questions</h2>
  {faq_html}

  <p style="font-size:12.5px;color:var(--mut);margin:30px 0 60px">Published {TODAY} by <a href="/about">Analytics Ascent</a>. Register snapshot {DATA_DATE}. Underlying data: national parking register (NPR), CC0. Related: <a href="/all-cities">all cities compared</a>, <a href="/garage/">garage directory</a>, <a href="/street-map">street tariff map</a>, <a href="/parking-fines">fines guide</a>.</p>
</div>
</body>
</html>"""
    (ROOT / "parking-price-index.html").write_text(page, "utf-8")
    print(f"index: {len(ranked)} cities ranked; top {top['city']} {eur(top['median_1h_eur'])}, low {low['city']} {eur(low['median_1h_eur'])}, spread {spread:.1f}x")

# ---------------------------------------------------------------- sitemap
def do_sitemap():
    sm_path = ROOT / "sitemap.xml"
    sm = sm_path.read_text("utf-8")
    urls = re.findall(r"<loc>([^<]+)</loc>", sm)
    def path_for(u):
        rel = u[len(SITE):].lstrip("/")
        if rel == "": return ROOT / "index.html"
        if rel.endswith("/"): return ROOT / (rel + "index.html")
        return ROOT / (rel + ".html")
    changed = 0
    def fix(m):
        nonlocal changed
        loc = m.group(1); p = path_for(loc)
        d = git_date(p) if p.exists() else None
        if not d: return m.group(0)
        # a file with uncommitted changes gets today's date
        st = subprocess.run(["git", "status", "--porcelain", "--", str(p)], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        if st: d = TODAY
        new = f"<loc>{loc}</loc>{m.group(2)}<lastmod>{d}</lastmod>"
        if new != m.group(0): changed += 1
        return new
    sm2 = re.sub(r"<loc>([^<]+)</loc>(\s*)<lastmod>[^<]+</lastmod>", fix, sm)
    if f"{SITE}/parking-price-index" not in urls:
        sm2 = sm2.replace("</urlset>", f"  <url>\n    <loc>{SITE}/parking-price-index</loc>\n    <lastmod>{TODAY}</lastmod>\n    <changefreq>monthly</changefreq>\n    <priority>0.9</priority>\n  </url>\n</urlset>")
    sm_path.write_text(sm2, "utf-8")
    print(f"sitemap: {changed} lastmod values rewritten from git history")

if __name__ == "__main__":
    what = sys.argv[1:] or ["garages", "cities", "index", "sitemap"]
    for w in what:
        {"garages": do_garages, "cities": do_cities, "index": do_index, "sitemap": do_sitemap}[w]()
