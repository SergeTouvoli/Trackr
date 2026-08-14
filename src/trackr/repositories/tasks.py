import sqlite3

from trackr import db_core as db
from trackr.models import TaskInput


def list_tasks(project_id: int) -> list[sqlite3.Row]:
    """Return one row per distinct project task with accumulated duration.

    Metadata comes from the ``task`` table. The sum is still calculated from
    ``timespent`` sessions, with a name fallback for legacy rows that do not have
    a ``task_id`` yet.
    """
    conn = db.get_connection()
    rows = conn.execute(
        """
        SELECT
            task.name AS task_name,
            COALESCE(SUM(timespent.duration_seconds), 0) AS total_seconds,
            task.status AS task_status,
            task.estimated_seconds,
            COALESCE(task.tags, '') AS task_tags
        FROM task
        LEFT JOIN timespent
            ON timespent.project_id = task.project_id
            AND (timespent.task_id = task.id OR (timespent.task_id IS NULL AND timespent.task_name = task.name))
        WHERE task.project_id = ?
        GROUP BY task.id
        ORDER BY task.name
        """,
        (project_id,),
    ).fetchall()
    conn.close()
    return rows


def get_task_by_name(project_id: int, task_name: str) -> sqlite3.Row | None:
    conn = db.get_connection()
    row = conn.execute(
        "SELECT name AS task_name FROM task WHERE project_id = ? AND name = ? LIMIT 1",
        (project_id, task_name),
    ).fetchone()
    conn.close()
    return row


def _normalize_task_status(task_status: str | None) -> str:
    return task_status if task_status in db.TASK_STATUSES else db.TASK_STATUS_PENDING


def add_task(
    project_id: int,
    task_name: str,
    task_status: str = db.TASK_STATUS_PENDING,
    estimated_seconds: int | None = None,
    task_tags: str = "",
) -> None:
    task = TaskInput(
        project_id=project_id,
        name=task_name,
        status=_normalize_task_status(task_status),
        estimated_seconds=estimated_seconds,
        tags=task_tags.strip(),
    )
    conn = db.get_connection()
    conn.execute(
        """
        INSERT INTO task (
            project_id, name, status, estimated_seconds, tags, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            task.project_id,
            task.name,
            task.status,
            task.estimated_seconds,
            task.tags,
            db._now(),
        ),
    )
    conn.commit()
    conn.close()


def get_task_metadata(project_id: int, task_name: str) -> sqlite3.Row | None:
    conn = db.get_connection()
    row = conn.execute(
        """
        SELECT
            status AS task_status,
            estimated_seconds,
            COALESCE(tags, '') AS task_tags
        FROM task
        WHERE project_id = ? AND name = ?
        LIMIT 1
        """,
        (project_id, task_name),
    ).fetchone()
    conn.close()
    return row


def update_task_metadata(
    project_id: int,
    task_name: str,
    task_status: str,
    estimated_seconds: int | None,
    task_tags: str = "",
) -> None:
    conn = db.get_connection()
    conn.execute(
        """
        UPDATE task
        SET status = ?, estimated_seconds = ?, tags = ?
        WHERE project_id = ? AND name = ?
        """,
        (_normalize_task_status(task_status), estimated_seconds, task_tags.strip(), project_id, task_name),
    )
    conn.commit()
    conn.close()


def rename_task(project_id: int, old_name: str, new_name: str) -> None:
    conn = db.get_connection()
    conn.execute(
        "UPDATE task SET name = ? WHERE project_id = ? AND name = ?",
        (new_name, project_id, old_name),
    )
    conn.execute(
        "UPDATE timespent SET task_name = ? WHERE project_id = ? AND task_name = ?",
        (new_name, project_id, old_name),
    )
    conn.commit()
    conn.close()


def delete_task(project_id: int, task_name: str) -> None:
    conn = db.get_connection()
    task = conn.execute("SELECT id FROM task WHERE project_id = ? AND name = ?", (project_id, task_name)).fetchone()
    if task is not None:
        conn.execute("DELETE FROM timespent WHERE task_id = ?", (task["id"],))
        conn.execute("DELETE FROM task WHERE id = ?", (task["id"],))
    conn.execute(
        "DELETE FROM timespent WHERE project_id = ? AND task_name = ?",
        (project_id, task_name),
    )
    conn.commit()
    conn.close()
