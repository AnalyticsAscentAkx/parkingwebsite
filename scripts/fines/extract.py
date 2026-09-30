#!/usr/bin/env python3
"""Stage 2 and 3: fetch each decision and pull the figures out of the prose.

Every value carries the verbatim sentence it came from. That is not decoration:
it is what makes the dataset defensible to a journalist, and it is the only
cheap guard against a regex that matched the wrong euro amount in a document
full of euro amounts.

Dutch number format is parsed explicitly, never by locale: "6.000" is six
thousand and "91,26" is ninety-one point two six. Getting this wrong silently
turns a €91 cost into a €9,126 one, so the parser refuses anything ambiguous.

Usage:
  python3 extract.py                # everything in discovered.json
  python3 extract.py --limit 40
"""
import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent / "data" / "fines"
CACHE = ROOT / "raw" / "cvdr"
UA = "parkingnetherlands-research (+https://parkingnetherlands.com/about)"

# The national cap per naheffingsaanslag, for sanity-checking what a
# municipality says it may charge. Derived from the decisions themselves
# where stated; these are the widely published values.
NATIONAL_MAX = {
    2012: 54.00, 2013: 55.00, 2014: 57.00, 2015: 58.00, 2016: 59.00,
    2017: 60.00, 2018: 62.00, 2019: 63.00, 2020: 65.30, 2021: 66.00,
    2022: 67.00, 2023: 70.00, 2024: 75.00, 2025: 78.00, 2026: 82.00,
}


def nl_number(s):
    """Parse a Dutch-formatted number. Returns None rather than guessing.

    '6.000'    -> 6000.0      thousands dot
    '91,26'    -> 91.26       decimal comma
    '292.348,' -> 292348.0    trailing comma from ',-'
    '54'       -> 54.0
    """
    if s is None:
        return None
    s = s.strip().replace(" ", " ").rstrip(",.- ")
    s = s.replace(" ", "")
    if not s:
        return None
    if "," in s:
        whole, _, frac = s.rpartition(",")
        whole = whole.replace(".", "")
        if not frac.isdigit() or len(frac) > 2:
            return None
        if whole and not whole.isdigit():
            return None
        try:
            return float(f"{whole or 0}.{frac}")
        except ValueError:
            return None
    # No comma: dots can only be thousands separators here.
    if "." in s:
        parts = s.split(".")
        if all(p.isdigit() for p in parts) and all(len(p) == 3 for p in parts[1:]):
            return float("".join(parts))
        return None
    return float(s) if s.isdigit() else None


