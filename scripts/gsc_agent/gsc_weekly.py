#!/usr/bin/env python3
"""
Weekly Google Search Console agent for parkingnetherlands.com.

Pulls Search Console performance data (queries + pages) via a Google
service account, then ranks SEO opportunities into a prioritized worklist
that a human — or a Claude Code run — can act on.

It NEVER edits the site. It only reads GSC and writes a report + worklist.
Actual page edits are left to a review step (see AGENT.md).

Auth (one-time setup, see README.md):
  1. Create a Google Cloud service account, enable the Search Console API.
  2. Download its JSON key.
  3. In Search Console -> Settings -> Users and permissions, add the service
     account's email as a "Full" (or "Restricted") user on the property.

Config (environment variables):
  GSC_SA_KEY    absolute path to the service-account JSON key
  GSC_PROPERTY  the property, e.g. "sc-domain:parkingnetherlands.com"
                (domain property) or "https://parkingnetherlands.com/"
  GSC_OUT_DIR   optional; where to write reports (default: ../../data/gsc)

Usage:
  python3 gsc_weekly.py            # last 90d vs prior 90d
  python3 gsc_weekly.py --days 28  # custom window
"""
import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent  # scripts/gsc_agent -> scripts -> repo root
DEFAULT_OUT = REPO_ROOT / "data" / "gsc"

# Rough organic CTR-by-position curve (Google, blended desktop+mobile).
# Used only to flag "CTR far below what this position usually earns".
CTR_BY_POSITION = {
    1: 0.28, 2: 0.155, 3: 0.10, 4: 0.07, 5: 0.052,
    6: 0.040, 7: 0.032, 8: 0.026, 9: 0.022, 10: 0.019,
}


def expected_ctr(position: float) -> float:
    """Expected CTR for an average position (floored beyond page 1)."""
    p = int(round(position))
    if p <= 0:
        return CTR_BY_POSITION[1]
    if p <= 10:
        return CTR_BY_POSITION[p]
    # Page 2+: small but nonzero.
    if p <= 20:
        return 0.012
    return 0.006


def get_service():
    """Build the Search Console API client from the service-account key."""
    key_path = os.environ.get("GSC_SA_KEY")
    if not key_path:
        sys.exit(
            "ERROR: GSC_SA_KEY is not set.\n"
            "Point it at your service-account JSON key. See README.md."
        )
    if not Path(key_path).is_file():
        sys.exit(f"ERROR: GSC_SA_KEY file not found: {key_path}")
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        sys.exit(
            "ERROR: missing deps. Run:\n"
            "  pip install -r scripts/gsc_agent/requirements.txt"
        )
    scopes = ["https://www.googleapis.com/auth/webmasters.readonly"]
    creds = service_account.Credentials.from_service_account_file(
        key_path, scopes=scopes
    )
    return build("searchconsole", "v1", credentials=creds, cache_discovery=False)


def query_gsc(service, prop, start, end, dimensions, row_limit=25000):
    """Run one searchanalytics.query and return its rows."""
    body = {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "dimensions": dimensions,
        "rowLimit": row_limit,
        "dataState": "final",
    }
    resp = (
        service.searchanalytics()
        .query(siteUrl=prop, body=body)
        .execute()
    )
    return resp.get("rows", [])


def rows_to_dicts(rows, dim_names):
    out = []
    for r in rows:
        keys = r.get("keys", [])
        d = {dim_names[i]: keys[i] for i in range(len(dim_names))}
        d["clicks"] = r.get("clicks", 0)
        d["impressions"] = r.get("impressions", 0)
        d["ctr"] = r.get("ctr", 0.0)
        d["position"] = r.get("position", 0.0)
        out.append(d)
    return out


def classify(row):
    """Return (category, rationale) for a query row, or (None, None)."""
    impr = row["impressions"]
    pos = row["position"]
    ctr = row["ctr"]
    exp = expected_ctr(pos)

    # Not enough demand to bother.
    if impr < 20:
        return None, None

    # On page 1 but under-clicked -> title/meta fix is the fastest win.
    if pos <= 10 and ctr < exp * 0.6:
        return (
            "ctr_fix",
            f"pos {pos:.1f}, CTR {ctr*100:.1f}% vs ~{exp*100:.0f}% expected "
            f"({impr:.0f} impr) — title/meta rewrite",
        )

    # Page 2 with real demand -> push ranking via content depth + links.
    if 10 < pos <= 20:
        return (
            "ranking_push",
            f"pos {pos:.1f} (page 2), {impr:.0f} impr — deepen content, "
            f"add internal links",
        )

    # Lots of impressions but buried -> likely a content/page gap.
    if pos > 20 and impr >= 40:
        return (
            "content_gap",
            f"pos {pos:.1f}, {impr:.0f} impr — weak/no dedicated page",
        )

    return None, None


def build_worklist(query_rows, page_rows, page_for_query):
    items = []
    for row in query_rows:
        cat, why = classify(row)
        if not cat:
            continue
        q = row["query"]
        items.append(
            {
                "query": q,
                "category": cat,
                "landing_page": page_for_query.get(q, ""),
                "impressions": round(row["impressions"]),
                "clicks": round(row["clicks"]),
                "ctr_pct": round(row["ctr"] * 100, 2),
                "position": round(row["position"], 1),
                "rationale": why,
            }
        )
    # Priority: potential clicks gained. For ctr_fix, gap to expected CTR;
    # for ranking/gap, impressions weighted by how close to page 1.
    def score(it):
        impr = it["impressions"]
        pos = it["position"]
        if it["category"] == "ctr_fix":
            gain = impr * max(expected_ctr(pos) - it["ctr_pct"] / 100, 0)
        elif it["category"] == "ranking_push":
            gain = impr * 0.15  # assume ~page-1 CTR if we move it up
        else:
            gain = impr * 0.05
        it["est_click_gain"] = round(gain, 1)
        return gain

    items.sort(key=score, reverse=True)
    return items


