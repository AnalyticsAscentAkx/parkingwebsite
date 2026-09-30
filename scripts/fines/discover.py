#!/usr/bin/env python3
"""Stage 1 of the parking-fine dataset: find the decisions.

Searches CVDR through the KOOP SRU 2.0 service and caches one metadata row
per regulation version. Feasibility notes established by probing the service
on 2026-09-30, since the spec's guesses were close but not exact:

  * The endpoint is right: https://zoekservice.overheid.nl/sru/Search with
    x-connection=cvdr.
  * The index is `dcterms.title`, NOT `cql.textAndIndexes`, which the service
    rejects as an unsupported index. `cql.serverChoice` is rejected too.
  * The service answers with HTTP 406 while returning a perfectly valid SRU
    body. Do not treat the status code as failure; parse the body.
  * Full text lives at the KOOP repository, not the portal:
    repository.officiele-overheidspublicaties.nl/CVDR/<id>/<ver>/xml/<id>_<ver>.xml
    The portal URL also works but wraps the text in page furniture.

Coverage reality: only about 35 regulations carry the dedicated
"Kostenbesluit naheffingsaanslag parkeerbelasting" title. Most municipalities
put the cost clause inside their Verordening parkeerbelastingen instead, and
there are thousands of those across years. Both are searched here.

Usage:
  python3 discover.py                 # all queries, cached
  python3 discover.py --query kosten  # one named query
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent / "data" / "fines"
RAW = ROOT / "raw"
SRU = "https://zoekservice.overheid.nl/sru/Search"
UA = "parkingnetherlands-research (+https://parkingnetherlands.com/about)"
PAGE = 100

# Narrow first, broad last. The narrow ones are nearly pure signal; the broad
# ones need the extractor to decide whether a cost clause is present at all.
QUERIES = {
    "kostenbesluit": 'dcterms.title all "kostenbesluit naheffingsaanslag parkeerbelasting"',
    "naheffing": 'dcterms.title all "naheffingsaanslag"',
    "uitvoeringsbesluit": 'dcterms.title all "uitvoeringsbesluit parkeerbelastingen"',
    "verordening": 'dcterms.title all "verordening parkeerbelastingen"',
}

FIELDS = {
    "cvdr": r"<dcterms:identifier[^>]*>([^<]+)<",
    "title": r"<dcterms:title[^>]*>([^<]+)<",
    "municipality": r"<dcterms:creator[^>]*>([^<]+)<",
    "issued": r"<dcterms:issued[^>]*>([^<]+)<",
    "in_force": r"<overheidrg:inwerkingtredingDatum[^>]*>([^<]+)<",
    "withdrawn": r"<overheidrg:uitwerkingtredingDatum[^>]*>([^<]+)<",
    "org_type": r"<organisatietype[^>]*>([^<]+)<",
}


def get(url, tries=4):
    """Fetch with backoff. A 406 here carries a valid body, so it is not an
    error; only a missing body is."""
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if body and "<record" in body or "<numberOfRecords" in body:
                return body
            if e.code in (429, 500, 502, 503, 504) and i < tries - 1:
                time.sleep(2 ** i * 2)
                continue
            return body
        except Exception:
            if i < tries - 1:
                time.sleep(2 ** i * 2)
                continue
            return ""
    return ""


def search(cql, start=1, n=PAGE):
    u = (f"{SRU}?version=2.0&operation=searchRetrieve&x-connection=cvdr"
         f"&query={urllib.parse.quote(cql)}&startRecord={start}&maximumRecords={n}")
    return get(u)


def parse(xml):
    total = re.search(r"<numberOfRecords>(\d+)", xml)
    total = int(total.group(1)) if total else 0
    rows = []
    for rec in re.findall(r"<recordData>(.*?)</recordData>", xml, re.S):
        row = {}
        for k, pat in FIELDS.items():
            m = re.search(pat, rec)
            row[k] = m.group(1).strip() if m else None
        if not row.get("cvdr"):
            continue
        # CVDR123763_1 -> id CVDR123763, version 1. The version matters: the
        # time series needs superseded texts, not only what is in force.
        m = re.match(r"(CVDR\d+)_(\d+)", row["cvdr"])
        if m:
            row["cvdr_id"], row["version"] = m.group(1), int(m.group(2))
            row["xml_url"] = (
                "https://repository.officiele-overheidspublicaties.nl/CVDR/"
                f"{m.group(1)}/{m.group(2)}/xml/{m.group(1)}_{m.group(2)}.xml")
        rows.append(row)
    return total, rows


def run(name, cql, cap):
    out, start = [], 1
    total, rows = parse(search(cql, start))
    out += rows
    print(f"  {name}: {total} records advertised")
    while len(out) < min(total, cap) and rows:
        start += PAGE
        time.sleep(1.0)              # the handbook asks for gentle pacing
        _, rows = parse(search(cql, start))
        out += rows
        print(f"    {len(out)}/{min(total, cap)}", end="\r", flush=True)
    print(f"    collected {len(out)}          ")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", choices=sorted(QUERIES))
    ap.add_argument("--cap", type=int, default=400,
                    help="max records per query, keeps a first pass quick")
    a = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)

    todo = {a.query: QUERIES[a.query]} if a.query else QUERIES
    seen, all_rows = set(), []
    for name, cql in todo.items():
        for r in run(name, cql, a.cap):
            if r["cvdr"] in seen:
                continue
            seen.add(r["cvdr"])
            r["found_by"] = name
            all_rows.append(r)

    gem = {r["municipality"] for r in all_rows
           if r.get("org_type") == "Gemeente" and r.get("municipality")}
    (ROOT / "discovered.json").write_text(json.dumps(all_rows, indent=1, ensure_ascii=False))
    print(f"\n{len(all_rows)} unique regulation versions")
    print(f"{len(gem)} distinct municipalities")
    print(f"-> {ROOT / 'discovered.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
