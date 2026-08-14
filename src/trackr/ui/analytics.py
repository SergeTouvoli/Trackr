from datetime import date, timedelta

import flet as ft

from trackr import db
from trackr.i18n import t


CHART_BAR_MAX_HEIGHT = 130
CHART_BAR_WIDTH = 14
RANK_BAR_TRACK_WIDTH = 200
RANK_BAR_HEIGHT = 14


def build_daily_chart(app, project_id: int) -> ft.Control:
    rows = db.get_daily_totals(project_id, app.analytics_days)
    totals_by_day = {r["day"]: (r["total_seconds"] or 0) for r in rows}
    if not any(totals_by_day.values()):
        return app._empty_state(ft.Icons.SHOW_CHART_ROUNDED, t("no_analytics_data", app.lang))

    max_seconds = max(totals_by_day.values(), default=0) or 1
    bar_color = app._sequential_color()
    columns = []
    for i in range(app.analytics_days - 1, -1, -1):
        day = date.today() - timedelta(days=i)
        seconds = totals_by_day.get(day.isoformat(), 0)
        bar_height = max(2, int(CHART_BAR_MAX_HEIGHT * seconds / max_seconds))
        columns.append(
            ft.Column(
                [
                    ft.Container(
                        height=CHART_BAR_MAX_HEIGHT,
                        alignment=ft.Alignment.BOTTOM_CENTER,
                        content=ft.Container(
                            width=CHART_BAR_WIDTH,
                            height=bar_height,
                            bgcolor=bar_color,
                            border_radius=ft.BorderRadius(top_left=4, top_right=4, bottom_left=0, bottom_right=0),
                            tooltip=f"{day.strftime('%d/%m')} · {app._format_duration(seconds)}",
                        ),
                    ),
                    ft.Text(day.strftime("%d/%m"), size=8, color=ft.Colors.OUTLINE),
                ],
                spacing=4,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )
    return ft.Row(columns, spacing=6, scroll=ft.ScrollMode.AUTO)


def build_ranked_bars(app, rows: list, name_key: str, color_key_fn) -> ft.Control:
    if not rows:
        return app._empty_state(ft.Icons.BAR_CHART_ROUNDED, t("no_analytics_data", app.lang))

    max_seconds = max((r["total_seconds"] or 0) for r in rows) or 1
    bars = []
    for row in rows:
        seconds = row["total_seconds"] or 0
        fill_width = max(4, int(RANK_BAR_TRACK_WIDTH * seconds / max_seconds))
        bars.append(
            ft.Row(
                [
                    ft.Container(
                        width=120,
                        content=ft.Text(row[name_key], size=12, overflow=ft.TextOverflow.ELLIPSIS, max_lines=1),
                    ),
                    ft.Container(
                        width=RANK_BAR_TRACK_WIDTH,
                        height=RANK_BAR_HEIGHT,
                        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
                        border_radius=4,
                        alignment=ft.Alignment.CENTER_LEFT,
                        content=ft.Container(
                            width=fill_width,
                            height=RANK_BAR_HEIGHT,
                            bgcolor=app._categorical_color(color_key_fn(row)),
                            border_radius=ft.BorderRadius(top_left=0, bottom_left=0, top_right=4, bottom_right=4),
                        ),
                    ),
                    ft.Text(app._format_duration(seconds), size=12, font_family="Consolas"),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )
    return ft.Column(bars, spacing=8)


def build(app) -> ft.Container:
    lang = app.lang
    project_id = app.selected_project_id

    period_dropdown = ft.Dropdown(
        label=t("analytics_period", lang),
        value=str(app.analytics_days),
        width=160,
        options=[
            ft.dropdown.Option(key="7", text=t("period_7", lang)),
            ft.dropdown.Option(key="14", text=t("period_14", lang)),
            ft.dropdown.Option(key="30", text=t("period_30", lang)),
        ],
    )

    def on_period_change(e):
        app.analytics_days = int(period_dropdown.value)
        app.show_analytics()

    period_dropdown.on_change = on_period_change

    sections = [
        ft.Row(
            [ft.Text(t("analytics", lang), size=26, weight=ft.FontWeight.BOLD), period_dropdown],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    ]

    if project_id is None:
        sections.append(
            app._settings_section(
                ft.Icons.SHOW_CHART_ROUNDED,
                t("analytics_daily", lang),
                [app._empty_state(ft.Icons.FOLDER_OFF_OUTLINED, t("select_project", lang))],
            )
        )
    else:
        sections.append(
            app._settings_section(
                ft.Icons.SHOW_CHART_ROUNDED,
                f"{t('analytics_daily', lang)} · {app.project_title.value}",
                [build_daily_chart(app, project_id)],
            )
        )
        task_rows = db.get_task_totals(project_id, app.analytics_days)
        sections.append(
            app._settings_section(
                ft.Icons.CHECKLIST_RTL_ROUNDED,
                t("analytics_tasks", lang),
                [build_ranked_bars(app, task_rows, "task_name", lambda r: r["task_name"])],
            )
        )

    project_rows = db.get_project_totals(app.analytics_days)
    sections.append(
        app._settings_section(
            ft.Icons.FOLDER_OUTLINED,
            t("analytics_projects", lang),
            [build_ranked_bars(app, project_rows, "project_name", lambda r: r["project_id"])],
        )
    )

    return ft.Container(
        padding=30,
        content=ft.Column(sections, spacing=18, scroll=ft.ScrollMode.AUTO),
    )
