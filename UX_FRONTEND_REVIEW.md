# UX and front-end review: Parking Netherlands

**Primary focus:** EV charging map at `/ev-charging`  
**Reviewed:** 28 September 2026  
**Scope:** Live page and the corresponding static HTML, CSS, JavaScript, and generated EV data in this project. This is a source-informed UX review, not a full browser/device compatibility, accessibility, security, or performance audit.

## Executive summary

The EV charging feature has a strong product idea: it combines charger location, operator-reported condition, charging price, and the parking tariff that can make an apparently cheap stop expensive. The split map/list interface, town-to-charger zoom levels, and viewport tile loading are sensible foundations for a dataset of this size.

The biggest problem is **trust and decision clarity**. The live page currently shows **0 days measured**. The generated dataset also says `days_measured: 0`, and the site’s reliability-history values are therefore unavailable. At the same time, the page presents a “Status” sort, advertises live charger status, and includes editorial copy with specific reliability comparisons. Some other counts differ between the live panel, static article, FAQ/schema, and generated data. A driver could reasonably wonder whether “working,” “live,” and the quoted cost mean what they think they mean.

The second biggest problem is the path to a useful charger. The default view is a national overview of unlabelled blue circles. The controls offer Status, Cost, and Power even though they do not change the overview list; the town search accepts exact or prefix matches and gives no message when it finds nothing. People have to infer that they should choose a town or zoom to level 12 before individual results and prices appear.

### Recommended order of work

1. Resolve the reliability-data gap and align every displayed claim with the actual dataset and its refresh time.
2. Make the first map view explain the circles and lead directly to a selected town or nearby charger.
3. Make controls state-aware: only show sorting that works in the current view, and give search a useful no-match state.
4. Show how the charge and parking totals were calculated, and do not present a global card rate as “cheapest here.”
5. Improve keyboard/screen-reader semantics and verify the mobile list/map flow.

## What is working well

- **A differentiated problem is being solved.** Parking cost is easy to overlook when comparing charging options. Combining the two is a useful reason to visit this tool.
- **The page presents a real working utility before the long article.** The map, town search, arrival/departure inputs, energy amount, sort buttons, and results list are immediately available on desktop.
- **The list and map are linked.** Selecting a location can connect a result row with a marker, and town rows take the visitor into a more detailed area.
- **The data approach is appropriately lightweight for a large national feed.** `ev-map.js` describes viewport tile loading instead of embedding the full location set in the HTML. It also caps rendered markers to avoid turning dense areas into unusable noise.
- **There is a mobile map/list switch.** This recognizes that two narrow side-by-side panes are not usable on a phone.
- **There are basic loading and error states.** The page uses skeleton rows and has copy for missing data or a failed Leaflet load.
- **The long-form content has useful decision context.** It explains electricity price, parking, charging speed, and Dutch charging vocabulary. The mobile-friendly horizontally scrollable tables are a good pattern for dense comparisons.
- **Some useful accessibility work is already present.** The main inputs have labels or accessible names, result counts use a polite live region, status sort buttons expose `aria-pressed`, and result rows are keyboard reachable.

## Detailed EV charging review

### 1. Critical: reliability claims are not backed by the current generated data

**Observed evidence:** The live tool reports `0 days measured`. The local `ev-data/meta.json` also contains `"days_measured":0`. The EV page generator derives this count from rows in the `reliability_daily` table. A sample generated tile has `null` uptime values throughout. The interface nevertheless has a **Status** sort and its metadata describes live status and reliability features. The article and FAQ give precise failure percentages and operator comparisons.

**Why it matters:** Reliability is a high-value reason to use this product: people may change their route based on whether a charger is usable. “0 days measured” next to status-focused controls makes the promise feel broken. An operator-reported point condition is also different from an available, unoccupied connector. The page should distinguish these concepts explicitly.

**Recommended action:**

- Treat zero history as a real product state, not as a minor statistic. Replace “0 days measured” with clear wording such as “Reliability history not available yet.”
- Until history exists, hide or disable **Status** sort, or redefine it as **Reported condition** and sort only on the current `DOWN` field. Do not imply historical uptime.
- Review the status-related SEO description, structured data, article tables, FAQ answers, and map legend against the feed actually published. Remove or qualify statements that the current feed cannot reproduce.
- Show a visible data timestamp beside the status label (for example, “Operator report received 14:20; refreshed 10 min ago”), and call it **operator-reported status**. If the source gives no useful timestamp, say status may be stale.
- State that “not reported faulty” does not mean “free connector available now.” Show occupancy/availability only if the data supports it.
- Add a generated-data quality check before publication: if the uptime history has zero days, the build should not publish copy that promises measured uptime.

