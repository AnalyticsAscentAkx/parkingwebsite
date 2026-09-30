#!/usr/bin/env python3
"""Garage pages in four languages from scripts/garages.json.

  python3 scripts/i18n/build_garages.py            # all languages
  python3 scripts/i18n/build_garages.py en nl      # some

Writes garage/<slug>.html (English, canonical) and <lang>/garage/<slug>.html.
Every page: official tariffs, cost calculator, paid windows per weekday where
the register has them, the comparison with the rest of the city, nearby
alternatives, map, a charge-here action, a send-to-phone QR, FAQ schema,
hreflang to the three other languages. Run scripts/site/apply_chrome.py after.
"""
import json, math, re, sys, statistics, datetime, html as H, subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from i18n.strings import S, LANGS, PREFIX, city_name, city_url, garage_url, money, num, pct

ROOT = Path(__file__).resolve().parents[2]
SITE = "https://parkingnetherlands.com"
TODAY = datetime.date.today().isoformat()
YEAR = "2026"
CITY_LABEL = {"amsterdam": "Amsterdam", "rotterdam": "Rotterdam", "the-hague": "The Hague", "utrecht": "Utrecht", "eindhoven": "Eindhoven", "groningen": "Groningen",
              "maastricht": "Maastricht", "leiden": "Leiden", "haarlem": "Haarlem", "breda": "Breda", "delft": "Delft", "nijmegen": "Nijmegen", "tilburg": "Tilburg", "zwolle": "Zwolle"}
