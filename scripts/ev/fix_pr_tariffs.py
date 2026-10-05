#!/usr/bin/env python3
"""Correct the Amsterdam P+R day tariffs in the parking tables.

The register's structure for these sites is right and matches the city's scheme
exactly: a flat 24-hour charge, one fare code for entering before 10:00 and
another for entering after, a four-day (5760 minute) maximum and an overstay
rate beyond it. Only the amounts are stale. They are the prices Amsterdam
charged before it raised them, and the feed has never been updated.

  enter after 10:00    1.00 per 24 h   ->   6.00
  enter before 10:00   8.00 first 24 h ->  13.00, then 6.00 per 24 h

Only bands charging by the day (step 1440) are touched. The per-minute overstay
ladders and P+R ArenA's event tariff, which is a genuinely different product at
1 euro per 20 minutes, are left exactly as the register has them.

Run after ingest. The daily pipeline re-reads RDW, so without this the old
figures come back.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evlayer import db

SOURCE = "https://www.amsterdam.nl/parkeren/parkeren-reizen/plaatsen-binnen-stad/pr-sloterdijk/"
CHECKED = "2026-10-05"
NEW_DAY, NEW_FIRST = 6.0, 13.0
OLD_DAY, OLD_FIRST = 1.0, 8.0


def main():
    codes = [r["fare_code"] for r in db.query(
        "SELECT DISTINCT fare_code FROM parking_tariff WHERE area_id LIKE %s", ("363_PR%",))]
    if not codes:
        sys.exit("no Amsterdam P+R fare codes found; has the area id scheme changed?")

    with db.conn() as c:
        a = c.execute(
            """UPDATE parking_fare_part SET amount=%s
               WHERE fare_code = ANY(%s) AND step_min=1440 AND amount=%s""",
            (NEW_DAY, codes, OLD_DAY)).rowcount
        b = c.execute(
            """UPDATE parking_fare_part SET amount=%s
               WHERE fare_code = ANY(%s) AND step_min=1440 AND amount=%s""",
            (NEW_FIRST, codes, OLD_FIRST)).rowcount
        d = c.execute(
            """UPDATE parking_tariff SET price_per_hour=%s, daily_max=%s
               WHERE fare_code = ANY(%s) AND daily_max=%s""",
            (NEW_DAY, NEW_DAY, codes, OLD_DAY)).rowcount
        e = c.execute(
            """UPDATE parking_tariff SET price_per_hour=%s, daily_max=%s
               WHERE fare_code = ANY(%s) AND daily_max=%s""",
            (NEW_FIRST, NEW_FIRST, codes, OLD_FIRST)).rowcount

    print(f"  fare codes touched        : {len(codes)}")
    print(f"  day bands 1.00 -> 6.00    : {a}")
    print(f"  first-day 8.00 -> 13.00   : {b}")
    print(f"  tariff windows 1.00 -> 6  : {d}")
    print(f"  tariff windows 8.00 -> 13 : {e}")
    print(f"  source {SOURCE} read {CHECKED}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
