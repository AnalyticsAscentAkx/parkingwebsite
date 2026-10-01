#!/usr/bin/env bash
# Daily QA agent for parkingnetherlands.com.
#
# Runs from ~/parking-site, never from ~/Documents: macOS TCC refuses to let
# launchd execute anything under Documents, which silently killed the daily
# publish job for 23 days before anyone noticed.
#
# Order matters. The deploy check runs first and its result colours everything
# after it: a clean audit against a stale deployment is a false all-clear, and
# that exact situation was live for over an hour on 2026-09-30.
set -uo pipefail          # NOT -e: a failing source must not abort the rest

REPO="${PARKING_REPO:-$HOME/parking-site}"
PY="${QA_PY:-$REPO/scripts/gsc_agent/.venv/bin/python}"
OUT="$REPO/data/qa"
mkdir -p "$OUT"
LOG="$OUT/run.log"
DAY="$(date +%F)"

export GSC_SA_KEY="${GSC_SA_KEY:-$HOME/.secrets/parkingnetherlands-gsc.json}"
export GSC_PROPERTY="${GSC_PROPERTY:-sc-domain:parkingnetherlands.com}"
export GSC_OUT_DIR="${GSC_OUT_DIR:-$REPO/data/gsc}"

say() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

say "=== QA run $DAY start"

# Always test the newest committed state, not whatever is on disk from a
# half-finished edit.
if [ -d "$REPO/.git" ]; then
  git -C "$REPO" fetch -q origin 2>>"$LOG" && \
  git -C "$REPO" reset -q --hard origin/main 2>>"$LOG" && \
  say "repo at $(git -C "$REPO" rev-parse --short HEAD)"
fi

# 1. Site audit. Exit 1 means hard findings, which is information, not failure.
say "1. site audit"
"$PY" "$REPO/scripts/qa/audit.py" --sample 120 >>"$LOG" 2>&1
AUDIT_RC=$?
say "   audit exit $AUDIT_RC"

# 2. Indexing progress. Needs the service-account key; skip quietly without it.
if [ -f "$GSC_SA_KEY" ]; then
  say "2. indexing watch"
  "$PY" "$REPO/scripts/gsc_agent/index_watch.py" --per-section 6 >>"$LOG" 2>&1 \
    || say "   index watch failed, see log"
else
  say "2. indexing watch SKIPPED, no key at $GSC_SA_KEY"
fi

# 3. Search Console. Weekly data, but cheap, and it is the demand signal.
if [ -f "$GSC_SA_KEY" ]; then
  say "3. search console"
  "$PY" "$REPO/scripts/gsc_agent/gsc_weekly.py" >>"$LOG" 2>&1 \
    || say "   gsc pull failed, see log"
fi

# 4. Analytics. Optional: needs the service account added to the GA4 property
#    and google-analytics-data installed. Absent, the rest still runs.
GA4_PROPERTY_ID="${GA4_PROPERTY_ID:-503850038}"
if [ -n "$GA4_PROPERTY_ID" ] && [ -f "$REPO/scripts/qa/ga4.py" ]; then
  say "4. ga4"
  GA4_PROPERTY_ID="$GA4_PROPERTY_ID" "$PY" "$REPO/scripts/qa/ga4.py" >>"$LOG" 2>&1 || say "   ga4 failed, see log"
else
  say "4. ga4 SKIPPED, GA4_PROPERTY_ID not set"
fi

# 5. One digest a human will actually read.
say "5. digest"
"$PY" "$REPO/scripts/qa/digest.py" >>"$LOG" 2>&1 || say "   digest failed"

say "=== QA run $DAY done. Report: $OUT/daily.md"
exit 0