def sentence_around(text, idx, width=260):
    """The clause a value came from, trimmed to sentence edges where possible."""
    a = max(0, idx - width // 2)
    b = min(len(text), idx + width // 2)
    chunk = text[a:b]
    first = chunk.find(". ")
    if 0 < first < 60:
        chunk = chunk[first + 2:]
    return " ".join(chunk.split())


NUM = r"([0-9][0-9.  ]*(?:,[0-9]{1,2})?)"

PATTERNS = {
    # "Kosten € 292.348,-: 5.200 = € 56,20 per naheffingsaanslag"
    # Order matters, and the loose middle pattern is gone. Many decisions read
    # "De kosten per naheffingsaanslag worden als volgt berekend: ...
    #  Kosten EUR 1.471.163,76 : 1.500 = EUR 98,08". A pattern anchored on the
    # phrase alone grabbed the TOTAL sitting beside it and reported a
    # per-ticket cost of 1.4 million euro on 16 of 98 rows. Only accept a
    # figure that follows the division or is bound to "per naheffingsaanslag".
    "cost_per_ticket_eur": [
        rf"=\s*€?\s*{NUM}\s*per\s+naheffingsaanslag",
        rf"€\s*{NUM}\s*per\s+naheffingsaanslag",
        rf"=\s*€\s*{NUM}\s*(?=[\s.;,]|$)",
        rf"kosten\s+per\s+naheffingsaanslag\s*(?:bedraag\w*|is|van)?\s*€\s*{NUM}",
    ],
    # "Aantal naheffingsaanslagen 5.200"
    "budgeted_ticket_count": [
        rf"aantal\s+(?:op\s+te\s+leggen\s+)?naheffingsaanslagen[^0-9]{{0,40}}{NUM}",
        rf"naheffingsaanslagen[^0-9]{{0,20}}(?:begroot|geraamd)[^0-9]{{0,20}}{NUM}",
    ],
    # "Totaal € 292.348,-"
    "budgeted_total_cost_eur": [
        rf"totaal[^0-9€]{{0,30}}€\s*{NUM}",
        rf"kosten\s+€\s*{NUM}\s*,?-?\s*:",
    ],
    # "het maximale tarief van de naheffingsaanslag € 54,-"
    "charged_amount_eur": [
        rf"maxima\w*\s+tarief[^0-9€]{{0,60}}€\s*{NUM}",
        rf"maximumbedrag[^0-9€]{{0,40}}€\s*{NUM}",
        rf"bedraagt\s+de\s+naheffingsaanslag[^0-9€]{{0,30}}€\s*{NUM}",
        rf"vastgesteld\s+op\s+€\s*{NUM}",
    ],
}

YEAR = re.compile(r"\b(20[0-3][0-9])\b")


def fetch(url, cvdr):
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{cvdr}.xml"
    if p.is_file():
        return p.read_text(encoding="utf-8", errors="replace")
    for i in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=45) as r:
                t = r.read().decode("utf-8", "replace")
            p.write_text(t, encoding="utf-8")
            time.sleep(1.0)
            return t
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return ""
            time.sleep(2 ** i * 2)
        except Exception:
            time.sleep(2 ** i * 2)
    return ""


def plain(xml):
    body = re.sub(r"(?s)<(script|style)\b.*?</\1>", " ", xml)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", body)).split())


def extract(rec):
    xml = fetch(rec["xml_url"], rec["cvdr"])
    if not xml:
        return None
    text = plain(xml)
    out = {
        "municipality": rec.get("municipality"),
        "cvdr_id": rec.get("cvdr_id"),
        "version": rec.get("version"),
        "title": rec.get("title"),
        "in_force": rec.get("in_force"),
        "source_url": rec["xml_url"],
        "extraction_method": "regex",
        "chars": len(text),
    }

    # Year: prefer the in-force date, fall back to the newest year named.
    yr = None
    if rec.get("in_force"):
        m = YEAR.search(rec["in_force"])
        if m:
            yr = int(m.group(1))
    if yr is None:
        yrs = [int(y) for y in YEAR.findall(text)]
        yr = max(yrs) if yrs else None
    out["year"] = yr
    out["national_max_eur"] = NATIONAL_MAX.get(yr)

    found = 0
    for field, pats in PATTERNS.items():
        for pat in pats:
            m = re.search(pat, text, re.I)
            if not m:
                continue
            v = nl_number(m.group(1))
            if v is None:
                continue
            out[field] = v
            out[f"source_{field}"] = sentence_around(text, m.start())
            found += 1
            break
        else:
            out[field] = None
    c = out.get("cost_per_ticket_eur")
    if c is not None and not (20.0 <= c <= 400.0):
        out["flag_cost_implausible"] = True
        found -= 1

    out["fields_found"] = found
    out["confidence"] = round(found / len(PATTERNS), 2)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default="", help="substring filter on found_by")
    a = ap.parse_args()

    recs = json.loads((ROOT / "discovered.json").read_text())
    recs = [r for r in recs if r.get("org_type") == "Gemeente" and r.get("xml_url")]
    if a.only:
        recs = [r for r in recs if a.only in (r.get("found_by") or "")]
    if a.limit:
        recs = recs[:a.limit]

    rows = []
    for i, r in enumerate(recs, 1):
        row = extract(r)
        if row:
            rows.append(row)
        if i % 10 == 0 or i == len(recs):
            print(f"  {i}/{len(recs)} fetched", end="\r", flush=True)
    print()

    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "extracted.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False))

    got = [r for r in rows if r.get("cost_per_ticket_eur") or r.get("budgeted_ticket_count")]
    both = [r for r in rows if r.get("cost_per_ticket_eur") and r.get("budgeted_ticket_count")]
    print(f"documents parsed          : {len(rows)}")
    print(f"with at least one figure  : {len(got)}")
    print(f"with cost AND count       : {len(both)}")
    print(f"distinct municipalities   : {len({r['municipality'] for r in got if r['municipality']})}")
    print(f"-> {ROOT / 'extracted.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
