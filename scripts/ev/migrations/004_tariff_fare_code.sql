-- A time window must say which fare ladder prices it. Zones publish several
-- products (hourly, dagkaart, avondkaart) and without the code the map could
-- only multiply a display figure by hours, which is exactly how a 12-hour
-- ticket got charged twice for a two-hour stop.
ALTER TABLE parking_tariff ADD COLUMN IF NOT EXISTS fare_code text;
