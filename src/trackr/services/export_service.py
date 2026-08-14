import csv
from pathlib import Path

from trackr import db


CSV_HEADERS = ["project", "task", "tags", "start", "end", "duration_seconds", "note"]


def write_sessions_csv(path: str) -> None:
    """Export all sessions to a flat CSV file.

    This service remains independent from Flet: the UI selects the file path, then
    the service reads sessions and writes the CSV. This makes export testable
    without opening a native dialog.
    """
    sessions = db.list_all_sessions()
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADERS)
        for session in sessions:
            writer.writerow(
                [
                    session["project_name"],
                    session["task_name"],
                    session["task_tags"],
                    session["start_time"],
                    session["end_time"],
                    session["duration_seconds"],
                    session["session_note"],
                ]
            )