GARAGES = json.loads((ROOT / "scripts/garages.json").read_text("utf-8"))
def git_date(path):
    out = subprocess.run(["git", "log", "-1", "--format=%cs", "--", str(path)], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", str(path)], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return TODAY if dirty or not out else out
SNAP = git_date(ROOT / "scripts/garages.json")
DAYS = [("MAANDAG", "d_mon"), ("DINSDAG", "d_tue"), ("WOENSDAG", "d_wed"), ("DONDERDAG", "d_thu"), ("VRIJDAG", "d_fri"), ("ZATERDAG", "d_sat"), ("ZONDAG", "d_sun")]

def esc(s): return H.escape(str(s), quote=True)
def short(g): return g["name"].rsplit(" (", 1)[0]
def priced(g): return g.get("rate_hr") is not None
def is_free(g): return priced(g) and g["rate_hr"] == 0 and (g.get("rate_day") or 0) == 0
def is_anom(g): return priced(g) and not is_free(g) and (g["rate_hr"] > 15 or g["rate_hr"] == g["rate_day"] or (g["rate_3h"] or 0) > 45)
def is_flat(g): return is_anom(g) and g["rate_hr"] == g["rate_3h"] == g["rate_day"] and g["rate_hr"] <= 15
def hav(a, b):
    r = 6371; dla = math.radians(b["lat"] - a["lat"]); dlo = math.radians(b["lng"] - a["lng"])
    x = math.sin(dla/2)**2 + math.cos(math.radians(a["lat"]))*math.cos(math.radians(b["lat"]))*math.sin(dlo/2)**2
    return 2*r*math.asin(math.sqrt(x))
def stepped(g, hours):
    h1, h3, d1 = g["rate_hr"], g["rate_3h"], g["rate_day"]
    def u(m):
        if m <= 60: return h1*max(m/60, .5)
        if m <= 180: return h1 + (h3-h1)*(m-60)/120
        return h3 + (d1-h3)*(m-180)/1260
    m = hours*60
    if m <= 1440: return u(m)
    d, r = divmod(m, 1440); return d*d1 + min(u(r), d1)
def ordinal(lang, n):
    if lang == "en": return f"{n}{'th' if 10 <= n % 100 <= 20 else {1:'st',2:'nd',3:'rd'}.get(n % 10, 'th')}"
    if lang == "fr": return "1er" if n == 1 else f"{n}e"
    return f"{n}."  if lang == "de" else str(n)
def hhmm(v): v = min(v, 2400); return f"{v//100:02d}:{v%100:02d}" if v < 2400 else "24:00"

# ------------------------------------------------------------- city stats
STATS = {}
for c in CITY_LABEL:
    gs = [g for g in GARAGES if g["city"] == c]; pr = [g for g in gs if priced(g)]
    paid = [g for g in pr if not is_free(g) and not is_anom(g)]
    s = {"all": gs, "priced": pr, "paid": paid, "free": [g for g in pr if is_free(g)]}
    if paid:
        s["med_hr"] = statistics.median(g["rate_hr"] for g in paid); s["med_3h"] = statistics.median(g["rate_3h"] for g in paid); s["med_day"] = statistics.median(g["rate_day"] for g in paid)
        caps = [g["capacity"] for g in gs if g.get("capacity")]; s["med_cap"] = statistics.median(caps) if caps else None
    STATS[c] = s

def compare(lang, g):
    T = S[lang]; city = g["city"]; cname = city_name(lang, CITY_LABEL[city]); s = STATS[city]; name = esc(short(g))
    M = lambda v: money(lang, v)
    others = [o for o in s["all"] if o["slug"] != g["slug"]]
    for o in others: o["_d"] = hav(g, o)
    near_paid = sorted([o for o in others if priced(o) and not is_free(o) and not is_anom(o) and o["_d"] <= 1.0], key=lambda o: o["rate_3h"])
    idx = T["see_index"].format(slug=city, city=cname)
    parts, faq = [f"<h2>{T['h_compare'].format(name=name, city=cname)}</h2>"], []
    def rel(d, what):
        if abs(d) < 1: return T["rel_same"].format(what=what)
        return (T["rel_above"] if d > 0 else T["rel_below"]).format(p=f"{abs(d):.0f}", what=what)
    if priced(g) and not is_free(g) and not is_anom(g) and s.get("med_hr") is not None:
        paid = s["paid"]; n = len(paid)
        rank = 1 + sum(1 for o in paid if o["rate_hr"] < g["rate_hr"]); rankd = 1 + sum(1 for o in paid if o["rate_day"] < g["rate_day"])
        d_hr = (g["rate_hr"]-s["med_hr"])/s["med_hr"]*100 if s["med_hr"] else 0; d_day = (g["rate_day"]-s["med_day"])/s["med_day"]*100 if s["med_day"] else 0
        pos = T["pos_cheapest"] if rank <= max(1, math.ceil(n*.25)) else T["pos_cheaper"] if rank <= n/2 else T["pos_mid"] if rank <= math.ceil(n*.75) else T["pos_dear"]
        parts.append("<p>" + T["c_lead"].format(h1=M(g["rate_hr"]), name=name, rank=ordinal(lang, rank), n=n, city=cname, pos=pos, medh=M(s["med_hr"]), medd=M(s["med_day"]), relh=rel(d_hr, T["what_hour"]), reld=rel(d_day, T["what_day"]), rankd=ordinal(lang, rankd)) + " " + idx + "</p>")
        def cell(a, b):
            d = (a-b)/b*100 if b else None
            return T["same"] if d is None or abs(d) < 1 else f"{'+' if d > 0 else ''}{d:.0f}%"
        rows = "".join(f'<tr><td>{T[lab]}</td><td class="price">{M(g[k])}</td><td class="price">{M(s[mk])}</td><td class="num">{cell(g[k], s[mk])}</td></tr>' for lab, k, mk in (("r_1h","rate_hr","med_hr"),("r_3h","rate_3h","med_3h"),("r_24h","rate_day","med_day")))
        parts.append(f'<div class="tbl-wrap"><table><thead><tr><th>{T["th_stay"]}</th><th>{name}</th><th>{T["th_median"].format(city=cname)}</th><th>{T["th_diff"]}</th></tr></thead><tbody>{rows}</tbody></table></div>')
        typ = ", ".join(T["typical_item"].format(h=h, v=M(stepped(g, h))) for h in (2, 4, 8))
        be = g["rate_day"]/g["rate_hr"] if g["rate_hr"] else None
        be_txt = (" " + T["breakeven"].format(n=f"{be:.0f}", verdict=T["be_good"] if be <= 8 else T["be_ok"] if be <= 16 else T["be_bad"])) if be else ""
        parts.append("<p>" + T["typical"].format(list=typ) + be_txt + "</p>")
        if near_paid:
            a = near_paid[0]; save = stepped(g, 3) - stepped(a, 3)
            if save > .05: parts.append("<p>" + T["alt_saves"].format(url=garage_url(lang, a["slug"]), alt=esc(short(a)), m=f"{a['_d']*1000:.0f}", h1=M(a["rate_hr"]), save=M(save)) + "</p>")
            else: parts.append("<p>" + T["alt_none"].format(name=name, url=garage_url(lang, a["slug"]), alt=esc(short(a)), m=f"{a['_d']*1000:.0f}", h3=M(a["rate_3h"])) + "</p>")
        else: parts.append("<p>" + T["alt_isolated"].format(name=name) + "</p>")
        best = []
        if rank <= max(1, math.ceil(n*.25)): best.append(T["b_short"].format(city=cname))
        if g["rate_day"] <= s["med_day"]*.8: best.append(T["b_day"].format(p=f"{abs(d_day):.0f}"))
        if (g.get("ev_points") or 0) >= 4: best.append(T["b_ev"].format(n=g["ev_points"]))
        if g.get("is_pr"): best.append(T["b_pr"])
        if (g.get("capacity") or 0) and s.get("med_cap") and g["capacity"] >= s["med_cap"]*1.5: best.append(T["b_big"].format(n=num(lang, g["capacity"]), city=cname, med=f"{s['med_cap']:.0f}"))
        if g.get("max_height_cm") and g["max_height_cm"] < 200: best.append(T["b_low"].format(h=f"{g['max_height_cm']/100:.2f}".replace(".", "," if lang != "en" else ".")))
        if not best: best.append(T["b_typical"].format(city=cname))
        if n < 5: best.append(T["b_small"].format(n=n, city=cname))
        parts.append(f"<p><strong>{T['best']}</strong>: " + "; ".join(best) + ".</p>")
        faq.append((T["faq_q_cheap"].format(name=short(g), city=cname), T["faq_a_cheap"].format(name=short(g), h1=M(g["rate_hr"]), rank=ordinal(lang, rank), n=n, city=cname, medh=M(s["med_hr"]), medd=M(s["med_day"]), relh=rel(d_hr, T["what_hour"])).replace("<", "").replace(">", "")))
    elif is_free(g):
        txt = T["free_lead"].format(name=name, k=len(s["free"]), n=len(s["all"]), city=cname) + " "
        if s.get("med_hr") is not None: txt += T["free_cmp"].format(city=cname, medh=M(s["med_hr"]), medd=M(s["med_day"])) + " "
        parts.append("<p>" + txt + T["free_catch"] + " " + idx + "</p>")
        faq.append((T["faq_q_free"].format(name=short(g)), T["faq_a_free"].format(name=short(g), city=cname)))
    else:
        near = sorted([o for o in others if priced(o) and not is_free(o) and not is_anom(o)], key=lambda o: o["_d"])[:1]
        cmp = T["none_cmp"].format(city=cname, medh=M(s["med_hr"]), medd=M(s["med_day"])) if s.get("med_hr") is not None else ""
        if is_flat(g):
            txt = T["flat_lead"].format(name=name, fee=M(g["rate_hr"])) + " "
            if s.get("med_hr") is not None: txt += T["flat_cmp"].format(city=cname, medh=M(s["med_hr"]), medd=M(s["med_day"]), cmp=T["flat_less"] if g["rate_hr"] < s["med_hr"] else T["flat_same"]) + " "
            txt += (T["flat_pr"] if g.get("is_pr") else T["flat_other"]) + " "
        elif is_anom(g): txt = T["anom_lead"].format(name=name, h1=M(g["rate_hr"]), day=M(g["rate_day"]), city=cname) + " " + (cmp + " " if cmp else "")
        else: txt = T["none_lead"].format(name=name, k=len(s["all"])-len(s["priced"]), n=len(s["all"]), city=cname) + " " + (cmp + " " if cmp else "")
        if near: a = near[0]; txt += T["nearest_priced"].format(url=garage_url(lang, a["slug"]), alt=esc(short(a)), m=f"{a['_d']*1000:.0f}", h1=M(a["rate_hr"]), day=M(a["rate_day"])) + " "
        parts.append("<p>" + txt + idx + "</p>")
        if is_flat(g):
            parts.append(f"<p><strong>{T['best']}</strong>: " + (T["flat_best_pr"] if g.get("is_pr") else T["flat_best"]) + ".</p>")
            faq.append((T["faq_q_flat"].format(name=short(g)), T["faq_a_flat"].format(name=short(g), city=cname, fee=M(g["rate_hr"]))))
        else:
            ans = (cmp or "") + ((" " + re.sub(r"<[^>]+>", "", T["nearest_priced"].format(url="", alt=short(near[0]), m=f"{near[0]['_d']*1000:.0f}", h1=M(near[0]["rate_hr"]), day=M(near[0]["rate_day"])))) if near else "")
            faq.append((T["faq_q_near"].format(name=short(g)), ans.strip()))
    return "\n".join(parts), faq

def hours_block(lang, g):
    w = g.get("windows")
    if not w: return ""
    T = S[lang]; M = lambda v: money(lang, v)
    rows = []
    for key, lab in DAYS:
        segs = sorted(w.get(key, []))
        if not segs:
            rows.append(f"<tr><td>{T[lab]}</td><td>{T['notpaid']}</td><td class='price'>-</td><td class='price'>-</td></tr>"); continue
        for st, en, h1, d1 in segs:
            win = T["allday"] if st == 0 and en >= 2400 else f"{hhmm(st)} - {hhmm(en)}"
            rows.append(f"<tr><td>{T[lab]}</td><td>{win}</td><td class='price'>{M(h1)}</td><td class='price'>{M(d1)}</td></tr>")
    return (f"<h2>{T['h_hours']}</h2><p>{T['hours_lead']}</p><div class='tbl-wrap'><table><thead><tr><th>{T['th_day']}</th><th>{T['th_window']}</th><th>{T['th_first']}</th><th>{T['th_dayrate']}</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>")

def page(lang, g):
    T = S[lang]; city = g["city"]; cname = city_name(lang, CITY_LABEL[city]); name = short(g); M = lambda v: money(lang, v)
    url = SITE + garage_url(lang, g["slug"]); has = priced(g); free = is_free(g)
    if free: price_line = T["price_free"].format(name=name, city=cname); desc = T["g_desc_free"].format(name=name, city=cname)
    elif has: price_line = T["price_paid"].format(name=name, city=cname, h1=M(g["rate_hr"]), h3=M(g["rate_3h"]), day=M(g["rate_day"]), year=YEAR); desc = T["g_desc_paid"].format(name=name, city=cname, h1=M(g["rate_hr"]), h3=M(g["rate_3h"]), day=M(g["rate_day"]), year=YEAR)
    else: price_line = T["price_none"].format(name=name, city=cname); desc = T["g_desc_none"].format(name=name, city=cname)
    desc = desc[:158]
    cmp_html, cmp_faq = compare(lang, g)
    facility = {"@context": "https://schema.org", "@type": "ParkingFacility", "name": name, "url": url, "geo": {"@type": "GeoCoordinates", "latitude": g["lat"], "longitude": g["lng"]},
                "address": {"@type": "PostalAddress", "addressLocality": CITY_LABEL[city], "addressCountry": "NL"}, "publicAccess": True, "isAccessibleForFree": bool(free)}
    if g.get("capacity"): facility["maximumAttendeeCapacity"] = g["capacity"]
    feats = []
    if g.get("ev_points"): feats.append({"@type": "LocationFeatureSpecification", "name": "EV charging points", "value": g["ev_points"]})
    if g.get("max_height_cm"): feats.append({"@type": "LocationFeatureSpecification", "name": "Maximum vehicle height", "value": f"{g['max_height_cm']/100:.2f} m"})
    if feats: facility["amenityFeature"] = feats
    if has and not free: facility["priceRange"] = f"€{g['rate_hr']:.2f}/hour"
    bc = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": T["home"], "item": SITE + (PREFIX[lang] or "") + "/"},
        {"@type": "ListItem", "position": 2, "name": T["parking_in"].format(city=cname), "item": SITE + city_url(lang, city)},
        {"@type": "ListItem", "position": 3, "name": name, "item": url}]}
    faqs = [(T["faq_q_cost"].format(name=name, city=cname), price_line),
            (T["faq_q_where"].format(name=name), T["faq_a_where"].format(name=name, city=cname, lat=f"{g['lat']:.5f}", lng=f"{g['lng']:.5f}") + (T["faq_a_cap"].format(n=g["capacity"]) if g.get("capacity") else ""))] + cmp_faq
    faq = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faqs]}
    ld = json.dumps([facility, bc, faq], ensure_ascii=False).replace("</", "<\\/")
    # tariff table
    if has and not free:
        rows = (f'<div class="tbl-wrap"><table><thead><tr><th>{T["th_stay"]}</th><th>{T["th_tariff"]}</th><th>{T["th_eff"]}</th></tr></thead><tbody>'
                f'<tr><td>{T["r_1h"]}</td><td class="price">{M(g["rate_hr"])}</td><td class="price">{M(g["rate_hr"])}</td></tr>'
                f'<tr><td>{T["r_3h"]}</td><td class="price">{M(g["rate_3h"])}</td><td class="price">{M(g["rate_3h"]/3)}</td></tr>'
                f'<tr><td>{T["r_24h"]}</td><td class="price">{M(g["rate_day"])}</td><td class="price">{M(g["rate_day"]/24)}</td></tr></tbody></table></div>'
                f'<p style="font-size:12.5px;color:var(--mut);margin-top:10px">{T["tariff_note"]}</p>')
    elif free: rows = f'<p><span class="badge badge-ok">{T["free_badge"]}</span> · {T["free_note"]}</p>'
    else: rows = f'<p><span class="badge badge-line">{T["none_badge"]}</span> · {T["none_note"]}</p>'
    facts = ""
    if g.get("capacity"): facts += f'<tr><td>{T["f_capacity"]}</td><td class="num">{T["f_spaces"].format(n=num(lang, g["capacity"]))}</td></tr>'
    if g.get("ev_points") is not None: facts += f'<tr><td>{T["f_ev"]}</td><td class="num">{g["ev_points"] or T["f_none"]}</td></tr>'
    if g.get("max_height_cm"): facts += f'<tr><td>{T["f_height"]}</td><td class="num">{g["max_height_cm"]/100:.2f} m</td></tr>'
    facts += f'<tr><td>{T["f_type"]}</td><td>{T["f_type_pr"] if g.get("is_pr") else T["f_type_garage"]}</td></tr><tr><td>{T["f_coords"]}</td><td class="num">{g["lat"]:.5f}, {g["lng"]:.5f}</td></tr><tr><td>{T["f_code"]}</td><td class="num">{esc(g["areaid"])}</td></tr>'
    nearby = sorted([o for o in STATS[city]["all"] if o["slug"] != g["slug"]], key=lambda o: hav(g, o))[:5]
    near_html = "".join(f'<tr><td><a href="{garage_url(lang, n["slug"])}" style="font-weight:600;color:var(--ink);text-decoration:none">{esc(short(n))}</a></td><td class="num">{hav(g, n)*1000:.0f} m</td><td class="price">{(M(n["rate_hr"]) + "/h") if n.get("rate_hr") else "-"}</td></tr>' for n in nearby)
    calc = ""
    if has and not free:
        dec = "." if lang == "en" else ","
        calc = f"""<div class="card card-pad" style="margin-top:22px"><div class="eyebrow" style="margin-bottom:10px">{T["calc_h"]}</div>
  <label for="dur" style="font-size:14px;font-weight:600">{T["calc_dur"]}: <span id="durL" class="num">3 h</span></label>
  <input type="range" id="dur" min="1" max="48" value="3" step="1" style="width:100%;margin:12px 0;accent-color:var(--sig)">
  <div style="font-size:15px">{T["calc_est"]}: <span id="durC" class="num" style="font-size:22px;font-weight:600;color:var(--ink)">{M(g["rate_3h"])}</span></div></div>
<script>(function(){{var h1={g['rate_hr']},h3={g['rate_3h']},d1={g['rate_day']};function cost(h){{var m=h*60;function u(m){{if(m<=60)return h1*Math.max(m/60,.5);if(m<=180)return h1+(h3-h1)*(m-60)/120;return h3+(d1-h3)*(m-180)/1260;}}if(m<=1440)return u(m);var d=Math.floor(m/1440),r=m%1440;return d*d1+Math.min(u(r),d1);}}
var s=document.getElementById('dur');s.addEventListener('input',function(){{document.getElementById('durL').textContent=s.value+' h';var v=cost(+s.value).toFixed(2);document.getElementById('durC').textContent={'"€"+v' if lang != 'fr' else 'v.replace(".",",")+" €"'}{'' if lang in ('en','fr') else '.replace(".",",")'};}});}})();</script>"""
    alts = "".join(f'<link rel="alternate" hreflang="{l}" href="{SITE}{garage_url(l, g["slug"])}">' for l in LANGS) + f'<link rel="alternate" hreflang="x-default" href="{SITE}{garage_url("en", g["slug"])}">'
    other = " · ".join(f'<a href="{garage_url(l, g["slug"])}" hreflang="{l}" lang="{l}">{S[l]["lang_name"]}</a>' for l in LANGS if l != lang)
    charge = f'<a class="btn btn-ghost btn-sm" href="/ev-charging?lat={g["lat"]}&lng={g["lng"]}&zoom=17">{T["btn_charge"].format(n=g["ev_points"])}</a>' if (g.get("ev_points") or 0) > 0 else ""
    op = f'<a class="btn btn-dark btn-sm" target="_blank" rel="noopener nofollow" href="{esc(g["op_url"])}">{T["btn_operator"]}</a>' if g.get("op_url") else ""
    gmaps = f"https://www.google.com/maps/dir/?api=1&destination={g['lat']},{g['lng']}"
    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2889604222343187" crossorigin="anonymous"></script>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(T["g_title"].format(name=name, city=cname, year=YEAR))}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{url}">
{alts}
<link rel="stylesheet" href="/site.css">
<link rel="icon" href="/favicon.ico?v=2" sizes="any"><link rel="icon" type="image/svg+xml" href="/favicon.svg?v=2">
<meta property="og:type" content="place"><meta property="og:url" content="{url}"><meta property="og:title" content="{esc(T["g_title"].format(name=name, city=cname, year=YEAR))}"><meta property="og:description" content="{esc(desc)}"><meta property="og:image" content="{SITE}/og-image.png">
<meta name="robots" content="index, follow">
<script type="application/ld+json">{ld}</script>
<style>
.gwrap{{max-width:860px;margin:0 auto;padding:0 24px}}
.crumb{{font-size:13px;color:var(--mut);padding:18px 0 0}}.crumb a{{color:var(--mut);text-decoration:none}}.crumb a:hover{{color:var(--ink)}}
.ghead h1{{font-size:clamp(1.6rem,3vw,2.2rem);font-weight:800;letter-spacing:-.03em;color:var(--ink);line-height:1.15;margin:10px 0 8px}}
.ghead .sub{{color:var(--mut);font-size:15px;margin-bottom:18px}}
.gwrap p{{margin:0 0 12px;line-height:1.6}}
#gmap{{height:300px;border-radius:var(--r-lg);border:1px solid var(--line);margin:26px 0;box-shadow:var(--sh)}}
.gwrap h2{{font-size:1.25rem;font-weight:800;letter-spacing:-.02em;color:var(--ink);margin:34px 0 14px}}
.qr{{display:none;margin-top:14px;padding:14px;border:1px solid var(--line);border-radius:var(--r-lg);background:#fff;max-width:280px;text-align:center}}
.qr.is-on{{display:block}}.qr img,.qr canvas{{display:block;margin:0 auto 8px}}.qr small{{color:var(--mut);font-size:12.5px;line-height:1.5}}
.glangs{{font-size:13.5px;color:var(--mut);margin:26px 0 0}}.glangs a{{color:var(--sig);font-weight:600;text-decoration:none}}
</style>
</head>
<body>
<div class="gwrap">
  <div class="crumb"><a href="{PREFIX[lang] or '/'}">{T["home"]}</a> / <a href="{city_url(lang, city)}">{T["parking_in"].format(city=cname)}</a> / {esc(name)}</div>
  <header class="ghead">
    <h1>{esc(name)}</h1>
    <p class="sub">{(T["g_sub_pr"] if g.get("is_pr") else T["g_sub_garage"]).format(city=cname)}{' · <span class="badge badge-pr">P+R</span>' if g.get("is_pr") else ''}</p>
    <div style="display:flex;gap:10px;flex-wrap:wrap">
      <a class="btn btn-primary btn-sm" target="_blank" rel="noopener" href="{gmaps}">{T["btn_directions"]}</a>
      <a class="btn btn-ghost btn-sm" href="/search?q={esc(name)} {esc(CITY_LABEL[city])}&lat={g['lat']}&lng={g['lng']}">{T["btn_compare"]}</a>
      {charge}
      <a class="btn btn-ghost btn-sm" href="{city_url(lang, city)}">{T["btn_guide"].format(city=cname)}</a>
      {op}
      <button type="button" class="btn btn-ghost btn-sm" id="qrBtn">{T["btn_phone"]}</button>
    </div>
    <div class="qr" id="qrBox"><div id="qrImg"></div><small>{T["qr_hint"]}</small></div>
  </header>
  <h2>{T["h_rates"]}</h2>
  <p style="font-size:15px;margin-bottom:14px">{esc(price_line)}</p>
  {rows}
  {calc}
  {hours_block(lang, g)}
  <h2>{T["h_facts"]}</h2>
  <div class="tbl-wrap"><table><tbody>{facts}</tbody></table></div>
  {cmp_html}
  <div id="gmap"></div>
  <h2>{T["h_nearby"]}</h2>
  <div class="tbl-wrap"><table><thead><tr><th>{T["th_garage"]}</th><th>{T["th_distance"]}</th><th>{T["th_rate"]}</th></tr></thead><tbody>{near_html}</tbody></table></div>
  <p class="glangs">{T["other_langs"]}: {other}</p>
  <p style="font-size:12.5px;color:var(--mut);margin:16px 0 60px">{T["source"].format(snap=SNAP, today=TODAY)}</p>
</div>
<script>
(function(){{
  function init(){{
    var css=document.createElement('link');css.rel='stylesheet';css.href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';document.head.appendChild(css);
    var js=document.createElement('script');js.src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
    js.onload=function(){{var map=L.map('gmap',{{scrollWheelZoom:false}}).setView([{g['lat']},{g['lng']}],15);
      L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',maxZoom:19}}).addTo(map);
      L.marker([{g['lat']},{g['lng']}]).addTo(map).bindPopup({json.dumps(name)}).openPopup();}};
    document.head.appendChild(js);
  }}
  if('IntersectionObserver' in window){{var o=new IntersectionObserver(function(e){{if(e[0].isIntersecting){{init();o.disconnect();}}}},{{rootMargin:'250px'}});o.observe(document.getElementById('gmap'));}} else init();
  var b=document.getElementById('qrBtn'),box=document.getElementById('qrBox'),done=false;
  b.addEventListener('click',function(){{box.classList.toggle('is-on');if(done||!box.classList.contains('is-on'))return;done=true;
    var s=document.createElement('script');s.src='https://cdnjs.cloudflare.com/ajax/libs/qrcode-generator/1.4.4/qrcode.min.js';
    s.onload=function(){{var q=qrcode(0,'M');q.addData({json.dumps(gmaps)});q.make();document.getElementById('qrImg').innerHTML=q.createSvgTag({{cellSize:4,margin:2}});if(window.track)window.track('send_to_phone',{{page:location.pathname}});}};
    document.head.appendChild(s);}});
}})();
</script>
</body>
</html>"""

if __name__ == "__main__":
    langs = [a for a in sys.argv[1:] if a in LANGS] or LANGS
    n = 0
    for lang in langs:
        out = ROOT / (PREFIX[lang].strip("/") + "/garage" if lang != "en" else "garage")
        out.mkdir(parents=True, exist_ok=True)
        for g in GARAGES:
            (out / f"{g['slug']}.html").write_text(page(lang, g), "utf-8"); n += 1
        print(f"{lang}: {len(GARAGES)} pages -> {out.relative_to(ROOT)}/")
    print("total", n)