**Code references:** [generated metadata](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-data/meta.json), [meta generation](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/scripts/ev/evlayer/seo/mapdata.py:157), [status fields and grade logic](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-map.js:25), [status sort](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-map.js:250), [page claim](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-charging.html:222).

### 2. Critical: EV counts drift between live UI, static copy, and metadata

The current live panel reports **80,001 locations**, **2,837 towns**, and **0 days measured**. The generated metadata matches 80,001 and 2,837. The HTML fallback initially says 2,844 towns, so a visitor can see a count change after data loads. Other page content reports 80,026 locations and 201,286 charge points, while structured data reports 80,001 locations and 201,239 charge points. The text also references 93,002 published tariffs.

Some variation can be legitimate if the measures represent different entities or different snapshot dates; the page does not explain that. Without a common “as of” date and precise labels, it reads as inconsistent data.

**Recommended action:**

- Generate the sidebar totals, article figures, FAQ, and JSON-LD from one build manifest or timestamped data snapshot.
- Define each measure in plain language: charging **locations**, **charge points**, **connectors**, and published **tariffs** are not interchangeable.
- Add a shared “Data snapshot: date/time” and show it in the interface and methodology section.
- Avoid duplicated hard-coded count values in HTML. If the data fetch fails, show “Count unavailable” instead of stale fallback values that disagree with the loaded data.
- If article figures intentionally use an older snapshot or a subset, label the denominator and date right beside the figure.

**Code references:** [initial count markup](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-charging.html:98), [JSON-LD dataset counts](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-charging.html:24), [article tariff count](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-charging.html:157), [FAQ counts](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-charging.html:31), [runtime stats](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-map.js:411).

### 3. High: national overview does not explain what the blue circles mean

At the initial Netherlands-wide zoom, the map shows many blue circles of different sizes. They represent towns, with radius based on location count. The map tooltip identifies a town and count, but is mainly discoverable by pointer hover; the visible hint only says “Zoom in to see individual chargers.” The status legend is hidden at this zoom, which is reasonable because the overview circles do not encode status, but there is no overview legend explaining size or what a circle represents.

**Why it matters:** A new visitor sees a map full of same-colour bubbles and may interpret them as individual stations or clusters. The map is visually prominent but its first state is not self-explanatory.

**Recommended action:**

- Add an overview legend: “Each circle is a town; larger circles have more charging locations.”
- Put town names and counts directly in the visible list rows (already partly present) and make the selected row visibly correspond to the selected map circle.
- Consider numeric count labels on larger circles or a conventional cluster marker showing the number of locations. Avoid relying on hover tooltips as the only explanation.
- When the user first opens the page, provide a clear action: “Search a town or select one from the list to see chargers.”
- Keep the status legend scoped to detail zoom, but announce that individual charger status appears after zooming in.

**Code references:** [overview marker drawing](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-map.js:165), [map hint and hidden legend](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-charging.html:81), [overview styles](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-map.css:29).

### 4. High: sort controls appear active when they do nothing

The **Status**, **Cost**, and **Power** controls are visible in the town overview. `listCities()` always sorts towns by location count. The click handler updates the selected sort state, but only redraws results when the map is in detail mode. So in the initial view, a visitor can press “Cost” or “Power” and see no change.

**Recommended action:**

- In town overview, either hide the charger sort control or provide town-level sort choices such as most locations, most charge points, and highest available power.
- In charger detail mode, label the sort by what it actually sorts: “Reported condition,” “Estimated total,” and “Max power.”
- If a control cannot apply yet, disable it with a short explanation such as “Zoom in to sort individual chargers.”
- Preserve the selected sort when zooming between modes only if that behavior is intuitive; otherwise reset and announce the reset.

**Code references:** [toolbar controls](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-charging.html:125), [town list sorting](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-map.js:230), [sort handler](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-map.js:373).

### 5. High: search failures are silent and search scope is narrow

The search input says “Find a town” and the handler searches town names by exact match or prefix. If there is no match, nothing changes: no inline message, suggestions, or focus guidance. It also does not search streets or addresses, despite the page being framed as a national charger finder.

**Recommended action:**

