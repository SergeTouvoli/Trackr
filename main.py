import sys
import traceback
from pathlib import Path

import flet as ft

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
if not getattr(sys, "frozen", False) and SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from trackr import db, single_instance
from trackr.app import main as app_main
from trackr.i18n import t
from trackr.notifications import send_notification
from trackr.paths import app_data_dir, assets_dir


def _write_crash_log(exc: BaseException) -> None:
    try:
        log_path = app_data_dir() / "startup-crash.log"
        log_path.write_text(
            "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
            encoding="utf-8",
        )
    except Exception:
        pass

if __name__ == "__main__":
    try:
        db.init_db()

        if single_instance.acquire():
            ft.app(target=app_main, assets_dir=str(assets_dir()))
        else:
            lang = db.get_setting("language", "fr")
            send_notification(t("app_title", lang), t("already_running", lang))
    except Exception as exc:
        _write_crash_log(exc)
        raise
