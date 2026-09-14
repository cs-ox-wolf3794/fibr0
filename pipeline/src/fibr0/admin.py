"""Database administration: apply SQL migrations and load seed CSVs.

Replaces psql for a machine that does not have it. Migrations are tracked in
schema_migrations by filename and applied in lexical order inside one transaction each.
Seeds are upserted so re-running is safe.
"""

from __future__ import annotations

import logging
from pathlib import Path

import psycopg

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"
SEED_DIR = REPO_ROOT / "supabase" / "seed"


def pending_migrations(conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR) -> list[Path]:
    with conn.cursor() as cur:
        cur.execute(
            "create table if not exists schema_migrations "
            "(filename text primary key, applied_at timestamptz not null default now())"
        )
        cur.execute("select filename from schema_migrations")
        applied = {row["filename"] for row in cur.fetchall()}
    return [p for p in sorted(directory.glob("*.sql")) if p.name not in applied]


def migrate(conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR) -> list[str]:
    applied: list[str] = []
    for path in pending_migrations(conn, directory):
        log.info("applying %s", path.name)
        with conn.cursor() as cur:
            cur.execute(path.read_text("utf-8"))
            cur.execute("insert into schema_migrations (filename) values (%s)", (path.name,))
        conn.commit()
        applied.append(path.name)
    return applied


def _upsert_from_csv(conn: psycopg.Connection, table: str, columns: list[str], path: Path) -> int:
    """COPY the CSV into a temp table, then upsert into the target on its primary key."""
    cols = ", ".join(columns)
    updates = ", ".join(f"{c} = excluded.{c}" for c in columns[1:])
    with conn.cursor() as cur:
        cur.execute(f"create temp table staging_{table} (like {table} including defaults)")
        with cur.copy(
            f"copy staging_{table} ({cols}) from stdin with (format csv, header true)"
        ) as copy:
            copy.write(path.read_bytes())
        cur.execute(
            f"insert into {table} ({cols}) select {cols} from staging_{table} "
            f"on conflict ({columns[0]}) do update set {updates}"
        )
        count = cur.rowcount
        cur.execute(f"drop table staging_{table}")
    conn.commit()
    return count


def seed(conn: psycopg.Connection, directory: Path = SEED_DIR) -> dict[str, int]:
    counts = {
        "sources": _upsert_from_csv(
            conn,
            "sources",
            ["id", "name", "tier", "trust_weight", "kind", "url", "enabled"],
            directory / "sources.csv",
        ),
        "ticker_universe": _upsert_from_csv(
            conn,
            "ticker_universe",
            ["ticker", "name", "sector", "subsector", "relationship_tags"],
            directory / "ticker_universe.csv",
        ),
    }
    log.info("seeded %s", counts)
    return counts


def status(conn: psycopg.Connection) -> dict[str, int]:
    """Row counts for a quick health check."""
    tables = ("sources", "ticker_universe", "raw_items", "events", "predictions", "resolutions")
    out: dict[str, int] = {}
    with conn.cursor() as cur:
        for table in tables:
            cur.execute(f"select count(*) as n from {table}")
            out[table] = cur.fetchone()["n"]
    return out
