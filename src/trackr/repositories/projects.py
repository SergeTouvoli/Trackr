import sqlite3

from trackr import db_core as db


def list_projects() -> list[sqlite3.Row]:
    conn = db.get_connection()
    rows = conn.execute("SELECT * FROM project ORDER BY name").fetchall()
    conn.close()
    return rows


def add_project(name: str) -> int:
    conn = db.get_connection()
    cur = conn.execute(
        "INSERT INTO project (name, created_at) VALUES (?, ?)", (name, db._now())
    )
    conn.commit()
    project_id = cur.lastrowid
    conn.close()
    return project_id


def get_project_by_name(name: str) -> sqlite3.Row | None:
    conn = db.get_connection()
    row = conn.execute("SELECT * FROM project WHERE name = ?", (name,)).fetchone()
    conn.close()
    return row


def get_project(project_id: int) -> sqlite3.Row | None:
    conn = db.get_connection()
    row = conn.execute("SELECT * FROM project WHERE id = ?", (project_id,)).fetchone()
    conn.close()
    return row


def delete_project(project_id: int) -> None:
    conn = db.get_connection()
    conn.execute("DELETE FROM project WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()
