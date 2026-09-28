-- Access: whether a driver can actually get to the post. The register says
-- so in four places: parking_type (street, lot, garage), opening hours,
-- charging_when_closed, and per-EVSE parking_restrictions (CUSTOMERS means
-- a hotel, shop or office car park). Kept so the map can warn "may be behind
-- a barrier" instead of sending people to a gate.
ALTER TABLE station ADD COLUMN IF NOT EXISTS open_247 boolean;
ALTER TABLE station ADD COLUMN IF NOT EXISTS charging_when_closed boolean;
ALTER TABLE station ADD COLUMN IF NOT EXISTS directions text;
ALTER TABLE evse ADD COLUMN IF NOT EXISTS restrictions jsonb;
