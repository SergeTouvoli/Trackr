# Trackr Time

Trackr Time is a desktop time-tracking application built with Python, Flet,
SQLite, and system notifications.

Current version: `v0.0.1` (`2026-08-12`)

## Features

- Project and task management with statuses, time estimates, and tags.
- Timer with editable session history and notes.
- Daily, task, and project statistics.
- CSV export for reporting and further analysis.
- Configurable daily reminders.
- Forgotten-timer alerts and Windows idle-time detection.
- Light and dark themes, plus compact display mode.
- French, English, Spanish, Italian, and German interfaces.
- Optional local password lock with a recovery code.

Trackr Time runs locally and does not require an account or a remote service.
Closing the application window stops the application; it does not continue
running in the background.

## Requirements

- Python 3.12 or later.
- The platform-specific requirements from the
  [official Flet publishing documentation](https://flet.dev/docs/publish/)
  when building a distributable application.

## Development setup

### Linux and macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### Windows

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Running the application

From the repository root:

```bash
python main.py
```

The application entry point is `main.py`, which automatically makes the
`src/` package available.

## Building

Flet provides the packaging workflow. From the repository root, run the command
matching the desktop platform:

```bash
flet build linux
flet build windows
flet build macos
```

Run only the target needed for your release. Build output is written to
`build/<target>` by default.

Build availability depends on the host operating system. Windows builds must run
on Windows, Linux builds run on Linux or Windows through WSL, and macOS builds
must run on macOS. Consult the
[Flet publishing guide](https://flet.dev/docs/publish/) for the current platform
matrix, prerequisites, signing, and target-specific options.

The first build may take longer because Flet can download the compatible Flutter
SDK when it is not installed and available on `PATH`.

## Tests

The unit tests use Python's standard `unittest` framework:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

## Local data

The SQLite database is stored in the application data directory:

- Windows: `%APPDATA%\Trackr Time\trackr.db`
- Linux: `$XDG_DATA_HOME/Trackr Time/trackr.db` or
  `~/.local/share/Trackr Time/trackr.db`
- macOS: `~/.local/share/Trackr Time/trackr.db`

The optional password lock protects access through the application interface.
It does not encrypt the SQLite database, so operating-system account and disk
security remain important.

After the application directory was renamed, the first launch automatically
copies the legacy `%APPDATA%\Trackr\trackr.db` or
`~/.local/share/Trackr/trackr.db` database when the new database does not exist.

## Project structure

- `main.py`: initializes the database, acquires the single-instance lock, and
  starts Flet.
- `src/trackr/app_metadata.py`: application version, release date, and author.
- `src/trackr/app.py`: Flet orchestration, navigation, and primary callbacks.
- `src/trackr/db.py`: public facade for the SQLite data layer.
- `src/trackr/db_core.py`: SQLite connection management and migrations.
- `src/trackr/repositories/`: domain-specific SQLite queries.
- `src/trackr/models/`: typed domain models.
- `src/trackr/services/`: services without a direct Flet dependency.
- `src/trackr/ui/`: extracted Flet views and components.
- `src/trackr/auth.py`: password hashing and recovery codes.
- `src/trackr/notifications.py`: notifications and daily reminders.
- `src/trackr/paths.py`: paths compatible with source and packaged execution.
