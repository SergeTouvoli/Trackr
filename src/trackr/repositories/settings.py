from trackr import db_core as db


def get_setting(name: str, default: str | None = None) -> str | None:
    conn = db.get_connection()
    row = conn.execute("SELECT value FROM setting WHERE name = ?", (name,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(name: str, value: str) -> None:
    conn = db.get_connection()
    conn.execute(
        "INSERT INTO setting (name, value) VALUES (?, ?) "
        "ON CONFLICT(name) DO UPDATE SET value = excluded.value",
        (name, value),
    )
    conn.commit()
    conn.close()
