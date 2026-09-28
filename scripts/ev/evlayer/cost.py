"""Charge + park total cost.

This is the number that exists nowhere else. Charge price is sold by several
vendors and parking price by several others; the sum of the two, for one bay,
for one arrival-to-departure window, is the product.

The window is the interface, matching how drivers actually search (Parkopedia
style: arriving 16:00, leaving 18:00). Parking is priced per the RDW tariff
windows the session actually crosses, which is why a 16:00-18:00 stay can be
cheaper than 17:00-19:00 at the same bay.
"""
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta

from . import db


@dataclass
class Breakdown:
    charge_eur: float
    park_eur: float
    total_eur: float
    kwh: float
    minutes: int
    card: str
    cheapest_card: str | None
    cheapest_card_eur: float | None
    savings_vs_worst_eur: float | None
    parking_note: str
    charge_note: str

    def as_dict(self) -> dict:
        return asdict(self)


# -------------------------------------------------------------------- parking
def parking_cost(area_id: str | None, arrive: datetime, leave: datetime) -> tuple[float, str]:
    """Walk the stay minute-block by minute-block across RDW tariff windows.

    Priced per calendar day so an overnight stay picks up each day's own
    windows, and so free hours (outside paid windows) really are free.
    """
    if not area_id or leave <= arrive:
        return 0.0, "No paid parking area matched to this charger."

    windows = db.query(
        """SELECT day_of_week, start_min, end_min, price_per_hour, daily_max
           FROM parking_tariff WHERE area_id = %s""",
        (area_id,),
    )
    if not windows:
        return 0.0, "No published tariff for this location."

    by_day: dict[int, list] = {}
    for w in windows:
        by_day.setdefault(w["day_of_week"], []).append(w)

    total, paid_minutes = 0.0, 0
    cursor = arrive
    while cursor < leave:
        day_end = (cursor + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0)
        seg_end = min(leave, day_end)
        dow = cursor.isoweekday()
        day_total, day_cap = 0.0, None

        for w in by_day.get(dow, []):
            ws = cursor.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=w["start_min"])
            we = cursor.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=w["end_min"])
            if we <= ws:                      # window wraps past midnight
                we += timedelta(days=1)
            overlap_start, overlap_end = max(cursor, ws), min(seg_end, we)
            if overlap_end > overlap_start:
                mins = (overlap_end - overlap_start).total_seconds() / 60.0
                day_total += float(w["price_per_hour"]) * mins / 60.0
                paid_minutes += int(mins)
            if w["daily_max"] is not None:
                day_cap = float(w["daily_max"])

        if day_cap is not None:
            day_total = min(day_total, day_cap)
        total += day_total
        cursor = seg_end

    stay = int((leave - arrive).total_seconds() // 60)
    if paid_minutes == 0:
        note = f"Free for the whole {stay} minute stay: outside paid hours."
    elif paid_minutes < stay:
        note = f"{paid_minutes} of {stay} minutes fall inside paid hours."
    else:
        note = f"All {stay} minutes are chargeable."
    return round(total, 2), note


# --------------------------------------------------------------------- charge
def _cpo_price(evse_id: str) -> tuple[float | None, float | None, float | None]:
    row = db.one(
        """SELECT t.price_per_kwh, t.price_per_min, t.start_fee
           FROM connector c
           JOIN LATERAL unnest(c.tariff_ids) AS tid ON true
           JOIN cpo_tariff t ON t.tariff_id = tid
           WHERE c.evse_id = %s
           ORDER BY t.valid_from DESC NULLS LAST
           LIMIT 1""",
        (evse_id,),
    )
    if not row:
        return None, None, None
    return row["price_per_kwh"], row["price_per_min"], row["start_fee"]


def _card_prices(cpo: str | None) -> list[dict]:
    """Card rows for this CPO, with the operator-specific row winning over
    the wildcard so a roaming surcharge is not silently dropped."""
    rows = db.query(
        """SELECT DISTINCT ON (card) card, price_per_kwh, price_per_min,
                  start_fee, roaming_markup_pct
           FROM card_tariff
           WHERE cpo_match = '*' OR cpo_match = %s
           ORDER BY card, (cpo_match <> '*') DESC, valid_from DESC""",
        (cpo or "",),
    )
    return rows


def charge_cost(evse_id: str, kwh: float, minutes: int, card: str = "Ad-hoc (no card)"):
    """Cost of the energy, for one card. Returns (eur, note, all_cards)."""
    cpo = db.one(
        """SELECT s.cpo FROM evse e JOIN station s ON s.station_id = e.station_id
           WHERE e.evse_id = %s""", (evse_id,))
    cpo_name = cpo["cpo"] if cpo else None
    ad_kwh, ad_min, ad_fee = _cpo_price(evse_id)

    priced = []
    for row in _card_prices(cpo_name):
        if row["card"] == "Ad-hoc (no card)":
            per_kwh, per_min, fee = ad_kwh, ad_min, ad_fee
            if per_kwh is None:
                continue
        else:
            per_kwh = float(row["price_per_kwh"] or 0)
            per_min = float(row["price_per_min"] or 0)
            fee = float(row["start_fee"] or 0)
            markup = float(row["roaming_markup_pct"] or 0)
            if markup:
                per_kwh *= (1 + markup / 100.0)
        eur = (float(per_kwh or 0) * kwh
               + float(per_min or 0) * minutes
               + float(fee or 0))
        priced.append({"card": row["card"], "eur": round(eur, 2)})

    priced.sort(key=lambda r: r["eur"])
    chosen = next((p for p in priced if p["card"] == card), None)
    if chosen is None and priced:
        chosen = priced[0]

    if not priced:
        return 0.0, "No published charging tariff for this operator.", []
    note = f"{kwh:g} kWh at {cpo_name or 'this operator'}."
    return chosen["eur"], note, priced


# ---------------------------------------------------------------------- total
def total_session_cost(evse_id: str, kwh: float = 20.0,
                       arrive: datetime | None = None,
                       leave: datetime | None = None,
                       minutes: int | None = None,
                       card: str = "Ad-hoc (no card)") -> Breakdown:
    """The headline function. Give it a bay and a window, get the real bill."""
    if arrive is None:
        arrive = datetime.now()
    if leave is None:
        leave = arrive + timedelta(minutes=minutes or 120)
    minutes = int((leave - arrive).total_seconds() // 60)

    link = db.one(
        """SELECT l.area_id FROM evse e
           JOIN station_parking_link l ON l.station_id = e.station_id
           WHERE e.evse_id = %s""", (evse_id,))
    park, park_note = parking_cost(link["area_id"] if link else None, arrive, leave)
    charge, charge_note, all_cards = charge_cost(evse_id, kwh, minutes, card)

    cheapest = all_cards[0] if all_cards else None
    worst = all_cards[-1] if all_cards else None
    return Breakdown(
        charge_eur=round(charge, 2),
        park_eur=park,
        total_eur=round(charge + park, 2),
        kwh=kwh,
        minutes=minutes,
        card=card,
        cheapest_card=cheapest["card"] if cheapest else None,
        cheapest_card_eur=cheapest["eur"] if cheapest else None,
        savings_vs_worst_eur=(round(worst["eur"] - cheapest["eur"], 2)
                              if cheapest and worst else None),
        parking_note=park_note,
        charge_note=charge_note,
    )
