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
