"""Windows system-idle detection through ctypes, without external dependencies."""
import sys

if sys.platform == "win32":
    import ctypes

    class _LastInputInfo(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
else:
    ctypes = None


def get_afk_seconds() -> float | None:
    """Return seconds since the last input, or None when unsupported."""
    if ctypes is None:
        return None
    try:
        info = _LastInputInfo()
        info.cbSize = ctypes.sizeof(_LastInputInfo)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return None
        millis = ctypes.windll.kernel32.GetTickCount() - info.dwTime
        return millis / 1000.0
    except Exception:
        return None
