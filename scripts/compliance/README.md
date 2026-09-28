# Compliance agent

Checks that every page honours the licence terms of the data it shows, and
that the site meets the legal basics an ad-funded EU site is fined for
(consent, affiliate disclosure). Runs inside the daily job; hard findings stop
the auto-publish.

    python3 scripts/compliance/audit.py            # audit, write report.md
    python3 scripts/compliance/audit.py --fetch    # + re-fetch terms pages, flag changes
    python3 scripts/compliance/fix_rdw.py          # rewrite RDW wording site-wide

Exit codes: 0 clean, 1 warnings, 2 hard findings or changed terms.

## Files

| File | Role |
|---|---|
| `sources.py` | The registry. One entry per data source or policy: licence, terms URL, the clause that matters (quoted, with the date a human read it), and the regex checks. Edit this when a source is added or its terms change. |
| `audit.py` | Scans every public `.html`/`.js`, decides which sources each page uses, applies the checks, writes `report.md`, optionally snapshots the terms pages into `snapshots/` and compares hashes in `state.json`. |
| `fix_rdw.py` | Rewrites every public statement that names RDW as the source (forbidden by RDW's CC0 bijsluiter) into "national parking register (NPR)" wording. Also patches the page generators so the wording cannot come back. |
| `report.md` | Latest result. Committed so the history shows when the site was clean. |

## The rules, in one table

| Source | Licence | What we must do | What we must not do |
|---|---|---|---|
| RDW / NPR tariffs | CC0 | describe as "national parking register (NPR)" | name RDW as the source; link opendata.rdw.nl as source; use RDW logo or house style |
| NDW / DOT-NL chargers | CC0 (site default) | credit "NDW / DOT-NL" (safe under CC0 and CC-BY) | reuse NDW images |
| OpenStreetMap tiles | OSMF tile policy + ODbL | "(c) OpenStreetMap contributors" linked to /copyright; send Referer; honour caching | bulk/offline use; no-referrer policy; no-cache |
| Photon geocoder | fair use | attribute OpenStreetMap; debounce input | hammer it per keystroke |
| Open Charge Map | CC BY-SA 4.0 | credit with link; send API key | redistribute derived data under another licence |
| CBS | CC BY 4.0 | cite "Statistics Netherlands (CBS)" | imply CBS endorsement |
| Stad Gent | per dataset (unverified) | credit Stad Gent | - |
| AdSense (EEA) | Google EU consent policy, AVG | privacy page + certified CMP | serve personalised ads without consent |
| Affiliate links | Reclamecode, Google | visible disclosure + rel="sponsored" | undisclosed paid links |

## Adding a source

1. Add an entry to `SOURCES` in `sources.py` with the terms URL and the quoted
   clause. Write `require`/`forbid` regexes that are true on a compliant page.
2. Run `audit.py --fetch` once to store the first terms snapshot.
3. Fix the findings, run again, commit `report.md`.

## What still needs a human

- **AdSense consent banner.** The pages link `/privacy` and carry the
  privacy-choices link, but the banner itself is switched on in the AdSense
  console: Privacy & messaging > GDPR message > publish. Until that is done the
  audit reports a hard finding on every page. No code change needed.
- **Stad Gent licence.** Open the parking dataset page on data.stad.gent and
  record its licence in `sources.py`.
- **Open Charge Map terms** are on a JavaScript-rendered page the fetcher
  cannot read; re-check by hand once a year.
- **OSM tile server.** Allowed, but the policy says access can be withdrawn
  without notice for heavy commercial use. Moving to CARTO basemaps or a
  self-hosted tile server removes the dependency.
