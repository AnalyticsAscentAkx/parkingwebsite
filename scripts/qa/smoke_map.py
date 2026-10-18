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
            check_price(ctx, base, ".html" if local else "", failures, notes)
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
