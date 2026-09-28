-- Monthly partitions for the two append-only history tables.
-- ensure_month_partitions() is idempotent: call it before any insert and on
-- boot. It covers the current month plus `ahead` following months so a run
-- that crosses midnight on the 1st never hits a missing partition.

CREATE OR REPLACE FUNCTION ensure_month_partitions(ahead int DEFAULT 2)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
  parent    text;
  m         int;
  from_ts   timestamptz;
  to_ts     timestamptz;
  part      text;
BEGIN
  FOREACH parent IN ARRAY ARRAY['state_change', 'availability_change'] LOOP
    FOR m IN 0..ahead LOOP
      from_ts := date_trunc('month', now()) + (m || ' month')::interval;
      to_ts   := from_ts + interval '1 month';
      part    := format('%s_%s', parent, to_char(from_ts, 'YYYYMM'));
      IF to_regclass(part) IS NULL THEN
        EXECUTE format(
          'CREATE TABLE %I PARTITION OF %I FOR VALUES FROM (%L) TO (%L)',
          part, parent, from_ts, to_ts);
      END IF;
    END LOOP;
  END LOOP;
END;
$$;

-- Retention: spec keeps raw changes 13 months, rollups forever.
CREATE OR REPLACE FUNCTION drop_old_partitions(keep_months int DEFAULT 13)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
  parent text;
  cutoff timestamptz := date_trunc('month', now()) - (keep_months || ' month')::interval;
  r      record;
BEGIN
  FOREACH parent IN ARRAY ARRAY['state_change', 'availability_change'] LOOP
    FOR r IN
      SELECT c.relname
      FROM pg_class c
      JOIN pg_inherits i ON i.inhrelid = c.oid
      JOIN pg_class p ON p.oid = i.inhparent
      WHERE p.relname = parent
        AND c.relname ~ '_[0-9]{6}$'
    LOOP
      IF to_date(right(r.relname, 6), 'YYYYMM') < cutoff THEN
        EXECUTE format('DROP TABLE IF EXISTS %I', r.relname);
      END IF;
    END LOOP;
  END LOOP;
END;
$$;

SELECT ensure_month_partitions();
