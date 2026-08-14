import shutil
import sqlite3
import os
from datetime import datetime

from trackr.paths import app_data_dir, bundle_dir, legacy_app_data_dir


DB_PATH = app_data_dir() / "trackr.db"
CURRENT_SCHEMA_VERSION = 6
TASK_STATUS_PENDING = "pending"
TASK_STATUS_IN_PROGRESS = "in_progress"
TASK_STATUS_DONE = "done"
TASK_STATUSES = {TASK_STATUS_PENDING, TASK_STATUS_IN_PROGRESS, TASK_STATUS_DONE}
DEFAULT_WORKING_DAYS = "0,1,2,3,4"




def _migrate_legacy_db() -> None:
    """Copy a legacy database into the current user data directory."""
    if DB_PATH.exists():
        return
    legacy_user_path = legacy_app_data_dir() / "trackr.db"
    if legacy_user_path.exists() and legacy_user_path != DB_PATH:
        shutil.copy2(legacy_user_path, DB_PATH)
        return
    legacy_path = bundle_dir() / "trackr.db"
    if legacy_path.exists() and legacy_path != DB_PATH:
        shutil.copy2(legacy_path, DB_PATH)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _now() -> str:
    return datetime.now().isoformat()


def _get_schema_version(conn: sqlite3.Connection) -> int:
    """Return the schema version stored in SQLite."""
    return conn.execute("PRAGMA user_version").fetchone()[0]


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    """Store the schema version after a successful migration."""
    conn.execute(f"PRAGMA user_version = {int(version)}")


def _column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    """Return whether a column already exists in a table."""
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row["name"] == column_name for row in rows)


def _apply_migration_1(conn: sqlite3.Connection) -> None:
    """Create the initial Trackr schema."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS setting (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS project (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS timespent (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            task_name TEXT NOT NULL,
            start_time TEXT,
            end_time TEXT,
            duration_seconds INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (project_id) REFERENCES project(id) ON DELETE CASCADE
        );
        """
    )
    conn.execute(
        "INSERT OR IGNORE INTO setting (name, value) VALUES (?, ?)",
        ("username", "user"),
    )


def _apply_migration_2(conn: sqlite3.Connection) -> None:
    """Add status and estimated time to legacy tasks."""
    if not _column_exists(conn, "timespent", "task_status"):
        conn.execute(
            "ALTER TABLE timespent "
            f"ADD COLUMN task_status TEXT NOT NULL DEFAULT '{TASK_STATUS_PENDING}'"
        )
    if not _column_exists(conn, "timespent", "estimated_seconds"):
        conn.execute("ALTER TABLE timespent ADD COLUMN estimated_seconds INTEGER")


def _apply_migration_3(conn: sqlite3.Connection) -> None:
    """Add task tags and session notes."""
    if not _column_exists(conn, "timespent", "task_tags"):
        conn.execute("ALTER TABLE timespent ADD COLUMN task_tags TEXT")
    if not _column_exists(conn, "timespent", "session_note"):
        conn.execute("ALTER TABLE timespent ADD COLUMN session_note TEXT")


def _apply_migration_4(conn: sqlite3.Connection) -> None:
    """Reserved for compatibility with databases already migrated to version 4."""
    return


def _apply_migration_5(conn: sqlite3.Connection) -> None:
    """Reserved for compatibility with databases already migrated to version 5."""
    return


def _apply_migration_6(conn: sqlite3.Connection) -> None:
    """Create a proper `task` table and migrate tasks inferred from `timespent`.

    Legacy metadata columns remain in `timespent` to avoid a risky SQLite table
    rebuild. New writes use `task`, while queries remain compatible with legacy
    sessions that do not have a `task_id` yet.
    """
    conn.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS task (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT '{TASK_STATUS_PENDING}',
            estimated_seconds INTEGER,
            tags TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES project(id) ON DELETE CASCADE,
            UNIQUE(project_id, name)
        );
        """
    )
    if not _column_exists(conn, "timespent", "task_id"):
        conn.execute("ALTER TABLE timespent ADD COLUMN task_id INTEGER")

    conn.execute(
        """
        INSERT OR IGNORE INTO task (
            project_id, name, status, estimated_seconds, tags, created_at
        )
        SELECT
            first.project_id,
            first.task_name,
            COALESCE(first.task_status, ?),
            first.estimated_seconds,
            first.task_tags,
            ?
        FROM timespent first
        JOIN (
            SELECT project_id, task_name, MIN(id) AS first_id
            FROM timespent
            GROUP BY project_id, task_name
        ) grouped ON grouped.first_id = first.id
        WHERE first.task_name IS NOT NULL
        """,
        (TASK_STATUS_PENDING, _now()),
    )
    conn.execute(
        """
        UPDATE timespent
        SET task_id = (
            SELECT task.id
            FROM task
            WHERE task.project_id = timespent.project_id
              AND task.name = timespent.task_name
        )
        WHERE task_id IS NULL
        """
    )


MIGRATIONS = {
    1: _apply_migration_1,
    2: _apply_migration_2,
    3: _apply_migration_3,
    4: _apply_migration_4,
    5: _apply_migration_5,
    6: _apply_migration_6,
}


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply all pending migrations in order."""
    schema_version = _get_schema_version(conn)
    if schema_version > CURRENT_SCHEMA_VERSION:
        raise RuntimeError(
            f"Base Trackr trop récente: version {schema_version}, application {CURRENT_SCHEMA_VERSION}"
        )

    for version in range(schema_version + 1, CURRENT_SCHEMA_VERSION + 1):
        migration = MIGRATIONS[version]
        migration(conn)
        _set_schema_version(conn, version)
    conn.commit()


def init_db() -> None:
    _migrate_legacy_db()
    conn = get_connection()
    try:
        _apply_migrations(conn)
    finally:
        conn.close()

    # On POSIX systems, restrict the database to its owner because it contains
    # project history and authentication hashes. Windows uses ACLs instead, and
    # chmod() cannot apply equivalent owner-only permissions there.
    if os.name != "nt":
        DB_PATH.chmod(0o600)
