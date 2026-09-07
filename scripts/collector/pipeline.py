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

# Alert when a collector's row yield falls to less than half the previous run's:
# a changed selector or a soft-block often shows up as a silent yield collapse
# that looks like success (principle 7 / spec 9).
YIELD_DROP_RATIO = 0.5


def _run_id(a) -> str:
    rid = getattr(a, "run_id", None)
    if not rid:
        rid = db.new_run_id()
        a.run_id = rid
    return rid


def _yield_check(con, collector, manifest_id, rows_out):
    """Return an alert note (and print it loud) if yield dropped hard, else None."""
    prev = db.previous_rows_out(con, collector, manifest_id)
    if prev and prev > 0 and rows_out < prev * YIELD_DROP_RATIO:
        drop = 100 * (1 - rows_out / prev)
        note = f"yield drop {drop:.0f}% ({rows_out} vs {prev} last run)"
        print(f"  [YIELD-DROP ALERT] {collector}: {note} - possible silent "
              f"breakage (selector/soft-block), investigate before trusting.")
        return note
    return None


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
    print(f"[autocomplete] {len(rows)} seeds, engines={a.engines}, "
          f"expand={not a.no_expand}, rps={a.rps}")

    rid = _run_id(a)
    mid = db.start_run(con, rid, "autocomplete", seeds_in=len(rows))
    con.commit()

    # Standalone runs take the lock; inside `weekly` it is already held.
    standalone = not getattr(a, "_locked", False)
    if standalone and not db.acquire_lock("autocomplete"):
        print("[autocomplete] another run holds the lock; aborting.")
        db.finish_run(con, mid, "failed", rows_out=0, notes="lock held")
        con.commit(); con.close()
        return
    try:
        out = autocomplete.collect(
            rows,
            engines=tuple(a.engines.split(",")),
            expand=not a.no_expand,
            recurse=a.recurse,
            rps=a.rps,
        )
    finally:
        if standalone:
            db.release_lock()

    seeds_mod.mark_seeds_run([r["id"] for r in rows])
    st = out["stats"]
    note = _yield_check(con, "autocomplete", mid, st["unique"])
    db.finish_run(
        con, mid, "partial" if note else "ok", rows_out=st["unique"],
        http_429=st["http_429"], http_403=st["http_403"],
        empty_200=st["empty_200"],
        notes=note or (f"skipped={st['skipped']}, "
                       f"soft_block_trips={st.get('soft_block_trips', 0)}"),
    )
    con.commit(); con.close()
    print("[autocomplete]", st)


def cmd_normalize(a):
    import normalize
    con = db.connect()
    rid = _run_id(a)
    mid = db.start_run(con, rid, "normalize")
    con.commit()
    stats = normalize.normalize_day()
    note = _yield_check(con, "normalize", mid, stats["upserts"])
    db.finish_run(
        con, mid, "partial" if note else "ok", rows_out=stats["upserts"],
        notes=note or (f"rejected={stats['rejected']}, "
                       f"clusters={stats['clusters']}"),
    )
    con.commit(); con.close()
    print("[normalize]", stats)


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
    rid = _run_id(a)
    print(f"=== WEEKLY RUN ({rid}) ===")
    cmd_init(a)
    if not db.acquire_lock("weekly"):
        print("[weekly] another collector run holds the lock "
              f"({db.LOCK_PATH}); aborting to avoid double-fetch.")
        return
    a._locked = True
    try:
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
    finally:
        db.release_lock()


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
