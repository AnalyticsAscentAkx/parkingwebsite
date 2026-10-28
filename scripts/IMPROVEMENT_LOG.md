# Improvement log

One entry per experiment. Each cycle: judge entries live 14+ days against their
baseline, then log new changes. Baselines are Search Console, 28 days, captured
by `scripts/qa/logchange.py` (machine copy in `data/qa/changes.jsonl`).
Lives under `scripts/` because the repo root is the public web root.

Verdict rule: a CTR or position change only counts when it beats the same
window's movement on untouched control pages (/map, /, /parking-apps until it
was changed) and a two-proportion z-test passes |z| >= 1.96. Otherwise NEUTRAL.

## Cycle 2026-10-22

### Judged (changes of 2026-10-05; before = 09-21..10-04, after = 10-06..10-19)

| Page | Change | Before | After | z | Verdict |
|---|---|---|---|---|---|
| /parking-fines | title leads with the amount | 9/611, 1.47%, pos 6.7 | 5/869, 0.58%, pos 10.2 | -1.76 | NEUTRAL (not significant, position confounded) |
| /free-parking | routes to map + inbound links | 9/218, 4.13%, pos 8.5 | 5/588, 0.85%, pos 12.5 | -3.16 | NEUTRAL (drop matches controls) |
| /street-parking | routes to map + inbound links | 4/235, 1.70%, pos 14.9 | 2/588, 0.34%, pos 18.0 | -2.07 | NEUTRAL (drop matches controls) |
| /free-parking-sunday | routes to map + inbound links | 2/169, 1.18%, pos 6.7 | 4/182, 2.20%, pos 6.7 | +0.73 | NEUTRAL (too few clicks) |

Controls, same windows, untouched: /map 10.7% -> 5.7% (pos 11.6 -> 13.1),
/ 6.8% -> 3.3% (12.1 -> 14.4), /parking-apps 2.7% -> 1.6% (17.8 -> 19.6).
Impressions grew 2-3x site-wide at worse positions; the CTR drop is the site
being shown for broader queries, not the edits. No reverts.
The scorecard's "backfired" labels have no control and no significance test.
Full 28-day judgement for all four: 2026-11-02.

### Shipped

**/parking-apps: rebuilt around verified 2026 fees**
- Change: fee table from each provider's own tariff page (EasyPark 15%, min
  0.19, max 0.70/h, max 7/session; Yellowbrick 0.49/session; ANWB no fee),
  fee per stop for 1 h and 2 h in Amsterdam, Utrecht, Rotterdam, Den Haag,
  Delft, charging-through-the-app cost at the 0.41/kWh median, FAQ + FAQPage
  schema rewritten, meta description rewritten. Title unchanged. Removed
  unsourced claims (EUR 2-5/visit, EUR 300-700/year), the duplicate
  Parkmobile row and the unsourced Mobimundo row.
- URL: https://parkingnetherlands.com/parking-apps
- Hypothesis: the page ranks for "parking app netherlands" intent at 8.8-13.8
  but averages 20 because the content was thin and wrong; specific, sourced
  fee and cost-per-stop data matches the comparison intent better.
- Metric: average position. Secondary: clicks.
- Baseline (28d to 2026-10-19): 11 clicks, 497 impressions, 2.21% CTR, pos 20.0.
- Expected: position 20 -> 12-15. At ~500 impressions/28d, a click change
  under ~10 will be noise.
- Judge on: 2026-11-19.
- 2026-10-28: ParkBee added mid-test (table row, pick card, FAQ + schema;
  title and meta unchanged), on the owner's request for its affiliate value.
  Treat a position move after this date as the combined effect.

### Held for a later cycle (ranked)
1. FCP ~4 s on every top landing page in Lighthouse mobile (home LCP 9.3 s,
   /map 7.6 s). Site-wide cause, not per page.
2. Charge-card block on /parking-apps, /ev-parking, /ev-charging says the
   national median is EUR 0.37; the site's own figure is EUR 0.41.
3. /de/parkstrafe-niederlande: 237 impressions, pos 8.4, 1.3% CTR (expected
   ~2.5%); title shares the pattern still under test on /parking-fines, so
   wait for that verdict.
4. GA4: 6 of 9 users who saw results since the 2026-10-18 fix still hit zero
   results. Too few to act on; recheck at 50+ users.
