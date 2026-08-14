import threading
from datetime import datetime

from trackr import db
from trackr.i18n import t

try:
    from plyer import notification
except ImportError:
    notification = None

CHECK_INTERVAL_SECONDS = 20


def send_notification(title: str, message: str) -> None:
    if notification is None:
        print(f"[notification skipped: plyer not installed] {title}: {message}")
        return
    try:
        notification.notify(title=title, message=message, app_name="Trackr Time", timeout=10)
    except Exception as exc:
        print(f"[notification failed] {exc}")


class ReminderScheduler:
    """Background thread that sends configured daily reminders."""

    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            self._check_once()
            self._stop_event.wait(CHECK_INTERVAL_SECONDS)

    def _check_once(self) -> None:
        now = datetime.now()
        current_hm = now.strftime("%H:%M")
        today = now.strftime("%Y-%m-%d")
        lang = db.get_setting("language", "fr")

        self._maybe_fire(
            time_setting="lunch_time",
            message_setting="lunch_message",
            default_message_key="notif_lunch_default",
            last_fired_setting="last_notif_lunch_date",
            current_hm=current_hm,
            today=today,
            lang=lang,
        )
        self._maybe_fire(
            time_setting="departure_time",
            message_setting="departure_message",
            default_message_key="notif_departure_default",
            last_fired_setting="last_notif_departure_date",
            current_hm=current_hm,
            today=today,
            lang=lang,
        )

    def _maybe_fire(
        self,
        *,
        time_setting: str,
        message_setting: str,
        default_message_key: str,
        last_fired_setting: str,
        current_hm: str,
        today: str,
        lang: str,
    ) -> None:
        target_hm = db.get_setting(time_setting, "")
        if not target_hm or target_hm != current_hm:
            return
        if db.get_setting(last_fired_setting, "") == today:
            return
        message = db.get_setting(message_setting, "") or t(default_message_key, lang)
        send_notification(t("app_title", lang), message)
        db.set_setting(last_fired_setting, today)
