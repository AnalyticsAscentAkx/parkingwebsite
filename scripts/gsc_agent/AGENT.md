# AGENT.md — the weekly SEO review step

This is the playbook a Claude Code run (or you) follows after the data pull.
Input: `data/gsc/latest_worklist.json`. Goal: **1000 organic clicks / 90 days.**

## How to work the worklist

Open `data/gsc/latest_worklist.json`. Work items top-down (already sorted by
estimated click gain). For each item, the `category` tells you the fix:

### category: `ctr_fix` (page 1, under-clicked)
The page already ranks — it's just not earning the click. Rewrite the
`<title>` and `<meta name="description">` of `landing_page`:
- Front-load the exact query.
- Keep the year current (2026/2027).
- Add a number or concrete benefit (`from €1.50/hr`, `9 P+R sites`, `[Map]`).
- Title < 60 chars, description < 155 chars.
- Match intent (price query → lead with price; "free" query → lead with free).
Do NOT invent facts — pull numbers from the page or `rdw-data.js`.

### category: `ranking_push` (page 2)
Ranking is the bottleneck. On `landing_page`:
- Add H2 sections answering the exact query variant and its "people also ask".
- Add a data table or list (LLMs and users both reward extractable answers).
- Add 2–3 internal links FROM strong pages (see the hub-and-spoke list below)
  TO this page, using the query as anchor text.

### category: `content_gap` (buried, high demand)
Likely no page truly owns this intent. Check if an existing page can be
sharpened first; only create a new page if the intent is genuinely distinct.

## Rules
- Edit the real `.html` files. One page = one primary query.
- Keep titles + meta descriptions unique across the whole site.
- Every new/changed page must stay valid: JSON-LD parses, links resolve, and
  the URL is in `sitemap.xml`.
- Leave changes for review unless told to ship. If shipping: commit with a clear
  message and push (Cloudflare Pages auto-deploys from `main`).

## Hub-and-spoke map (for internal linking)
- **Hubs** (link out to spokes): `index.html`, `all-cities.html`
- **Topic hubs**: `parking-fines`, `free-parking`, `street-parking`, `parking-apps`
- **Spokes**: city pages (`amsterdam`, `rotterdam`, `the-hague`, `utrecht`, …)
  and the 324 `garage/*` pages.
Every city page should link up to its topic hub and out to 2–3 sibling cities.

## LLM-visibility checklist (GEO/AEO)
For any page you touch, make it answer-engine friendly:
- One direct-answer sentence right under the H1 (the "snippet").
- FAQ JSON-LD with the real questions people ask.
- A comparison/price table with plain units.
- "Last updated" date visible + in schema.
- Keep `llms.txt` "Key Facts" in sync with any price/number you change.
