
import threading
from pathlib import Path

from database import TaskDatabase
from downloader import TikTokDownloader


class TaskManager:
    """Quản lý hàng đợi và kết nối cơ sở dữ liệu với bộ tải."""

    def __init__(
        self,
        output_dir="TikTokDownloads",
        max_workers=5,
        on_update=None
    ):
        self.database = TaskDatabase()
        self.lock = threading.RLock()

        self.on_update = on_update

        self.task_map = {}
        self.pending_events = {}

        self.downloader = TikTokDownloader(
            output_dir=output_dir,
            max_workers=max_workers,
            on_progress=self._on_progress,
            on_status=self._on_status
        )

    def _notify(self):
        if self.on_update:
            try:
                self.on_update()
            except Exception:
                pass

    def _dispatch(self, task_id, event_type, *args):
        """Xử lý sự kiện, kể cả khi tác vụ vừa được tạo."""

        with self.lock:
            db_id = self.task_map.get(task_id)

            if db_id is None:
                self.pending_events.setdefault(
                    task_id, []
                ).append((event_type, args))
                return

        self._apply_event(db_id, event_type, args)

    def _register_task(self, task_id, db_id):
        with self.lock:
            self.task_map[task_id] = db_id

            pending = self.pending_events.pop(
                task_id, []
            )

        for event_type, args in pending:
            self._apply_event(db_id, event_type, args)

    def _apply_event(self, db_id, event_type, args):
        if event_type == "status":
            status, message = args

            if status == "completed":
                self.database.update_task(
                    db_id,
                    status="completed",
                    progress=100,
                    file_path=message,
                    error=""
                )

            elif status == "failed":
                self.database.update_task(
                    db_id,
                    status="failed",
                    error=message
                )

            elif status == "cancelled":
                self.database.update_task(
                    db_id,
                    status="cancelled",
                    error=message
                )

            elif status == "paused":
                self.database.update_task(
                    db_id,
                    status="paused"
                )

            elif status == "downloading":
                self.database.update_task(
                    db_id,
                    status="downloading"
                )

            elif status == "queued":
                self.database.update_task(
                    db_id,
                    status="queued"
                )

        elif event_type == "progress":
            percent, data = args

            self.database.update_task(
                db_id,
                progress=percent,
                status="downloading"
            )

        self._notify()

    def _on_status(self, task_id, status, message=""):
        self._dispatch(
            task_id,
            "status",
            status,
            message
        )

    def _on_progress(self, task_id, percent, data=None):
        self._dispatch(
            task_id,
            "progress",
            percent,
            data or {}
        )

    def add_url(self, url):
        """Thêm một link và tự động bỏ qua link trùng."""

        url = (url or "").strip()

        if not url:
            return {
                "success": False,
                "reason": "empty_url"
            }

        db_id, is_new = self.database.add_task(url)

        if not is_new:
            return {
                "success": False,
                "reason": "duplicate",
                "db_id": db_id
            }

        try:
            task_id = self.downloader.add_download(url)

            self._register_task(task_id, db_id)

            self._notify()

            return {
                "success": True,
                "task_id": task_id,
                "db_id": db_id
            }

        except Exception as error:
            self.database.update_task(
                db_id,
                status="failed",
                error=str(error)
            )

            self._notify()

            return {
                "success": False,
                "reason": "download_error",
                "error": str(error)
            }

    def add_urls(self, text):
        """Nhận nhiều link, mỗi dòng một link."""

        results = {
            "added": 0,
            "duplicates": 0,
            "invalid": 0,
            "errors": 0
        }

        urls = [
            line.strip()
            for line in (text or "").splitlines()
            if line.strip()
        ]

        for url in urls:
            result = self.add_url(url)

            if result["success"]:
                results["added"] += 1

            elif result["reason"] == "duplicate":
                results["duplicates"] += 1

            elif result["reason"] == "empty_url":
                results["invalid"] += 1

            else:
                results["errors"] += 1

        return results

    def pause(self, db_id):
        task_id = self._find_task_id(db_id)

        if not task_id:
            return False

        return self.downloader.pause_download(task_id)

    def resume(self, db_id):
        task_id = self._find_task_id(db_id)

        if not task_id:
            return False

        return self.downloader.resume_download(task_id)

    def cancel(self, db_id):
        task_id = self._find_task_id(db_id)

        if not task_id:
            return False

        return self.downloader.cancel_download(task_id)

    def _find_task_id(self, db_id):
        with self.lock:
            for task_id, saved_db_id in self.task_map.items():
                if saved_db_id == db_id:
                    return task_id

        return None

    def get_tasks(self, status=None):
        return self.database.list_tasks(status)

    def get_task(self, db_id):
        return self.database.get_task(db_id)

    def clear_completed(self):
        count = self.database.clear_completed()
        self._notify()
        return count

    def shutdown(self, wait=True):
        self.downloader.shutdown(wait=wait)
