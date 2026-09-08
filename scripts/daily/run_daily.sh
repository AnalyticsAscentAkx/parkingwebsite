#!/bin/bash
# ---------------------------------------------------------------------------
# Parking Netherlands - daily midday job.
#
# Runs a few recurring SEO tasks and auto-publishes:
#   1. Refresh demand data  (collector: autocomplete -> normalize -> shortlist)
#   2. Build + publish 1 page (deterministic POI generator, next in the queue)
#   3. GSC pull + report     (weekly GSC agent, best-effort, needs key)
#   4. Freshen sitemap, commit + push, verify live, ping IndexNow
#
# Every step is best-effort: one failing never stops the rest (collector design
# principle 2). All output is logged to scripts/daily/logs/daily-YYYY-MM-DD.log.
#
# Install (runs at 12:00 daily via launchd): see scripts/daily/README.md
# ---------------------------------------------------------------------------
set -u
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

REPO="/Users/aakash.chavash/Documents/Personal Script/parking_website "
DAILY="$REPO/scripts/daily"
LOGDIR="$DAILY/logs"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/daily-$(date +%F).log"
BRANCH="main"

log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
step(){ log ""; log "== $* =="; }

cd "$REPO" || { echo "repo not found"; exit 1; }
log "###### DAILY RUN $(date) ######"

# --- 0. sync ----------------------------------------------------------------
step "0. Sync with origin"
git rev-parse --abbrev-ref HEAD | grep -qx "$BRANCH" || { log "not on $BRANCH; abort"; exit 0; }
git pull --ff-only origin "$BRANCH" >>"$LOG" 2>&1 && log "pulled" || log "WARN pull failed (continuing)"

# --- 1. refresh demand data (gitignored output) -----------------------------
step "1. Refresh demand data (collector)"
if [ -f "$REPO/scripts/collector/pipeline.py" ]; then
  ( cd "$REPO/scripts/collector" \
    && python3 pipeline.py init >>"$LOG" 2>&1 \
    && python3 pipeline.py seed >>"$LOG" 2>&1 \
    && python3 pipeline.py autocomplete --limit-seeds 250 --langs nl,en >>"$LOG" 2>&1 \
    && python3 pipeline.py normalize >>"$LOG" 2>&1 \
    && python3 pipeline.py shortlist >>"$LOG" 2>&1 ) \
    && log "collector refreshed (shortlist regenerated)" \
    || log "WARN collector step failed (continuing)"
else
  log "collector not present, skipping"
fi

# --- 2. build + publish 1 page (stages files, no commit) --------------------
step "2. Build next POI page"
GEN_OUT="$(python3 "$DAILY/generate_poi_page.py" --next 2>&1)"
log "$GEN_OUT"

# --- 3. GSC pull (best-effort, needs GSC_SA_KEY) ----------------------------
step "3. GSC pull + report"
if [ -n "${GSC_SA_KEY:-}" ] && [ -f "$REPO/scripts/gsc_agent/gsc_weekly.py" ]; then
  ( cd "$REPO/scripts/gsc_agent" && python3 gsc_weekly.py >>"$LOG" 2>&1 ) \
    && log "GSC agent ran" || log "WARN GSC agent failed (continuing)"
else
  log "GSC_SA_KEY unset or agent missing, skipping"
fi

# --- 4. freshen sitemap lastmod for changed root pages ----------------------
step "4. Freshen sitemap for changed pages"
CHANGED_SLUGS="$(git diff --cached --name-only 2>/dev/null | grep -E '^[a-z0-9-]+\.html$' | sed 's/\.html$//')"
if [ -n "$CHANGED_SLUGS" ]; then
  TODAY="$(date +%F)" python3 - "$CHANGED_SLUGS" <<'PY' >>"$LOG" 2>&1
import os, re, sys, pathlib
today = os.environ["TODAY"]
slugs = sys.argv[1].split()
p = pathlib.Path("sitemap.xml"); s = p.read_text("utf-8")
for slug in slugs:
    loc = "/" + ("" if slug == "index" else slug)
    s = re.sub(r'(<loc>https://parkingnetherlands\.com'+re.escape(loc)+r'</loc><lastmod>)[0-9-]+',
               r'\g<1>'+today, s)
p.write_text(s, "utf-8")
print("freshened sitemap lastmod for:", ", ".join(slugs))
PY
  git add sitemap.xml
  log "changed pages: $(echo $CHANGED_SLUGS | tr '\n' ' ')"
else
  log "no page changes staged"
fi

# --- 5. commit + push -------------------------------------------------------
step "5. Commit + push"
if ! git diff --cached --quiet; then
  MSG="Daily auto-update $(date +%F): $(echo $CHANGED_SLUGS | tr '\n' ' ')"
  git commit -q -m "$MSG" -m "Automated by scripts/daily/run_daily.sh" \
    -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" >>"$LOG" 2>&1
  if git push origin "$BRANCH" >>"$LOG" 2>&1; then
    log "pushed: $MSG"
    PUSHED=1
  else
    log "ERROR push failed - changes committed locally only"
    PUSHED=0
  fi
else
  log "nothing to commit"
  PUSHED=0
fi

# --- 6. verify live + ping IndexNow -----------------------------------------
if [ "${PUSHED:-0}" = "1" ] && [ -n "$CHANGED_SLUGS" ]; then
  step "6. Verify live (Cloudflare deploy) + IndexNow"
  URLS=""
  for slug in $CHANGED_SLUGS; do
    url="https://parkingnetherlands.com/$slug"
    ok=0
    for i in $(seq 1 12); do
      code=$(curl -s -o /dev/null -w "%{http_code}" -L "$url")
      [ "$code" = "200" ] && { ok=1; break; }
      sleep 15
    done
    [ "$ok" = "1" ] && log "LIVE 200: $url" || log "WARN not 200 after ~3min: $url"
    URLS="$URLS $url"
  done
  # IndexNow ping (Bing/Yandex/others). Google ignores this; use GSC for Google.
  KEYF="$DAILY/indexnow_key.txt"
  if [ -f "$KEYF" ]; then
    KEY="$(cat "$KEYF")"
    BODY=$(python3 - "$KEY" $URLS <<'PY'
import json, sys
key = sys.argv[1]; urls = sys.argv[2:]
print(json.dumps({"host":"parkingnetherlands.com","key":key,
  "keyLocation":f"https://parkingnetherlands.com/{key}.txt","urlList":urls}))
PY
)
    rc=$(curl -s -o /dev/null -w "%{http_code}" -X POST "https://api.indexnow.org/indexnow" \
         -H "Content-Type: application/json" -d "$BODY")
    log "IndexNow ping HTTP $rc for:$URLS"
  else
    log "no IndexNow key file, skipping ping"
  fi
fi

log "###### DONE $(date) ######"
