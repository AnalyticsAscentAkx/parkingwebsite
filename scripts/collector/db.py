#!/usr/bin/env python3
"""
Storage layer for the Parking-NL demand-signal collector (Phase 1).

Two stores:
  1. Raw object store  -> data/collector/raw/{source}/{YYYY-MM-DD}/{seed_hash}.json
     Every API/HTML response written untouched. Never deleted. (Design principle 1.)
  2. Normalised SQLite -> data/collector/collector.db
     The clean tables the rest of the pipeline reads/writes.

Everything under data/collector/ is gitignored: raw responses and the DB are
regenerable and may contain first-party (GSC) data that must never be committed.
"""
import hashlib
import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent            # scripts/collector -> scripts -> repo
DATA_DIR = REPO_ROOT / "data" / "collector"
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "collector.db"

VALID_SOURCES = {
    "autocomplete_google", "autocomplete_bing", "paa", "reddit",
    "maps_reviews", "youtube", "gsc", "keyword_planner", "events",
    "first_party",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS queries (
  id            INTEGER PRIMARY KEY,
  query_text    TEXT NOT NULL,
  query_norm    TEXT NOT NULL,
  language      TEXT,
  source        TEXT NOT NULL,
  seed_id       INTEGER,
  location_tag  TEXT,
  location_type TEXT,
  first_seen    TEXT NOT NULL,
  last_seen     TEXT NOT NULL,
  seen_count    INTEGER DEFAULT 1,
  raw_ref       TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_query_dedupe
  ON queries(query_norm, source, location_tag);

CREATE TABLE IF NOT EXISTS seeds (
  id            INTEGER PRIMARY KEY,
  seed_text     TEXT NOT NULL,
  seed_type     TEXT,
  language      TEXT,
  weight        REAL DEFAULT 1.0,
  active        INTEGER DEFAULT 1,
  last_run      TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_seed_dedupe
  ON seeds(seed_text, language);

CREATE TABLE IF NOT EXISTS serp_snapshots (
  id             INTEGER PRIMARY KEY,
  query_id       INTEGER NOT NULL,
  captured_at    TEXT NOT NULL,
  result_count   INTEGER,
  top_domains    TEXT,
  has_forum      INTEGER,
  has_ai_answer  INTEGER,
  our_position   INTEGER,
  raw_ref        TEXT
);
CREATE INDEX IF NOT EXISTS idx_serp_query ON serp_snapshots(query_id);

CREATE TABLE IF NOT EXISTS keyword_metrics (
  id            INTEGER PRIMARY KEY,
  query_id      INTEGER NOT NULL,
  captured_at   TEXT NOT NULL,
  volume_low    INTEGER,
  volume_high   INTEGER,
  bid_low       REAL,
  bid_high      REAL,
  competition   TEXT
);
CREATE INDEX IF NOT EXISTS idx_metrics_query ON keyword_metrics(query_id);

CREATE TABLE IF NOT EXISTS outcomes (
  id            INTEGER PRIMARY KEY,
  query_id      INTEGER,
  page_url      TEXT,
  published_at  TEXT,
  cohort        TEXT,
  impressions   INTEGER,
  clicks        INTEGER,
  position      REAL,
  measured_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_outcomes_query ON outcomes(query_id);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today_str() -> str:
    return date.today().isoformat()


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    return con


def init_db() -> None:
    con = connect()
    with con:
        con.executescript(SCHEMA)
    con.close()


def seed_hash(seed_text: str) -> str:
    """Stable short hash for keying raw files by seed."""
    return hashlib.sha1(seed_text.encode("utf-8")).hexdigest()[:16]


def write_raw(source: str, seed_text: str, payload) -> str:
    """
    Write a raw response into the raw store. Returns the relative raw_ref path.
    Appends if a file for this seed already exists today (multiple sub-requests
    per seed, e.g. alphabet expansion, are stored as a JSON list).
    """
    if source not in VALID_SOURCES:
        raise ValueError(f"unknown source: {source}")
    day = today_str()
    out_dir = RAW_DIR / source / day
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{seed_hash(seed_text)}.json"
    path = out_dir / fname
    record = {"seed": seed_text, "fetched_at": now_iso(), "payload": payload}
    if path.exists():
        try:
            existing = json.loads(path.read_text("utf-8"))
            if not isinstance(existing, list):
                existing = [existing]
        except Exception:
            existing = []
        existing.append(record)
        path.write_text(json.dumps(existing, ensure_ascii=False), "utf-8")
    else:
        path.write_text(json.dumps([record], ensure_ascii=False), "utf-8")
    return str(path.relative_to(DATA_DIR))


if __name__ == "__main__":
    init_db()
    print(f"Initialised DB at {DB_PATH}")
    print(f"Raw store at      {RAW_DIR}")
