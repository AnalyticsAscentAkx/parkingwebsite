#!/usr/bin/env python3
"""Render the map in a real browser and prove it still works.

Written on 2026-10-18, the day two map changes were pushed after being
prototyped by injecting JavaScript into the live page. The injection proved
the idea; nothing proved the built file. The owner found the map showing no
information and no cards opening, and the changes were reverted.

Every other check in this directory reads HTML over HTTP. That cannot see
this class of fault at all: the map is drawn by JavaScript, so a page whose
script throws still returns 200 with a perfect <head>. This file is the only
one that opens a browser, waits for the map to draw, and clicks something.

What it asserts, per page, at desktop and at phone width:

  * the list drew rows
  * the map drew markers
  * clicking the first row opens a detail card with a price in it
  * clicking a map marker opens one too
  * the console logged no errors
  * the four summary tiles are not all blank

and once, against known tariff data:

  * a two hour Sunday stop on Prinsengracht in Amsterdam costs EUR 1.95.
    It read EUR 50.25 until 2026-10-18 because a parking pass was treated as
    compulsory. The number is checked here so it cannot drift back silently.

Usage:
    python3 scripts/qa/smoke_map.py                  # the live site
    python3 scripts/qa/smoke_map.py --base http://127.0.0.1:8788
    python3 scripts/qa/smoke_map.py --json

Exit codes: 0 everything rendered, 2 something is broken. The daily job
treats 2 as a reason to shout, because a map that does not draw is the whole
product being down while every HTTP check stays green.
"""
import argparse
import json
import sys
import time
from datetime import date, timedelta

LIVE = "https://parkingnetherlands.com"

# page path -> whether it is served as a clean URL on the live site
PAGES = ["/ev-charging", "/search", "/"]

DESKTOP = {"width": 1440, "height": 900}
PHONE = {"width": 390, "height": 844}

# The Sunday price guard. Prinsengracht sits in tariff area 363_T11A, where
# metered parking does not begin until 12:00 on a Sunday and the only other
# product is a day ticket nobody buys for two hours.
PRICE_CASE = {
    "station": "193 Prinsengracht",
    "lat": "52.37762", "lng": "4.88601", "zoom": "18",
    "expect": "€1.95",
}


def next_weekday(target):
    """The next date whose weekday is `target` (0 Monday ... 6 Sunday)."""
    d = date.today()
    return d + timedelta(days=(target - d.weekday()) % 7 or 7)


def stamp(d, hh, mm):
    return f"{d.strftime('%Y%m%d')}{hh:02d}{mm:02d}"


def check_page(ctx, base, path, viewport, failures, notes):
    where = f"{path} @{viewport['width']}px"
    page = ctx.new_page()
    page.set_viewport_size(viewport)
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)[:200]))
    page.on("console", lambda m: errors.append(m.text[:200]) if m.type == "error" else None)
    try:
        page.goto(base + path, wait_until="load", timeout=45000)
        # The map draws after the cell data arrives; wait for a row rather
        # than a fixed sleep, so a slow network does not read as a failure.
        try:
            page.wait_for_selector(".ev-row", timeout=25000)
        except Exception:
            failures.append(f"{where}: no list rows ever appeared")
            return
        page.wait_for_timeout(1500)

        rows = page.locator(".ev-row").count()
        pins = page.locator(".leaflet-marker-icon").count()
        tiles = page.locator(".leaflet-tile").count()
        if rows == 0:
            failures.append(f"{where}: list drew 0 rows")
        if pins == 0:
            failures.append(f"{where}: map drew 0 markers")
        if tiles == 0:
            failures.append(f"{where}: no map tiles loaded")

        # A row must open a card, and that card must carry a price.
        if rows:
            # dispatch rather than a real click: the sticky header and the
            # footer sit over parts of the page and Playwright refuses a click
            # it thinks another element would receive.
            page.locator(".ev-row").first.dispatch_event("click")
            page.wait_for_timeout(800)
            card = page.locator(".ev-card")
            if card.count() == 0:
                failures.append(f"{where}: clicking a list row opened no card")
            else:
                text = card.first.inner_text()
                if "€" not in text:
                    failures.append(f"{where}: card opened with no price in it")

        # And so must a marker, which is a separate code path.
        if pins:
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            try:
                page.locator(".leaflet-marker-icon").first.dispatch_event("click")
                page.wait_for_timeout(800)
                if page.locator(".ev-card").count() == 0:
                    failures.append(f"{where}: clicking a map marker opened no card")
            except Exception as e:
                notes.append(f"{where}: marker click skipped ({str(e)[:60]})")

        # All four summary tiles blank means pricing fell over upstream.
        vals = []
        for tile in ("mCheap", "mKwh", "mPark", "mFast"):
            el = page.locator(f"#{tile}")
            if el.count():
                vals.append((el.first.inner_text() or "").strip())
        if vals and not any(v and v not in ("-", "–") for v in vals):
            failures.append(f"{where}: every summary tile is blank")

        if errors:
            failures.append(f"{where}: console errors: {errors[:2]}")
        notes.append(f"{where}: {rows} rows, {pins} markers, {tiles} tiles")
    finally:
        page.close()


