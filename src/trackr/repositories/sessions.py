import sqlite3
from datetime import date, datetime, timedelta

from trackr import db_core as db


def start_timer(project_id: int, task_name: str) -> int:
    """Create a running session and return its identifier.

    The new session copies metadata from the existing task so status, estimate,
    and tags remain available in exports and history, even though ``task`` is now
    the canonical source.
    """
    conn = db.get_connection()
    metadata = conn.execute(
        """
        SELECT
            id,
            status AS task_status,
            estimated_seconds,
            COALESCE(tags, '') AS task_tags
        FROM task
        WHERE project_id = ? AND name = ?
        LIMIT 1
        """,
        (project_id, task_name),
    ).fetchone()
    task_status = (
        db.TASK_STATUS_IN_PROGRESS
        if metadata is None or metadata["task_status"] == db.TASK_STATUS_PENDING
        else metadata["task_status"]
    )
    estimated_seconds = metadata["estimated_seconds"] if metadata else None
    task_tags = metadata["task_tags"] if metadata else ""
    task_id = metadata["id"] if metadata else None
    conn.execute(
        """
        UPDATE task
        SET status = ?
        WHERE project_id = ? AND name = ? AND status = ?
        """,
        (db.TASK_STATUS_IN_PROGRESS, project_id, task_name, db.TASK_STATUS_PENDING),
    )
    cur = conn.execute(
        """
        INSERT INTO timespent (
            project_id, task_id, task_name, start_time, duration_seconds, task_status,
            estimated_seconds, task_tags
        )
        VALUES (?, ?, ?, ?, 0, ?, ?, ?)
        """,
        (
            project_id,
            task_id,
            task_name,
            db._now(),
            task_status,
            estimated_seconds,
            task_tags,
        ),
    )
    conn.commit()
    session_id = cur.lastrowid
    conn.close()
    return session_id


def stop_timer(session_id: int, duration_seconds: int, session_note: str = "") -> None:
    conn = db.get_connection()
    conn.execute(
        "UPDATE timespent SET end_time = ?, duration_seconds = ?, session_note = ? WHERE id = ?",
        (db._now(), duration_seconds, session_note.strip(), session_id),
    )
    conn.commit()
    conn.close()


def update_session(
    session_id: int,
    start_time: str,
    end_time: str | None,
    duration_seconds: int,
    session_note: str,
) -> None:
    conn = db.get_connection()
    conn.execute(
        """
        UPDATE timespent
        SET start_time = ?, end_time = ?, duration_seconds = ?, session_note = ?
        WHERE id = ?
        """,
        (start_time, end_time, max(0, int(duration_seconds)), session_note.strip(), session_id),
    )
    conn.commit()
    conn.close()


def delete_session(session_id: int) -> None:
    conn = db.get_connection()
    conn.execute("DELETE FROM timespent WHERE id = ? AND start_time IS NOT NULL", (session_id,))
    conn.commit()
    conn.close()


def list_task_sessions(project_id: int, task_name: str) -> list[sqlite3.Row]:
    conn = db.get_connection()
    rows = conn.execute(
        """
        SELECT id, start_time, end_time, duration_seconds, COALESCE(session_note, '') AS session_note
        FROM timespent
        WHERE project_id = ?
          AND task_name = ?
          AND start_time IS NOT NULL
        ORDER BY start_time DESC
        """,
        (project_id, task_name),
    ).fetchall()
    conn.close()
    return rows


def parse_working_days(value: str | None) -> set[int]:
    days: set[int] = set()
    for part in (value or db.DEFAULT_WORKING_DAYS).split(","):
        part = part.strip()
        if part.isdigit():
            day = int(part)
            if 0 <= day <= 6:
                days.add(day)
    return days or {0, 1, 2, 3, 4}


def get_summary(project_id: int, working_days: set[int] | None = None) -> dict:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    conn = db.get_connection()
    today_total = conn.execute(
        "SELECT COALESCE(SUM(duration_seconds), 0) AS total FROM timespent "
        "WHERE project_id = ? AND date(start_time) = ?",
        (project_id, today.isoformat()),
    ).fetchone()["total"]
    if working_days is None:
        week_total = conn.execute(
            "SELECT COALESCE(SUM(duration_seconds), 0) AS total FROM timespent "
            "WHERE project_id = ? AND date(start_time) >= ?",
            (project_id, monday.isoformat()),
        ).fetchone()["total"]
    else:
        rows = conn.execute(
            "SELECT start_time, duration_seconds FROM timespent "
            "WHERE project_id = ? AND start_time IS NOT NULL AND date(start_time) >= ?",
            (project_id, monday.isoformat()),
        ).fetchall()
        week_total = sum(
            row["duration_seconds"] or 0
            for row in rows
            if datetime.fromisoformat(row["start_time"]).weekday() in working_days
        )
    conn.close()
    return {"today": today_total, "week": week_total}


def list_all_sessions() -> list[sqlite3.Row]:
    conn = db.get_connection()
    rows = conn.execute(
        """
        SELECT
            p.name AS project_name,
            t.task_name,
            COALESCE(t.task_tags, '') AS task_tags,
            t.start_time,
            t.end_time,
            t.duration_seconds,
            COALESCE(t.session_note, '') AS session_note
        FROM timespent t
        JOIN project p ON p.id = t.project_id
        WHERE t.start_time IS NOT NULL
        ORDER BY t.start_time
        """
    ).fetchall()
    conn.close()
    return rows


def list_day_sessions(target_day: date | None = None) -> list[sqlite3.Row]:
    day = target_day or date.today()
    conn = db.get_connection()
    rows = conn.execute(
        """
        SELECT
            t.id,
            p.id AS project_id,
            p.name AS project_name,
            t.task_name,
            COALESCE(t.task_tags, '') AS task_tags,
            t.start_time,
            t.end_time,
            t.duration_seconds,
            COALESCE(t.session_note, '') AS session_note
        FROM timespent t
        JOIN project p ON p.id = t.project_id
        WHERE t.start_time IS NOT NULL AND date(t.start_time) = ?
        ORDER BY t.start_time
        """,
        (day.isoformat(),),
    ).fetchall()
    conn.close()
    return rows


def get_day_total(target_day: date | None = None) -> int:
    day = target_day or date.today()
    conn = db.get_connection()
    total = conn.execute(
        "SELECT COALESCE(SUM(duration_seconds), 0) AS total FROM timespent WHERE date(start_time) = ?",
        (day.isoformat(),),
    ).fetchone()["total"]
    conn.close()
    return total
