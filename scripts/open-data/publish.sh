#!/bin/bash
# Publish (or refresh) the open-data repository on GitHub from the live data files.
# Run from anywhere. Needs: gh logged in as AnalyticsAscentAkx.
#   bash scripts/open-data/publish.sh
set -eu
REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
NAME="parking-netherlands-open-data"
WORK="$(mktemp -d)/$NAME"
mkdir -p "$WORK/data"
cp "$REPO_DIR/scripts/open-data/README.md" "$REPO_DIR/scripts/open-data/LICENSE" "$WORK/"
cp "$REPO_DIR/data/parking-price-index-2026.json" "$REPO_DIR/data/parking-price-index-2026.csv" \
   "$REPO_DIR/data/ev-adoption-2026.json" "$REPO_DIR/data/ev-adoption-2026.csv" "$WORK/data/"
cp "$REPO_DIR/ev-data/tariffs.json" "$WORK/data/ev-charging-tariffs-by-operator.json"
cp "$REPO_DIR/ev-data/meta.json" "$WORK/data/ev-register-meta.json"
cd "$WORK"
if gh repo view "AnalyticsAscentAkx/$NAME" >/dev/null 2>&1; then
  git clone -q "https://github.com/AnalyticsAscentAkx/$NAME.git" ../clone
  cp -R ../clone/.git .git
  git add -A && git -c user.name="Analytics Ascent" -c user.email="noreply@analyticascent.com" commit -q -m "Data refresh $(date +%F)" || { echo "nothing changed"; exit 0; }
  git push -q origin HEAD
else
  git init -q && git add -A
  git -c user.name="Analytics Ascent" -c user.email="noreply@analyticascent.com" commit -q -m "Parking price index, EV adoption and charging tariffs for the Netherlands, 2026 (CC BY 4.0)"
  gh repo create "AnalyticsAscentAkx/$NAME" --public --source . --push \
    --description "Open data behind parkingnetherlands.com: Dutch garage tariffs per city, EV adoption per municipality, charging tariffs per operator. CC BY 4.0."
fi
echo "published: https://github.com/AnalyticsAscentAkx/$NAME"
