#!/usr/bin/env bash
# Weekly GSC agent runner. Called by launchd (see the .plist) or by hand.
#
# It (1) pulls Search Console data and writes a report + worklist, then
# (2) has the model draft fixes for the top worklist items and opens them as
# a PR for review. Nothing goes live until the PR is merged.
set -euo pipefail

# --- Config: edit these two lines (or export them in your shell) ---
export GSC_SA_KEY="${GSC_SA_KEY:-$HOME/.secrets/parkingnetherlands-gsc.json}"
export GSC_PROPERTY="${GSC_PROPERTY:-sc-domain:parkingnetherlands.com}"
# -------------------------------------------------------------------

# launchd starts with a bare PATH; claude and gh live in Homebrew.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

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

# launchd fires at 08:00 Monday, often the moment the laptop wakes and before
# Wi-Fi is up; the 2026-10-26 run died on "Unable to find the server at
# oauth2.googleapis.com". Wait up to 10 minutes for the network, then retry
# the pull itself up to 3 times.
for i in $(seq 1 20); do
  curl -s -o /dev/null --max-time 5 https://oauth2.googleapis.com && break
  sleep 30
done

echo "[$(date)] Pulling GSC data..." >> "$LOG_DIR/run.log"
for attempt in 1 2 3; do
  if "$VENV/bin/python" "$AGENT_DIR/gsc_weekly.py" >> "$LOG_DIR/run.log" 2>&1; then
    break
  fi
  if [ "$attempt" = 3 ]; then
    echo "[$(date)] Pull failed 3 times, giving up." >> "$LOG_DIR/run.log"
    exit 1
  fi
  sleep 120
done

# --- Weekly draft PR: the model works the worklist, the owner merges ---
# The model gets read/edit tools only. This script makes the branch, the
# commit and the PR, in a separate worktree so the daily job's checkout of
# main is never touched. Nothing reaches the live site until the PR is merged.
# Off with GSC_DRAFT_PR=0.
if [ "${GSC_DRAFT_PR:-1}" = 1 ] && command -v claude >/dev/null && command -v gh >/dev/null; then
  DAY="$(date +%Y-%m-%d)"
  BR="seo/weekly-$DAY"
  WT="$HOME/parking-site-weekly"
  git -C "$REPO" worktree remove --force "$WT" 2>/dev/null || true
  git -C "$REPO" fetch --quiet origin main
  if git -C "$REPO" ls-remote --exit-code --heads origin "$BR" >/dev/null 2>&1; then
    echo "[$(date)] $BR already exists, skipping draft." >> "$LOG_DIR/run.log"
  else
    git -C "$REPO" worktree add --quiet -B "$BR" "$WT" origin/main
    cp "$LOG_DIR/latest_worklist.json" "$LOG_DIR/latest_report.md" "$WT/data/gsc/" 2>/dev/null || true
    (cd "$WT" && claude -p --permission-mode acceptEdits \
      --allowedTools "Read,Edit,Grep,Glob" \
      "Read scripts/gsc_agent/AGENT.md, data/gsc/latest_worklist.json and scripts/IMPROVEMENT_LOG.md. \
Pick the top 3 worklist items by estimated click gain whose landing page is NOT \
an experiment still being judged in IMPROVEMENT_LOG.md and is not /amsterdam-cheap-parking \
(a 301 waiting on recrawl). Fix each per AGENT.md: titles/meta for ctr_fix, an \
answer section plus internal links for ranking_push. Use only numbers already on \
the site. No em dashes. No mention of AI or a model in page text. Edit the real \
files, then append a dated entry to scripts/IMPROVEMENT_LOG.md with each page, \
query, baseline clicks/impressions/position from the worklist, and a judge-on \
date 28 days out. Finish with a plain list of what you changed." \
      > "$LOG_DIR/draft_$DAY.md" 2>> "$LOG_DIR/run.log") || true
    cd "$WT"
    if git diff --quiet; then
      echo "[$(date)] Draft made no changes." >> "$LOG_DIR/run.log"
    elif git diff > "$LOG_DIR/draft_$DAY.diff" && grep -q '^+.*—' "$LOG_DIR/draft_$DAY.diff"; then
      echo "[$(date)] Draft added an em dash, not opening a PR. See $WT" >> "$LOG_DIR/run.log"
    else
      git add -A -- . ':!data/gsc'
      git commit --quiet -m "SEO weekly $DAY: worklist fixes from Search Console"
      git push --quiet -u origin "$BR" >> "$LOG_DIR/run.log" 2>&1
      gh pr create --base main --head "$BR" --title "SEO weekly $DAY" \
        --body-file "$LOG_DIR/draft_$DAY.md" >> "$LOG_DIR/run.log" 2>&1
      git -C "$REPO" worktree remove --force "$WT"
    fi
  fi
fi

echo "[$(date)] Done. See $LOG_DIR/latest_report.md" >> "$LOG_DIR/run.log"
