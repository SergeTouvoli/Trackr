import asyncio
import os
import re
import threading
import time
from datetime import date, datetime, timedelta

import flet as ft

from trackr import auth, db
from trackr.afk import get_afk_seconds
from trackr.i18n import t
from trackr.notifications import ReminderScheduler, send_notification
from trackr.paths import asset_path
from trackr.services import export_service, timer_service
from trackr.ui import analytics as analytics_ui
from trackr.ui import main_view
from trackr.ui import settings as settings_ui
from trackr.ui import tasks as task_ui

TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
RADIUS = 14
LOGO_PNG = "trackr-icon.png"
LOGO_ICO = "trackr-icon.ico"
TIME_DISPLAY_HMS = "hms"
TIME_DISPLAY_HUMAN = "human"
TIME_DISPLAY_MINUTES = "minutes"
TIME_DISPLAY_FORMATS = {TIME_DISPLAY_HMS, TIME_DISPLAY_HUMAN, TIME_DISPLAY_MINUTES}
TASK_SORT_NAME = "name"
TASK_SORT_TIME_DESC = "time_desc"
TASK_SORT_STATUS = "status"
TASK_SORTS = {TASK_SORT_NAME, TASK_SORT_TIME_DESC, TASK_SORT_STATUS}

# Fixed-order categorical palette: colors follow entities, not their rank.
CATEGORICAL_LIGHT = ["#2a78d6", "#1baf7a", "#eda100", "#008300", "#4a3aa7", "#e34948", "#e87ba4", "#eb6834"]
CATEGORICAL_DARK = ["#3987e5", "#199e70", "#c98500", "#008300", "#9085e9", "#e66767", "#d55181", "#d95926"]
SEQUENTIAL_LIGHT = "#2a78d6"
SEQUENTIAL_DARK = "#3987e5"