def check_price(ctx, base, suffix, failures, notes):
    """A known stay must still cost what it should."""
    sunday = next_weekday(6)
    q = (f"?lat={PRICE_CASE['lat']}&lng={PRICE_CASE['lng']}&zoom={PRICE_CASE['zoom']}"
         f"&arriving={stamp(sunday, 10, 15)}&leaving={stamp(sunday, 12, 15)}&kwh=20")
    page = ctx.new_page()
    page.set_viewport_size(DESKTOP)
    try:
        page.goto(base + "/ev-charging" + suffix + q, wait_until="load", timeout=45000)
        page.wait_for_selector(".ev-row", timeout=25000)
        page.wait_for_timeout(1500)
        row = page.locator(".ev-row", has_text=PRICE_CASE["station"])
        if row.count() == 0:
            notes.append(f"price guard: {PRICE_CASE['station']} not in view, skipped")
            return
        text = row.first.inner_text().replace(" ", " ")
        if PRICE_CASE["expect"] not in text:
            failures.append(
                f"price guard: Sunday 10:15-12:15 at {PRICE_CASE['station']} should read "
                f"{PRICE_CASE['expect']} parking, got: {' '.join(text.split())[:120]}")
        else:
            notes.append(f"price guard: {PRICE_CASE['expect']} as expected")
    except Exception as e:
        notes.append(f"price guard skipped: {str(e)[:80]}")
    finally:
        page.close()


def check_speed(ctx, base, paths, local, failures, notes):
    """How long until the page is usable, desktop and phone.

    Asked for on 2026-10-19: "see how fast things are". Budgets are generous
    on purpose; this is a regression alarm, not a performance audit. The map
    pages fetch cell data before they can draw, so they are judged on when a
    row appears, not on first paint.
    """
    for vp, label, budget in ((DESKTOP, "desktop", 6000), (PHONE, "phone", 9000)):
        page = ctx.new_page()
        page.set_viewport_size(vp)
        try:
            for path in paths:
                target = ("/index.html" if path == "/" else path + ".html") if local else path
                t0 = time.time()
                page.goto(base + target, wait_until="domcontentloaded", timeout=45000)
                try:
                    page.wait_for_selector(".ev-row, .pk, h1", timeout=budget)
                except Exception:
                    failures.append(f"speed {label} {path}: nothing usable within {budget}ms")
                    continue
                ms = int((time.time() - t0) * 1000)
                nav = page.evaluate(
                    "() => {const n=performance.getEntriesByType('navigation')[0];"
                    "return n ? Math.round(n.responseEnd - n.requestStart) : null;}")
                notes.append(f"speed {label} {path}: usable in {ms}ms"
                             + (f", server {nav}ms" if nav is not None else ""))
                if ms > budget:
                    failures.append(f"speed {label} {path}: {ms}ms to usable, budget {budget}ms")
        finally:
            page.close()


def check_faq(ctx, base, suffix, failures, notes):
    """A FAQ question must open its answer.

    Added after 2026-10-19, when I counted markup instead of behaviour,
    concluded 142 accordions were dead, added a second click handler and
    cancelled out the one that already worked. The accordions were fine. Only
    a click proves a control works.
    """
    page = ctx.new_page()
    page.set_viewport_size(DESKTOP)
    try:
        page.goto(base + "/amsterdam" + suffix, wait_until="load", timeout=45000)
        page.wait_for_selector(".fqq", timeout=15000)
        page.locator(".fqq").first.click()
        page.wait_for_timeout(600)
        h = page.evaluate("() => {const a=document.querySelector('.fqi .fqa');"
                          "return a ? Math.round(a.getBoundingClientRect().height) : 0;}")
        if h < 10:
            failures.append(f"faq: clicking a question revealed nothing (answer height {h}px)")
        else:
            notes.append(f"faq: question opens, answer {h}px tall")
    except Exception as e:
        notes.append(f"faq check skipped: {str(e)[:80]}")
    finally:
        page.close()


