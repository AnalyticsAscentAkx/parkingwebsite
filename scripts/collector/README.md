# Parking-NL Demand-Signal Collector (Phase 1)

A weekly pipeline that harvests real search demand for parking in the
Netherlands, stores it raw, normalises it, and produces a ranked shortlist of
**underserved queries to write about** (the low-hanging fruit: real demand,
thin supply, no page of ours ranking).

Built to the spec in `parking-nl-collector-architecture.md`. Phase 1 only:
collect → normalise → shortlist. No scoring model yet (Phase 2), no live price
layer yet (Phase 3).

## Design principles (why it's shaped this way)

1. **Store raw forever** - every response is written untouched to
   `data/collector/raw/{source}/{date}/{seed_hash}.json`. Parsing improves; you
   can't re-fetch the past.
2. **Collectors are independent** - one failing never stops the others; each
   skips cleanly if its creds/deps are missing.
3. **Normalise late** - collectors write raw; `normalize.py` reads raw and
   produces the clean `queries` table.
4. **Everything timestamped + geo-tagged** - queries carry `location_tag`,
   `location_type`, `first_seen`, `last_seen`, `seen_count`.
5. **No scoring in Phase 1** - the shortlist sorts by `seen_count`, nothing clever.

## Quick start

```bash
cd scripts/collector
python3 pipeline.py init         # create DB + raw store
python3 pipeline.py seed         # build the location x modifier x language seeds

# smoke test (fast, ~2 min, no alphabet expansion):
python3 pipeline.py weekly --limit-seeds 30 --no-expand --skip-paa --skip-community

# real overnight run (~8-12h, full a-z0-9 expansion, per spec):
LIMIT_SEEDS=2000 ./run_weekly.sh
```

Output: `data/collector/shortlist_{date}.csv` — read it, pick 10, write them.

## The modules (build order)

| Module | Source | Needs | Notes |
|---|---|---|---|
| `db.py` | — | stdlib | schema + raw store |
| `seed_data.py` / `seeds.py` | — | stdlib | locations × modifiers × langs (+ events); weight-ranked selection |
| `autocomplete.py` | Google/Bing suggest | stdlib | keyless; a-z/0-9 expansion; depth-2; rate-limited |
| `normalize.py` | reads raw | stdlib | dedupe on (query_norm, source, location_tag); geo-tags |
| `firstparty.py` | Search Console | `GSC_SA_KEY`,`GSC_PROPERTY` + google libs | your zero-competition demand; flags appear-but-no-click |
| `paa.py` | Google SERP | `playwright` + chromium | PAA + supply signals (forum-in-top10, our_position, AI overview) |
| `community.py` | Reddit / Maps | stdlib (reddit); `GOOGLE_PLACES_KEY` (maps) | upvoted unanswered = gap |
| `feedback.py` | outcomes | stdlib | credits earned impressions back to seeds; re-weights |
| `shortlist.py` | queries+serp+outcomes | stdlib | the Phase-1 CSV |
| `pipeline.py` | — | — | CLI orchestrator; `run_weekly.sh` crons it |

## Enabling the credentialed collectors

- **First-party (do this first — cheapest, highest value):** reuse the same
  service account as `scripts/gsc_agent`. Set `GSC_SA_KEY` and `GSC_PROPERTY`
  (`sc-domain:parkingnetherlands.com`) and `pip install -r requirements.txt`.
  GSC queries with impressions but ~0 clicks are the highest-value writes on the
  whole site (you appear, but the page is wrong).
- **PAA + SERP:** `pip install playwright && python -m playwright install chromium`.
  Best-effort; Google's consent wall / captcha in a datacentre IP may need a
  residential proxy. Selectors are centralised in `paa.py` for tuning.
- **Maps reviews:** set `GOOGLE_PLACES_KEY` (integration point stubbed in
  `community.py`).

## Extending locations to all 342 municipalities

`seed_data.py` ships a strong working core (largest municipalities + airports,
hospitals, stadiums, ferries, beaches, border towns). Drop the rest into
`scripts/collector/locations_extra.txt`, one `Name|type` per line; they merge in
automatically. That file is gitignored.

## Data hygiene

Everything under `data/collector/` (raw responses, the SQLite DB, shortlists,
logs) is **gitignored** — it's regenerable and the GSC pull is first-party data
that must never be committed. Only the code lives in git.

## Scheduling

`run_weekly.sh` on cron (Sunday night) or launchd, mirroring
`scripts/gsc_agent/`. Monthly: Keyword Planner metrics on the shortlist only, and
`feedback` weight recalculation.

## Next phases (not built yet)

- **Phase 2 — scoring:** a hand-weighted sum of demand + scarcity + commercial +
  answerability, fit against `outcomes` only once ~50 pages are live.
- **Phase 3 — the data product:** daily live price scraping (Q-Park, APCOA,
  Interparking, P1, ParkBee, municipal), price history moat, a machine-readable
  JSON feed (an afternoon away from an MCP server), LLM-visibility hygiene, and a
  sellable parking-price API.