def render_report(prop, start, end, prev_totals, totals, worklist):
    def pct(n, d):
        return f"{(n/d*100):.2f}%" if d else "0%"

    lines = []
    lines.append(f"# GSC weekly report — {prop}")
    lines.append(f"_Window: {start} to {end}_\n")
    lines.append("## Totals")
    lines.append("| Metric | This window | Prior window | Δ |")
    lines.append("|---|---|---|---|")
    for label, key, fmt in [
        ("Clicks", "clicks", lambda v: f"{v:.0f}"),
        ("Impressions", "impressions", lambda v: f"{v:.0f}"),
        ("CTR", "ctr", lambda v: f"{v*100:.2f}%"),
        ("Avg position", "position", lambda v: f"{v:.1f}"),
    ]:
        cur = totals.get(key, 0)
        prev = prev_totals.get(key, 0)
        delta = cur - prev
        arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "—")
        lines.append(
            f"| {label} | {fmt(cur)} | {fmt(prev)} | {arrow} {fmt(abs(delta))} |"
        )

    buckets = {"ctr_fix": [], "ranking_push": [], "content_gap": []}
    for it in worklist:
        buckets[it["category"]].append(it)

    titles = {
        "ctr_fix": "Title/meta rewrites (page 1, under-clicked) — fastest wins",
        "ranking_push": "Content depth + internal links (page 2)",
        "content_gap": "Content/page gaps (buried, high demand)",
    }
    for cat in ("ctr_fix", "ranking_push", "content_gap"):
        rows = buckets[cat][:15]
        lines.append(f"\n## {titles[cat]} ({len(buckets[cat])})")
        if not rows:
            lines.append("_None this window._")
            continue
        lines.append("| Query | Page | Impr | CTR | Pos | Est. +clicks |")
        lines.append("|---|---|---|---|---|---|")
        for it in rows:
            page = it["landing_page"].replace(
                "https://parkingnetherlands.com", ""
            ) or "—"
            lines.append(
                f"| {it['query']} | {page} | {it['impressions']} | "
                f"{it['ctr_pct']}% | {it['position']} | {it['est_click_gain']} |"
            )
    lines.append(
        "\n---\n_Generated by scripts/gsc_agent/gsc_weekly.py. "
        "This agent does not edit the site — see AGENT.md for the review step._"
    )
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--out", default=os.environ.get("GSC_OUT_DIR", str(DEFAULT_OUT)))
    args = ap.parse_args()

    prop = os.environ.get("GSC_PROPERTY")
    if not prop:
        sys.exit(
            "ERROR: GSC_PROPERTY not set "
            '(e.g. "sc-domain:parkingnetherlands.com"). See README.md.'
        )

    # GSC data lags ~2-3 days; end the window 3 days back.
    end = date.today() - timedelta(days=3)
    start = end - timedelta(days=args.days)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=args.days)

    service = get_service()

    q_rows = rows_to_dicts(
        query_gsc(service, prop, start, end, ["query"]), ["query"]
    )
    page_q_rows = rows_to_dicts(
        query_gsc(service, prop, start, end, ["query", "page"]),
        ["query", "page"],
    )
    # Best landing page per query = the one with most impressions.
    page_for_query = {}
    best_impr = {}
    for r in page_q_rows:
        q = r["query"]
        if r["impressions"] > best_impr.get(q, -1):
            best_impr[q] = r["impressions"]
            page_for_query[q] = r["page"]

    def totals_from(rows):
        clicks = sum(r["clicks"] for r in rows)
        impr = sum(r["impressions"] for r in rows)
        # Weighted avg position.
        wpos = (
            sum(r["position"] * r["impressions"] for r in rows) / impr
            if impr
            else 0
        )
        return {
            "clicks": clicks,
            "impressions": impr,
            "ctr": clicks / impr if impr else 0,
            "position": wpos,
        }

    totals = totals_from(q_rows)
    prev_rows = rows_to_dicts(
        query_gsc(service, prop, prev_start, prev_end, ["query"]), ["query"]
    )
    prev_totals = totals_from(prev_rows)

    worklist = build_worklist(q_rows, page_q_rows, page_for_query)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = end.isoformat()

    report = render_report(prop, start, end, prev_totals, totals, worklist)
    (out_dir / f"report_{stamp}.md").write_text(report)
    (out_dir / "latest_report.md").write_text(report)

    worklist_payload = {
        "generated_for": stamp,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "totals": totals,
        "prev_totals": prev_totals,
        "goal": "Grow to 1000 organic clicks/90d",
        "items": worklist,
    }
    (out_dir / f"worklist_{stamp}.json").write_text(
        json.dumps(worklist_payload, indent=2)
    )
    (out_dir / "latest_worklist.json").write_text(
        json.dumps(worklist_payload, indent=2)
    )

    print(f"Wrote {out_dir}/latest_report.md")
    print(f"Wrote {out_dir}/latest_worklist.json")
    print(
        f"Totals: {totals['clicks']:.0f} clicks, "
        f"{totals['impressions']:.0f} impr, "
        f"CTR {totals['ctr']*100:.2f}%, pos {totals['position']:.1f}"
    )
    print(f"Opportunities: {len(worklist)}")


if __name__ == "__main__":
    main()
