
import os
import sqlite3
import threading
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from datetime import datetime


def get_data_dir():
    """Lưu dữ liệu riêng trên máy tính, không lưu trong thư mục GitHub."""
    if os.name == "nt":
        base = os.getenv("LOCALAPPDATA") or str(Path.home())
        folder = Path(base) / "TikTokDownloaderPro"
    else:
        folder = Path.home() / ".tiktok-downloader-pro"

    folder.mkdir(parents=True, exist_ok=True)
    return folder


def normalize_url(url):
    """Chuẩn hóa URL để hạn chế thêm video trùng."""
    url = (url or "").strip()

    if not url:
        return ""

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        parts = urlsplit(url)
        return urlunsplit((
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/"),
            "",
            ""
        ))
    except Exception:
        return url


class TaskDatabase:
    """Quản lý lịch sử tải và chống trùng bằng SQLite."""

    def __init__(self, db_path=None):
        self.db_path = str(
            db_path or (get_data_dir() / "downloads.db")
        )
        self.lock = threading.RLock()
        self.create_tables()

    def connect(self):
        conn = sqlite3.connect(
            self.db_path,
            timeout=30
        )
        conn.row_factory = sqlite3.Row
        return conn

    def create_tables(self):
        with self.lock:
            with self.connect() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS tasks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        url TEXT NOT NULL,
                        normalized_url TEXT NOT NULL UNIQUE,
                        title TEXT DEFAULT '',
                        status TEXT DEFAULT 'queued',
                        progress REAL DEFAULT 0,
                        file_path TEXT DEFAULT '',
                        error TEXT DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)

                conn.execute("""
                    CREATE INDEX IF NOT EXISTS
                    idx_tasks_status ON tasks(status)
                """)

                conn.commit()

    def add_task(self, url, title=""):
        """Thêm công việc. Trả về ID và trạng thái thêm mới."""
        original_url = (url or "").strip()
        clean_url = normalize_url(original_url)

        if not clean_url:
            return None, False

        now = datetime.now().isoformat(timespec="seconds")

        with self.lock:
            with self.connect() as conn:
                cursor = conn.execute("""
                    INSERT OR IGNORE INTO tasks
                    (url, normalized_url, title, status,
                     created_at, updated_at)
                    VALUES (?, ?, ?, 'queued', ?, ?)
                """, (
                    original_url,
                    clean_url,
                    title,
                    now,
                    now
                ))

                conn.commit()

                if cursor.rowcount == 1:
                    return cursor.lastrowid, True

                row = conn.execute("""
                    SELECT id FROM tasks
                    WHERE normalized_url = ?
                """, (clean_url,)).fetchone()

                return (row["id"] if row else None), False

    def update_task(self, task_id, **fields):
        """Cập nhật trạng thái, tiến độ, đường dẫn hoặc lỗi."""
        allowed = {
            "title",
            "status",
            "progress",
            "file_path",
            "error"
        }

        updates = {
            key: value
            for key, value in fields.items()
            if key in allowed
        }

        if not updates:
            return False

        updates["updated_at"] = datetime.now().isoformat(
            timespec="seconds"
        )

        columns = ", ".join(
            f"{key} = ?" for key in updates
        )

        values = list(updates.values())
        values.append(task_id)

        with self.lock:
            with self.connect() as conn:
                cursor = conn.execute(
                    f"UPDATE tasks SET {columns} WHERE id = ?",
                    values
                )
                conn.commit()
                return cursor.rowcount > 0

    def get_task(self, task_id):
        with self.lock:
            with self.connect() as conn:
                row = conn.execute(
                    "SELECT * FROM tasks WHERE id = ?",
                    (task_id,)
                ).fetchone()

                return dict(row) if row else None

    def list_tasks(self, status=None):
        with self.lock:
            with self.connect() as conn:
                if status:
                    rows = conn.execute("""
                        SELECT * FROM tasks
                        WHERE status = ?
                        ORDER BY id DESC
                    """, (status,)).fetchall()
                else:
                    rows = conn.execute("""
                        SELECT * FROM tasks
                        ORDER BY id DESC
                    """).fetchall()

                return [dict(row) for row in rows]

    def is_duplicate(self, url):
        clean_url = normalize_url(url)

        if not clean_url:
            return False

        with self.lock:
            with self.connect() as conn:
                row = conn.execute("""
                    SELECT id FROM tasks
                    WHERE normalized_url = ?
                """, (clean_url,)).fetchone()

                return row is not None

    def delete_task(self, task_id):
        with self.lock:
            with self.connect() as conn:
                cursor = conn.execute(
                    "DELETE FROM tasks WHERE id = ?",
                    (task_id,)
                )
                conn.commit()
                return cursor.rowcount > 0

    def clear_completed(self):
        with self.lock:
            with self.connect() as conn:
                cursor = conn.execute("""
                    DELETE FROM tasks
                    WHERE status = 'completed'
                """)
                conn.commit()
                return cursor.rowcount

    def export_rows(self):
        """Lấy dữ liệu để xuất Excel."""
        with self.lock:
            with self.connect() as conn:
                rows = conn.execute("""
                    SELECT id, url, title, status, progress,
                           file_path, error, created_at, updated_at
                    FROM tasks
                    ORDER BY id DESC
                """).fetchall()

                return [dict(row) for row in rows]
