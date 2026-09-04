#!/usr/bin/env python3
"""
Seed table population and weight-ranked selection (spec sections 2 and 7).

populate_seeds()  builds the location x modifier x language seed universe and
                  upserts it into the seeds table (idempotent).
select_seeds()    returns the top-N active seeds by weight for a collector run.
"""
from db import connect, now_iso
import seed_data


def _lang_ok_for_location(ltype: str, lang: str) -> bool:
    """
    Keep the seed universe sane: only run DE/FR modifiers against border and
    coastal/airport locations (where that demand actually exists, spec 6).
    NL and EN run everywhere.
    """
    if lang in ("nl", "en"):
        return True
    return ltype in ("border", "beach", "ferry", "airport", "city")


def build_seed_rows():
    """Yield (seed_text, seed_type, language) for the whole universe."""
    locations = seed_data.load_locations()
    for name, ltype in locations:
        for lang, mods in seed_data.MODIFIERS.items():
            if not _lang_ok_for_location(ltype, lang):
                continue
            for mod in mods:
                # Natural word order per language: NL/DE/FR put place after term
                # is fine either way for autocomplete; we use "modifier location"
                # for EN and "modifier location" generally - suggest engines are
                # order-tolerant and we also expand alphabetically.
                yield (f"{mod} {name}", f"location_modifier:{ltype}", lang)
    # Event / temporal seeds (spec 6)
    for venue in seed_data.EVENT_VENUES:
        for lang in ("nl", "en"):
            mod = "parkeren" if lang == "nl" else "parking"
            yield (f"{mod} {venue}", "event", lang)
    for term in seed_data.EVENT_TERMS:
        yield (f"parkeren {term}", "event", "nl")


def populate_seeds() -> dict:
    con = connect()
    added, total = 0, 0
    with con:
        for seed_text, seed_type, lang in build_seed_rows():
            total += 1
            cur = con.execute(
                """INSERT OR IGNORE INTO seeds
                   (seed_text, seed_type, language, weight, active)
                   VALUES (?, ?, ?, 1.0, 1)""",
                (seed_text, seed_type, lang),
            )
            if cur.rowcount:
                added += 1
    con.close()
    return {"generated": total, "new": added}


def select_seeds(limit: int = 2000, only_types=None):
    """Top-N active seeds by weight desc, oldest-run first as tiebreak."""
    con = connect()
    q = "SELECT * FROM seeds WHERE active = 1"
    params = []
    if only_types:
        placeholders = ",".join("?" * len(only_types))
        q += f" AND seed_type IN ({placeholders})"
        params += list(only_types)
    q += " ORDER BY weight DESC, COALESCE(last_run,'') ASC, id ASC LIMIT ?"
    params.append(limit)
    rows = con.execute(q, params).fetchall()
    con.close()
    return rows


def mark_seeds_run(seed_ids):
    if not seed_ids:
        return
    con = connect()
    ts = now_iso()
    with con:
        con.executemany(
            "UPDATE seeds SET last_run = ? WHERE id = ?",
            [(ts, sid) for sid in seed_ids],
        )
    con.close()


if __name__ == "__main__":
    from db import init_db
    init_db()
    stats = populate_seeds()
    print(f"Seeds generated: {stats['generated']}, new inserted: {stats['new']}")
    con = connect()
    n = con.execute("SELECT COUNT(*) FROM seeds").fetchone()[0]
    by_lang = con.execute(
        "SELECT language, COUNT(*) c FROM seeds GROUP BY language ORDER BY c DESC"
    ).fetchall()
    con.close()
    print(f"Total active seeds in table: {n}")
    for r in by_lang:
        print(f"  {r['language']:>3}: {r['c']}")
