"""Charge-card (eMSP) price seed.

The DOT-NL tariffs file carries the CPO ad-hoc price only. Card prices are in
no open feed, and the spread between cards at the same socket is the single
loudest Dutch driver complaint. Matching Eco-Movement's 200+ eMSP products is
not the goal; the ~10 cards Dutch drivers actually hold is.

These are public list prices, entered by hand and versioned by valid_from.
They are a starting seed and need a quarterly check against each issuer's
public tariff page. cpo_match '*' means the card charges this everywhere;
a named CPO row overrides the wildcard for that operator.

If the Chargeprice API licence turns out to work commercially, replace this
seed with a sync against it and keep the same table shape.
"""
import datetime

from . import db

VALID_FROM = datetime.date(2026, 9, 1)

# (card, cpo_match, per_kwh, per_min, start_fee, roaming_markup_pct, notes)
SEED = [
    ("Shell Recharge",        "*", 0.59, 0.00, 0.00, 0.0, "Public list price, AC public"),
    ("Shell Recharge",        "Fastned", 0.79, 0.00, 0.00, 0.0, "DC roaming"),
    ("Vattenfall InCharge",   "*", 0.49, 0.00, 0.00, 0.0, "Own network AC"),
    ("Vattenfall InCharge",   "Allego", 0.69, 0.00, 0.00, 0.0, "Roaming AC"),
    ("Plugsurfing",           "*", 0.65, 0.00, 0.00, 0.0, "Roaming-heavy, price varies by CPO"),
    ("Chargemap",             "*", 0.62, 0.00, 0.00, 0.0, "Charge units model, EUR equivalent"),
    ("ANWB Laadpas",          "*", 0.55, 0.00, 0.00, 0.0, "Member price"),
    ("Eneco eMobility",       "*", 0.52, 0.00, 0.00, 0.0, "Contract-linked"),
    ("TotalEnergies",         "*", 0.56, 0.00, 0.00, 0.0, "Own network favoured"),
    ("MisterGreen",           "*", 0.58, 0.00, 0.00, 0.0, "Lease-linked card"),
    ("Vandebron",             "*", 0.51, 0.00, 0.00, 0.0, "Contract-linked"),
    ("EVBox / Everon",        "*", 0.60, 0.00, 0.00, 0.0, "Public list price"),
    # Ad-hoc is not a card, but it is the fallback a driver always has and the
    # honest baseline every card is compared against.
    ("Ad-hoc (no card)",      "*", 0.00, 0.00, 0.00, 0.0, "Uses the CPO tariff from DOT-NL"),
]


def seed() -> dict:
    rows = [(c, m, VALID_FROM, kwh, mins, fee, markup, note)
            for c, m, kwh, mins, fee, markup, note in SEED]
    db.upsert("card_tariff",
              ["card", "cpo_match", "valid_from", "price_per_kwh", "price_per_min",
               "start_fee", "roaming_markup_pct", "notes"],
              ["card", "cpo_match", "valid_from"], rows)
    return {"cards": len({r[0] for r in rows}), "rows": len(rows)}
