-- EV charger reliability + cost layer. Schema per build spec section 4.
-- Data sources: DOT-NL / NDW (attribute), RDW (CC-0, do NOT attribute).

-- ---------------------------------------------------------------- registry
-- Refreshed from the OCPI locations bulk file.
CREATE TABLE IF NOT EXISTS station (
  station_id      text PRIMARY KEY,           -- OCPI location id
  cpo             text,                       -- operator name
  name            text,
  lat             double precision,
  lon             double precision,
  address         text,
  postal_code     text,
  city            text,
  access_type     text,                       -- FreePublic / Restricted / ...
  parking_type    text,                       -- ON_STREET / PARKING_LOT (OCPI)
  facilities      jsonb,
  last_seen       timestamptz,
  first_seen      timestamptz
);
CREATE INDEX IF NOT EXISTS station_city_idx ON station (city);
CREATE INDEX IF NOT EXISTS station_cpo_idx  ON station (cpo);
CREATE INDEX IF NOT EXISTS station_geo_idx  ON station (lat, lon);

CREATE TABLE IF NOT EXISTS evse (
  evse_id         text PRIMARY KEY,           -- OCPI EVSE uid
  station_id      text REFERENCES station (station_id) ON DELETE CASCADE,
  physical_ref    text,
  status_current  text,                       -- last known OCPI status
  status_since    timestamptz,
  capabilities    jsonb
);
CREATE INDEX IF NOT EXISTS evse_station_idx ON evse (station_id);

CREATE TABLE IF NOT EXISTS connector (
  connector_id    text PRIMARY KEY,           -- "<evse_id>:<connector id>"
  evse_id         text REFERENCES evse (evse_id) ON DELETE CASCADE,
  standard        text,                       -- IEC_62196_T2, CHADEMO, ...
  format          text,                       -- CABLE / SOCKET
  power_type      text,                       -- AC_1_PHASE / AC_3_PHASE / DC
  max_power_kw    numeric,
  tariff_ids      text[]
);
CREATE INDEX IF NOT EXISTS connector_evse_idx ON connector (evse_id);

-- ------------------------------------------------------------- the history
-- Append-only. One row per observed state transition, never a snapshot.
-- This table is the moat: it cannot be backfilled from any public source.
CREATE TABLE IF NOT EXISTS state_change (
  id              bigserial,
  evse_id         text NOT NULL,
  status          text NOT NULL,              -- AVAILABLE/CHARGING/OCCUPIED/OUTOFORDER/UNKNOWN/REMOVED
  observed_at     timestamptz NOT NULL,
  PRIMARY KEY (id, observed_at)
) PARTITION BY RANGE (observed_at);
CREATE INDEX IF NOT EXISTS state_change_evse_idx ON state_change (evse_id, observed_at);

-- Availability observations keyed by location + connector type, which is the
-- grain the GeoJSON feed actually publishes. Feeds busyness rollups.
CREATE TABLE IF NOT EXISTS availability_change (
  id              bigserial,
  station_id      text NOT NULL,
  connector_key   text NOT NULL,              -- "<standard>|<power_type>"
  total           int,
  available       int,
  observed_at     timestamptz NOT NULL,
  PRIMARY KEY (id, observed_at)
) PARTITION BY RANGE (observed_at);
CREATE INDEX IF NOT EXISTS availability_change_station_idx
  ON availability_change (station_id, observed_at);

-- --------------------------------------------------------------- pricing
-- CPO ad-hoc tariffs from the DOT-NL tariffs file. No card prices here.
CREATE TABLE IF NOT EXISTS cpo_tariff (
  tariff_id       text,
  valid_from      timestamptz,
  currency        text,
  price_per_kwh   numeric,
  price_per_min   numeric,
  start_fee       numeric,
  raw             jsonb,
  PRIMARY KEY (tariff_id, valid_from)
);

-- Hand-curated eMSP / charge-card prices. Not in any open feed.
CREATE TABLE IF NOT EXISTS card_tariff (
  card               text,
  cpo_match          text,                    -- '*' matches any CPO
  valid_from         date,
  price_per_kwh      numeric,
  price_per_min      numeric,
  start_fee          numeric,
  roaming_markup_pct numeric,
  notes              text,
  PRIMARY KEY (card, cpo_match, valid_from)
);

-- --------------------------------------------------------------- parking
-- RDW open data. CC-0: commercial use fine, but crediting RDW is NOT allowed.
CREATE TABLE IF NOT EXISTS parking_area (
  area_id     text PRIMARY KEY,
  geom        jsonb,
  city        text,
  on_street   boolean,
  capacity    int,
  lat         double precision,
  lon         double precision,
  name        text
);
CREATE INDEX IF NOT EXISTS parking_area_geo_idx ON parking_area (lat, lon);

CREATE TABLE IF NOT EXISTS parking_tariff (
  area_id        text,
  day_of_week    int,                         -- 1 = Monday .. 7 = Sunday
  start_min      int,                         -- minutes from midnight
  end_min        int,
  price_per_hour numeric,
  daily_max      numeric,
  PRIMARY KEY (area_id, day_of_week, start_min)
);

-- --------------------------------------------------------------- rollups
CREATE TABLE IF NOT EXISTS reliability_daily (
  evse_id            text,
  day                date,
  uptime_pct         numeric,                 -- % of observed time working
  outages            int,
  longest_outage_min int,
  PRIMARY KEY (evse_id, day)
);
CREATE INDEX IF NOT EXISTS reliability_daily_day_idx ON reliability_daily (day);

CREATE TABLE IF NOT EXISTS busyness_hourly (
  station_id    text,
  dow           int,                          -- 1 = Monday .. 7 = Sunday
  hour          int,
  occupancy_pct numeric,
  samples       int,
  PRIMARY KEY (station_id, dow, hour)
);

CREATE TABLE IF NOT EXISTS flag (
  evse_id   text,
  flag_type text,                             -- STUCK_STATE / LIKELY_BROKEN / ICE_BLOCK_SUSPECTED
  since     timestamptz,
  detail    jsonb,
  PRIMARY KEY (evse_id, flag_type, since)
);

-- Conditional-GET bookkeeping so a re-run does not re-download an unchanged file.
CREATE TABLE IF NOT EXISTS fetch_state (
  url           text PRIMARY KEY,
  etag          text,
  last_modified text,
  fetched_at    timestamptz,
  bytes         bigint
);

-- Nearest parking area per station, precomputed by the rollup job so the
-- cost engine and page generator do not repeat the geo search.
CREATE TABLE IF NOT EXISTS station_parking_link (
  station_id  text PRIMARY KEY,
  area_id     text,
  distance_m  numeric,
  linked_at   timestamptz
);
