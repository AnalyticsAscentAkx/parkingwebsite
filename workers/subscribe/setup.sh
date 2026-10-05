#!/usr/bin/env bash
# One-shot setup for the subscribe Worker.
#
# Logs in (opens a browser once), creates the KV namespace, writes its id into
# wrangler.toml and deploys. Safe to re-run: if the namespace already exists it
# keeps the one in the file and just redeploys.
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Cloudflare login (a browser window may open)"
npx --yes wrangler whoami >/dev/null 2>&1 || npx --yes wrangler login

if grep -q "REPLACE_WITH_KV_NAMESPACE_ID" wrangler.toml; then
  echo "==> creating the KV namespace"
  out=$(npx --yes wrangler kv namespace create SUBS 2>&1 | tee /dev/stderr)
  id=$(printf '%s' "$out" | grep -oE '[0-9a-f]{32}' | head -1)
  if [ -z "$id" ]; then
    echo "Could not read the namespace id from wrangler's output." >&2
    echo "Open wrangler.toml and paste it in by hand, then run this again." >&2
    exit 1
  fi
  # macOS and GNU sed disagree about -i, so write through a temp file.
  sed "s/REPLACE_WITH_KV_NAMESPACE_ID/$id/" wrangler.toml > wrangler.toml.tmp
  mv wrangler.toml.tmp wrangler.toml
  echo "==> namespace $id written into wrangler.toml"
else
  echo "==> namespace already configured, skipping"
fi

echo "==> deploying"
npx --yes wrangler deploy

cat <<'EOF'

Done. Wrangler printed the Worker URL above.

If it is a workers.dev URL, open subscribe.js in the site repo and set
ENDPOINT to it, then commit. If you would rather use
alerts.parkingnetherlands.com, add that DNS record in the Cloudflare
dashboard, uncomment the [[routes]] block in wrangler.toml, run this
script again, and leave ENDPOINT as it is.

Check it is alive:
  curl -i -X POST "<worker-url>/subscribe" \
    -H 'Content-Type: application/json' \
    -H 'Origin: https://parkingnetherlands.com' \
    -d '{"email":"test@example.com","consent":true,"topics":["tariffs"]}'
EOF
