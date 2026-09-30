#!/usr/bin/env python3
"""One page a human will actually read, assembled from the day's sources.

The separate reports are all useful and nobody opens four files. This folds
the QA audit, the indexing watch and the Search Console pull into a single
ordered digest: what is broken, what changed, what to do.

Ordering is deliberate. Deploy state comes first, because every other finding
is conditional on it: a clean audit against a deployment that is hours behind
the repo is a false all-clear, which is exactly what happened on 2026-09-30.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
QA = REPO / "data" / "qa"
GSC = REPO / "data" / "gsc"


def load(p, default=None):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return default


def main():
    now = datetime.now(timezone.utc)
    out = [f"# Daily digest {now:%Y-%m-%d %H:%M} UTC", ""]

    issues = load(QA / "issues.json", {}) or {}
    all_i = issues.get("issues", [])
    hard = [i for i in all_i if i["level"] == "HARD"]
    warn = [i for i in all_i if i["level"] == "WARN"]

    # Deploy first. It qualifies everything else.
    deploy = [i for i in hard if i["where"] == "deploy"]
    if deploy:
        out += ["## Not deployed", "",
                f"**{deploy[0]['what']}**", "",
                "Every finding below was measured against the OLD live site, "
                "so fixes already committed will still show as broken.", ""]
    else:
        out += ["## Deploy", "", "Live site matches the repo.", ""]

    out += [f"## Site health: {len(hard)} hard, {len(warn)} warnings", ""]
    if not hard:
        out.append("No hard findings.")
    else:
        seen, shown = set(), 0
        for i in hard:
            if i["where"] == "deploy":
                continue
            key = i["what"][:40]
            if key in seen and shown > 12:
                continue
            seen.add(key)
            shown += 1
            out.append(f"- `{i['where']}` {i['what']}")
    out.append("")

    if warn:
        out += ["<details><summary>Warnings</summary>", ""]
        for i in warn[:40]:
            out.append(f"- `{i['where']}` {i['what']}")
        out += ["", "</details>", ""]

    # Indexing: the number that actually moves right now.
    hist = []
    p = GSC / "index_watch.jsonl"
    if p.is_file():
        hist = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    if hist:
        last = hist[-1]
        t = last["total"]
        pct = t["indexed"] / t["n"] * 100 if t["n"] else 0
        out += ["## Indexing", "",
                f"{t['indexed']} of {t['n']} sampled pages indexed ({pct:.0f}%).", ""]
        can = last.get("canaries") or {}
        if can:
            idx = [k for k, v in can.items() if v.get("verdict") == "PASS"]
            miss = [k for k, v in can.items() if v.get("verdict") != "PASS"]
            out.append(f"Key pages indexed: {', '.join(f'`{k}`' for k in idx) or 'none'}")
            if miss:
                out.append(f"Key pages NOT indexed: {', '.join(f'`{k}`' for k in miss)}")
            out.append("")
        if len(hist) > 1:
            prev = hist[-2]["total"]
            d = t["indexed"] - prev["indexed"]
            if d:
                out += [f"Change since last run: {d:+d} pages.", ""]

    # Search Console: demand, and what is closest to paying off.
    wl = load(GSC / "latest_worklist.json", {}) or {}
    tot = wl.get("totals") or {}
    if tot:
        out += ["## Search", "",
                f"{tot.get('clicks', 0):.0f} clicks, {tot.get('impressions', 0):.0f} "
                f"impressions, average position {tot.get('position', 0):.1f} over 90 days.", ""]
        items = next((v for v in wl.values()
                      if isinstance(v, list) and v and isinstance(v[0], dict)), [])
        top = sorted(items, key=lambda x: -x.get("est_click_gain", 0))[:5]
        if top:
            out.append("Closest wins:")
            for i in top:
                out.append(f"- {i['query']} at position {i['position']}, "
                           f"{i['impressions']} impressions, "
                           f"about {i.get('est_click_gain', 0):.0f} clicks available")
            out.append("")

    QA.mkdir(parents=True, exist_ok=True)
    (QA / "daily.md").write_text("\n".join(out))
    print(f"digest -> {QA / 'daily.md'}  ({len(hard)} hard, {len(warn)} warn)")


if __name__ == "__main__":
    main()
