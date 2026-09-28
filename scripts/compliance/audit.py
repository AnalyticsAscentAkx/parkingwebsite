#!/usr/bin/env python3
"""Data-licence and legal compliance audit for parkingnetherlands.com.

Reads every public page, works out which external sources each page uses,
and checks the licence obligations recorded in sources.py. Writes a report,
returns a non-zero exit when something must be fixed.

    python3 scripts/compliance/audit.py            # audit the working tree
    python3 scripts/compliance/audit.py --fetch    # also re-fetch every terms
                                                   # page and flag changed text
    python3 scripts/compliance/audit.py --json     # machine-readable to stdout

Exit codes: 0 clean, 1 warnings only, 2 hard findings (daily job must not
publish). The report lands in scripts/compliance/report.md.
"""
import argparse
import hashlib
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from sources import SOURCES, POLICIES, IDENT_ALLOW, PUBLIC_GLOBS, SKIP_DIRS  # noqa: E402

SNAP = HERE / "snapshots"
REPORT = HERE / "report.md"
STATE = HERE / "state.json"


def public_files():
    seen = set()
    for g in PUBLIC_GLOBS:
        for p in ROOT.glob(g):
            if any(part in SKIP_DIRS for part in p.relative_to(ROOT).parts):
                continue
            if p.is_file() and p not in seen:
                seen.add(p)
                yield p


def strip_identifiers(text):
    for pat in IDENT_ALLOW:
        text = re.sub(pat, "", text)
    return text


def check_rules(rules, text, rel, source_key, findings, severity, kind):
    """kind='require' -> finding when pattern is ABSENT; 'forbid'/'advise' -> when PRESENT."""
    for pat, msg in rules:
        hits = list(re.finditer(pat, text, re.I | re.S))
        if kind == "require" and not hits:
            findings.append({"severity": severity, "source": source_key, "file": rel, "msg": msg, "snippet": ""})
        elif kind != "require" and hits:
            m = hits[0]
            snip = re.sub(r"\s+", " ", text[max(0, m.start() - 60): m.end() + 60]).strip()
            findings.append({"severity": severity, "source": source_key, "file": rel, "msg": msg,
                             "snippet": snip[:200], "count": len(hits)})


def audit_files():
    findings = []
    usage = {}
    entries = [dict(s, severity=s.get("severity", "HARD")) for s in SOURCES] + POLICIES
    for p in public_files():
        rel = p.relative_to(ROOT).as_posix()
        raw = p.read_text("utf-8", errors="replace")
        text = strip_identifiers(raw)
        for s in entries:
            if not re.search(s["uses"], raw, re.I):
                continue
            usage.setdefault(s["key"], []).append(rel)
            sev = s["severity"]
            check_rules(s.get("require", []), text, rel, s["key"], findings, sev, "require")
            check_rules(s.get("forbid", []), text, rel, s["key"], findings, sev, "forbid")
            check_rules(s.get("advise", []), text, rel, s["key"], findings, "WARN", "advise")
        # RDW naming is forbidden everywhere, even on pages that do not "use" the data.
        rdw = next(x for x in SOURCES if x["key"] == "rdw")
        if "rdw" not in [f["source"] for f in findings if f["file"] == rel]:
            check_rules(rdw["forbid"][:1], text, rel, "rdw", findings, "HARD", "forbid")
    return findings, usage


def fetch_terms():
    """Re-fetch each terms page, hash the visible text, and report changes."""
    SNAP.mkdir(exist_ok=True)
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    changes = []
    for s in SOURCES + POLICIES:
        url = s["terms_url"]
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "parkingnetherlands-compliance/1.0 (+https://parkingnetherlands.com/about)"})
            html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
        except Exception as e:  # network or 404: report, never crash the audit
            changes.append({"key": s["key"], "url": url, "status": f"fetch failed: {e}"})
            continue
        text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        digest = hashlib.sha256(text.encode()).hexdigest()[:16]
        prev = state.get(s["key"], {})
        (SNAP / f"{s['key']}.txt").write_text(text, "utf-8")
        if prev.get("hash") and prev["hash"] != digest:
            changes.append({"key": s["key"], "url": url, "status": f"TERMS CHANGED since {prev.get('date')} (re-read and update sources.py)"})
        elif not prev.get("hash"):
            changes.append({"key": s["key"], "url": url, "status": "first snapshot stored"})
        state[s["key"]] = {"hash": digest, "date": date.today().isoformat(), "url": url}
    STATE.write_text(json.dumps(state, indent=1))
    return changes


def write_report(findings, usage, changes):
    hard = [f for f in findings if f["severity"] == "HARD"]
    warn = [f for f in findings if f["severity"] == "WARN"]
    by = {}
    for f in findings:
        by.setdefault((f["severity"], f["source"], f["msg"]), []).append(f)
    lines = [f"# Data-licence compliance report", "", f"Generated {date.today().isoformat()} by scripts/compliance/audit.py", "",
             f"**{len(hard)} hard findings** across {len({f['file'] for f in hard})} files, "
             f"**{len(warn)} warnings** across {len({f['file'] for f in warn})} files.", ""]
    lines += ["## Sources in use", ""]
    for s in SOURCES + POLICIES:
        n = len(usage.get(s["key"], []))
        lines.append(f"- **{s['name']}**: {n} file(s). Licence: {s['licence'] if 'licence' in s else 'policy'}. Terms: {s['terms_url']}")
    lines += ["", "## Findings", ""]
    if not findings:
        lines.append("None. Every page honours the recorded terms.")
    for (sev, src, msg), fs in sorted(by.items(), key=lambda kv: (kv[0][0] != "HARD", kv[0][1])):
        files = sorted({f["file"] for f in fs})
        lines.append(f"### [{sev}] {src}: {msg}")
        lines.append(f"{len(files)} file(s): " + ", ".join(files[:12]) + (f" ... +{len(files)-12} more" if len(files) > 12 else ""))
        ex = next((f for f in fs if f.get("snippet")), None)
        if ex:
            lines.append(f"> e.g. `{ex['file']}`: …{ex['snippet']}…")
        lines.append("")
    if changes:
        lines += ["## Terms pages", ""] + [f"- {c['key']}: {c['status']} ({c['url']})" for c in changes] + [""]
    lines += ["## What each source allows", ""]
    for s in SOURCES:
        lines.append(f"- **{s['key']}**: {s['verified']}")
    REPORT.write_text("\n".join(lines) + "\n", "utf-8")
    return hard, warn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="re-fetch terms pages and diff against last snapshot")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    findings, usage = audit_files()
    changes = fetch_terms() if a.fetch else []
    hard, warn = write_report(findings, usage, changes)
    changed_terms = [c for c in changes if "CHANGED" in c["status"]]
    if a.json:
        print(json.dumps({"hard": hard, "warn": warn, "terms": changes}, indent=1))
    else:
        print(f"compliance: {len(hard)} hard, {len(warn)} warn, {len(changed_terms)} terms changed -> {REPORT.relative_to(ROOT)}")
        for f in hard[:8]:
            print(f"  HARD {f['source']:<10} {f['file']}: {f['msg']}")
        if len(hard) > 8:
            print(f"  ... {len(hard)-8} more hard findings in the report")
    if hard or changed_terms:
        return 2
    return 1 if warn else 0


if __name__ == "__main__":
    sys.exit(main())
