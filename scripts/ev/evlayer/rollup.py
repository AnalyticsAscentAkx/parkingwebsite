"""Daily rollups: reliability, busyness, flags.

Everything here is derived from state_change / availability_change, which is
the part of the stack nobody else has. The inputs are free to everyone; the
history is not.

Uptime method, stated once so an audit report can defend it:
  - Each state_change starts an interval that runs until the next change.
  - An interval counts as working if its status maps to UP or BUSY.
  - UNKNOWN is tolerated for UNKNOWN_GRACE_MINUTES, then counts as downtime.
    An operator that stops reporting is not demonstrating uptime.
  - Intervals are clipped to the day boundary, so a 3-day outage is charged
    to all three days rather than to the day it started.
"""
from datetime import date, timedelta

from . import db, status as st


def reliability(days: int = 1, end: date | None = None) -> dict:
    """Recompute reliability_daily for the last `days` days."""
    end = end or date.today()
    start = end - timedelta(days=days)

    sql = """
    WITH bounds AS (
      SELECT %s::date AS d0, %s::date AS d1
    ),
    -- Each change, plus when the next one superseded it.
    spans AS (
      SELECT evse_id, status, observed_at,
             LEAD(observed_at) OVER (PARTITION BY evse_id ORDER BY observed_at) AS next_at
      FROM state_change, bounds
      WHERE observed_at >= bounds.d0 - interval '7 days'
    ),
    -- Clip every span to each day it touches.
    clipped AS (
      SELECT s.evse_id,
             gs.day::date AS day,
             s.status,
             GREATEST(s.observed_at, gs.day)                         AS seg_start,
             LEAST(COALESCE(s.next_at, now()), gs.day + interval '1 day') AS seg_end
      FROM spans s
      JOIN bounds ON true
      CROSS JOIN LATERAL generate_series(
          date_trunc('day', GREATEST(s.observed_at, bounds.d0)),
          date_trunc('day', LEAST(COALESCE(s.next_at, now()), bounds.d1 + interval '1 day')),
          interval '1 day') AS gs(day)
      WHERE gs.day::date >= bounds.d0 AND gs.day::date <= bounds.d1
    ),
    graded AS (
      SELECT evse_id, day, status, seg_start, seg_end,
             EXTRACT(epoch FROM (seg_end - seg_start)) / 60.0 AS minutes,
             CASE
               WHEN status IN ('AVAILABLE','CHARGING','OCCUPIED','RESERVED','BLOCKED') THEN true
               -- UNKNOWN is forgiven only while it is brief.
               WHEN status = 'UNKNOWN'
                    AND EXTRACT(epoch FROM (seg_end - seg_start))/60.0 <= %s THEN true
               ELSE false
             END AS working
      FROM clipped
      WHERE seg_end > seg_start
    )
    INSERT INTO reliability_daily (evse_id, day, uptime_pct, outages, longest_outage_min)
    SELECT evse_id, day,
           ROUND(100.0 * SUM(minutes) FILTER (WHERE working) / NULLIF(SUM(minutes),0), 2),
           COUNT(*) FILTER (WHERE NOT working),
           COALESCE(ROUND(MAX(minutes) FILTER (WHERE NOT working))::int, 0)
    FROM graded
    GROUP BY evse_id, day
    ON CONFLICT (evse_id, day) DO UPDATE SET
      uptime_pct = EXCLUDED.uptime_pct,
      outages = EXCLUDED.outages,
      longest_outage_min = EXCLUDED.longest_outage_min
    """
    n = db.execute(sql, (start, end, st.UNKNOWN_GRACE_MINUTES))
    return {"rows": n, "from": str(start), "to": str(end)}


def busyness() -> dict:
    """Occupancy by day-of-week and hour, from availability observations."""
    sql = """
    INSERT INTO busyness_hourly (station_id, dow, hour, occupancy_pct, samples)
    SELECT station_id,
           EXTRACT(isodow FROM observed_at)::int AS dow,
           EXTRACT(hour   FROM observed_at)::int AS hour,
           ROUND(AVG(100.0 * (total - available) / NULLIF(total,0))::numeric, 1),
           COUNT(*)
    FROM availability_change
    WHERE total > 0 AND available IS NOT NULL
      AND observed_at > now() - interval '90 days'
    GROUP BY station_id, dow, hour
    ON CONFLICT (station_id, dow, hour) DO UPDATE SET
      occupancy_pct = EXCLUDED.occupancy_pct,
      samples = EXCLUDED.samples
    """
    return {"rows": db.execute(sql)}


def flags(stuck_days: int = 3) -> dict:
    """Broken-charger detection. Beats the operator's own dashboard, because
    it is measured from outside and nobody can quietly reset it."""
    stuck = db.execute(
        """INSERT INTO flag (evse_id, flag_type, since, detail)
           SELECT evse_id, 'LIKELY_BROKEN', status_since,
                  jsonb_build_object('status', status_current,
                                     'days', EXTRACT(day FROM now() - status_since))
           FROM evse
           WHERE status_current IN ('OUTOFORDER','INOPERATIVE')
             AND status_since < now() - (%s || ' days')::interval
           ON CONFLICT (evse_id, flag_type, since) DO NOTHING""",
        (stuck_days,),
    )
    # A status that has not moved at all is usually a dead feed, not a busy bay.
    frozen = db.execute(
        """INSERT INTO flag (evse_id, flag_type, since, detail)
           SELECT evse_id, 'STUCK_STATE', status_since,
                  jsonb_build_object('status', status_current)
           FROM evse
           WHERE status_current = 'UNKNOWN'
             AND status_since < now() - (%s || ' days')::interval
           ON CONFLICT (evse_id, flag_type, since) DO NOTHING""",
        (stuck_days,),
    )
    # Bay shows capacity free but never transitions to CHARGING: possibly an
    # ICE car parked in it. Weak signal, so it is only ever "suspected".
    ice = db.execute(
        """INSERT INTO flag (evse_id, flag_type, since, detail)
           SELECT e.evse_id, 'ICE_BLOCK_SUSPECTED', now(),
                  jsonb_build_object('note','available but never observed charging')
           FROM evse e
           WHERE e.status_current = 'AVAILABLE'
             AND NOT EXISTS (
               SELECT 1 FROM state_change s
               WHERE s.evse_id = e.evse_id AND s.status = 'CHARGING'
                 AND s.observed_at > now() - interval '30 days')
             AND EXISTS (
               SELECT 1 FROM state_change s
               WHERE s.evse_id = e.evse_id
                 AND s.observed_at < now() - interval '30 days')
           ON CONFLICT (evse_id, flag_type, since) DO NOTHING"""
    )
    return {"likely_broken": stuck, "stuck_state": frozen, "ice_suspected": ice}


def run_all() -> dict:
    return {"reliability": reliability(days=2),
            "busyness": busyness(),
            "flags": flags()}
