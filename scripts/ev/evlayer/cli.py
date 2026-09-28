"""Command line. Every command is one-shot and safe to re-run.

Nothing here schedules itself. Putting these on a timer is the separate
daily-collection job, deliberately not built yet.

  ev init                     create schema and partitions
  ev registry                 refresh stations, EVSEs, connectors (hourly)
  ev availability             one availability observation (every 5 min)
  ev tariffs                  refresh CPO ad-hoc tariffs (2x/day)
  ev rdw                      load parking areas and tariffs (daily)
  ev link                     match each charger to its parking area
  ev cards                    seed the charge-card price table
  ev rollup                   recompute reliability, busyness, flags (daily)
  ev cost EVSE_ID             price one session
  ev build                    generate the site pages from the database
  ev build --source feed      generate from the live feed, no database needed
  ev clean                    remove every generated page
  ev audit                    per-operator uptime benchmark
  ev status                   what is loaded and how much history exists
"""
import argparse
import json
import sys
from datetime import datetime


def _p(obj):
    print(json.dumps(obj, indent=2, default=str))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ev", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")
    for name in ("registry", "availability", "tariffs"):
        s = sub.add_parser(name)
        s.add_argument("--force", action="store_true",
                       help="ignore the conditional-GET cache and re-download")
    sub.add_parser("rdw")
    sub.add_parser("link")
    sub.add_parser("cards")
    sub.add_parser("status")

    r = sub.add_parser("rollup")
    r.add_argument("--days", type=int, default=2)

    c = sub.add_parser("cost")
    c.add_argument("evse_id")
    c.add_argument("--kwh", type=float, default=20.0)
    c.add_argument("--arriving", help="YYYYMMDDHHMM")
    c.add_argument("--leaving", help="YYYYMMDDHHMM")
    c.add_argument("--card", default="Ad-hoc (no card)")

    b = sub.add_parser("build")
    b.add_argument("--source", choices=["db", "feed"], default="db")
    b.add_argument("--city", action="append", help="repeatable")
    b.add_argument("--max-cities", type=int, default=0)
    b.add_argument("--no-stations", action="store_true",
                   help="hubs and intent pages only")
    sub.add_parser("clean")

    a = sub.add_parser("audit")
    a.add_argument("--days", type=int, default=30)

    args = ap.parse_args(argv)

    if args.cmd == "init":
        from . import db
        applied = db.migrate()
        _p({"migrations": applied})
        return 0

    if args.cmd in ("registry", "availability", "tariffs"):
        from . import ingest
        _p(getattr(ingest, args.cmd)(force=args.force))
        return 0

    if args.cmd == "rdw":
        from . import rdw
        _p(rdw.load())
        return 0

    if args.cmd == "link":
        from . import rdw
        _p(rdw.link_stations())
        return 0

    if args.cmd == "cards":
        from . import cards
        _p(cards.seed())
        return 0

    if args.cmd == "rollup":
        from . import rollup
        _p({"reliability": rollup.reliability(days=args.days),
            "busyness": rollup.busyness(),
            "flags": rollup.flags()})
        return 0

    if args.cmd == "cost":
        from . import cost
        parse = lambda v: datetime.strptime(v, "%Y%m%d%H%M") if v else None
        _p(cost.total_session_cost(args.evse_id, kwh=args.kwh,
                                   arrive=parse(args.arriving),
                                   leave=parse(args.leaving),
                                   card=args.card).as_dict())
        return 0

    if args.cmd == "build":
        from .seo import build as B
        _p(B.build(source=args.source, cities=args.city,
                   max_cities=args.max_cities, stations=not args.no_stations))
        return 0

    if args.cmd == "clean":
        from .seo import build as B
        _p(B.clean())
        return 0

    if args.cmd == "audit":
        from . import db
        _p(db.query(
            """SELECT s.cpo, COUNT(DISTINCT e.evse_id)::int AS evses,
                      ROUND(AVG(r.uptime_pct), 2) AS uptime_pct,
                      SUM(r.outages)::int AS outages
               FROM station s
               JOIN evse e ON e.station_id = s.station_id
               JOIN reliability_daily r ON r.evse_id = e.evse_id
               WHERE r.day > current_date - %s AND s.cpo IS NOT NULL
               GROUP BY s.cpo
               HAVING COUNT(DISTINCT e.evse_id) >= 25
               ORDER BY uptime_pct ASC""", (args.days,)))
        return 0

    if args.cmd == "status":
        from . import db
        _p({
            "stations": db.one("SELECT COUNT(*) AS n FROM station")["n"],
            "evses": db.one("SELECT COUNT(*) AS n FROM evse")["n"],
            "connectors": db.one("SELECT COUNT(*) AS n FROM connector")["n"],
            "state_changes": db.one("SELECT COUNT(*) AS n FROM state_change")["n"],
            "availability_changes": db.one("SELECT COUNT(*) AS n FROM availability_change")["n"],
            "parking_areas": db.one("SELECT COUNT(*) AS n FROM parking_area")["n"],
            "days_measured": db.one("SELECT COUNT(DISTINCT day) AS n FROM reliability_daily")["n"],
            "first_observation": db.one("SELECT MIN(observed_at) AS t FROM state_change")["t"],
        })
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