- For the current town-only behavior, say so: “Search towns or municipalities.” Add suggestions and a no-match state with an example or a reset action.
- If the target is “find a nearby charger,” support an address/place search or current-location control. Ask for geolocation only after the user explicitly taps it; keep town search as the no-permission fallback.
- Show the selected town in the search field or a clear location chip, with an obvious “Clear location” action.
- Explain that selecting a town zooms to individual chargers and that the list follows the map bounds.
- If results are limited by viewport or the 1,200 marker cap, give a useful next action (“Zoom in to see more nearby chargers”), not just a number.

**Code references:** [search input](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-charging.html:104), [prefix-only search](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-map.js:345), [marker cap](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-map.js:17).

### 6. High: “Cheapest card here” is calculated globally, not per charger/operator

`bestCard(kwh)` calculates one best card from the generic card-rate list using only the requested kWh. It does not receive the charger or operator. The result is then printed on every station row as “Cheapest card here.” It is therefore the same card/price for every charger, even though the editorial content correctly says card rates vary by operator and location.

**Recommended action:**

- Either remove the “here” claim and label it as a general benchmark, or use operator-specific card tariffs that are joined to each location.
- Show the price basis, validity date, and whether a start/session fee is included.
- If the app cannot substantiate a location-specific card rate, make the primary amount explicitly “operator ad-hoc estimate” and link to a card comparison explainer.
- Do not suggest a specific card is cheapest at a particular post unless the data maps that card’s rate to that operator/post.

**Code references:** [generic card calculation](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-map.js:97), [cards data query](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/scripts/ev/evlayer/seo/mapdata.py:145), [“Cheapest card here” output](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-map.js:283).

### 7. High: the cost total needs a clearer breakdown and assumptions

The main cost calculation multiplies the charger’s published per-kWh rate by the requested energy and adds the parking tariff for the selected time window. That is useful as an estimate, but the result is displayed as a single euro total. The user cannot quickly see how much is electricity versus parking, what rate source was used, or whether the requested kWh can realistically be delivered in the selected window.

The details are also not a full charging-session forecast: the code does not constrain delivered kWh by charger power, vehicle acceptance rate, battery curve, card-specific rate, session fees, or connector compatibility. Those limitations matter especially when a user chooses a short stay or a high kWh value.

**Recommended action:**

- Display a transparent breakdown: “Energy: €X (Y kWh × €Z/kWh) + parking: €A = estimated total €B.”
- Keep the requested kWh input, but call it **energy to buy**, not an exact charging outcome. Add “Estimate excludes card/session fees and vehicle charging limits.”
- If start/end time is meant to imply charge duration, use charger power and a conservative charging model, or clarify that time affects parking only.
- For a charger without a published energy price, do not imply the total includes electricity. Show “Parking estimate only; charging price unavailable.”
- Explain what a missing parking-area match means. `parkCost()` returns null when there is no tariff record, and the UI may then show a charge-only amount; users need to distinguish “free parking” from “parking data unavailable.”
- Show the tariff/source and validity/update date next to the result or in an accessible details disclosure.

**Code references:** [parking tariff calculation](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-map.js:67), [combined price](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-map.js:90), [result price label](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-map.js:266), [data caveat](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-charging.html:147).

### 8. Medium-high: city overview’s “Open” label is ambiguous

In the overview list, every town row ends with the word “Open.” This reads like a live availability/status value even though that row represents a town, not an individual charger. It may be intended as an action, but it is not styled or worded like one.

**Recommended action:** Replace “Open” with a clear button/action such as “View chargers,” or remove it because the whole row already activates. On charger rows, keep “reported operational,” “reported faulty,” and “status unavailable” distinct from “available now.”

**Code reference:** [overview row rendering](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-map.js:236).

### 9. Medium: the result card needs a better scan hierarchy

The detail row gives name, operator, max kW, uptime/down text, and total price. Important decision factors are present but do not yet form a clear “best option for me” card. The first-order choices for a driver are usually: compatible connector, can I charge now, how fast, how much total, how far, and what costs are excluded. The current source data does not appear to include connector type, route distance, or a confirmed occupied/free state.

**Recommended action:**

- Put the **estimated total** and price breakdown in a consistent primary position.
- Use compact, plain-language chips for **reported status**, **max kW**, and **price unavailable**.
- Add distance only if it reflects a route or label it “straight-line distance.”
- Add connector types and live occupancy only if the source provides reliable data; otherwise say “not provided.”
- Let the user open a details panel with operator, connector count/type, source timestamp, access notes, parking match, and caveats.
- Consider a “Best fit” ranking only after the user can specify what matters (fast, cheap, reliable, walkable). Keep its scoring explanation accessible.

