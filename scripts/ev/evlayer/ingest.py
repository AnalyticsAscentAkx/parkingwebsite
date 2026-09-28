"""Ingest of the three DOT-NL bulk files.

Every function here is one-shot and idempotent: run it by hand, run it twice,
run it after a crash. Nothing schedules itself. Wiring these onto a timer is
the separate "daily pipeline" job.

Cadence these are designed for, per spec:
  availability  GeoJSON        every POLL_SECONDS (300)
  registry      OCPI locations hourly
  tariffs       OCPI tariffs   2x/day
"""
from datetime import datetime, timezone

from . import config, db, fetch, status as st


def _now():
    return datetime.now(timezone.utc)


def _power_kw(c: dict) -> float | None:
    """OCPI max_electric_power is frequently null, so fall back to V x A.
    Checked against the GeoJSON: 3-phase 230 V 16 A gives 11040 W, which is
    exactly what the feed publishes for the same connector."""
    watts = c.get("max_electric_power")
    if watts:
        return round(float(watts) / 1000.0, 2)
    v, a = c.get("max_voltage"), c.get("max_amperage")
    if not v or not a:
        return None
    phases = 3 if (c.get("power_type") or "").upper() == "AC_3_PHASE" else 1
    return round(float(v) * float(a) * phases / 1000.0, 2)


# --------------------------------------------------------------- availability
def availability(force: bool = False) -> dict:
    """GeoJSON -> availability_change. Writes only rows that differ from the
    last observation, which is what keeps a year of national history small."""
    data = fetch.get_json(config.GEOJSON_URL, force=force)
    if data is None:
        return {"skipped": "not modified"}

    prior = {
        (r["station_id"], r["connector_key"]): (r["total"], r["available"])
        for r in db.query(
            """SELECT DISTINCT ON (station_id, connector_key)
                      station_id, connector_key, total, available
               FROM availability_change
               ORDER BY station_id, connector_key, observed_at DESC"""
        )
    }

    seen, changes = 0, []
    now = _now()
    for feat in data.get("features", []):
        sid = feat.get("id")
        props = feat.get("properties") or {}
        for a in props.get("availabilities") or []:
            key = f"{a.get('connector_type')}|{a.get('power_type')}"
            total, avail = a.get("total"), a.get("available")
            seen += 1
            if prior.get((sid, key)) != (total, avail):
                changes.append((sid, key, total, avail, now))

    db.ensure_partitions()
    written = db.copy_rows(
        "availability_change",
        ["station_id", "connector_key", "total", "available", "observed_at"],
        changes,
    )
    return {"observed": seen, "changed": written, "locations": len(data.get("features", []))}


# ------------------------------------------------------------------- registry
def registry(force: bool = False) -> dict:
    """OCPI locations -> station / evse / connector, plus EVSE state_change.

    This file is ~197 MB raw and refreshes every minute. Pulling it every
    minute would be ~24 GB/day, so it runs hourly and the fine-grained
    availability signal comes from the much smaller GeoJSON instead.
    """
    data = fetch.get_json(config.OCPI_LOCATIONS_URL, force=force)
    if data is None:
        return {"skipped": "not modified"}

    now = _now()
    stations, evses, connectors = [], [], []
    for loc in data:
        coords = loc.get("coordinates") or {}
        op = loc.get("operator") or {}
        stations.append((
            loc.get("id"),
            op.get("name"),
            loc.get("name"),
            float(coords["latitude"]) if coords.get("latitude") else None,
            float(coords["longitude"]) if coords.get("longitude") else None,
            loc.get("address"),
            loc.get("postal_code"),
            loc.get("city"),
            "FreePublic" if loc.get("publish") else "Restricted",
            loc.get("parking_type"),
            db.Json(loc.get("facilities")) if loc.get("facilities") else None,
            now, now,
        ))
        for e in loc.get("evses") or []:
            uid = e.get("uid") or e.get("evse_id")
            if not uid:
                continue
            evses.append((
                uid, loc.get("id"), e.get("physical_reference"),
                e.get("status"), now,
                db.Json(e.get("capabilities")) if e.get("capabilities") else None,
            ))
            for c in e.get("connectors") or []:
                connectors.append((
                    f"{uid}:{c.get('id')}", uid, c.get("standard"), c.get("format"),
                    c.get("power_type"), _power_kw(c), c.get("tariff_ids") or [],
                ))

    db.upsert("station",
              ["station_id", "cpo", "name", "lat", "lon", "address", "postal_code",
               "city", "access_type", "parking_type", "facilities", "last_seen", "first_seen"],
              ["station_id"], stations)

    # EVSE status diffs become history before the registry row is overwritten.
    prior = {r["evse_id"]: r["status_current"]
             for r in db.query("SELECT evse_id, status_current FROM evse")}
    transitions = [(uid, statusv, now)
                   for uid, _sid, _ref, statusv, _ts, _cap in evses
                   if prior.get(uid) != statusv]

    db.upsert("evse",
              ["evse_id", "station_id", "physical_ref", "status_current", "status_since", "capabilities"],
              ["evse_id"], evses)
    db.upsert("connector",
              ["connector_id", "evse_id", "standard", "format", "power_type", "max_power_kw", "tariff_ids"],
              ["connector_id"], connectors)

    db.ensure_partitions()
    written = db.copy_rows("state_change", ["evse_id", "status", "observed_at"], transitions)

    return {"stations": len(stations), "evses": len(evses),
            "connectors": len(connectors), "state_changes": written}


# -------------------------------------------------------------------- tariffs
def tariffs(force: bool = False) -> dict:
    """OCPI tariffs -> cpo_tariff.

    Important limitation, and the reason card_tariff exists: this file carries
    the CPO's ad-hoc price only. It contains no charge-card / eMSP prices, and
    the spread between cards at the same socket reaches 70%.
    """
    data = fetch.get_json(config.OCPI_TARIFFS_URL, force=force)
    if data is None:
        return {"skipped": "not modified"}

    rows = []
    for t in data:
        per_kwh = per_min = start_fee = None
        for el in t.get("elements") or []:
            for pc in el.get("price_components") or []:
                kind, price = (pc.get("type") or "").upper(), pc.get("price")
                if price is None:
                    continue
                if kind == "ENERGY" and per_kwh is None:
                    per_kwh = price
                elif kind in ("TIME", "PARKING_TIME") and per_min is None:
                    per_min = price / 60.0 if price > 2 else price
                elif kind == "FLAT" and start_fee is None:
                    start_fee = price
        valid = t.get("start_date_time") or t.get("last_updated") or _now().isoformat()
        rows.append((t.get("id"), valid, t.get("currency") or "EUR",
                     per_kwh, per_min, start_fee, db.Json(t)))

    db.upsert("cpo_tariff",
              ["tariff_id", "valid_from", "currency", "price_per_kwh",
               "price_per_min", "start_fee", "raw"],
              ["tariff_id", "valid_from"], rows)
    return {"tariffs": len(rows)}
