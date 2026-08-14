def parse_optional_seconds(value: str | None, multiplier: int = 1) -> int | None:
    """Convert an optional numeric setting to seconds.

    Trackr duration settings accept ``0`` or an empty value to disable an alert.
    The multiplier shares the logic between hours and minutes without duplicating
    validation blocks.
    """
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        number = int(raw)
    except ValueError:
        return None
    return number * multiplier if number > 0 else None
