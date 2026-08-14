"""Single-instance lock using a named Windows mutex without dependencies.

A mutex is preferable to a lock file: Windows releases it automatically when the
process exits or crashes, without requiring stale-lock cleanup.
"""
import sys

_MUTEX_NAME = "Trackr-SingleInstance-Mutex"
_ERROR_ALREADY_EXISTS = 183

_handle = None  # Kept for the process lifetime to retain the lock.


def acquire() -> bool:
    """Return True when no other instance already holds the lock."""
    global _handle
    if sys.platform != "win32":
        return True
    import ctypes

    _handle = ctypes.windll.kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    if not _handle:
        return True  # Fail open: an unavailable mutex must not block startup.
    return ctypes.windll.kernel32.GetLastError() != _ERROR_ALREADY_EXISTS
