# Parking and EV charging in the Netherlands: open data

Datasets behind [parkingnetherlands.com](https://parkingnetherlands.com), published by [Analytics Ascent](https://analyticascent.com). Licence: CC BY 4.0. Cite as "Parking Netherlands (Analytics Ascent), <dataset>, <date>" with a link.

## What is here

| File | Rows | What | Source |
|---|---|---|---|
| `data/parking-price-index-2026.json` / `.csv` | 14 cities | Garage and P+R tariffs per city: facilities, priced, free, median and cheapest 1 h / 3 h / 24 h rates, EV points, capacity | National parking register (NPR / RDW, CC0), snapshot 2026-10-04 |
| `data/ev-adoption-2026.json` / `.csv` | 342 municipalities | Electric share of private cars and public charge points per 100 EVs per municipality | CBS (1 January 2026) and the national charge point register |
| `data/ev-charging-tariffs-by-operator.json` | per operator | Charging price per kWh and session fee per operator as published to the register, used to price stops on the live map | National charge point register (NDW / DOT-NL) |
| `data/ev-register-meta.json` | 1 | Size of the latest register export (79,147 public charge points, 2026-10-05) | National charge point register |

## Headline figures

- 323 register-listed garages, car parks and P+R sites across 14 cities, 175 with published tariffs.
- Median priced garage: EUR 2.85 per hour, EUR 62.88 per 24 hours. Range EUR 0.33 to EUR 8.00 per hour.
- 68 P+R sites, 27 free facilities, 574 garage charge points.
- 16.0% of private cars electric nationally, from 28.0% (Rozendaal) to 8.2% (Achtkarspelen).

## How the numbers are made

Tariffs are the official drive-in tariffs from the national parking register, not scraped from operator websites. Where the register carries a tariff that the municipality's own decision contradicts (this happened for P+R sites), the municipal figure is used and the override is recorded in `tariff-overrides.json` on the site. Medians exclude free facilities and obvious register errors (an hourly rate above EUR 15, or equal to the day rate).

Charging prices come from the register's published tariffs. Where an operator publishes no tariff, the live map says so and prices with the operator's usual rate elsewhere or the national median, and labels which of the three it used.

## Live versions

- https://parkingnetherlands.com/data/parking-price-index-2026.json
- https://parkingnetherlands.com/data/ev-adoption-2026.json
- https://parkingnetherlands.com/ev-data/tariffs.json

Interactive: [charger map priced with parking](https://parkingnetherlands.com/ev-charging), [price index](https://parkingnetherlands.com/parking-price-index), [EV adoption map](https://parkingnetherlands.com/ev-adoption), [charging gap map](https://parkingnetherlands.com/charging-gap).

## Licence

Creative Commons Attribution 4.0 International (CC BY 4.0). Underlying registers: NPR / RDW (CC0), NDW / DOT-NL open data, CBS open data.
