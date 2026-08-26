#!/usr/bin/env bash
# Weekly GSC agent runner. Called by launchd (see the .plist) or by hand.
#
# It (1) pulls Search Console data and writes a report + worklist, then
# (2) OPTIONALLY asks Claude Code to draft edits from the worklist.
# Step 2 is OFF by default — SEO edits should be reviewed before going live.
set -euo pipefail

# --- Config: edit these two lines (or export them in your shell) ---
export GSC_SA_KEY="${GSC_SA_KEY:-$HOME/.secrets/parkingnetherlands-gsc.json}"
export GSC_PROPERTY="${GSC_PROPERTY:-sc-domain:parkingnetherlands.com}"
# -------------------------------------------------------------------

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AGENT_DIR="$REPO/scripts/gsc_agent"
VENV="$AGENT_DIR/.venv"
LOG_DIR="$REPO/data/gsc"
mkdir -p "$LOG_DIR"

# One-time venv bootstrap.
if [ ! -d "$VENV" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet -r "$AGENT_DIR/requirements.txt"
fi

echo "[$(date)] Pulling GSC data..." >> "$LOG_DIR/run.log"
"$VENV/bin/python" "$AGENT_DIR/gsc_weekly.py" >> "$LOG_DIR/run.log" 2>&1

# --- OPTIONAL: let Claude Code draft edits from the worklist ---
# Uncomment to enable. Runs headless, leaves changes UNCOMMITTED for review.
# Requires the `claude` CLI on PATH.
#
# cd "$REPO"
# claude -p "Read data/gsc/latest_worklist.json and scripts/gsc_agent/AGENT.md. \
# Work the top 3 'ctr_fix' items: rewrite each page's <title>/meta description \
# per the rules in AGENT.md. Make the edits to the real files. Do NOT commit or \
# push. Then summarize what you changed." >> "$LOG_DIR/claude.log" 2>&1

echo "[$(date)] Done. See $LOG_DIR/latest_report.md" >> "$LOG_DIR/run.log"
