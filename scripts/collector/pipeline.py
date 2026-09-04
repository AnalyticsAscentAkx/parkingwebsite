#!/usr/bin/env python3
"""
Parking-NL demand-signal collector - CLI orchestrator (spec section 9).

A thin sequencer over the collector modules. Each subcommand is independent so
one failing does not stop the others (design principle 2).

  python3 pipeline.py init
  python3 pipeline.py seed
  python3 pipeline.py autocomplete [--limit-seeds N] [--engines google,bing]
                                   [--no-expand] [--rps 1.7] [--langs nl,en,de,fr]
  python3 pipeline.py normalize
  python3 pipeline.py firstparty [--days 90]
  python3 pipeline.py paa [--limit 400]
  python3 pipeline.py community
  python3 pipeline.py feedback
  python3 pipeline.py shortlist [--min-seen 1]
  python3 pipeline.py weekly     # the whole chain with sane defaults

Full overnight run: `weekly` with --limit-seeds 2000 (~8-12h). For a quick smoke
test: `weekly --limit-seeds 30 --no-expand`.
"""
import argparse
import sys

import db
import seeds as seeds_mod


def cmd_init(a):
    db.init_db()
    print(f"DB ready at {db.DB_PATH}")


def cmd_seed(a):
    db.init_db()
    print(seeds_mod.populate_seeds())


def cmd_autocomplete(a):
    import autocomplete
    langs = a.langs.split(",") if a.langs else None
    con = db.connect()
    q = "SELECT * FROM seeds WHERE active=1"
    params = []
    if langs:
        q += " AND language IN (%s)" % ",".join("?" * len(langs))
        params += langs
    q += " ORDER BY weight DESC, COALESCE(last_run,'') ASC, id ASC LIMIT ?"
    params.append(a.limit_seeds)
    rows = con.execute(q, params).fetchall()
    con.close()
    print(f"[autocomplete] {len(rows)} seeds, engines={a.engines}, "
          f"expand={not a.no_expand}, rps={a.rps}")
    out = autocomplete.collect(
        rows,
        engines=tuple(a.engines.split(",")),
        expand=not a.no_expand,
        recurse=a.recurse,
        rps=a.rps,
    )
    seeds_mod.mark_seeds_run([r["id"] for r in rows])
    print("[autocomplete]", out["stats"])


def cmd_normalize(a):
    import normalize
    print("[normalize]", normalize.normalize_day())


def cmd_firstparty(a):
    import firstparty
    firstparty.collect(days=a.days)


def cmd_paa(a):
    import paa
    paa.collect(limit=a.limit, headless=not a.headful)


def cmd_community(a):
    import community
    community.collect()


def cmd_feedback(a):
    import feedback
    feedback.recalc()


def cmd_shortlist(a):
    import shortlist
    shortlist.generate(min_seen=a.min_seen)


def cmd_weekly(a):
    print("=== WEEKLY RUN ===")
    cmd_init(a)
    cmd_seed(a)
    print("\n-- first-party (GSC) --");     cmd_firstparty(a)
    print("\n-- autocomplete --");          cmd_autocomplete(a)
    print("\n-- normalize --");             cmd_normalize(a)
    if not a.skip_paa:
        print("\n-- paa + serp --");        cmd_paa(a)
    if not a.skip_community:
        print("\n-- community --");         cmd_community(a)
    print("\n-- feedback --");              cmd_feedback(a)
    print("\n-- shortlist --");             cmd_shortlist(a)
    print("\n=== DONE ===")


def build_parser():
    p = argparse.ArgumentParser(description="Parking-NL demand collector")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp):
        sp.add_argument("--limit-seeds", type=int, default=2000, dest="limit_seeds")
        sp.add_argument("--engines", default="google")
        sp.add_argument("--no-expand", action="store_true", dest="no_expand")
        sp.add_argument("--recurse", type=int, default=2)
        sp.add_argument("--rps", type=float, default=1.7)
        sp.add_argument("--langs", default=None)
        sp.add_argument("--days", type=int, default=90)
        sp.add_argument("--limit", type=int, default=400)
        sp.add_argument("--headful", action="store_true")
        sp.add_argument("--min-seen", type=int, default=1, dest="min_seen")
        sp.add_argument("--skip-paa", action="store_true", dest="skip_paa")
        sp.add_argument("--skip-community", action="store_true", dest="skip_community")

    for name, fn in [
        ("init", cmd_init), ("seed", cmd_seed), ("autocomplete", cmd_autocomplete),
        ("normalize", cmd_normalize), ("firstparty", cmd_firstparty),
        ("paa", cmd_paa), ("community", cmd_community), ("feedback", cmd_feedback),
        ("shortlist", cmd_shortlist), ("weekly", cmd_weekly),
    ]:
        sp = sub.add_parser(name)
        add_common(sp)
        sp.set_defaults(func=fn)
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    args.func(args)
