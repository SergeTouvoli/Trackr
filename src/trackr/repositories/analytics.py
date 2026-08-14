import sqlite3
from datetime import date, timedelta

from trackr import db_core as db


def get_daily_totals(project_id: int, days: int = 14) -> list[sqlite3.Row]:
    since = (date.today() - timedelta(days=days - 1)).isoformat()
    conn = db.get_connection()
    rows = conn.execute(
        """
        SELECT date(start_time) AS day, SUM(duration_seconds) AS total_seconds
        FROM timespent
        WHERE project_id = ? AND start_time IS NOT NULL AND date(start_time) >= ?
        GROUP BY day
        ORDER BY day
        """,
        (project_id, since),
    ).fetchall()
    conn.close()
    return rows


def get_task_totals(project_id: int, days: int = 14) -> list[sqlite3.Row]:
    since = (date.today() - timedelta(days=days - 1)).isoformat()
    conn = db.get_connection()
    rows = conn.execute(
        """
        SELECT task_name, SUM(duration_seconds) AS total_seconds
        FROM timespent
        WHERE project_id = ? AND start_time IS NOT NULL AND date(start_time) >= ?
        GROUP BY task_name
        HAVING total_seconds > 0
        ORDER BY total_seconds DESC
        """,
        (project_id, since),
    ).fetchall()
    conn.close()
    return rows


def get_project_totals(days: int = 14) -> list[sqlite3.Row]:
    since = (date.today() - timedelta(days=days - 1)).isoformat()
    conn = db.get_connection()
    rows = conn.execute(
        """
        SELECT p.id AS project_id, p.name AS project_name, SUM(t.duration_seconds) AS total_seconds
        FROM timespent t
        JOIN project p ON p.id = t.project_id
        WHERE t.start_time IS NOT NULL AND date(t.start_time) >= ?
        GROUP BY p.id
        HAVING total_seconds > 0
        ORDER BY total_seconds DESC
        """,
        (since,),
    ).fetchall()
    conn.close()
    return rows
