# Weekly GSC agent

Pulls Google Search Console data every week and turns it into a prioritized
SEO worklist for parkingnetherlands.com. Lives inside the site repo — no
separate repo to clone (that was the failure mode of the old cloud schedule).

## What it does

1. `gsc_weekly.py` queries Search Console (`searchanalytics`) for the last 90
   days vs the prior 90 days, by query and by page.
2. It ranks opportunities into three buckets:
   - **ctr_fix** — page 1, clicked less than the position deserves → title/meta rewrite (fastest wins)
   - **ranking_push** — page 2 with real demand → deepen content + internal links
   - **content_gap** — buried but high demand → weak or missing dedicated page
3. It writes `data/gsc/latest_report.md` (human) and `data/gsc/latest_worklist.json`
   (machine-readable, for the Claude review step in `AGENT.md`).

It never edits the site.

## One-time setup

1. **Create a service account** in Google Cloud, enable the *Search Console API*,
   and download its JSON key. Save it OUTSIDE the repo, e.g.
   `~/.secrets/parkingnetherlands-gsc.json`.
2. **Grant it access**: Search Console → Settings → Users and permissions → Add
   user → paste the service account's email (looks like
   `name@project.iam.gserviceaccount.com`) → permission "Full" or "Restricted".
3. **Configure** — edit `run.sh` (or export in your shell):
   ```bash
   export GSC_SA_KEY="$HOME/.secrets/parkingnetherlands-gsc.json"
   export GSC_PROPERTY="sc-domain:parkingnetherlands.com"
   ```
   (Use `sc-domain:` for a domain property; use the full `https://…/` URL for a
   URL-prefix property.)

## Run it

```bash
bash scripts/gsc_agent/run.sh        # bootstraps a venv, pulls data, writes report
# or directly:
python3 scripts/gsc_agent/gsc_weekly.py --days 90
```

Output lands in `data/gsc/` (gitignored — analytics + secrets never get committed).

## Schedule it weekly (macOS launchd)

1. Edit the paths + secrets in `com.parkingnetherlands.gsc-weekly.plist`.
2. `cp scripts/gsc_agent/com.parkingnetherlands.gsc-weekly.plist ~/Library/LaunchAgents/`
3. `launchctl load ~/Library/LaunchAgents/com.parkingnetherlands.gsc-weekly.plist`
4. Test immediately: `launchctl start com.parkingnetherlands.gsc-weekly`

Runs every Monday 08:00. Logs in `data/gsc/`.

## Security note

The old scheduled agent had a broad-scope `ghp_` PAT in plaintext with push
rights to the live site. Rotate it, store it as a secret, and scope the
replacement to only the repos it needs. This agent keeps the GSC key outside
the repo and gitignores `*-gsc.json`.