### 10. Medium: map and list need more robust interaction feedback

The map and list are synchronized in code, and list rows support Enter, Space, and arrow-up/down. Search and map interactions can still feel abrupt: town search silently moves the map, tapping a town jumps to zoom 13, and there is no persistent selected-town context. In detail mode, the list is constrained to current map bounds; that is a sound model but needs to be visible to the user.

**Recommended action:**

- Keep a selected-town label above results and include a clear “Back to all towns” action.
- Announce map-driven list changes through a polite live region (currently the count is live, which is a useful start).
- On selecting a result row, keep focus in the list and announce the matching marker, instead of requiring a sighted user to infer the map movement.
- Consider an explicit “Search this area” action after panning, rather than silently refreshing a large result set after every move.
- Show “Showing N chargers in this map area” and “Zoom in to see more” when the 1,200 result cap is reached.

### 11. Medium: screen-reader semantics are mixed

The location list uses `role="listbox"` and rows use `role="option"`, but these options are interactive map actions, not conventional selectable values in a form. A map is marked `role="application"`, which can change how some assistive technologies handle it. The page also contains Leaflet canvas/SVG markers that are not a substitute for the result list.

**Recommended action:**

- Consider a normal semantic list (`ul`/`li`) with a real button for “Show on map” or a details link per station. This better reflects the action and usually needs less custom keyboard behavior than a listbox.
- If retaining a listbox pattern, implement the full expected keyboard/focus/selection model and test with screen readers.
- Give the map a concise accessible description of current mode, selected area, and available keyboard shortcuts. Do not rely on tooltip content alone.
- Ensure map keyboard controls have discoverable help and do not trap focus.
- Add accessible names and states for the mobile Map/List toggle and confirm its `aria-pressed` state tracks the visible panel.

**Code references:** [map role](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-charging.html:81), [listbox markup](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-charging.html:138), [row keyboard handlers](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-map.js:319), [mobile view tabs](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-charging.html:76).

### 12. Medium: mobile layout is a useful start but needs a full-height/scroll check

The Map/List toggle is the right overall direction. The app shell uses `100vh` sizing with separate scroll areas; mobile browsers can change the visible viewport as browser chrome expands or collapses. The panel header contains several controls before the list starts, so on a small screen the user may have little result-list area. The responsive breakpoint changes the whole interaction at 900px, which should be checked around that transition and on landscape phones/tablets.

**Recommended action:**

- Use `100dvh` with a `100vh` fallback for mobile browser chrome behavior.
- Keep search and town context near the top of List view, but consider collapsing secondary controls (energy/date inputs) behind a “Price this stop” disclosure.
- Make the mobile tab bar sticky and ensure it does not cover map attribution, controls, or focused list rows.
- Test small screens in both map and list modes, including a long city name, large text settings, and the on-screen keyboard open.
- Check map attribution remains visible and does not overlap controls/menus; the CSS already adjusts z-index, which is good.

**Code references:** [app shell dimensions](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-map.css:7), [mobile mode rules](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-map.css:167), [responsive viewport rule](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-map.css:202).

### 13. Medium: initialize time and URL behavior need predictable updates

The page defaults to a two-hour charging stop and stores `arriving`/`leaving` in the URL when the date inputs change. Invalid or reversed times are silently ignored by `syncWindow()`. Energy changes redraw charger results in detail mode, but the page does not make clear which controls recalculate immediately and which need the user to search/zoom.

**Recommended action:**

- Validate leaving time is after arrival inline and associate the error with the relevant field.
- Make the default duration visible: “2-hour stop, starting now” or include a one-click reset to now + 2 hours.
- Make URL state include the selected town/map center/zoom if returning to a shared link should restore the same results. Today only the time window is persisted.
- Update the result count and sort immediately when energy/time changes; announce the update.
- Consider a small “Reset time” control so visitors can recover quickly after editing.

**Code reference:** [time validation and URL update](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-map.js:332).

### 14. Medium: data loading and map readiness should be observable

The page fetches four JSON resources in `Promise.all`, then loads Leaflet from a CDN before initializing the map. The skeleton helps with the list, and errors are shown in the result panel, but no explicit freshness indicator or distinction between an empty tile and a failed tile is visible. `loadTiles()` converts failed HTTP responses and network errors to empty arrays, which makes a failed tile look like a genuinely empty area.

**Recommended action:**

