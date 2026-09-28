# Status collector

The moat: per-charge-point status history that no one else keeps. Installed
2026-09-28.

**Runs from `~/ev-collector/`, not from this repo**, because launchd cannot
read `~/Documents` on this Mac (TCC). That folder is a copy of `evlayer/`,
`migrations/`, `pyproject.toml` and `.env` with its own venv; Postgres is
shared (`evlayer` on localhost:5432).

| What | Where |
|---|---|
| Job | `~/Library/LaunchAgents/com.parkingnetherlands.ev-collector.plist`, every 30 min, also at login |
| Script | `~/ev-collector/collect.sh`: `registry` (state changes) + `availability`; `rollup --days 2` in the 03:00 run |
| Logs | `~/ev-collector/logs/collect-YYYY-MM-DD.log` (30 days kept) |
| Check | `launchctl print gui/$(id -u)/com.parkingnetherlands.ev-collector \| grep -E 'state\|last exit'` |
| Growth | `SELECT count(*), max(observed_at) FROM state_change;` |

Publishing the history to the site happens in the daily job
(`scripts/daily/run_daily.sh`, step 3d): rollup, re-export `ev-data/`, commit.
That job needs the repo, so it still runs by hand until Terminal/bash has
Full Disk Access.

After changing `evlayer/` here, refresh the runtime:

    rsync -a --delete --exclude .venv --exclude cache --exclude __pycache__ \
      scripts/ev/evlayer scripts/ev/migrations scripts/ev/pyproject.toml ~/ev-collector/
    ~/ev-collector/.venv/bin/python -m evlayer.cli init   # applies new migrations

Uptime definition is in `evlayer/status.py` and `evlayer/rollup.py`; the map
shows history once `reliability_daily` has rows (`days_measured` in
`ev-data/meta.json`).
