import flet as ft


LOGO_PNG = "trackr-icon.png"


def build(app) -> ft.Row:
    left_panel = ft.Container(
        width=290,
        padding=ft.Padding.only(left=18, right=18, top=20, bottom=18),
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Image(src=LOGO_PNG, width=26, height=26, border_radius=8, fit=ft.BoxFit.COVER),
                        app.brand_text,
                    ],
                    spacing=10,
                ),
                ft.Container(
                    height=1,
                    bgcolor=ft.Colors.OUTLINE_VARIANT,
                    margin=ft.Margin.symmetric(vertical=14),
                ),
                app.projects_header,
                app.project_search_field,
                app.projects_list,
                ft.Container(
                    height=1,
                    bgcolor=ft.Colors.OUTLINE_VARIANT,
                    margin=ft.Margin.symmetric(vertical=8),
                ),
                ft.Row(
                    [
                        app.new_project_field,
                        ft.IconButton(
                            icon=ft.Icons.ADD_CIRCLE_ROUNDED,
                            icon_color=ft.Colors.PRIMARY,
                            icon_size=34,
                            on_click=app.on_add_project,
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=4,
                ),
            ],
            expand=True,
        ),
    )

    right_header = ft.Row(
        [
            app.project_avatar,
            ft.Column([app.project_title], spacing=0, expand=True),
            app._stat_chip(ft.Icons.TODAY_ROUNDED, app.summary_today_label, app.summary_today_value),
            app._stat_chip(ft.Icons.DATE_RANGE_ROUNDED, app.summary_week_label, app.summary_week_value),
        ],
        spacing=12,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    task_toolbar = ft.Container(
        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
        border_radius=10,
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        content=ft.Row(
            [
                ft.Container(content=app.task_search_field, expand=True),
                app.task_sort_controls,
                app.compact_mode_switch,
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    right_panel = ft.Container(
        expand=True,
        padding=ft.Padding.only(left=30, right=30, top=26, bottom=20),
        content=ft.Column(
            [
                right_header,
                task_toolbar,
                app.tasks_list,
                ft.Row(
                    [
                        app.new_task_field,
                        app.new_task_estimate_field,
                        app.new_task_tags_field,
                        ft.IconButton(
                            icon=ft.Icons.ADD_CIRCLE_ROUNDED,
                            icon_color=ft.Colors.PRIMARY,
                            icon_size=34,
                            on_click=app.on_add_task,
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=4,
                ),
            ],
            expand=True,
        ),
    )

    return ft.Row([left_panel, right_panel], expand=True, spacing=0)