- Track tile fetch failures separately from valid empty tiles and show “Some charger data could not be loaded” when relevant.
- Show map/list loading state until the first viewport data is ready; retain the previous list while a new viewport loads to avoid blank flashes.
- Add a “data updated at” value to `meta.json` and display it in the panel/methodology note.
- Consider a local/pinned Leaflet asset or integrity-protected CDN loading and show a meaningful map fallback if the library fails.
- Keep the viewport-only fetching approach; it is a good fit. Add cancellation or request-generation guards if users pan quickly and old tile requests can overwrite newer visible state.

**Code references:** [tile error fallback](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-map.js:122), [tile rendering flow](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-map.js:142), [runtime asset loading](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-map.js:411).

### 15. Medium: article content and app currently feel like separate products

The interactive utility occupies a full viewport-height app shell, followed by a long editorial article. The article is valuable, but once a visitor scrolls away from the tool there is no obvious persistent route back to the chosen area or current results. Some article facts are duplicated in FAQ and structured data, which compounds the data-drift risk.

**Recommended action:**

- Keep the interactive tool first, then use a compact “How to use the map” section before the long article.
- Add an in-page jump link from the article back to the map and preserve any selected area/time in the URL.
- Generate article tables, FAQs, and structured data from the same data snapshot as the map.
- Add a small “Updated” label and methodology link beside dynamic-looking figures, instead of making the reader scroll to learn the source.

## Wider site observations from the initial review

The homepage gives destination search appropriate prominence, and its map/city routes give several ways into the data. The main site opportunity is to move visitors from broad claims into a concrete comparison sooner and reduce repeated long-form content between the homepage and city guides. The search page also deserves the same price-estimation disclosure described above: its code interpolates between tariff points, while the marketing copy suggests exact pricing. The main parking map should make its city filter actually filter results or rename it to “Go to city.”

The EV page is the highest-priority area because the data directly affects a driver’s route and expected cost. Make the current source state honest first, then polish visual hierarchy and add richer features.

## Suggested target experience for the EV page

1. **Open:** Show map/list controls, map centered on the Netherlands, and a clear prompt to search a town or use location. Explain the circles and give a “Choose a town” list.
2. **Choose area:** Search returns autocomplete suggestions with an explicit no-results/error state. Selecting a town updates the area label and map.
3. **Compare:** The user sees individual chargers with operator, reported condition, maximum power, connector details when known, distance, and a total cost breakdown for the chosen window and kWh.
4. **Trust:** Each result says what is known, what is estimated, when it was updated, and what fees/availability the dataset does not cover.
5. **Act:** Clear directions and an operator link are available, along with a way to change the search area without losing the date/energy inputs.
6. **Accessible alternative:** The same results and actions work as a semantic list without needing to operate the map.

## Prioritized implementation plan

### P0 — Trust and correctness

- Fix the reliability-history story: currently 0 measured days.
- Synchronize location, town, connector, tariff, and fault totals across UI, article, FAQ, metadata, and schema.
- Add dataset `updated_at` and source timestamp; change “live” to “operator-reported” unless freshness is genuinely near-real-time.
- Remove or qualify generic “Cheapest card here” output.
- Make cost component and missing-data states explicit.

### P1 — Core task flow

- Explain national overview markers and direct visitors toward town selection.
- Make search useful for no-match and clarify whether it supports towns only or addresses too.
- Hide/disable irrelevant overview sort controls, or make them town-specific.
- Replace “Open” on town rows with “View chargers.”
- Preserve selected town and pricing inputs through map/list switching and shareable URLs.

### P2 — Accessibility and responsive fit

- Use semantic list/button actions or implement the complete listbox pattern.
- Improve map keyboard help and provide the list as a complete alternative.
- Verify mobile viewport height, tab state, scroll containment, large text, and keyboard-open behavior.
- Add visible inline validation and polite announcements for result changes.

### P3 — Refinement

- Improve station comparison hierarchy and “best fit” guidance.
- Add optional nearby-address or location search, connector and access filters, and explicit availability only where the data supports them.
- Add visual indicators for data quality, rate type, source, and update time.
- Consider performance improvements only after measurement; the current tiled data design is a strong starting point.

## Review limitations

I reviewed the live EV charging page at desktop width and inspected the local HTML/CSS/JS/data paths. I did not run automated accessibility checks, device/browser coverage, performance profiling, or a charging-price validation against the source provider. Recommendations about behavior are grounded in the code path; third-party feed correctness and tariff accuracy need validation against their source data.

