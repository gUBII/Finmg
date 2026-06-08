"""Idempotent SQLite migration runner.

Reads `src/db/schema/NNN_*.sql` in version order, applies any not yet recorded
in `schema_migrations`, and records each one as it succeeds. Before applying
*any* new migration on an existing DB, copies the DB file to
`data/backups/finmg_<UTC_timestamp>.db` so a bad migration is never silently
destructive.

Run directly:
    python3 -m src.db.migrations
or:
    python3 src/db/migrations.py
"""

from __future__ import annotations

import re
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_DIR = REPO_ROOT / "src" / "db" / "schema"
DEFAULT_DB_PATH = REPO_ROOT / "data" / "finmg.db"
BACKUP_DIR = REPO_ROOT / "data" / "backups"

VERSION_RE = re.compile(r"^(\d{3})_.*\.sql$")


def discover_migrations(schema_dir: Path = SCHEMA_DIR) -> list[tuple[str, Path]]:
    """Return [(version, path), ...] sorted by version."""
    files: list[tuple[str, Path]] = []
    if not schema_dir.exists():
        return files
    for path in schema_dir.iterdir():
        match = VERSION_RE.match(path.name)
        if match:
            files.append((match.group(1), path))
    files.sort(key=lambda x: x[0])
    return files


def applied_versions(conn: sqlite3.Connection) -> set[str]:
    """Return the set of versions already recorded in schema_migrations.

    Returns empty set if the schema_migrations table doesn't exist yet (the
    first migration creates it).
    """
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    if not row:
        return set()
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {r[0] for r in rows}


def backup_db(db_path: Path, backup_dir: Path = BACKUP_DIR) -> Path | None:
    """Copy the DB file to a timestamped backup. No-op if DB doesn't exist yet."""
    if not db_path.exists():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = backup_dir / f"finmg_{stamp}.db"
    shutil.copy2(db_path, dest)
    return dest


def apply_migration(conn: sqlite3.Connection, version: str, sql_path: Path) -> None:
    """Apply one migration file inside a transaction and record its version."""
    sql_text = sql_path.read_text(encoding="utf-8")
    conn.executescript(sql_text)
    conn.execute(
        "INSERT INTO schema_migrations (version) VALUES (?)",
        (version,),
    )
    conn.commit()


def apply_all(
    conn: sqlite3.Connection,
    db_path: Path | None = None,
    schema_dir: Path = SCHEMA_DIR,
    backup_dir: Path = BACKUP_DIR,
) -> list[str]:
    """Apply every pending migration in version order.

    Returns the list of versions newly applied (empty if DB was already
    up-to-date).
    """
    migrations = discover_migrations(schema_dir)
    already = applied_versions(conn)
    pending = [(v, p) for (v, p) in migrations if v not in already]

    if not pending:
        return []

    if db_path is not None:
        backup_db(db_path, backup_dir)

    newly_applied: list[str] = []
    for version, path in pending:
        apply_migration(conn, version, path)
        newly_applied.append(version)
    return newly_applied


def main(argv: list[str] | None = None) -> int:
    from src.db.database import get_connection

    db_path = DEFAULT_DB_PATH
    conn = get_connection(db_path)
    try:
        applied = apply_all(conn, db_path=db_path)
        if applied:
            print(f"Applied migrations: {', '.join(applied)}")
        else:
            print("No pending migrations.")
        rows = conn.execute(
            "SELECT version, applied_at FROM schema_migrations ORDER BY version"
        ).fetchall()
        print("Applied history:")
        for r in rows:
            print(f"  {r['version']}  {r['applied_at']}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
