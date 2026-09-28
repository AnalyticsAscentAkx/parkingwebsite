"""FastAPI service: JSON for the site, plus a B2B export hook.

Run: uvicorn evlayer.api:app --reload
"""
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Query

from . import config, cost, db

app = FastAPI(title="EV charger reliability + cost layer", version="0.1.0")

ATTRIB = {"charging_data": config.ATTRIBUTION_NDW}


@app.get("/health")
def health():
    try:
        db.one("SELECT 1 AS ok")
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(503, f"database unreachable: {exc}")


@app.get("/station/{station_id}")
def station(station_id: str):
    s = db.one("SELECT * FROM station WHERE station_id = %s", (station_id,))
    if not s:
        raise HTTPException(404, "unknown station")
    s["evses"] = db.query(
        """SELECT e.evse_id, e.status_current, e.status_since,
                  r.uptime_pct, r.outages
           FROM evse e
           LEFT JOIN LATERAL (
             SELECT uptime_pct, outages FROM reliability_daily
             WHERE evse_id = e.evse_id ORDER BY day DESC LIMIT 1) r ON true
           WHERE e.station_id = %s""",
        (station_id,),
    )
    s["busyness"] = db.query(
        "SELECT dow, hour, occupancy_pct FROM busyness_hourly WHERE station_id = %s",
        (station_id,),
    )
    s["reliability_30d"] = db.one(
        """SELECT ROUND(AVG(r.uptime_pct), 1) AS uptime_pct,
                  SUM(r.outages)::int AS outages,
                  COUNT(DISTINCT r.day)::int AS days
           FROM reliability_daily r JOIN evse e ON e.evse_id = r.evse_id
           WHERE e.station_id = %s AND r.day > current_date - 30""",
        (station_id,),
    )
    s["attribution"] = ATTRIB
    return s


@app.get("/cost")
def session_cost(
    evse_id: str,
    kwh: float = 20.0,
    arriving: str | None = Query(None, description="YYYYMMDDHHMM"),
    leaving: str | None = Query(None, description="YYYYMMDDHHMM"),
    card: str = "Ad-hoc (no card)",
):
    """Charge + park for one window. Accepts the same compact timestamp format
    the station pages put in the query string."""
    def parse(v, default):
        if not v:
            return default
        try:
            return datetime.strptime(v, "%Y%m%d%H%M")
        except ValueError:
            raise HTTPException(400, f"bad timestamp {v!r}, expected YYYYMMDDHHMM")

    arrive = parse(arriving, datetime.now())
    leave = parse(leaving, arrive + timedelta(hours=2))
    if leave <= arrive:
        raise HTTPException(400, "leaving must be after arriving")
    return cost.total_session_cost(evse_id, kwh=kwh, arrive=arrive,
                                   leave=leave, card=card).as_dict()


@app.get("/map")
def map_layer(minLon: float, minLat: float, maxLon: float, maxLat: float,
              limit: int = 500):
    """Bounding-box layer for the site map."""
    return {
        "attribution": ATTRIB,
        "stations": db.query(
            """SELECT s.station_id, s.name, s.cpo, s.lat, s.lon, s.city,
                      ROUND(AVG(r.uptime_pct), 1) AS uptime_pct,
                      COUNT(DISTINCT e.evse_id)::int AS evses
               FROM station s
               JOIN evse e ON e.station_id = s.station_id
               LEFT JOIN reliability_daily r
                 ON r.evse_id = e.evse_id AND r.day > current_date - 30
               WHERE s.lon BETWEEN %s AND %s AND s.lat BETWEEN %s AND %s
               GROUP BY s.station_id
               LIMIT %s""",
            (minLon, maxLon, minLat, maxLat, limit),
        ),
    }


@app.get("/city/{city}")
def city(city: str, order: str = "reliable", limit: int = 100):
    """Ranked station list backing the city and intent pages."""
    orders = {
        "reliable": "uptime_pct DESC NULLS LAST",
        "fast": "max_power_kw DESC NULLS LAST",
        "cheap": "uptime_pct DESC NULLS LAST",
    }
    if order not in orders:
        raise HTTPException(400, f"order must be one of {sorted(orders)}")
    return {
        "city": city,
        "attribution": ATTRIB,
        "stations": db.query(
            f"""SELECT s.station_id, s.name, s.cpo, s.lat, s.lon, s.address,
                       ROUND(AVG(r.uptime_pct), 1) AS uptime_pct,
                       MAX(c.max_power_kw) AS max_power_kw,
                       COUNT(DISTINCT e.evse_id)::int AS evses
                FROM station s
                JOIN evse e ON e.station_id = s.station_id
                LEFT JOIN connector c ON c.evse_id = e.evse_id
                LEFT JOIN reliability_daily r
                  ON r.evse_id = e.evse_id AND r.day > current_date - 30
                WHERE lower(s.city) = lower(%s)
                GROUP BY s.station_id
                ORDER BY {orders[order]}
                LIMIT %s""",
            (city, limit),
        ),
    }


@app.get("/audit/operator")
def operator_audit(days: int = 30):
    """Per-operator uptime benchmark. This is the B2B wedge: an independent
    number an operator cannot quietly reset, published by someone with no
    commercial stake in the answer."""
    return {
        "window_days": days,
        "attribution": ATTRIB,
        "method": "Uptime = share of observed time in AVAILABLE/CHARGING/OCCUPIED/"
                  "RESERVED/BLOCKED. OUTOFORDER and prolonged UNKNOWN count as down.",
        "operators": db.query(
            """SELECT s.cpo,
                      COUNT(DISTINCT e.evse_id)::int AS evses,
                      ROUND(AVG(r.uptime_pct), 2) AS uptime_pct,
                      SUM(r.outages)::int AS outages
               FROM station s
               JOIN evse e ON e.station_id = s.station_id
               JOIN reliability_daily r ON r.evse_id = e.evse_id
               WHERE r.day > current_date - %s AND s.cpo IS NOT NULL
               GROUP BY s.cpo
               HAVING COUNT(DISTINCT e.evse_id) >= 25
               ORDER BY uptime_pct ASC""",
            (days,),
        ),
    }