def format_duration(total_seconds: int) -> str:
    total_seconds = max(0, int(total_seconds))
    h, rem = divmod(total_seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_duration_short(total_seconds: int) -> str:
    total_seconds = max(0, int(total_seconds))
    h, rem = divmod(total_seconds, 3600)
    m = rem // 60
    return f"{h:02d}:{m:02d}"


def format_duration_display(total_seconds: int | float, display_format: str) -> str:
    total_seconds = max(0, int(total_seconds))
    if display_format == TIME_DISPLAY_MINUTES:
        return f"{total_seconds // 60} min"
    if display_format == TIME_DISPLAY_HUMAN:
        h, rem = divmod(total_seconds, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}h{m:02d}"
        if m:
            return f"{m} min"
        return f"{s} s"
    return format_duration(total_seconds)


def parse_estimated_seconds(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    if not value.isdigit():
        raise ValueError("invalid_estimate") from None
    return int(value) * 60


def format_estimated_minutes(total_seconds: int | None) -> str:
    if total_seconds is None:
        return ""
    return str(max(0, int(total_seconds)) // 60)


def normalize_tags(value: str) -> str:
    tags = []
    seen = set()
    for raw_tag in value.replace(";", ",").split(","):
        tag = raw_tag.strip().lstrip("#")
        if tag and tag.lower() not in seen:
            seen.add(tag.lower())
            tags.append(tag)
    return ", ".join(tags)


def split_tags(value: str | None) -> list[str]:
    return [tag.strip().lstrip("#") for tag in (value or "").split(",") if tag.strip().lstrip("#")]


def initials(name: str) -> str:
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


class TrackrApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.lang = db.get_setting("language", "fr")
        self.theme_mode_value = db.get_setting("theme_mode", "light")
        self.time_display_format = db.get_setting("time_display_format", TIME_DISPLAY_HMS)
        if self.time_display_format not in TIME_DISPLAY_FORMATS:
            self.time_display_format = TIME_DISPLAY_HMS
        self.task_sort_value = db.get_setting("task_sort", TASK_SORT_NAME)
        if self.task_sort_value not in TASK_SORTS:
            self.task_sort_value = TASK_SORT_NAME
        self.compact_mode = db.get_setting("compact_mode", "0") == "1"

        self.selected_project_id: int | None = None
        self.tasks: list = []
        self.running: dict | None = None
        self.analytics_days = 14
        self.project_search_query = ""
        self.task_search_query = ""

        self.projects_list = ft.ListView(expand=True, spacing=6)
        self.tasks_list = ft.ListView(expand=True, spacing=6 if self.compact_mode else 10)
        self.brand_text = ft.Text(size=16, weight=ft.FontWeight.BOLD)
        self.breadcrumb_text = ft.Text(size=15, weight=ft.FontWeight.W_600, color=ft.Colors.ON_SURFACE)
        self.appbar_today_text = ft.Text(size=13, weight=ft.FontWeight.W_600, color=ft.Colors.ON_SURFACE_VARIANT)
        self.project_search_field = ft.TextField(
            dense=True,
            filled=True,
            border_radius=10,
            prefix_icon=ft.Icons.SEARCH_ROUNDED,
            on_change=self.on_project_search_change,
        )
        self.task_search_field = ft.TextField(
            dense=True,
            filled=True,
            border_radius=10,
            prefix_icon=ft.Icons.SEARCH_ROUNDED,
            on_change=self.on_task_search_change,
        )
        self.task_sort_controls = ft.Row(spacing=6, wrap=True)
        self.compact_mode_switch = ft.Checkbox(
            value=self.compact_mode,
            scale=0.9,
            on_change=self.on_compact_mode_change,
        )
        self.project_title = ft.Text(size=24, weight=ft.FontWeight.BOLD)
        self.project_avatar = ft.CircleAvatar(radius=24, content=ft.Icon(ft.Icons.FOLDER_OUTLINED))
        self.projects_header = ft.Text(size=13, weight=ft.FontWeight.BOLD)
        self.summary_today_label = ft.Text(size=11, color=ft.Colors.ON_SECONDARY_CONTAINER)
        self.summary_today_value = ft.Text(size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_SECONDARY_CONTAINER)
        self.summary_week_label = ft.Text(size=11, color=ft.Colors.ON_SECONDARY_CONTAINER)
        self.summary_week_value = ft.Text(size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_SECONDARY_CONTAINER)

        self.new_project_field = ft.TextField(
            dense=True,
            expand=True,
            filled=True,
            border_radius=10,
            on_submit=self.on_add_project,
            on_change=self._clear_new_project_error,
        )
        self.new_task_field = ft.TextField(
            dense=True,
            expand=True,
            filled=True,
            width=130,
            border_radius=10,
            label="",
            on_submit=self.on_add_task,
            on_change=self._clear_new_task_error,
        )
        self.new_task_estimate_field = ft.TextField(
            dense=True,
            filled=True,
            width=145,
            border_radius=10,
            on_submit=self.on_add_task,
            on_change=self._clear_new_task_error,
        )
        self.new_task_tags_field = ft.TextField(
            dense=True,
            filled=True,
            width=165,
            border_radius=10,
            on_submit=self.on_add_task,
            on_change=self._clear_new_task_error,
        )

        self._build_page()
        self.apply_texts()
        self.refresh_projects()

        self.scheduler = ReminderScheduler()
        try:
            self.scheduler.start()
        except Exception:
            pass

        self._route_startup()

    def _route_startup(self) -> None:
        if db.get_setting("onboarding_done") != "1":
            self.show_onboarding()
        elif db.get_setting("auth_password_hash"):
            self.show_lock()
        else:
            self.show_main()

    # ---------- layout ----------

    def _build_page(self) -> None:
        self.page.title = t("app_title", self.lang)
        self.page.theme = ft.Theme(color_scheme_seed=ft.Colors.INDIGO, use_material3=True)
        self.page.dark_theme = ft.Theme(color_scheme_seed=ft.Colors.INDIGO, use_material3=True)
        self.page.theme_mode = ft.ThemeMode.DARK if self.theme_mode_value == "dark" else ft.ThemeMode.LIGHT
        self.page.padding = 0
        self.page.window.width = 1250
        self.page.window.height = 800
        self.page.window.min_width = 620
        self.page.window.min_height = 520
        self.page.window.prevent_close = True
        self.page.window.on_event = self.on_window_event
        self.page.window.icon = str(asset_path(LOGO_ICO))

        self.analytics_btn = ft.IconButton(
            icon=ft.Icons.INSIGHTS_ROUNDED, icon_color=ft.Colors.ON_SURFACE_VARIANT, on_click=lambda e: self.show_analytics()
        )
        self.export_btn = ft.IconButton(
            icon=ft.Icons.DOWNLOAD_ROUNDED, icon_color=ft.Colors.ON_SURFACE_VARIANT, on_click=self.on_export_csv
        )
        self.settings_btn = ft.IconButton(
            icon=ft.Icons.SETTINGS_ROUNDED, icon_color=ft.Colors.ON_SURFACE_VARIANT, on_click=lambda e: self.show_settings()
        )
        self.page.appbar = ft.AppBar(
            title=self.breadcrumb_text,
            center_title=False,
            bgcolor=ft.Colors.SURFACE,
            color=ft.Colors.ON_SURFACE,
            actions=[
                self.appbar_today_text,
                self.analytics_btn,
                self.export_btn,
                self.settings_btn,
                ft.Container(width=8),
            ],
        )

        self.file_picker = ft.FilePicker()
        self.page.services.append(self.file_picker)
        self.clipboard = ft.Clipboard()
        self.page.services.append(self.clipboard)

        self.main_row = self._build_main_view()
        self.content_host = ft.Container(expand=True, content=self.main_row)
        self.page.add(
            ft.Column(
                [
                    ft.Container(height=1, bgcolor=ft.Colors.OUTLINE_VARIANT),
                    self.content_host,
                ],
                spacing=0,
                expand=True,
            )
        )

    def _build_main_view(self) -> ft.Row:
        return main_view.build(self)

    def _stat_chip(self, icon: str, label: ft.Text, value: ft.Text) -> ft.Container:
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=12, vertical=7),
            border_radius=10,
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
            content=ft.Row(
                [
                    ft.Icon(icon, size=17, color=ft.Colors.ON_SECONDARY_CONTAINER),
                    ft.Column([label, value], spacing=0, tight=True),
                ],
                spacing=8,
                tight=True,
            ),
        )

    def _empty_state(self, icon: str, message: str) -> ft.Container:
        return ft.Container(
            padding=30,
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                [
                    ft.Icon(icon, size=42, color=ft.Colors.OUTLINE),
                    ft.Text(message, color=ft.Colors.OUTLINE, text_align=ft.TextAlign.CENTER, size=13),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
            ),
        )

    def _task_status_label(self, task_status: str) -> str:
        return t(f"task_status_{task_status}", self.lang)

    def _task_status_color(self, task_status: str) -> str:
        if task_status == db.TASK_STATUS_DONE:
            return ft.Colors.GREEN
        if task_status == db.TASK_STATUS_IN_PROGRESS:
            return ft.Colors.BLUE
        return ft.Colors.OUTLINE

    def _task_status_chip(self, task_status: str) -> ft.Container:
        color = self._task_status_color(task_status)
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=8, vertical=3),
            border_radius=999,
            border=ft.Border.all(1, color),
            content=ft.Text(self._task_status_label(task_status), size=11, color=color),
        )

    def _task_duration_summary(self, actual_seconds: int | float, estimated_seconds: int | None) -> str:
        actual = self._format_duration(actual_seconds)
        planned = self._format_duration(estimated_seconds) if estimated_seconds else "--:--:--"
        return f"{actual} / {planned}"

    def _task_duration_font_size(self, estimated_seconds: int | None) -> int:
        return 13

    def _format_duration(self, total_seconds: int | float) -> str:
        return format_duration_display(total_seconds, self.time_display_format)

    def _tag_chips(self, tags_text: str, compact: bool = False) -> ft.Row:
        chips = [
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=7, vertical=2),
                border_radius=999,
                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                content=ft.Text(f"#{tag}", size=10 if compact else 11, color=ft.Colors.ON_SURFACE_VARIANT),
            )
            for tag in split_tags(tags_text)
        ]
        return ft.Row(chips, spacing=5, wrap=True)

    def _projects_breadcrumb(self) -> str:
        lang = self.lang
        if self.selected_project_id is None:
            return t("projects", lang)
        return f"{t('projects', lang)} › {self.project_title.value}"

    def apply_texts(self) -> None:
        lang = self.lang
        self.brand_text.value = t("app_title", lang)
        self.breadcrumb_text.value = self._projects_breadcrumb()
        self.analytics_btn.tooltip = t("analytics", lang)
        self.export_btn.tooltip = t("export_csv", lang)
        self.settings_btn.tooltip = t("settings", lang)
        self.appbar_today_text.value = t("global_today", lang, duration=self._format_duration(db.get_day_total()))
        self.projects_header.value = t("projects", lang).upper()
        self.new_project_field.label = t("new_project", lang)
        self.new_task_field.label = t("new_task", lang)
        self.new_task_estimate_field.label = t("estimated_time", lang)
        self.new_task_estimate_field.hint_text = t("estimated_time_hint", lang)
        self.new_task_tags_field.label = t("tags", lang)
        self.new_task_tags_field.hint_text = t("tags_hint", lang)
        self.project_search_field.label = t("search_projects", lang)
        self.task_search_field.label = t("search_tasks", lang)
        self._refresh_task_sort_controls()
        self.compact_mode_switch.label = t("compact_mode", lang)
        self.summary_today_label.value = t("today", lang)
        self.summary_week_label.value = t("this_week", lang)
        if self.selected_project_id is None:
            self.project_title.value = t("select_project", lang)
        self.page.update()

    def _refresh_task_sort_controls(self) -> None:
        labels = {
            TASK_SORT_NAME: t("task_sort_name", self.lang),
            TASK_SORT_TIME_DESC: t("task_sort_time", self.lang),
            TASK_SORT_STATUS: t("task_sort_status", self.lang),
        }
        controls = [ft.Text(t("task_sort", self.lang), size=12, color=ft.Colors.ON_SURFACE_VARIANT)]
        for sort_value in (TASK_SORT_NAME, TASK_SORT_TIME_DESC, TASK_SORT_STATUS):
            selected = self.task_sort_value == sort_value
            controls.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=10, vertical=5),
                    border_radius=999,
                    bgcolor=ft.Colors.PRIMARY_CONTAINER if selected else ft.Colors.SURFACE_CONTAINER_HIGH,
                    border=ft.Border.all(1, ft.Colors.PRIMARY if selected else ft.Colors.OUTLINE_VARIANT),
                    ink=True,
                    on_click=lambda e, value=sort_value: self.set_task_sort(value),
                    content=ft.Text(
                        labels[sort_value],
                        size=12,
                        weight=ft.FontWeight.W_600 if selected else ft.FontWeight.NORMAL,
                        color=ft.Colors.ON_PRIMARY_CONTAINER if selected else ft.Colors.ON_SURFACE_VARIANT,
                    ),
                )
            )
        self.task_sort_controls.controls = controls

    def show_settings(self) -> None:
        self.page.appbar.visible = True
        self.page.appbar.leading = ft.IconButton(icon=ft.Icons.ARROW_BACK_ROUNDED, on_click=lambda e: self.show_main())
        self.breadcrumb_text.value = t("settings", self.lang)
        self.content_host.content = self._build_settings_view()
        self.page.update()

    def show_main(self) -> None:
        self.page.appbar.visible = True
        self.page.appbar.leading = None
        self.breadcrumb_text.value = self._projects_breadcrumb()
        self.content_host.content = self.main_row
        self.page.update()

    def show_analytics(self) -> None:
        self.page.appbar.visible = True
        self.page.appbar.leading = ft.IconButton(icon=ft.Icons.ARROW_BACK_ROUNDED, on_click=lambda e: self.show_main())
        self.breadcrumb_text.value = t("analytics", self.lang)
        self.content_host.content = self._build_analytics_view()
        self.page.update()

    def show_onboarding(self) -> None:
        self.page.appbar.visible = False
        self.content_host.content = self._build_onboarding_view()
        self.page.update()

    def show_lock(self) -> None:
        self._lock_mode = "password"
        self.page.appbar.visible = False
        self.content_host.content = self._build_lock_view()
        self.page.update()

    # ---------- onboarding / locking ----------

    def _auth_card(self, *controls) -> ft.Container:
        return ft.Container(
            expand=True,
            alignment=ft.Alignment.CENTER,
            content=ft.Container(
                width=420,
                padding=30,
                border_radius=RADIUS,
                bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Image(src=LOGO_PNG, width=32, height=32, border_radius=8, fit=ft.BoxFit.COVER),
                                ft.Text(t("app_title", self.lang), size=20, weight=ft.FontWeight.BOLD),
                            ],
                            spacing=10,
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                        *controls,
                    ],
                    spacing=16,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ),
        )

    def _show_recovery_code_dialog(self, code: str, on_close) -> None:
        lang = self.lang

        async def copy_code(e):
            await self.clipboard.set(code)
            self.page.show_dialog(ft.SnackBar(ft.Text(t("copied", lang))))

        def close(e):
            self.page.pop_dialog()
            on_close()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(t("recovery_code_title", lang)),
            content=ft.Column(
                [
                    ft.Text(t("recovery_code_body", lang), width=340),
                    ft.Row(
                        [
                            ft.Container(
                                padding=14,
                                border_radius=10,
                                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
                                expand=True,
                                alignment=ft.Alignment.CENTER,
                                content=ft.SelectionArea(
                                    content=ft.Text(code, size=18, weight=ft.FontWeight.BOLD, font_family="Consolas")
                                ),
                            ),
                            ft.IconButton(icon=ft.Icons.COPY_ROUNDED, tooltip=t("copy", lang), on_click=copy_code),
                        ],
                        spacing=8,
                    ),
                ],
                tight=True,
                spacing=14,
            ),
            actions=[ft.FilledButton(content=t("recovery_code_confirm", lang), on_click=close)],
        )
        self.page.show_dialog(dialog)

    def _build_onboarding_view(self) -> ft.Control:
        lang = self.lang
        username_field = ft.TextField(label=t("username", lang), value="user")
        password_checkbox = ft.Checkbox(label=t("protect_with_password", lang), value=False)
        password_field = ft.TextField(
            label=t("password", lang), password=True, can_reveal_password=True, visible=False
        )
        confirm_field = ft.TextField(
            label=t("confirm_password", lang), password=True, can_reveal_password=True, visible=False
        )
        error_text = ft.Text("", color=ft.Colors.ERROR)

        def toggle_password(e):
            password_field.visible = password_checkbox.value
            confirm_field.visible = password_checkbox.value
            password_field.update()
            confirm_field.update()

        password_checkbox.on_change = toggle_password

        def submit(e):
            username = (username_field.value or "").strip() or "user"
            db.set_setting("username", username)
            db.set_setting("onboarding_done", "1")
            if password_checkbox.value:
                pwd = password_field.value or ""
                if len(pwd) < 4:
                    error_text.value = t("password_too_short", lang)
                    error_text.update()
                    return
                if pwd != (confirm_field.value or ""):
                    error_text.value = t("password_mismatch", lang)
                    error_text.update()
                    return
                salt_hex, hash_hex = auth.hash_secret(pwd)
                db.set_setting("auth_password_salt", salt_hex)
                db.set_setting("auth_password_hash", hash_hex)
                recovery_code = auth.generate_recovery_code()
                r_salt, r_hash = auth.hash_secret(recovery_code)
                db.set_setting("auth_recovery_salt", r_salt)
                db.set_setting("auth_recovery_hash", r_hash)
                self._show_recovery_code_dialog(recovery_code, self.show_main)
            else:
                self.show_main()

        return self._auth_card(
            ft.Text(t("onboarding_welcome", lang), size=14, color=ft.Colors.OUTLINE, text_align=ft.TextAlign.CENTER),
            username_field,
            password_checkbox,
            password_field,
            confirm_field,
            error_text,
            ft.FilledButton(
                content=t("continue", lang), icon=ft.Icons.ARROW_FORWARD_ROUNDED, on_click=submit, height=48
            ),
        )

    def _build_lock_view(self) -> ft.Control:
        lang = self.lang
        mode = getattr(self, "_lock_mode", "password")
        error_text = ft.Text("", color=ft.Colors.ERROR)

        def go_password(e):
            self._lock_mode = "password"
            self.content_host.content = self._build_lock_view()
            self.page.update()

        def go_recovery(e):
            self._lock_mode = "recovery"
            self.content_host.content = self._build_lock_view()
            self.page.update()

        if mode == "recovery":
            recovery_field = ft.TextField(label=t("recovery_code", lang))
            new_password_field = ft.TextField(label=t("new_password", lang), password=True, can_reveal_password=True)
            confirm_field = ft.TextField(
                label=t("confirm_password", lang), password=True, can_reveal_password=True
            )

            def do_reset(e):
                code = (recovery_field.value or "").strip().upper()
                if not auth.verify_secret(
                    code, db.get_setting("auth_recovery_salt", ""), db.get_setting("auth_recovery_hash", "")
                ):
                    error_text.value = t("wrong_recovery_code", lang)
                    error_text.update()
                    return
                new_pwd = new_password_field.value or ""
                if len(new_pwd) < 4:
                    error_text.value = t("password_too_short", lang)
                    error_text.update()
                    return
                if new_pwd != (confirm_field.value or ""):
                    error_text.value = t("password_mismatch", lang)
                    error_text.update()
                    return
                salt_hex, hash_hex = auth.hash_secret(new_pwd)
                db.set_setting("auth_password_salt", salt_hex)
                db.set_setting("auth_password_hash", hash_hex)
                new_code = auth.generate_recovery_code()
                r_salt, r_hash = auth.hash_secret(new_code)
                db.set_setting("auth_recovery_salt", r_salt)
                db.set_setting("auth_recovery_hash", r_hash)
                self._show_recovery_code_dialog(new_code, self.show_main)

            body = [
                recovery_field,
                new_password_field,
                confirm_field,
                error_text,
                ft.FilledButton(content=t("reset_password", lang), on_click=do_reset, height=48),
                ft.TextButton(content=t("back", lang), on_click=go_password),
            ]
        else:
            password_field = ft.TextField(label=t("password", lang), password=True, can_reveal_password=True)

            def try_unlock(e):
                if auth.verify_secret(
                    password_field.value or "", db.get_setting("auth_password_salt", ""), db.get_setting("auth_password_hash", "")
                ):
                    self.show_main()
                else:
                    error_text.value = t("wrong_password", lang)
                    error_text.update()

            password_field.on_submit = try_unlock

            body = [
                ft.Icon(ft.Icons.LOCK_ROUNDED, size=36, color=ft.Colors.PRIMARY),
                password_field,
                error_text,
                ft.FilledButton(content=t("unlock", lang), on_click=try_unlock, height=48),
                ft.TextButton(content=t("forgot_password", lang), on_click=go_recovery),
            ]

        return self._auth_card(*body)

    def _open_set_password_dialog(self, require_current: bool) -> None:
        lang = self.lang
        current_field = (
            ft.TextField(label=t("current_password", lang), password=True, can_reveal_password=True)
            if require_current
            else None
        )
        new_field = ft.TextField(label=t("new_password", lang), password=True, can_reveal_password=True)
        confirm_field = ft.TextField(label=t("confirm_password", lang), password=True, can_reveal_password=True)
        error_text = ft.Text("", color=ft.Colors.ERROR)

        def save(e):
            if require_current and not auth.verify_secret(
                current_field.value or "", db.get_setting("auth_password_salt", ""), db.get_setting("auth_password_hash", "")
            ):
                error_text.value = t("wrong_password", lang)
                error_text.update()
                return
            new_pwd = new_field.value or ""
            if len(new_pwd) < 4:
                error_text.value = t("password_too_short", lang)
                error_text.update()
                return
            if new_pwd != (confirm_field.value or ""):
                error_text.value = t("password_mismatch", lang)
                error_text.update()
                return
            salt_hex, hash_hex = auth.hash_secret(new_pwd)
            db.set_setting("auth_password_salt", salt_hex)
            db.set_setting("auth_password_hash", hash_hex)
            recovery_code = auth.generate_recovery_code()
            r_salt, r_hash = auth.hash_secret(recovery_code)
            db.set_setting("auth_recovery_salt", r_salt)
            db.set_setting("auth_recovery_hash", r_hash)
            self.page.pop_dialog()
            self._show_recovery_code_dialog(recovery_code, self.show_settings)

        fields = ([current_field] if require_current else []) + [new_field, confirm_field, error_text]
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(t("set_password_title", lang)),
            content=ft.Column(fields, tight=True, spacing=10),
            actions=[
                ft.TextButton(content=t("cancel", lang), on_click=lambda e: self.page.pop_dialog()),
                ft.FilledButton(content=t("save", lang), on_click=save),
            ],
        )
        self.page.show_dialog(dialog)

    def _open_disable_lock_dialog(self) -> None:
        lang = self.lang
        current_field = ft.TextField(label=t("current_password", lang), password=True, can_reveal_password=True)
        error_text = ft.Text("", color=ft.Colors.ERROR)

        def confirm(e):
            if not auth.verify_secret(
                current_field.value or "", db.get_setting("auth_password_salt", ""), db.get_setting("auth_password_hash", "")
            ):
                error_text.value = t("wrong_password", lang)
                error_text.update()
                return
            db.set_setting("auth_password_hash", "")
            db.set_setting("auth_password_salt", "")
            db.set_setting("auth_recovery_hash", "")
            db.set_setting("auth_recovery_salt", "")
            self.page.pop_dialog()
            self.show_settings()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(t("disable_lock_title", lang)),
            content=ft.Column(
                [ft.Text(t("disable_lock_body", lang), width=320), current_field, error_text], tight=True, spacing=10
            ),
            actions=[
                ft.TextButton(content=t("cancel", lang), on_click=lambda e: self.page.pop_dialog()),
                ft.FilledButton(
                    content=t("confirm", lang),
                    on_click=confirm,
                    style=ft.ButtonStyle(bgcolor=ft.Colors.RED_600, color=ft.Colors.WHITE),
                ),
            ],
        )
        self.page.show_dialog(dialog)

    def _settings_section(self, icon: str, title: str, controls: list) -> ft.Card:
        return ft.Card(
            elevation=0,
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            content=ft.Container(
                padding=20,
                content=ft.Column(
                    [
                        ft.Row(
                            [ft.Icon(icon, color=ft.Colors.PRIMARY), ft.Text(title, size=15, weight=ft.FontWeight.BOLD)],
                            spacing=10,
                        ),
                        ft.Divider(height=1, color=ft.Colors.OUTLINE_VARIANT),
                        *controls,
                    ],
                    spacing=14,
                ),
            ),
        )

    def _settings_hint(self, text: str) -> ft.Text:
        return ft.Text(text, size=12, color=ft.Colors.OUTLINE)

    def _build_settings_view(self) -> ft.Container:
        return settings_ui.build(self)

    # ---------- analytics dashboard ----------

    def _categorical_color(self, key) -> str:
        palette = CATEGORICAL_DARK if self.theme_mode_value == "dark" else CATEGORICAL_LIGHT
        return palette[hash(key) % len(palette)]

    def _sequential_color(self) -> str:
        return SEQUENTIAL_DARK if self.theme_mode_value == "dark" else SEQUENTIAL_LIGHT

    def _build_daily_chart(self, project_id: int) -> ft.Control:
        return analytics_ui.build_daily_chart(self, project_id)

    def _build_ranked_bars(self, rows: list, name_key: str, color_key_fn) -> ft.Control:
        return analytics_ui.build_ranked_bars(self, rows, name_key, color_key_fn)

    def _build_analytics_view(self) -> ft.Container:
        return analytics_ui.build(self)

    # ---------- confirmation helper ----------

    def _confirm(self, title: str, body: str, on_confirm) -> None:
        def confirm_click(e):
            self.page.pop_dialog()
            on_confirm()

        def cancel_click(e):
            self.page.pop_dialog()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(title),
            content=ft.Text(body),
            actions=[
                ft.TextButton(content=t("cancel", self.lang), on_click=cancel_click),
                ft.FilledButton(
                    content=t("confirm", self.lang),
                    on_click=confirm_click,
                    style=ft.ButtonStyle(bgcolor=ft.Colors.RED_600, color=ft.Colors.WHITE),
                ),
            ],
        )
        self.page.show_dialog(dialog)

    # ---------- projects ----------

    def _project_row(self, project) -> ft.Container:
        selected = project["id"] == self.selected_project_id
        return ft.Container(
            border_radius=RADIUS,
            padding=ft.Padding.symmetric(horizontal=10, vertical=8),
            bgcolor=ft.Colors.PRIMARY_CONTAINER if selected else None,
            ink=True,
            on_click=lambda e, pid=project["id"]: self.select_project(pid),
            content=ft.Row(
                [
                    ft.CircleAvatar(
                        content=ft.Text(initials(project["name"]), size=13, weight=ft.FontWeight.BOLD),
                        bgcolor=ft.Colors.ON_PRIMARY_CONTAINER if selected else ft.Colors.PRIMARY,
                        color=ft.Colors.PRIMARY_CONTAINER if selected else ft.Colors.ON_PRIMARY,
                        radius=16,
                    ),
                    ft.Text(
                        project["name"],
                        weight=ft.FontWeight.W_600 if selected else ft.FontWeight.NORMAL,
                        color=ft.Colors.ON_PRIMARY_CONTAINER if selected else ft.Colors.ON_SURFACE,
                        expand=True,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE,
                        icon_size=16,
                        icon_color=ft.Colors.ON_PRIMARY_CONTAINER if selected else ft.Colors.OUTLINE,
                        tooltip=t("delete", self.lang),
                        on_click=lambda e, pid=project["id"]: self.on_delete_project(pid),
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def _render_projects_list(self, projects) -> None:
        query = self.project_search_query.strip().lower()
        filtered = [p for p in projects if query in p["name"].lower()] if query else projects

        self.projects_list.controls.clear()
        if not filtered:
            message = t("no_search_results", self.lang) if query else t("no_projects", self.lang)
            self.projects_list.controls.append(self._empty_state(ft.Icons.FOLDER_OFF_OUTLINED, message))
            return
        for p in filtered:
            self.projects_list.controls.append(self._project_row(p))

    def on_project_search_change(self, e) -> None:
        self.project_search_query = self.project_search_field.value or ""
        self._render_projects_list(db.list_projects())
        self.page.update()

    def refresh_projects(self) -> None:
        projects = db.list_projects()
        if self.selected_project_id is None and projects:
            self.selected_project_id = projects[0]["id"]
        if self.selected_project_id is not None and not any(p["id"] == self.selected_project_id for p in projects):
            self.selected_project_id = None

        if self.selected_project_id is not None:
            self.select_project(self.selected_project_id)
            return

        self._render_projects_list(projects)
        self.project_title.value = t("select_project", self.lang)
        self.project_avatar.content = ft.Icon(ft.Icons.FOLDER_OUTLINED)
        self.project_avatar.bgcolor = None
        self.tasks_list.controls.clear()
        self.breadcrumb_text.value = self._projects_breadcrumb()
        self.update_summary()
        self.page.update()

    def _clear_new_project_error(self, e) -> None:
        if self.new_project_field.error:
            self.new_project_field.error = None
            self.new_project_field.update()

    def on_add_project(self, e) -> None:
        name = self.new_project_field.value.strip() if self.new_project_field.value else ""
        if not name:
            return
        existing = db.get_project_by_name(name)
        if existing:
            self.new_project_field.error = t("project_exists", self.lang)
            self.new_project_field.update()
            return
        project_id = db.add_project(name)
        self.new_project_field.value = ""
        self.new_project_field.error = None
        self.selected_project_id = project_id
        self.refresh_projects()

    def on_delete_project(self, project_id: int) -> None:
        def do_delete():
            if self.running and self.running["project_id"] == project_id:
                self.stop_running()
            db.delete_project(project_id)
            if self.selected_project_id == project_id:
                self.selected_project_id = None
            self.refresh_projects()

        self._confirm(
            t("confirm_delete_project_title", self.lang),
            t("confirm_delete_project_body", self.lang),
            do_delete,
        )

    def select_project(self, project_id: int) -> None:
        if project_id != self.selected_project_id:
            self.task_search_field.value = ""
            self.task_search_query = ""
        self.selected_project_id = project_id
        projects = db.list_projects()
        project = next((p for p in projects if p["id"] == project_id), None)
        self._render_projects_list(projects)
        if project:
            self.project_title.value = project["name"]
            self.project_avatar.content = ft.Text(initials(project["name"]), size=18, weight=ft.FontWeight.BOLD)
            self.project_avatar.bgcolor = ft.Colors.PRIMARY
            self.project_avatar.color = ft.Colors.ON_PRIMARY
        self.breadcrumb_text.value = self._projects_breadcrumb()
        self.new_task_field.error = None
        self.refresh_tasks()
        self.update_summary()
        self.page.update()

    # ---------- tasks ----------

    def _task_card(self, task_row) -> ft.Card:
        return task_ui.build_task_card(self, task_row)

    def refresh_tasks(self) -> None:
        if self.selected_project_id is None:
            self.tasks_list.controls.clear()
            self.page.update()
            return

        self.tasks = db.list_tasks(self.selected_project_id)
        self.tasks_list.controls.clear()

        query = self.task_search_query.strip().lower()
        filtered = [
            t_row
            for t_row in self.tasks
            if query in t_row["task_name"].lower() or query in (t_row["task_tags"] or "").lower()
        ] if query else self.tasks
        status_order = {
            db.TASK_STATUS_IN_PROGRESS: 0,
            db.TASK_STATUS_PENDING: 1,
            db.TASK_STATUS_DONE: 2,
        }
        if self.task_sort_value == TASK_SORT_TIME_DESC:
            filtered = sorted(filtered, key=lambda row: (-(row["total_seconds"] or 0), row["task_name"].lower()))
        elif self.task_sort_value == TASK_SORT_STATUS:
            filtered = sorted(
                filtered,
                key=lambda row: (status_order.get(row["task_status"] or db.TASK_STATUS_PENDING, 9), row["task_name"].lower()),
            )
        else:
            filtered = sorted(filtered, key=lambda row: row["task_name"].lower())

        if not filtered:
            message = t("no_search_results", self.lang) if query else t("no_tasks", self.lang)
            self.tasks_list.controls.append(self._empty_state(ft.Icons.CHECKLIST_RTL_ROUNDED, message))
        else:
            for task_row in filtered:
                self.tasks_list.controls.append(self._task_card(task_row))
        self.page.update()

    def on_task_search_change(self, e) -> None:
        self.task_search_query = self.task_search_field.value or ""
        self.refresh_tasks()

    def set_task_sort(self, sort_value: str) -> None:
        self.task_sort_value = sort_value if sort_value in TASK_SORTS else TASK_SORT_NAME
        db.set_setting("task_sort", self.task_sort_value)
        self._refresh_task_sort_controls()
        self.refresh_tasks()

    def on_compact_mode_change(self, e) -> None:
        self.compact_mode = bool(self.compact_mode_switch.value)
        db.set_setting("compact_mode", "1" if self.compact_mode else "0")
        self.tasks_list.spacing = 6 if self.compact_mode else 10
        self.refresh_tasks()

    def _clear_new_task_error(self, e) -> None:
        if self.new_task_field.error:
            self.new_task_field.error = None
            self.new_task_field.update()
        if self.new_task_estimate_field.error:
            self.new_task_estimate_field.error = None
            self.new_task_estimate_field.update()
        if self.new_task_tags_field.error:
            self.new_task_tags_field.error = None
            self.new_task_tags_field.update()

    def on_add_task(self, e) -> None:
        if self.selected_project_id is None:
            return
        name = self.new_task_field.value.strip() if self.new_task_field.value else ""
        if not name:
            return
        if db.get_task_by_name(self.selected_project_id, name):
            self.new_task_field.error = t("task_exists", self.lang)
            self.new_task_field.update()
            return
        try:
            estimated_seconds = parse_estimated_seconds(self.new_task_estimate_field.value or "")
        except ValueError:
            self.new_task_estimate_field.error = t("invalid_estimated_time", self.lang)
            self.new_task_estimate_field.update()
            return
        task_tags = normalize_tags(self.new_task_tags_field.value or "")
        db.add_task(self.selected_project_id, name, estimated_seconds=estimated_seconds, task_tags=task_tags)
        self.new_task_field.value = ""
        self.new_task_field.error = None
        self.new_task_estimate_field.value = ""
        self.new_task_estimate_field.error = None
        self.new_task_tags_field.value = ""
        self.new_task_tags_field.error = None
        self.refresh_tasks()

    def on_edit_task(self, task_name: str) -> None:
        """Open the full task editor and synchronize its metadata.

        A task is represented by multiple `timespent` rows in the database, so
        any change to its name, status, estimate, or tags must be propagated to
        all sessions that share this task name.
        """
        metadata = db.get_task_metadata(self.selected_project_id, task_name)
        current_status = metadata["task_status"] if metadata else db.TASK_STATUS_PENDING
        current_estimate = metadata["estimated_seconds"] if metadata else None
        current_tags = metadata["task_tags"] if metadata else ""
        name_field = ft.TextField(label=t("new_name", self.lang), value=task_name)
        status_dropdown = ft.Dropdown(
            label=t("task_status", self.lang),
            value=current_status,
            options=[
                ft.dropdown.Option(key=db.TASK_STATUS_PENDING, text=t("task_status_pending", self.lang)),
                ft.dropdown.Option(key=db.TASK_STATUS_IN_PROGRESS, text=t("task_status_in_progress", self.lang)),
                ft.dropdown.Option(key=db.TASK_STATUS_DONE, text=t("task_status_done", self.lang)),
            ],
        )
        estimate_field = ft.TextField(
            label=t("estimated_time", self.lang),
            value=format_estimated_minutes(current_estimate),
            hint_text=t("estimated_time_hint", self.lang),
        )
        tags_field = ft.TextField(
            label=t("tags", self.lang),
            value=current_tags,
            hint_text=t("tags_hint", self.lang),
        )
        error_text = ft.Text("", color=ft.Colors.ERROR)

        def save(e):
            new_name = (name_field.value or "").strip()
            if not new_name:
                self.page.pop_dialog()
                return
            if new_name != task_name and db.get_task_by_name(self.selected_project_id, new_name):
                error_text.value = t("task_exists", self.lang)
                error_text.update()
                return
            try:
                estimated_seconds = parse_estimated_seconds(estimate_field.value or "")
            except ValueError:
                error_text.value = t("invalid_estimated_time", self.lang)
                error_text.update()
                return
            if new_name != task_name:
                db.rename_task(self.selected_project_id, task_name, new_name)
            db.update_task_metadata(
                self.selected_project_id,
                new_name,
                status_dropdown.value,
                estimated_seconds,
                normalize_tags(tags_field.value or ""),
            )
            if (
                self.running
                and self.running["project_id"] == self.selected_project_id
                and self.running["task_name"] == task_name
            ):
                self.running["task_name"] = new_name
            self.page.pop_dialog()
            self.refresh_tasks()

        def cancel(e):
            self.page.pop_dialog()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(t("edit_task_title", self.lang)),
            content=ft.Column(
                [
                    name_field,
                    status_dropdown,
                    estimate_field,
                    tags_field,
                    error_text,
                ],
                tight=True,
                spacing=8,
            ),
            actions=[
                ft.TextButton(content=t("cancel", self.lang), on_click=cancel),
                ft.FilledButton(content=t("save", self.lang), on_click=save),
            ],
        )
        self.page.show_dialog(dialog)

    def on_rename_task(self, task_name: str) -> None:
        self.on_edit_task(task_name)

    def _duplicate_task_name(self, task_name: str) -> str:
        base_name = f"{task_name} {t('duplicate_suffix', self.lang)}"
        candidate = base_name
        index = 2
        while db.get_task_by_name(self.selected_project_id, candidate):
            candidate = f"{base_name} {index}"
            index += 1
        return candidate

    def on_duplicate_task(self, task_name: str) -> None:
        if self.selected_project_id is None:
            return
        metadata = db.get_task_metadata(self.selected_project_id, task_name)
        if metadata is None:
            return
        new_name = self._duplicate_task_name(task_name)
        db.add_task(
            self.selected_project_id,
            new_name,
            task_status=metadata["task_status"],
            estimated_seconds=metadata["estimated_seconds"],
            task_tags=metadata["task_tags"],
        )
        self.refresh_tasks()

    def on_delete_task(self, task_name: str) -> None:
        def do_delete():
            if (
                self.running
                and self.running["project_id"] == self.selected_project_id
                and self.running["task_name"] == task_name
            ):
                self.stop_running()
            db.delete_task(self.selected_project_id, task_name)
            self.refresh_tasks()
            self.update_summary()

        self._confirm(
            t("confirm_delete_task_title", self.lang),
            t("confirm_delete_task_body", self.lang),
            do_delete,
        )

    def _format_session_date(self, d: date) -> str:
        today = date.today()
        if d == today:
            return t("today", self.lang)
        if d == today - timedelta(days=1):
            return t("yesterday", self.lang)
        return d.strftime("%d/%m/%Y")

    def on_show_history(self, task_name: str) -> None:
        """Display a task's history with sessions grouped by day.

        Grouping is performed in the UI so date separators, daily totals, and
        edit/delete actions can be inserted alongside session rows.
        """
        lang = self.lang
        sessions = db.list_task_sessions(self.selected_project_id, task_name)

        if not sessions:
            content = self._empty_state(ft.Icons.HISTORY_ROUNDED, t("no_sessions", lang))
        else:
            rows: list = []
            current_day = None
            day_rows: list = []
            day_total = 0

            def flush_day():
                if current_day is None:
                    return
                rows.append(
                    ft.Row(
                        [
                            ft.Text(self._format_session_date(current_day), weight=ft.FontWeight.BOLD, size=13),
                            ft.Text(
                                self._format_duration(day_total),
                                size=13,
                                color=ft.Colors.OUTLINE,
                                font_family="Consolas",
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    )
                )
                rows.extend(day_rows)
                rows.append(ft.Divider(height=1, color=ft.Colors.OUTLINE_VARIANT))

            for s in sessions:
                start_dt = datetime.fromisoformat(s["start_time"])
                day = start_dt.date()
                if day != current_day:
                    flush_day()
                    current_day = day
                    day_rows = []
                    day_total = 0
                day_total += s["duration_seconds"] or 0
                if s["end_time"]:
                    end_dt = datetime.fromisoformat(s["end_time"])
                    time_range = f"{start_dt:%H:%M} – {end_dt:%H:%M}"
                    duration_text = self._format_duration(s["duration_seconds"] or 0)
                else:
                    time_range = f"{start_dt:%H:%M} – …"
                    duration_text = t("in_progress", lang)
                session_controls = [
                    ft.Row(
                        [
                            ft.Text(time_range, size=13, color=ft.Colors.OUTLINE),
                            ft.Row(
                                [
                                    ft.Text(duration_text, size=13, font_family="Consolas"),
                                    ft.IconButton(
                                        icon=ft.Icons.EDIT_OUTLINED,
                                        icon_size=15,
                                        tooltip=t("edit_session", lang),
                                        disabled=s["end_time"] is None,
                                        on_click=lambda e, session=s, tn=task_name: self.on_edit_session(tn, session),
                                    ),
                                    ft.IconButton(
                                        icon=ft.Icons.DELETE_OUTLINE,
                                        icon_size=15,
                                        tooltip=t("delete_session", lang),
                                        disabled=s["end_time"] is None,
                                        on_click=lambda e, sid=s["id"], tn=task_name: self.on_delete_session(tn, sid),
                                    ),
                                ],
                                spacing=2,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    )
                ]
                if s["session_note"]:
                    session_controls.append(ft.Text(s["session_note"], size=12, color=ft.Colors.ON_SURFACE_VARIANT))
                day_rows.append(ft.Column(session_controls, spacing=2))
            flush_day()

            content = ft.Container(
                width=380,
                height=420,
                content=ft.Column(rows, spacing=6, scroll=ft.ScrollMode.AUTO),
            )

        def close(e):
            self.page.pop_dialog()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(t("history_title", lang, task=task_name)),
            content=content,
            actions=[ft.TextButton(content=t("close", lang), on_click=close)],
        )
        self.page.show_dialog(dialog)

    def on_edit_session(self, task_name: str, session) -> None:
        """Allow a completed session to be corrected manually.

        Date, start time, and end time are validated together so a consistent
        duration can be calculated before writing the correction to the database.
        """
        if session["end_time"] is None:
            return
        start_dt = datetime.fromisoformat(session["start_time"])
        end_dt = datetime.fromisoformat(session["end_time"])
        date_field = ft.TextField(label=t("session_date", self.lang), value=start_dt.date().isoformat())
        start_field = ft.TextField(label=t("session_start", self.lang), value=start_dt.strftime("%H:%M"))
        end_field = ft.TextField(label=t("session_end", self.lang), value=end_dt.strftime("%H:%M"))
        note_field = ft.TextField(
            label=t("session_note", self.lang),
            value=session["session_note"],
            multiline=True,
            min_lines=3,
            max_lines=5,
        )
        error_text = ft.Text("", color=ft.Colors.ERROR)

        def save(e):
            try:
                session_date = date.fromisoformat((date_field.value or "").strip())
            except ValueError:
                error_text.value = t("invalid_session_date", self.lang)
                error_text.update()
                return
            start_text = (start_field.value or "").strip()
            end_text = (end_field.value or "").strip()
            if not TIME_RE.match(start_text) or not TIME_RE.match(end_text):
                error_text.value = t("invalid_session_time", self.lang)
                error_text.update()
                return
            new_start = datetime.fromisoformat(f"{session_date.isoformat()}T{start_text}:00")
            new_end = datetime.fromisoformat(f"{session_date.isoformat()}T{end_text}:00")
            if new_end <= new_start:
                error_text.value = t("session_end_after_start", self.lang)
                error_text.update()
                return
            duration_seconds = int((new_end - new_start).total_seconds())
            db.update_session(session["id"], new_start.isoformat(), new_end.isoformat(), duration_seconds, note_field.value or "")
            self.page.pop_dialog()
            self.refresh_tasks()
            self.update_summary()
            self.on_show_history(task_name)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(t("edit_session", self.lang)),
            content=ft.Container(
                width=420,
                content=ft.Column(
                    [
                        date_field,
                        start_field,
                        end_field,
                        note_field,
                        error_text,
                    ],
                    tight=True,
                    spacing=10,
                ),
            ),
            actions=[
                ft.TextButton(content=t("cancel", self.lang), on_click=lambda e: self.page.pop_dialog()),
                ft.FilledButton(content=t("save", self.lang), on_click=save),
            ],
        )
        self.page.show_dialog(dialog)

    def on_delete_session(self, task_name: str, session_id: int) -> None:
        def do_delete():
            db.delete_session(session_id)
            self.refresh_tasks()
            self.update_summary()
            self.on_show_history(task_name)

        self._confirm(t("delete_session_title", self.lang), t("delete_session_body", self.lang), do_delete)

    # ---------- summary ----------

    def update_summary(self) -> None:
        if self.selected_project_id is None:
            self.summary_today_value.value = "--"
            self.summary_week_value.value = "--"
        else:
            working_days = db.parse_working_days(db.get_setting("working_days", db.DEFAULT_WORKING_DAYS))
            summary = db.get_summary(self.selected_project_id, working_days)
            self.summary_today_value.value = self._format_duration(summary["today"])
            self.summary_week_value.value = self._format_duration(summary["week"])
        self.appbar_today_text.value = t("global_today", self.lang, duration=self._format_duration(db.get_day_total()))
        self.appbar_today_text.update()
        self.summary_today_value.update()
        self.summary_week_value.update()

    # ---------- timer ----------

    def on_toggle_timer(self, task_name: str) -> None:
        if (
            self.running is not None
            and self.running["project_id"] == self.selected_project_id
            and self.running["task_name"] == task_name
        ):
            self._open_stop_note_dialog()
            return

        if self.running is not None:
            self.stop_running()

        self.start_running(self.selected_project_id, task_name)
        self.refresh_tasks()

    def start_running(self, project_id: int, task_name: str) -> None:
        base_seconds = next(
            (t_row["total_seconds"] or 0 for t_row in self.tasks if t_row["task_name"] == task_name), 0
        )
        session_id = db.start_timer(project_id, task_name)
        stop_event = threading.Event()
        self.running = {
            "session_id": session_id,
            "project_id": project_id,
            "task_name": task_name,
            "start_monotonic": time.monotonic(),
            "start_date": date.today(),
            "base_seconds": base_seconds,
            "stop_event": stop_event,
            "text_control": None,
            "estimated_seconds": None,
            "idle_alert_seconds": self._idle_alert_seconds(),
            "idle_alert_fired": False,
            "afk_threshold_seconds": self._afk_threshold_seconds(),
            "afk_started_monotonic": None,
        }
        # Run on Flet's event loop through run_task instead of a system thread:
        # control.update() uses an asyncio queue that must be handled from this
        # loop, otherwise the visual tick may fail.
        self.page.run_task(self._tick_loop, stop_event)

    def _idle_alert_seconds(self) -> int | None:
        return timer_service.parse_optional_seconds(db.get_setting("idle_alert_hours", "4"), 3600)

    def _afk_threshold_seconds(self) -> int | None:
        return timer_service.parse_optional_seconds(db.get_setting("afk_threshold_minutes", "5"), 60)

    def _prompt_afk_return(self, afk_duration: float) -> None:
        if self.running is None:
            return
        task_name = self.running["task_name"]
        duration_label = format_duration(int(afk_duration))

        def keep(e):
            self.page.pop_dialog()

        def discard(e):
            if self.running is not None:
                self.running["start_monotonic"] += afk_duration
            self.page.pop_dialog()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(t("afk_prompt_title", self.lang)),
            content=ft.Text(t("afk_prompt_body", self.lang, task=task_name, duration=duration_label)),
            actions=[
                ft.TextButton(content=t("afk_keep", self.lang), on_click=keep),
                ft.FilledButton(content=t("afk_discard", self.lang), on_click=discard),
            ],
        )
        self.page.show_dialog(dialog)

    def _open_stop_note_dialog(self) -> None:
        if self.running is None:
            return
        lang = self.lang
        task_name = self.running["task_name"]
        note_field = ft.TextField(
            label=t("session_note", lang),
            hint_text=t("session_note_hint", lang),
            multiline=True,
            min_lines=3,
            max_lines=5,
        )

        def finish(note: str = ""):
            self.page.pop_dialog()
            self.stop_running(note)
            self.refresh_tasks()
            self.update_summary()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(t("stop_timer_title", lang, task=task_name)),
            content=ft.Container(width=420, content=note_field),
            actions=[
                ft.TextButton(content=t("cancel", lang), on_click=lambda e: self.page.pop_dialog()),
                ft.TextButton(content=t("stop_without_note", lang), on_click=lambda e: finish()),
                ft.FilledButton(content=t("save_note_and_stop", lang), on_click=lambda e: finish(note_field.value or "")),
            ],
        )
        self.page.show_dialog(dialog)

    def stop_running(self, session_note: str = "") -> None:
        if self.running is None:
            return
        session_seconds = int(time.monotonic() - self.running["start_monotonic"])
        db.stop_timer(self.running["session_id"], session_seconds, session_note)
        self.running["stop_event"].set()
        self.running = None

    async def _tick_loop(self, stop_event: threading.Event) -> None:
        """Update the active timer and trigger time-related alerts.

        This coroutine runs on Flet's asyncio loop to update visual controls
        without touching the UI from an external thread. It also handles forgotten
        timer alerts and return-from-idle detection.
        """
        while not stop_event.is_set():
            await asyncio.sleep(1)
            if stop_event.is_set() or self.running is None:
                return
            elapsed = self.running["base_seconds"] + (time.monotonic() - self.running["start_monotonic"])
            text_control = self.running.get("text_control")
            estimated_seconds = self.running.get("estimated_seconds")
            if text_control is not None:
                text_control.value = self._task_duration_summary(elapsed, estimated_seconds)
                try:
                    text_control.update()
                except Exception:
                    pass
            active_today_seconds = int(time.monotonic() - self.running["start_monotonic"]) if self.running.get("start_date") == date.today() else 0
            self.appbar_today_text.value = t(
                "global_today",
                self.lang,
                duration=self._format_duration(db.get_day_total() + active_today_seconds),
            )
            try:
                self.appbar_today_text.update()
            except Exception:
                pass

            idle_alert_seconds = self.running.get("idle_alert_seconds")
            if (
                idle_alert_seconds
                and not self.running.get("idle_alert_fired")
                and elapsed >= idle_alert_seconds
            ):
                self.running["idle_alert_fired"] = True
                send_notification(
                    t("app_title", self.lang),
                    t("idle_timer_alert", self.lang, task=self.running["task_name"]),
                )

            afk_threshold = self.running.get("afk_threshold_seconds")
            if afk_threshold:
                afk_seconds = get_afk_seconds()
                if afk_seconds is not None:
                    if afk_seconds >= afk_threshold:
                        if self.running.get("afk_started_monotonic") is None:
                            self.running["afk_started_monotonic"] = time.monotonic() - afk_seconds
                    else:
                        afk_started = self.running.get("afk_started_monotonic")
                        if afk_started is not None:
                            self.running["afk_started_monotonic"] = None
                            afk_duration = time.monotonic() - afk_started
                            if afk_duration >= afk_threshold:
                                self._prompt_afk_return(afk_duration)

    # ---------- CSV export ----------

    async def on_export_csv(self, e) -> None:
        """Export all sessions to a flat CSV usable outside Trackr Time.

        The export retains metadata useful for billing and tracking: project,
        task, tags, dates, raw duration, and session note.
        """
        path = await self.file_picker.save_file(
            dialog_title=t("export_csv", self.lang),
            file_name="trackr_time_export.csv",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["csv"],
        )
        if not path:
            return
        export_service.write_sessions_csv(path)
        self.page.show_dialog(ft.SnackBar(ft.Text(t("csv_exported", self.lang, path=path))))

    # ---------- window lifecycle ----------

    def on_window_event(self, e: ft.WindowEvent) -> None:
        if e.type == ft.WindowEventType.CLOSE:
            self.on_close_request()

    def on_close_request(self) -> None:
        self.quit_app()

    def quit_app(self) -> None:
        self.scheduler.stop()
        self.page.run_task(self.page.window.destroy)
        # Additional safeguard: if the native window does not fully close in the
        # packaged executable, the Python process may remain in the background
        # while holding the single-instance mutex. Force exit after requesting a
        # clean shutdown so the mutex is released.
        threading.Timer(1.5, lambda: os._exit(0)).start()


def main(page: ft.Page) -> None:
    TrackrApp(page)
