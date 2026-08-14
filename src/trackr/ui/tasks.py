import flet as ft

from trackr import db
from trackr.i18n import t


def build_task_card(app, task_row) -> ft.Card:
    task_name = task_row["task_name"]
    total_seconds = task_row["total_seconds"] or 0
    task_status = task_row["task_status"] or db.TASK_STATUS_PENDING
    estimated_seconds = task_row["estimated_seconds"]
    task_tags = task_row["task_tags"] or ""
    compact = app.compact_mode
    is_running = (
        app.running is not None
        and app.running["project_id"] == app.selected_project_id
        and app.running["task_name"] == task_name
    )

    duration_text = ft.Text(
        app._task_duration_summary(total_seconds, estimated_seconds),
        size=max(13, app._task_duration_font_size(estimated_seconds) - 2) if compact else app._task_duration_font_size(estimated_seconds),
        weight=ft.FontWeight.BOLD,
        font_family="Consolas",
        width=166 if compact else 184,
        text_align=ft.TextAlign.RIGHT,
    )
    if is_running:
        app.running["text_control"] = duration_text
        app.running["estimated_seconds"] = estimated_seconds

    title_children = [
        ft.Text(
            task_name,
            size=15,
            weight=ft.FontWeight.W_600,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
            tooltip=task_name,
        )
    ]
    if is_running:
        title_children.append(ft.Text(t("recording", app.lang), size=11, color=ft.Colors.RED))
    if task_tags:
        title_children.append(app._tag_chips(task_tags, compact=True))

    return ft.Card(
        elevation=1 if is_running else 0,
        bgcolor=ft.Colors.with_opacity(0.14, ft.Colors.RED) if is_running else ft.Colors.SURFACE_CONTAINER_HIGH,
        content=ft.Container(
            padding=ft.Padding.symmetric(horizontal=12 if compact else 14, vertical=6 if compact else 10),
            content=ft.Row(
                [
                    ft.Container(
                        width=34 if compact else 42,
                        height=34 if compact else 42,
                        border_radius=17 if compact else 21,
                        bgcolor=ft.Colors.RED if is_running else ft.Colors.PRIMARY,
                        alignment=ft.Alignment.CENTER,
                        ink=True,
                        on_click=lambda e, tn=task_name: app.on_toggle_timer(tn),
                        content=ft.Icon(
                            ft.Icons.STOP_ROUNDED if is_running else ft.Icons.PLAY_ARROW_ROUNDED,
                            color=ft.Colors.WHITE,
                            size=19 if compact else 22,
                        ),
                    ),
                    ft.Column(title_children, spacing=2, expand=True),
                    ft.Row(
                        [app._task_status_chip(task_status), duration_text],
                        spacing=8,
                        tight=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.HISTORY_ROUNDED,
                        icon_size=17,
                        icon_color=ft.Colors.OUTLINE,
                        tooltip=t("history", app.lang),
                        on_click=lambda e, tn=task_name: app.on_show_history(tn),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.EDIT_OUTLINED,
                        icon_size=17,
                        icon_color=ft.Colors.OUTLINE,
                        tooltip=t("edit_task", app.lang),
                        on_click=lambda e, tn=task_name: app.on_edit_task(tn),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CONTENT_COPY_ROUNDED,
                        icon_size=17,
                        icon_color=ft.Colors.OUTLINE,
                        tooltip=t("duplicate_task", app.lang),
                        on_click=lambda e, tn=task_name: app.on_duplicate_task(tn),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE,
                        icon_size=17,
                        icon_color=ft.Colors.OUTLINE,
                        tooltip=t("delete", app.lang),
                        on_click=lambda e, tn=task_name: app.on_delete_task(tn),
                    ),
                ],
                spacing=9 if compact else 14,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ),
    )