## Product and SEO direction: how to make this a standout service

The route to a stronger product is not to publish the most pages or add more map controls. It is to become the most dependable answer to a driver's actual question: **“Where can I charge near where I’m going, what will this stop cost me, and what should I expect when I arrive?”** The SEO program should grow out of answering that question better than a generic directory.

### What the code says about the current SEO foundation

- The page is crawlable HTML with real explanatory content, canonical URLs, FAQ and dataset structured data, and links to city pages. The map's data loads in the browser, while the location detail pages are generated as HTML. That gives the site a usable foundation, but the interactive map itself is not the complete indexable experience.
- The data pipeline deliberately gates individual charger pages on `MIN_HISTORY_DAYS`, which is a useful thin-page safeguard. City pages currently become indexable at three locations, regardless of whether their price or reliability data is useful enough to support the title and description.
- Intent pages are added to the sitemap as indexable whenever the city has enough total locations. The “most reliable” page claims measured 30-day uptime even when no history is available. The “cheapest” page can be generated without usable tariffs, and the fast-charging generator falls back to the full city list when it finds no qualifying high-power stations. Those conditions can make the page title, promise, result set, and sitemap disagree.
- The sitemap generator writes today's date as `lastmod` for every URL whenever the build runs. `lastmod` should represent a material page change, so it should come from page/data change tracking rather than build time.
- Current statistics, article copy, FAQ answers, and structured data are maintained separately from the map snapshot. Their differing counts and unsupported reliability details are a publication-quality problem before they are a keyword opportunity.

