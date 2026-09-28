"""Thin Postgres helpers. Raw SQL by design, no ORM."""
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json  # re-exported: ingest modules use db.Json

from . import config


@contextmanager
def conn():
    with psycopg.connect(config.DSN, row_factory=dict_row) as c:
        yield c


def migrate() -> list[str]:
    """Apply every migrations/*.sql in order. All of them are idempotent."""
    applied = []
    with conn() as c:
        for path in sorted(config.MIGRATIONS.glob("*.sql")):
            c.execute(path.read_text())
            applied.append(path.name)
        c.commit()
    return applied


def ensure_partitions(ahead: int = 2) -> None:
    with conn() as c:
        c.execute("SELECT ensure_month_partitions(%s)", (ahead,))
        c.commit()


def query(sql: str, params: tuple = ()) -> list[dict]:
    with conn() as c:
        return c.execute(sql, params).fetchall()


def one(sql: str, params: tuple = ()) -> dict | None:
    with conn() as c:
        return c.execute(sql, params).fetchone()


def execute(sql: str, params: tuple = ()) -> int:
    with conn() as c:
        cur = c.execute(sql, params)
        c.commit()
        return cur.rowcount


def copy_rows(table: str, columns: list[str], rows) -> int:
    """Bulk insert via COPY. Used for the append-only history tables, where
    a run can write hundreds of thousands of rows and executemany is too slow."""
    n = 0
    cols = ", ".join(columns)
    with conn() as c:
        with c.cursor().copy(f"COPY {table} ({cols}) FROM STDIN") as cp:
            for row in rows:
                cp.write_row(row)
                n += 1
        c.commit()
    return n


def upsert(table: str, columns: list[str], key: list[str], rows: list[tuple]) -> int:
    """INSERT .. ON CONFLICT DO UPDATE for the registry/reference tables."""
    if not rows:
        return 0
    cols = ", ".join(columns)
    ph = ", ".join(["%s"] * len(columns))
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns if c not in key)
    sql = (
        f"INSERT INTO {table} ({cols}) VALUES ({ph}) "
        f"ON CONFLICT ({', '.join(key)}) DO UPDATE SET {updates}"
        if updates
        else f"INSERT INTO {table} ({cols}) VALUES ({ph}) ON CONFLICT DO NOTHING"
    )
    with conn() as c:
        with c.cursor() as cur:
            cur.executemany(sql, rows)
        c.commit()
    return len(rows)
