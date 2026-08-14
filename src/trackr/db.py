"""Public facade for the SQLite data layer.

The technical foundation lives in ``db_core.py`` and domain queries live in
``trackr.repositories``. This module preserves the historical ``trackr.db.*`` API
used by the application and tests.
"""

from trackr.db_core import (
    CURRENT_SCHEMA_VERSION,
    DB_PATH,
    DEFAULT_WORKING_DAYS,
    TASK_STATUSES,
    TASK_STATUS_DONE,
    TASK_STATUS_IN_PROGRESS,
    TASK_STATUS_PENDING,
    _migrate_legacy_db,
    _now,
    get_connection,
    init_db,
)
from trackr.repositories.analytics import get_daily_totals, get_project_totals, get_task_totals
from trackr.repositories.projects import (
    add_project,
    delete_project,
    get_project,
    get_project_by_name,
    list_projects,
)
from trackr.repositories.sessions import (
    delete_session,
    get_day_total,
    get_summary,
    list_all_sessions,
    list_day_sessions,
    list_task_sessions,
    parse_working_days,
    start_timer,
    stop_timer,
    update_session,
)
from trackr.repositories.settings import get_setting, set_setting
from trackr.repositories.tasks import (
    add_task,
    delete_task,
    get_task_by_name,
    get_task_metadata,
    list_tasks,
    rename_task,
    update_task_metadata,
)
