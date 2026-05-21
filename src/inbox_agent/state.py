import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class StateDB:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS processed_emails (
                email_hash TEXT PRIMARY KEY,
                notion_page_id TEXT,
                processed_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS processed_meetings (
                page_id TEXT PRIMARY KEY,
                processed_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
                notion_page_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                doability_flag TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS sync_runs (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                emails_processed INTEGER DEFAULT 0,
                tasks_created INTEGER DEFAULT 0,
                errors INTEGER DEFAULT 0
            );
        """)
        self.conn.commit()

    @staticmethod
    def hash_email(sender: str, subject: str, date: str) -> str:
        raw = f"{sender}|{subject}|{date}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def is_email_processed(self, email_hash: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM processed_emails WHERE email_hash = ?", (email_hash,)
        ).fetchone()
        return row is not None

    def record_email(self, email_hash: str, notion_page_id: str | None = None):
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "INSERT OR IGNORE INTO processed_emails (email_hash, notion_page_id, processed_at) VALUES (?, ?, ?)",
            (email_hash, notion_page_id, now),
        )
        self.conn.commit()

    def is_meeting_processed(self, page_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM processed_meetings WHERE page_id = ?", (page_id,)
        ).fetchone()
        return row is not None

    def record_meeting(self, page_id: str):
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "INSERT OR IGNORE INTO processed_meetings (page_id, processed_at) VALUES (?, ?)",
            (page_id, now),
        )
        self.conn.commit()

    def record_task(self, notion_page_id: str, status: str, doability_flag: str):
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT OR REPLACE INTO tasks
               (notion_page_id, status, doability_flag, created_at)
               VALUES (?, ?, ?, ?)""",
            (notion_page_id, status, doability_flag, now),
        )
        self.conn.commit()

    def mark_task_completed(self, notion_page_id: str):
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "UPDATE tasks SET status = 'completed', completed_at = ? WHERE notion_page_id = ?",
            (now, notion_page_id),
        )
        self.conn.commit()

    def is_task_archived(self, notion_page_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM tasks WHERE notion_page_id = ? AND status = 'archived'",
            (notion_page_id,),
        ).fetchone()
        return row is not None

    def start_sync_run(self) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cursor = self.conn.execute(
            "INSERT INTO sync_runs (started_at) VALUES (?)", (now,)
        )
        self.conn.commit()
        return cursor.lastrowid

    def finish_sync_run(self, run_id: int, emails: int, tasks: int, errors: int):
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """UPDATE sync_runs
               SET completed_at = ?, emails_processed = ?, tasks_created = ?, errors = ?
               WHERE run_id = ?""",
            (now, emails, tasks, errors, run_id),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()
