import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from trackr import db, db_core


class DbTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = db_core.DB_PATH
        self.old_migrate_legacy_db = db_core._migrate_legacy_db
        db_core.DB_PATH = Path(self.temp_dir.name) / "trackr.db"
        db_core._migrate_legacy_db = lambda: None

    def tearDown(self):
        db_core._migrate_legacy_db = self.old_migrate_legacy_db
        db_core.DB_PATH = self.old_db_path
        self.temp_dir.cleanup()

    def test_initialise_schema_versionne(self):
        db.init_db()

        conn = sqlite3.connect(db_core.DB_PATH)
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            username = conn.execute("SELECT value FROM setting WHERE name = 'username'").fetchone()[0]
            columns = [row[1] for row in conn.execute("PRAGMA table_info(timespent)").fetchall()]
            task_columns = [row[1] for row in conn.execute("PRAGMA table_info(task)").fetchall()]
        finally:
            conn.close()

        self.assertEqual(version, db.CURRENT_SCHEMA_VERSION)
        self.assertEqual(username, "user")
        self.assertIn("task_status", columns)
        self.assertIn("estimated_seconds", columns)
        self.assertIn("task_tags", columns)
        self.assertIn("session_note", columns)
        self.assertIn("task_id", columns)
        self.assertIn("name", task_columns)
        self.assertIn("status", task_columns)

    def test_migre_base_existante_non_versionnee(self):
        conn = sqlite3.connect(db_core.DB_PATH)
        try:
            conn.execute("CREATE TABLE setting (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, value TEXT)")
            conn.execute("INSERT INTO setting (name, value) VALUES (?, ?)", ("username", "legacy"))
            conn.commit()
        finally:
            conn.close()

        db.init_db()

        conn = sqlite3.connect(db_core.DB_PATH)
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            username = conn.execute("SELECT value FROM setting WHERE name = 'username'").fetchone()[0]
            project_count = conn.execute("SELECT COUNT(*) FROM project").fetchone()[0]
            columns = [row[1] for row in conn.execute("PRAGMA table_info(timespent)").fetchall()]
            task_columns = [row[1] for row in conn.execute("PRAGMA table_info(task)").fetchall()]
        finally:
            conn.close()

        self.assertEqual(version, db.CURRENT_SCHEMA_VERSION)
        self.assertEqual(username, "legacy")
        self.assertEqual(project_count, 0)
        self.assertIn("task_status", columns)
        self.assertIn("estimated_seconds", columns)
        self.assertIn("task_tags", columns)
        self.assertIn("session_note", columns)
        self.assertIn("task_id", columns)
        self.assertIn("name", task_columns)
        self.assertIn("status", task_columns)

    def test_enregistre_session_et_resume(self):
        db.init_db()
        project_id = db.add_project("Client")
        db.add_task(project_id, "Développement", estimated_seconds=7200, task_tags="dev, client")
        session_id = db.start_timer(project_id, "Développement")

        db.stop_timer(session_id, 42, "Implémentation")

        tasks = db.list_tasks(project_id)
        summary = db.get_summary(project_id)
        sessions = db.list_task_sessions(project_id, "Développement")

        self.assertEqual(tasks[0]["task_name"], "Développement")
        self.assertEqual(tasks[0]["total_seconds"], 42)
        self.assertEqual(tasks[0]["task_status"], db.TASK_STATUS_IN_PROGRESS)
        self.assertEqual(tasks[0]["estimated_seconds"], 7200)
        self.assertEqual(tasks[0]["task_tags"], "dev, client")
        self.assertEqual(sessions[0]["session_note"], "Implémentation")
        self.assertEqual(summary["today"], 42)
        self.assertEqual(summary["week"], 42)

    def test_met_a_jour_statut_et_temps_prevu(self):
        db.init_db()
        project_id = db.add_project("Client")
        db.add_task(project_id, "Recette")

        db.update_task_metadata(project_id, "Recette", db.TASK_STATUS_DONE, 1800, "qa, client")

        task = db.list_tasks(project_id)[0]
        self.assertEqual(task["task_status"], db.TASK_STATUS_DONE)
        self.assertEqual(task["estimated_seconds"], 1800)
        self.assertEqual(task["task_tags"], "qa, client")

    def test_sessions_du_jour_contiennent_notes_et_tags(self):
        db.init_db()
        project_id = db.add_project("Client")
        db.add_task(project_id, "Support", task_tags="support")
        session_id = db.start_timer(project_id, "Support")

        db.stop_timer(session_id, 300, "Appel client")

        sessions = db.list_day_sessions()

        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["project_name"], "Client")
        self.assertEqual(sessions[0]["task_tags"], "support")
        self.assertEqual(sessions[0]["session_note"], "Appel client")

    def test_corrige_et_supprime_session(self):
        db.init_db()
        project_id = db.add_project("Client")
        db.add_task(project_id, "Support")
        session_id = db.start_timer(project_id, "Support")
        db.stop_timer(session_id, 300, "Avant")

        today = date.today().isoformat()
        db.update_session(session_id, f"{today}T09:00:00", f"{today}T09:45:00", 2700, "Corrigé")
        session = db.list_task_sessions(project_id, "Support")[0]
        self.assertEqual(session["duration_seconds"], 2700)
        self.assertEqual(session["session_note"], "Corrigé")

        db.delete_session(session_id)
        self.assertEqual(db.list_task_sessions(project_id, "Support"), [])

    def test_resume_filtre_les_jours_ouvres(self):
        db.init_db()
        project_id = db.add_project("Client")
        monday = date.today() - timedelta(days=date.today().weekday())
        saturday = monday + timedelta(days=5)

        conn = db.get_connection()
        try:
            conn.execute(
                "INSERT INTO timespent (project_id, task_name, start_time, duration_seconds) VALUES (?, ?, ?, ?)",
                (project_id, "Dev", f"{monday.isoformat()}T09:00:00", 100),
            )
            conn.execute(
                "INSERT INTO timespent (project_id, task_name, start_time, duration_seconds) VALUES (?, ?, ?, ?)",
                (project_id, "Support", f"{saturday.isoformat()}T09:00:00", 200),
            )
            conn.commit()
        finally:
            conn.close()

        summary = db.get_summary(project_id, {0, 1, 2, 3, 4})

        self.assertEqual(summary["week"], 100)

    def test_migre_taches_existantes_vers_table_task(self):
        conn = sqlite3.connect(db_core.DB_PATH)
        try:
            conn.executescript(
                """
                CREATE TABLE setting (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    value TEXT
                );
                CREATE TABLE project (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    archived_at TEXT
                );
                CREATE TABLE timespent (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    task_name TEXT NOT NULL,
                    start_time TEXT,
                    end_time TEXT,
                    duration_seconds INTEGER NOT NULL DEFAULT 0,
                    task_status TEXT NOT NULL DEFAULT 'pending',
                    estimated_seconds INTEGER,
                    task_tags TEXT,
                    session_note TEXT
                );
                """
            )
            conn.execute("PRAGMA user_version = 5")
            conn.execute("INSERT INTO setting (name, value) VALUES ('username', 'legacy')")
            conn.execute("INSERT INTO project (id, name, created_at) VALUES (1, 'Client', '2026-07-20T09:00:00')")
            conn.execute(
                """
                INSERT INTO timespent (
                    project_id, task_name, start_time, duration_seconds,
                    task_status, estimated_seconds, task_tags
                )
                VALUES (1, 'Bug', '2026-07-20T09:30:00', 600, 'done', 1800, 'dev')
                """
            )
            conn.commit()
        finally:
            conn.close()

        db.init_db()

        task = db.list_tasks(1)[0]
        sessions = db.list_task_sessions(1, "Bug")
        self.assertEqual(task["task_name"], "Bug")
        self.assertEqual(task["task_status"], db.TASK_STATUS_DONE)
        self.assertEqual(task["estimated_seconds"], 1800)
        self.assertEqual(task["task_tags"], "dev")
        self.assertEqual(sessions[0]["duration_seconds"], 600)


if __name__ == "__main__":
    unittest.main()
