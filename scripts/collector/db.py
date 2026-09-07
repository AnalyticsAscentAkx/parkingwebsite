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
import os
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent            # scripts/collector -> scripts -> repo
# COLLECTOR_DATA_DIR overrides the store location (used by tests to run against
# a throwaway DB without touching the real one). Defaults to data/collector.
DATA_DIR = Path(os.environ.get("COLLECTOR_DATA_DIR",
                               REPO_ROOT / "data" / "collector"))
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
  cluster_id    INTEGER,
  language      TEXT,
  language_conf REAL,
  is_parking    INTEGER,
  intent        TEXT,
  source        TEXT NOT NULL,
  seed_id       INTEGER,
  location_tag  TEXT,
  location_type TEXT,
  location_conf REAL,
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
  weight_floor  REAL DEFAULT 0.05,
  runs_since_hit INTEGER DEFAULT 0,
  active        INTEGER DEFAULT 1,
  last_run      TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_seed_dedupe
  ON seeds(seed_text, language);

-- Rejected rows, kept for QA rather than dropped silently (principle 7)
CREATE TABLE IF NOT EXISTS rejects (
  id           INTEGER PRIMARY KEY,
  query_text   TEXT NOT NULL,
  reason       TEXT,               -- not_parking | non_nl_geo | gibberish | duplicate
  source       TEXT,
  raw_ref      TEXT,
  created_at   TEXT NOT NULL
);

-- Observability: one row per collector per run (spec section 9)
CREATE TABLE IF NOT EXISTS run_manifest (
  id             INTEGER PRIMARY KEY,
  run_id         TEXT NOT NULL,
  collector      TEXT NOT NULL,
  started_at     TEXT NOT NULL,
  finished_at    TEXT,
  status         TEXT,              -- ok | partial | failed
  seeds_in       INTEGER,
  rows_out       INTEGER,
  http_429       INTEGER,
  http_403       INTEGER,
  empty_200      INTEGER,           -- soft-block detector: 200s with no payload
  notes          TEXT
);
CREATE INDEX IF NOT EXISTS idx_manifest_run ON run_manifest(run_id);
CREATE INDEX IF NOT EXISTS idx_manifest_collector ON run_manifest(collector, started_at);

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


def new_run_id() -> str:
    """One id per weekly pipeline invocation, sortable and human-readable."""
    return "run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    return con


# Columns added after the first release. `CREATE TABLE IF NOT EXISTS` never
# alters an existing table, so a DB built by the original schema needs these
# back-filled by ALTER. Keep this list append-only and idempotent.
_ADDED_COLUMNS = {
    "queries": [
        ("cluster_id", "INTEGER"),
        ("language_conf", "REAL"),
        ("is_parking", "INTEGER"),
        ("intent", "TEXT"),
        ("location_conf", "REAL"),
    ],
    "seeds": [
        ("weight_floor", "REAL DEFAULT 0.05"),
        ("runs_since_hit", "INTEGER DEFAULT 0"),
    ],
}


def _ensure_columns(con) -> None:
    """Add any post-release columns missing from an existing DB (idempotent)."""
    for table, cols in _ADDED_COLUMNS.items():
        have = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
        for name, decl in cols:
            if name not in have:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
    # Index that depends on a migrated column, created only after it exists.
    con.execute("CREATE INDEX IF NOT EXISTS idx_query_cluster "
                "ON queries(cluster_id)")


def init_db() -> None:
    con = connect()
    with con:
        con.executescript(SCHEMA)
        _ensure_columns(con)
    con.close()


def seed_hash(seed_text: str) -> str:
    """Stable short hash for keying raw files by seed."""
    return hashlib.sha1(seed_text.encode("utf-8")).hexdigest()[:16]


def raw_path(source: str, seed_text: str, day: str = None) -> Path:
    """Absolute path where this seed's raw file for `day` lives (may not exist)."""
    day = day or today_str()
    return RAW_DIR / source / day / f"{seed_hash(seed_text)}.json"


def raw_exists(source: str, seed_text: str, day: str = None) -> bool:
    """Idempotency check for resume: has this seed already been fetched today?"""
    return raw_path(source, seed_text, day).exists()


# --- lockfile: stop two overnight runs overlapping and double-fetching -------
LOCK_PATH = DATA_DIR / "collector.lock"


def acquire_lock(owner: str = "pipeline") -> bool:
    """
    Best-effort exclusive lock via O_EXCL create. Returns True on success.
    A stale lock (process no longer alive) is reclaimed automatically.
    """
    import os
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, f"{owner} pid={os.getpid()} {now_iso()}".encode())
        os.close(fd)
        return True
    except FileExistsError:
        # Reclaim if the recorded pid is dead.
        try:
            txt = LOCK_PATH.read_text("utf-8")
            pid = int(txt.split("pid=", 1)[1].split()[0])
        except Exception:
            pid = None
        if pid is not None:
            try:
                os.kill(pid, 0)          # signal 0 = liveness probe
                return False             # holder is alive
            except ProcessLookupError:
                pass                     # stale -> reclaim below
            except PermissionError:
                return False             # alive but not ours
        try:
            LOCK_PATH.unlink()
            return acquire_lock(owner)
        except Exception:
            return False


def release_lock() -> None:
    try:
        LOCK_PATH.unlink()
    except FileNotFoundError:
        pass


# --- run_manifest: observability, one row per collector per run --------------
def start_run(con, run_id: str, collector: str, seeds_in: int = None) -> int:
    cur = con.execute(
        "INSERT INTO run_manifest "
        "(run_id, collector, started_at, status, seeds_in, rows_out, "
        " http_429, http_403, empty_200) "
        "VALUES (?, ?, ?, 'running', ?, 0, 0, 0, 0)",
        (run_id, collector, now_iso(), seeds_in),
    )
    return cur.lastrowid


def finish_run(con, manifest_id: int, status: str = "ok", rows_out: int = None,
               http_429: int = None, http_403: int = None,
               empty_200: int = None, notes: str = None) -> None:
    sets = ["finished_at = ?", "status = ?"]
    vals = [now_iso(), status]
    for col, v in (("rows_out", rows_out), ("http_429", http_429),
                   ("http_403", http_403), ("empty_200", empty_200),
                   ("notes", notes)):
        if v is not None:
            sets.append(f"{col} = ?")
            vals.append(v)
    vals.append(manifest_id)
    con.execute(f"UPDATE run_manifest SET {', '.join(sets)} WHERE id = ?", vals)


def previous_rows_out(con, collector: str, before_manifest_id: int) -> int:
    """rows_out of the last successful prior run of this collector, or None."""
    row = con.execute(
        "SELECT rows_out FROM run_manifest "
        "WHERE collector = ? AND id < ? AND status IN ('ok','partial') "
        "AND rows_out IS NOT NULL ORDER BY id DESC LIMIT 1",
        (collector, before_manifest_id),
    ).fetchone()
    return row["rows_out"] if row else None


def insert_reject(con, query_text: str, reason: str,
                  source: str = None, raw_ref: str = None) -> None:
    con.execute(
        "INSERT INTO rejects (query_text, reason, source, raw_ref, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (query_text, reason, source, raw_ref, now_iso()),
    )


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