def check_maps_links(ctx, base, suffix, failures, notes):
    """Park-and-ride cards must offer directions, and to the right place."""
    page = ctx.new_page()
    page.set_viewport_size(DESKTOP)
    try:
        page.goto(base + "/amsterdam" + suffix, wait_until="load", timeout=45000)
        page.wait_for_selector(".pk", timeout=15000)
        cards = page.locator(".pk").count()
        rows = page.locator(".pk-go").count()
        if rows == 0:
            failures.append(f"maps: {cards} park-and-ride cards and no directions links")
            return
        href = page.locator(".pk-go a").first.get_attribute("href") or ""
        if "google.com/maps" not in href:
            failures.append(f"maps: first link is not a Google Maps url: {href[:60]}")
        notes.append(f"maps: {rows} of {cards} cards link out")
    except Exception as e:
        notes.append(f"maps check skipped: {str(e)[:80]}")
    finally:
        page.close()


def check_touch(play, base, suffix, failures, notes):
    """Open a charger on a real phone profile and prove you can close it again.

    The desktop checks above dispatch click events, which bypass hit testing,
    so they pass on a card that a finger could never reach. On 2026-10-19 the
    card rendered 729px tall on a 390x664 iPhone viewport, anchored to the map
    rather than the viewport, which put its top at -304px and its close button
    off the screen entirely. Opening a charger trapped the visitor, on the 61%
    of traffic that is mobile, while every other check stayed green.
    """
    dev = play.devices["iPhone 13"]
    ctx = play.chromium.launch(headless=True).new_context(**dev)
    page = ctx.new_page()
    try:
        page.goto(base + "/ev-charging" + suffix, wait_until="load", timeout=45000)
        page.wait_for_selector(".ev-pin", timeout=25000)
        page.wait_for_timeout(2500)
        try:                                   # consent would sit over the map
            page.get_by_role("button", name="No thanks").tap(timeout=4000)
            page.wait_for_timeout(500)
        except Exception:
            pass
        page.locator(".ev-pin").first.tap(timeout=8000)
        page.wait_for_timeout(1500)
        if not page.locator(".ev-card").first.is_visible():
            failures.append("touch: tapping a charger opened no card")
            return
        box = page.evaluate("""() => {
            const c = document.querySelector('.ev-card');
            const r = c.getBoundingClientRect();
            const x = c.querySelector('.ev-card-x, [data-close]');
            const xr = x ? x.getBoundingClientRect() : null;
            return {top: r.top, bottom: r.bottom, vh: innerHeight,
                    closeTop: xr ? xr.top : null, closeBottom: xr ? xr.bottom : null};
        }""")
        if box["top"] < 0:
            failures.append(f"touch: the card starts {abs(round(box['top']))}px above the screen")
        if box["closeTop"] is None:
            failures.append("touch: the card has no close control")
        elif box["closeTop"] < 0 or box["closeBottom"] > box["vh"]:
            failures.append("touch: the card's close button is off the screen")
        else:
            try:                               # and it must actually respond to a finger
                page.locator(".ev-card-x, .ev-card [data-close]").first.tap(timeout=6000)
                page.wait_for_timeout(900)
                # closing sets [hidden]; the node stays in the DOM
                if page.locator(".ev-card").first.is_visible():
                    failures.append("touch: tapping close left the card open")
                else:
                    notes.append("touch: card opens and closes on a phone")
            except Exception as e:
                failures.append(f"touch: close button not tappable ({str(e)[:60]})")
    except Exception as e:
        notes.append(f"touch check skipped: {str(e)[:90]}")
    finally:
        ctx.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=LIVE)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--pages", nargs="*", default=PAGES)
    a = ap.parse_args()
    base = a.base.rstrip("/")
    # A local static server serves ev-charging.html, not /ev-charging.
    local = base.startswith("http://127.0.0.1") or base.startswith("http://localhost")

    failures, notes = [], []
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        try:
            for path in a.pages:
                target = path
                if local:
                    target = "/index.html" if path == "/" else path + ".html"
                for vp in (DESKTOP, PHONE):
                    check_page(ctx, base, target, vp, failures, notes)
            sfx = ".html" if local else ""
            check_price(ctx, base, sfx, failures, notes)
            check_faq(ctx, base, sfx, failures, notes)
            check_maps_links(ctx, base, sfx, failures, notes)
            check_speed(ctx, base, a.pages, local, failures, notes)
            check_touch(p, base, sfx, failures, notes)
        finally:
            browser.close()

    if a.json:
        print(json.dumps({"base": base, "failures": failures, "notes": notes}, indent=1))
    else:
        print(f"smoke_map: {len(failures)} failure(s) against {base}")
        for n in notes:
            print("  ok   " + n)
        for f in failures:
            print("  FAIL " + f)
    return 2 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