Google's current guidance favors helpful, original, accurate content over search-engine-first or scaled generic pages. Structured data must represent visible page content and does not guarantee a rich result. Treat crawlable pages, accurate data and distinct user value as the SEO work; there is no special schema shortcut to rankings. References: [Google's people-first content guide](https://developers.google.com/search/docs/fundamentals/creating-helpful-content), [SEO Starter Guide](https://developers.google.com/search/docs/fundamentals/seo-starter-guide), [JavaScript SEO basics](https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics), and [structured data policies](https://developers.google.com/search/docs/appearance/structured-data/sd-policies).

### Recommended SEO execution sequence

**Phase 0 — Make every promise verifiable**

1. Create one versioned data snapshot for the live map, page facts, article tables, FAQ answers, JSON-LD, update date, and sitemap. Generate the displayed totals and any data-backed sentences from that snapshot.
2. Define each metric precisely: locations vs. charge points vs. connectors; operator-reported faults vs. uptime history vs. live connector availability; listed energy tariff vs. estimated session total; matched parking tariff vs. unknown parking price.
3. Add a source/update panel and methodology page that state source, refresh cadence, coverage, known gaps, and price assumptions. Keep the page's copy consistent with the snapshot's quality flags.
4. Add publication gates to the builder: do not emit an indexable reliability page without sufficient measured observations; do not call an area “cheapest” without enough priced results; do not publish a fast-charging ranking without qualifying stations. Record an accurate `lastmod` only when a page's meaningful content changes.

**Phase 1 — Win the high-intent Dutch EV charging journeys**

Build a small, justified set of location and comparison pages around needs the data can answer: public EV charging in major cities; fast/DC charging where there are enough qualifying sites; charger plus parking cost where both rates are available; and destination corridors or regions only if coverage and source quality support them. Each page should contain a useful summary, honest counts, map/list entry point, real comparison data, practical local context, and links to related areas. Do not create near-identical pages for every town merely because a slug can be generated.

Prioritize Dutch-language intent and terminology if Dutch drivers are a core audience, while preserving English pages for visitors who need them. Use actual Search Console queries and landing-page performance to choose language, titles, internal links, and follow-up topics rather than guessing a giant keyword list.

**Phase 2 — Make the tool itself earn links and repeat use**

Improve the task flow so a visitor can search a town, understand the map, choose a charger, compare the electricity and parking components, and get directions. Let useful selections be shareable and give each indexable city page a server-rendered summary and result list that remains meaningful before JavaScript runs. Add operator, connector, access, price and status filters only where underlying fields are accurate and sufficiently complete. Offer export/shareable comparisons if user research supports them.

**Phase 3 — Grow from evidence**

Review Search Console indexing and queries, analytics task completion, map/list usage, no-result searches, data freshness, and source coverage. Expand or consolidate page types based on observed demand and whether the page helps someone complete a task. Measure Core Web Vitals and accessibility on real mobile devices before investing in a redesign or extra motion. Keep sitemap entries limited to canonical, indexable, useful pages.

### Senior UX/front-end product bar

- **One obvious start:** town/address search, a clear national map overview, and an alternate list path; no controls that appear active but cannot affect results.
- **Decision-ready results:** operator, connector/power where known, reported condition with freshness, distance where a user location was explicitly supplied, and a legible total split into charging and parking.
- **Honest estimates:** define energy, time, fees and missing tariffs. Never call an unpriced location free or a station available based only on a fault flag.
- **Robust interaction:** useful no-match and network-error states, keyboard operation, visible focus, proper mobile map/list behavior, preserved filters and URL state, and a non-map route to the same results.
- **Trust that is easy to inspect:** provider attribution, update time, methodology and a correction/contact route close to the data they explain.

## Changes made after the initial review

In the first implementation pass, [ev-map.js](/Users/aakash.chavash/Documents/Personal%20Script/parking_website%20/ev-map.js) now distinguishes failed map-tile requests from valid empty tiles, shows a partial-data warning, and retries failed tiles when the user moves the map. It explains the town-circle overview, hides charger sort controls until individual chargers are shown, searches for town-name fragments, announces a no-match state, and replaces the ambiguous “Open” text on town rows with “View chargers.” It also removes the misleading “Cheapest card here” estimate because the source was a site-wide benchmark rather than the charger operator's tariff. The page now shows “Not available” for missing uptime history and aligns its town count with the generated data. The EV page generator now emits only comparison pages supported by enough history, priced locations, or qualifying fast chargers; it also removes uptime promises and replaces the zero-days statistic when history is unavailable. These are scoped improvements; they do not synchronize the manually maintained `/ev-charging` article, FAQ and structured data with the data snapshot, or yet make generated page content unique and useful beyond its result list.

## Follow-up review: current live page and content organization

**Reviewed:** 28 September 2026, live `/ev-charging` at a narrow mobile viewport, including Map and List states and the full page text. This is a content and interaction review, not a full device matrix.

### Highest-impact user-friction findings

1. **The mobile list makes the user configure a stop before finding a charger.** The sequence is title and paragraph, three statistics, town search, arrival time, departure time, energy amount, then results. On the observed phone-sized view, those controls consume most of the first screen and only a few town rows are visible. Put town search first, show results next, and move the date/time/energy inputs into a clearly named expandable “Refine cost estimate” section. Keep sensible defaults so cost sorting still works.
2. **“400 towns” can read as a complete result count.** The list is intentionally capped at 400 visible towns, while the page reports 2,837 towns nationally. Say “Showing up to 400 towns in this map view; search to find another town,” or change the interaction so search filters all 2,837 towns and the visible-map count is explicit. Do not imply the list is complete.
3. **The two ways to start are not equally easy to discover.** On mobile, map/list is the right pattern, but the map can be visually dense in the Randstad. Make search available in both modes and let typing narrow the town list immediately. If map circles overlap, the town list should remain the reliable route; do not ask the user to tap a tiny circle.
4. **The page has no contents navigation before a long article.** After the tool, the reader reaches seven substantial topics, several tables, a glossary, seven FAQs, and methodology. Add a short “On this page” row of anchors (Costs, Parking, Status, Fast charging, Cities, Questions, Sources). On mobile it can wrap or scroll horizontally with a visible affordance.
5. **The data tables compete with the main explanation.** The operator-price and fault tables each have ten rows, and the city table has fifteen. Lead each with a one-sentence takeaway and keep a compact top-five/summary visible. Put the full comparison in a labeled disclosure such as “See all 10 operators.” Give every disclosure a useful summary, keep captions and table headers intact, and leave one table open at most by default.

### Fix content contradictions before polishing the prose

- The map result no longer shows a “cheapest card” estimate, but the FAQ still says the map shows the cheapest card for each location. Remove or rewrite that answer; it now promises a feature the tool does not provide.
- The methodology says an unreported failed post “will still show as working,” while the map uses a separate unavailable/no-history state when reliability is absent. Align the sentence with the actual interface: operator-reported faults are shown; missing reports are unknown, not verified working.
- Several current-snapshot numbers are repeated in the opening, tables, FAQ, structured data and explanatory text. Keep one canonical source and derive the copies from it; label snapshot-dependent facts with an “As of” date/time.
- “Broken right now” and “refreshed continuously” sound more precise than a page without a visible last-updated timestamp. Prefer “reported faulty in the latest feed snapshot” and show the snapshot time, or describe the update cadence that can actually be guaranteed.
- “What a stop actually costs” overpromises a calculation based on requested kWh and matched hourly parking. Call it an estimate and state that vehicle charging speed, taper, card/session fees, occupancy and access restrictions can change the real stop.

### Recommended page outline

1. **Find a charger** — concise H1 and one-sentence value proposition; town search; Map/List switch; visible result count; results. Keep the map available, but don't let it be the only path to towns.
2. **Optional cost estimate** — collapsed by default on mobile; arrival, departure and kWh; describe the current default estimate. Expand automatically only if the user chooses cost sorting or opens a result's price details.
3. **Quick answers** — three compact cards: typical charging-price range, parking may be charged separately, and status is operator-reported. Include the snapshot date and links to deeper sections.
4. **Compare costs and parking** — short explanation and key result first; detailed operator table behind a disclosure; link to the full parking guide.
5. **Check status and choose speed** — keep current faults distinct from historical reliability; summarize AC vs DC; detailed breakdown available on demand.
6. **Explore by city** — a compact, searchable city directory/table that links to useful city charger pages. Avoid repeating the site-wide parking-guide links as if they were charger results.
7. **Practical questions** — 4–5 concise FAQs addressing cost, parking, current status, fast charging, and payment. Remove answers that simply restate a table or promise missing app functionality.
8. **Sources and method** — put data providers, matching radius, price limitations, status meaning, refresh time and contact/correction route in one scannable section.

Keep the page long enough to answer real questions, but make detail optional. Collapsing secondary tables and grouping topics improves scanning without deleting useful indexable text. Avoid making every paragraph an accordion: users should see the core answer and the most useful evidence without opening several controls.

### Suggested implementation order

**P0:** fix the obsolete card-price FAQ; accurately state how missing status is represented; make the 400-town cap explicit; add a compact contents nav and real snapshot timestamp.

**P1:** reorder the mobile panel to Search → Results → optional cost estimate; make town search filter the list; collapse secondary tables and remove the default-open FAQ answer.

**P2:** group content into the outline above, replace duplicated factual copy with generated values, and review whether the city directory belongs on this page or on a dedicated index page.

## Map inspiration: patterns to borrow from ParkBee

ParkBee's official product material describes one map experience that puts nearby street and garage options together, with prices, opening hours and availability, and a map control to switch street parking on or off. Its published app imagery also uses price labels on map pins and a selected-location card with the rate, availability, practical constraints and a direct action. These patterns help the driver compare and act without reading a long explanation first. See [ParkBee's app overview](https://parkbee.com/en/pages/parking-app) and [how it works](https://parkbee.com/en/how-it-works).

Apply the interaction principles to charger discovery, while displaying only facts your data can support:

1. **Start with the destination.** Keep “Search town or address” visible above the map/list and let it filter the town results as the user types. On the current mobile list, the visitor must pass the national counts and all three estimate fields before reaching results.
2. **Make the map markers carry a decision.** At town zoom, use clusters/counts instead of hundreds of overlapping circles. At charger zoom, consider price labels for an explicitly defined example session, or keep the map clean and show price/status in a strong selected-location card. Avoid putting price, fault status, power and cluster size into color/shape simultaneously.
3. **Give a selected charger a useful preview.** Selecting a marker should reveal a mobile bottom sheet / desktop detail panel with operator, reported status and timestamp, maximum power and connector details when known, charge estimate, parking estimate and combined total. Make the next action clear (for example, directions) only when the location data can support it.
4. **Keep map and list in sync.** Highlight the selected row and pin, preserve the selected location when switching modes, and give the user a “Search this area” action after panning. A list is especially valuable in dense Randstad clusters where small map targets overlap.
5. **Offer a few task-based map filters.** Use concise chips such as “Fast charging,” “Lower estimated cost,” and “Reported faulty,” provided the relevant data is present. Make filters visibly active and include a one-tap clear action. “Reported faulty” must not imply live connector availability.
6. **Put the price context in the result.** ParkBee's public description emphasizes comparing options with rates and availability together. For your map, say what the total represents (for example, “20 kWh + 2 hours”) and keep the charging and parking parts visible. Do not call it a guaranteed final bill.

The strongest ParkBee lesson is the order: search, compare nearby options, inspect one option, then act. The charger map already has meaningful data; reducing the steps and making map pins answer “which one should I look at?” will make that data easier to use.
