from dataclasses import dataclass


@dataclass(frozen=True)
class Session:
    """Time session recorded for a task."""

    id: int
    project_id: int
    task_id: int | None
    task_name: str
    start_time: str
    end_time: str | None
    duration_seconds: int
    note: str = ""
