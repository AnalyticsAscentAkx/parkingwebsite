#!/usr/bin/env bash
# Weekly demand-collector run (spec section 9). Cron this on Sunday night.
# A shell script calling the pipeline in sequence is all the orchestration
# this needs at this scale - do not over-engineer it.
set -uo pipefail
cd "$(dirname "$0")"

# Optional creds (collectors skip cleanly if unset):
#   export GSC_SA_KEY=/abs/path/to/service-account.json
#   export GSC_PROPERTY="sc-domain:parkingnetherlands.com"
#   export GOOGLE_PLACES_KEY=...   # enables Maps review mining

LIMIT_SEEDS="${LIMIT_SEEDS:-2000}"
LOG="../../data/collector/run_$(date +%Y-%m-%d).log"
mkdir -p ../../data/collector

echo "== weekly run $(date) ==" | tee -a "$LOG"
python3 pipeline.py weekly --limit-seeds "$LIMIT_SEEDS" --engines google 2>&1 | tee -a "$LOG"
echo "== done $(date) ==" | tee -a "$LOG"
