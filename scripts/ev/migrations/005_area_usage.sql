-- The register's usage code says what an area is (paid street, permit zone,
-- garage, P+R, terrein). "Not on-street" was too coarse: it swept 3,400
-- permit and blue zones into the garage list.
ALTER TABLE parking_area ADD COLUMN IF NOT EXISTS usage text;
