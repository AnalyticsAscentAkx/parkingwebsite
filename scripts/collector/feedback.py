#!/usr/bin/env python3
"""
The learning loop (spec section 7). What makes this an agent, not a script.

Credit flows from earned impressions back to the seed that produced the query:
  1. A GSC/first-party outcome carries a query_norm and impressions.
  2. Autocomplete queries with the same query_norm carry a seed_id.
  3. That seed gets credited; its weight rises. Seeds that have run but produced
     nothing decay and are eventually deactivated.

Next run selects top-N seeds by weight, so the collector drifts toward the
places that actually pay off - without anyone touching the seed list.

In Phase 1 `outcomes` is mostly empty, so this mainly demotes barren seeds. It
becomes meaningful as pages go live and GSC data accumulates.
"""
import math

from db import connect, now_iso

DECAY = 0.7          # barren-seed weight multiplier per recalculation
DEACTIVATE_BELOW = 0.2
MAX_WEIGHT = 5.0


def recalc() -> dict:
    con = connect()
    # queries that carry a seed, keyed by norm -> set(seed_id)
    seed_by_norm = {}
    productive = set()
    for r in con.execute(
            "SELECT query_norm, seed_id FROM queries WHERE seed_id IS NOT NULL"):
        seed_by_norm.setdefault(r["query_norm"], set()).add(r["seed_id"])
        productive.add(r["seed_id"])

    # impressions per query_norm from outcomes (GSC etc.)
    impr_by_norm = {}
    for r in con.execute("""
            SELECT q.query_norm AS qn, SUM(o.impressions) AS imp
            FROM outcomes o JOIN queries q ON q.id = o.query_id
            WHERE o.impressions IS NOT NULL
            GROUP BY q.query_norm"""):
        if r["imp"]:
            impr_by_norm[r["qn"]] = r["imp"]

    # credit impressions back to seeds
    credit = {}
    for norm, imp in impr_by_norm.items():
        for sid in seed_by_norm.get(norm, ()):
            credit[sid] = credit.get(sid, 0) + imp

    ts = now_iso()
    stats = {"up": 0, "decayed": 0, "deactivated": 0, "unchanged": 0}
    with con:
        for s in con.execute("SELECT id, weight, active, last_run FROM seeds").fetchall():
            sid, w, active, last_run = s["id"], s["weight"], s["active"], s["last_run"]
            imp = credit.get(sid, 0)
            if imp > 0:
                new_w = min(MAX_WEIGHT, 1.0 + math.log1p(imp))
                if new_w != w:
                    con.execute("UPDATE seeds SET weight=? WHERE id=?", (new_w, sid))
                    stats["up"] += 1
                continue
            # barren: has been run but produced no queries at all -> decay
            if last_run and sid not in productive:
                new_w = max(0.05, w * DECAY)
                new_active = 0 if new_w < DEACTIVATE_BELOW else active
                con.execute("UPDATE seeds SET weight=?, active=? WHERE id=?",
                            (new_w, new_active, sid))
                stats["decayed"] += 1
                if new_active == 0 and active == 1:
                    stats["deactivated"] += 1
            else:
                stats["unchanged"] += 1
    con.close()
    print(f"  [feedback] up:{stats['up']} decayed:{stats['decayed']} "
          f"deactivated:{stats['deactivated']} unchanged:{stats['unchanged']}")
    return stats


if __name__ == "__main__":
    print(recalc())
