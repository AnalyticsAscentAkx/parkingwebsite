-- RDW prices parking as a stepped ladder of duration bands, not a flat hourly
-- rate: the first 30 minutes may be free, the next hour billed per 20 minutes.
-- A charging stop is short enough that flattening this misprices it, so the
-- ladder is stored as published and parking_tariff.price_per_hour is only a
-- display figure derived from it.
CREATE TABLE IF NOT EXISTS parking_fare_part (
  area_id   text,
  fare_code text,
  start_min int,          -- band starts this many minutes into the stay
  end_min   int,
  step_min  int,          -- billing increment inside the band
  amount    numeric,      -- charged per step
  PRIMARY KEY (area_id, fare_code, start_min)
);
