from dataclasses import dataclass


@dataclass(frozen=True)
class Task:
    """Trackr task as read from the database"""

    id: int
    project_id: int
    name: str
    status: str
    total_seconds: int = 0
    estimated_seconds: int | None = None
    tags: str = ""


@dataclass(frozen=True)
class TaskInput:
    """Validated data required to create a task"""

    project_id: int
    name: str
    status: str
    estimated_seconds: int | None = None
    tags: str = ""
