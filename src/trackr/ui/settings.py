import re

import flet as ft

from trackr import db
from trackr.app_metadata import APP_RELEASE_AUTHOR, APP_RELEASE_DATE, APP_VERSION
from trackr.i18n import t


TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
TIME_DISPLAY_HMS = "hms"
TIME_DISPLAY_HUMAN = "human"
TIME_DISPLAY_MINUTES = "minutes"
TIME_DISPLAY_FORMATS = {TIME_DISPLAY_HMS, TIME_DISPLAY_HUMAN, TIME_DISPLAY_MINUTES}


def build(app) -> ft.Container:
    """Build the Settings page and centralize field validation.

    This view centralizes preferences persisted in SQLite. Keeping validation here
    prevents a partial save when a field is invalid.
    """
    lang = app.lang
    username_field = ft.TextField(label=t("username", lang), value=db.get_setting("username", "user"))
    lunch_time_field = ft.TextField(
        label=f"{t('lunch_time', lang)} (HH:MM)", value=db.get_setting("lunch_time", ""), expand=True
    )
    lunch_message_field = ft.TextField(
        label=t("lunch_message", lang),
        value=db.get_setting("lunch_message", ""),
        hint_text=t("notif_lunch_default", lang),
    )
    departure_time_field = ft.TextField(
        label=f"{t('departure_time', lang)} (HH:MM)", value=db.get_setting("departure_time", ""), expand=True
    )
    departure_message_field = ft.TextField(
        label=t("departure_message", lang),
        value=db.get_setting("departure_message", ""),
        hint_text=t("notif_departure_default", lang),
    )
    idle_alert_hours_field = ft.TextField(
        label=t("idle_alert_hours", lang),
        value=db.get_setting("idle_alert_hours", "4"),
        hint_text=t("idle_alert_hint", lang),
        expand=True,
    )
    afk_threshold_field = ft.TextField(
        label=t("afk_threshold_minutes", lang),
        value=db.get_setting("afk_threshold_minutes", "5"),
        hint_text=t("afk_threshold_hint", lang),
        expand=True,
    )
    theme_dropdown = ft.Dropdown(
        label=t("theme", lang),
        value=app.theme_mode_value,
        expand=True,
        options=[
            ft.dropdown.Option(key="light", text=t("theme_light", lang)),
            ft.dropdown.Option(key="dark", text=t("theme_dark", lang)),
        ],
    )
    language_dropdown = ft.Dropdown(
        label=t("language", lang),
        value=lang,
        expand=True,
        options=[
            ft.dropdown.Option(key="fr", text="Français"),
            ft.dropdown.Option(key="en", text="English"),
            ft.dropdown.Option(key="es", text="Español"),
            ft.dropdown.Option(key="it", text="Italiano"),
            ft.dropdown.Option(key="de", text="Deutsch"),
        ],
    )
    time_display_dropdown = ft.Dropdown(
        label=t("time_display_format", lang),
        value=app.time_display_format,
        expand=True,
        options=[
            ft.dropdown.Option(key=TIME_DISPLAY_HMS, text=t("time_display_hms", lang)),
            ft.dropdown.Option(key=TIME_DISPLAY_HUMAN, text=t("time_display_human", lang)),
            ft.dropdown.Option(key=TIME_DISPLAY_MINUTES, text=t("time_display_minutes", lang)),
        ],
    )
    selected_working_days = db.parse_working_days(db.get_setting("working_days", db.DEFAULT_WORKING_DAYS))
    working_day_checkboxes = [
        ft.Checkbox(label=t(f"weekday_{day}", lang), value=day in selected_working_days)
        for day in range(7)
    ]
    error_text = ft.Text("", color=ft.Colors.ERROR)

    def save(e):
        lt = (lunch_time_field.value or "").strip()
        dt = (departure_time_field.value or "").strip()
        if lt and not TIME_RE.match(lt):
            error_text.value = f"{t('lunch_time', lang)}: format HH:MM"
            error_text.update()
            return
        if dt and not TIME_RE.match(dt):
            error_text.value = f"{t('departure_time', lang)}: format HH:MM"
            error_text.update()
            return
        idle_hours = (idle_alert_hours_field.value or "").strip()
        if idle_hours and not idle_hours.isdigit():
            error_text.value = f"{t('idle_alert_hours', lang)}: nombre entier requis"
            error_text.update()
            return
        afk_minutes = (afk_threshold_field.value or "").strip()
        if afk_minutes and not afk_minutes.isdigit():
            error_text.value = f"{t('afk_threshold_minutes', lang)}: nombre entier requis"
            error_text.update()
            return
        working_days = {day for day, checkbox in enumerate(working_day_checkboxes) if checkbox.value}
        if not working_days:
            error_text.value = t("working_days_required", lang)
            error_text.update()
            return

        db.set_setting("username", (username_field.value or "user").strip())
        db.set_setting("lunch_time", lt)
        db.set_setting("lunch_message", (lunch_message_field.value or "").strip())
        db.set_setting("departure_time", dt)
        db.set_setting("departure_message", (departure_message_field.value or "").strip())
        db.set_setting("idle_alert_hours", idle_hours or "0")
        db.set_setting("afk_threshold_minutes", afk_minutes or "0")
        db.set_setting("working_days", ",".join(str(day) for day in sorted(working_days)))

        app.theme_mode_value = theme_dropdown.value
        db.set_setting("theme_mode", app.theme_mode_value)
        app.page.theme_mode = ft.ThemeMode.DARK if app.theme_mode_value == "dark" else ft.ThemeMode.LIGHT
        app.time_display_format = time_display_dropdown.value
        if app.time_display_format not in TIME_DISPLAY_FORMATS:
            app.time_display_format = TIME_DISPLAY_HMS
        db.set_setting("time_display_format", app.time_display_format)

        app.lang = language_dropdown.value
        db.set_setting("language", app.lang)

        app.apply_texts()
        app.page.show_dialog(ft.SnackBar(ft.Text(t("settings_saved", app.lang))))
        app.show_main()

    lock_enabled = bool(db.get_setting("auth_password_hash", ""))
    if lock_enabled:
        security_controls = [
            app._settings_hint(t("security_hint", lang)),
            ft.Text(t("lock_enabled", lang), size=13, color=ft.Colors.OUTLINE),
            ft.Row(
                [
                    ft.OutlinedButton(
                        content=t("change_password", lang),
                        on_click=lambda e: app._open_set_password_dialog(True),
                    ),
                    ft.OutlinedButton(
                        content=t("disable_lock", lang),
                        on_click=lambda e: app._open_disable_lock_dialog(),
                        style=ft.ButtonStyle(color=ft.Colors.RED_600),
                    ),
                ],
                spacing=10,
            ),
        ]
    else:
        security_controls = [
            app._settings_hint(t("security_hint", lang)),
            ft.Text(t("lock_disabled_hint", lang), size=13, color=ft.Colors.OUTLINE),
            ft.FilledButton(
                content=t("enable_lock", lang),
                icon=ft.Icons.LOCK_ROUNDED,
                on_click=lambda e: app._open_set_password_dialog(False),
            ),
        ]

    return ft.Container(
        padding=30,
        content=ft.Column(
            [
                ft.Text(t("settings", lang), size=26, weight=ft.FontWeight.BOLD),
                app._settings_section(
                    ft.Icons.PERSON_OUTLINE_ROUNDED,
                    t("profile_section", lang),
                    [app._settings_hint(t("profile_hint", lang)), username_field],
                ),
                app._settings_section(ft.Icons.LOCK_OUTLINE_ROUNDED, t("security_section", lang), security_controls),
                app._settings_section(
                    ft.Icons.NOTIFICATIONS_OUTLINED,
                    t("notifications_section", lang),
                    [
                        app._settings_hint(t("notifications_hint", lang)),
                        ft.Row([lunch_time_field, departure_time_field], spacing=14),
                        lunch_message_field,
                        departure_message_field,
                        app._settings_hint(t("idle_alert_hint_detail", lang)),
                        idle_alert_hours_field,
                    ],
                ),
                app._settings_section(
                    ft.Icons.PAUSE_CIRCLE_OUTLINED,
                    t("afk_section", lang),
                    [app._settings_hint(t("afk_hint", lang)), afk_threshold_field],
                ),
                app._settings_section(
                    ft.Icons.CALENDAR_MONTH_OUTLINED,
                    t("time_tracking_section", lang),
                    [
                        app._settings_hint(t("time_display_hint", lang)),
                        time_display_dropdown,
                        app._settings_hint(t("working_days_hint", lang)),
                        ft.Text(t("working_days", lang), size=13, weight=ft.FontWeight.W_600),
                        ft.Row(working_day_checkboxes, spacing=4, wrap=True),
                    ],
                ),
                app._settings_section(
                    ft.Icons.PALETTE_OUTLINED,
                    t("appearance_section", lang),
                    [app._settings_hint(t("appearance_hint", lang)), ft.Row([theme_dropdown, language_dropdown], spacing=14)],
                ),
                app._settings_section(
                    ft.Icons.INFO_OUTLINE_ROUNDED,
                    t("about_section", lang),
                    [
                        ft.Text(
                            t(
                                "version_info",
                                lang,
                                version=APP_VERSION,
                                date=APP_RELEASE_DATE,
                                author=APP_RELEASE_AUTHOR,
                            ),
                            size=13,
                            color=ft.Colors.OUTLINE,
                        )
                    ],
                ),
                error_text,
                ft.FilledButton(content=t("save", lang), icon=ft.Icons.SAVE_ROUNDED, on_click=save, height=48),
            ],
            spacing=18,
            scroll=ft.ScrollMode.AUTO,
        ),
    )
