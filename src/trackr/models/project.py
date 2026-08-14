from dataclasses import dataclass


@dataclass(frozen=True)
class Project:
    """Local Trackr Time project."""

    id: int
    name: str
    created_at: str
