# Daily midday SEO job

A single launchd job that runs every day at **12:00** and does a few recurring
tasks, then auto-publishes. Built on the same pattern as `scripts/gsc_agent`.

## What it does (each step is best-effort; one failing never stops the rest)

1. **Refresh demand data** - runs the collector (`autocomplete -> normalize ->
   shortlist`) so `data/collector/shortlist_*.csv` is regenerated daily. Output
   is gitignored; nothing is committed from this step.
2. **Build + publish 1 page** - `generate_poi_page.py --next` builds the next
   `/parking-<city>-centraal` page in the `targets.json` queue, **deterministically
   from the real RDW garage register** (no LLM, so nothing unpredictable goes
   live). It wires the redirect, sitemap entry, and a reciprocal city-page link.
3. **GSC pull** - runs the weekly GSC agent if `GSC_SA_KEY` is set (else skips).
4. **Freshen + publish** - bumps sitemap `lastmod` for changed pages, commits,
   pushes to `main` (Cloudflare auto-deploys), verifies each changed URL returns
   200 on production, and pings **IndexNow** (Bing/Yandex). Google is not pinged
   (their API is dead) - use GSC "Request Indexing" for fast Google indexing.

## Files

| File | Purpose |
|---|---|
| `run_daily.sh` | Orchestrator (the 4 steps above). Logs to `logs/daily-YYYY-MM-DD.log`. |
| `generate_poi_page.py` | Deterministic POI page generator. `--next`, `--list`, or `<target_key>`. |
| `targets.json` | Queue of POI targets (slug, station, city, coords, geo, P+R). Append to extend. |
| `indexnow_key.txt` | IndexNow key; the matching `<key>.txt` at the site root is the hosted proof. |
| `com.parkingnetherlands.daily.plist` | launchd schedule (12:00 daily). |

## Install (once)

Run as your **login user** so git push uses the keychain credential
(AnalyticsAscentAkx) already configured:

```bash
cp "scripts/daily/com.parkingnetherlands.daily.plist" ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.parkingnetherlands.daily.plist
launchctl kickstart -k gui/$(id -u)/com.parkingnetherlands.daily   # run once now to test
tail -f "scripts/daily/logs/daily-$(date +%F).log"
```

Uninstall: `launchctl bootout gui/$(id -u)/com.parkingnetherlands.daily`

## Notes / safety

- **Auto-push is on.** Each run commits and pushes to `main`. The page build is
  deterministic and validated (schema, resolvable garage links, price-anomaly
  filter, no template leaks), so this is safe - but it does go live unreviewed.
  To make it review-first instead, change the `git push` in `run_daily.sh` to
  push a branch and open a PR.
- **The Mac must be awake at noon.** launchd runs the job at the next
  opportunity if the machine was asleep. For always-on reliability, move this to
  a cloud routine.
- **Queue runs dry** when every target in `targets.json` is built - the job then
  just refreshes data and does nothing else until you add more targets.
- **Extend the queue**: add objects to `targets.json` (any station/POI with
  garages in `garage/*<city_slug>*.html`). Verify P+R facts before adding;
  everything else (prices, distances) is pulled from real data.
- Manual dry run without waiting for noon:
  `bash "scripts/daily/run_daily.sh"` (it will push if there are changes).
