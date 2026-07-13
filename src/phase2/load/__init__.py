"""Stage 3 — load: bulk-insert normalized CSVs into the SQLite base tables.

Reads data/interim/{agent,trial,arm,regimen_component,outcome}.csv and inserts
in FK order. The database must already exist (make db) with lookup tables seeded.

Details:
  * empty CSV cells -> SQL NULL; numeric strings are coerced by column affinity
    (schema declares INTEGER/REAL), so CHECK constraints see real numbers.
  * INSERT OR IGNORE makes re-runs idempotent: rows whose deterministic PK
    already exists are skipped. OR IGNORE does NOT apply to FOREIGN KEY
    constraints, so a FK-violating row raises IntegrityError and rolls back the
    whole load (fail loud) — transform is responsible for referential integrity.
"""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from .. import config, db

# insertion order respects foreign keys
LOAD_ORDER = ["agent", "trial", "arm", "regimen_component", "outcome"]


def _coerce(value: str | None) -> str | None:
    """Empty CSV cell -> NULL; everything else passes through for affinity."""
    return value if value not in ("", None) else None


def load_table(conn: sqlite3.Connection, path: Path, table: str) -> tuple[int, int]:
    """Insert one CSV into `table`. Returns (inserted, skipped)."""
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        cols = reader.fieldnames or []
        rows = [tuple(_coerce(r[c]) for c in cols) for r in reader]
    if not rows:
        return 0, 0
    sql = (f"INSERT OR IGNORE INTO {table} ({','.join(cols)}) "
           f"VALUES ({','.join('?' * len(cols))})")
    before = conn.total_changes
    conn.executemany(sql, rows)
    inserted = conn.total_changes - before
    return inserted, len(rows) - inserted


def run() -> None:
    cfg = config.load()
    interim = config.ROOT / cfg["paths"]["interim"]
    if not config.db_path().exists():
        raise FileNotFoundError(
            f"database not found: {config.db_path()} — run `make db` first")

    with db.session() as conn:
        for table in LOAD_ORDER:
            path = interim / f"{table}.csv"
            if not path.exists():
                print(f"[load] {table}: no {path.name} — run transform first")
                continue
            inserted, skipped = load_table(conn, path, table)
            note = f", {skipped} skipped" if skipped else ""
            print(f"[load] {table}: {inserted} inserted{note}")
