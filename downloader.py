
import os
import threading
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import yt_dlp


class DownloadCancelled(Exception):
    """Thông báo một tác vụ đã bị hủy."""
    pass


class DownloadControl:
    """Điều khiển tạm dừng, tiếp tục và hủy tải."""

    def __init__(self):
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.cancel_event = threading.Event()

    def pause(self):
        self.pause_event.clear()

    def resume(self):
        self.pause_event.set()

    def cancel(self):
        self.cancel_event.set()
        self.pause_event.set()


class TikTokDownloader:
    """Bộ máy tải video TikTok."""

    def __init__(
        self,
        output_dir="TikTokDownloads",
        max_workers=5,
        on_progress=None,
        on_status=None
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.max_workers = max(1, min(int(max_workers), 5))

        self.on_progress = on_progress
        self.on_status = on_status

        self.executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="TikTokDownload"
        )

        self.controls = {}
        self.futures = {}
        self.lock = threading.RLock()
        self.closed = False

    def _status(self, task_id, status, message=""):
        if self.on_status:
            try:
                self.on_status(task_id, status, message)
            except Exception:
                pass

    def _progress(self, task_id, percent, data=None):
        if self.on_progress:
            try:
                self.on_progress(task_id, percent, data or {})
            except Exception:
                pass

    def add_download(self, url):
        """Thêm video vào hàng đợi tải."""

        url = (url or "").strip()

        if not url.startswith(("https://", "http://")):
            raise ValueError("Đường link không hợp lệ.")

        with self.lock:
            if self.closed:
                raise RuntimeError("Bộ tải đã được đóng.")

            task_id = str(uuid.uuid4())
            control = DownloadControl()

            self.controls[task_id] = control

            future = self.executor.submit(
                self._download,
                task_id,
                url,
                control
            )

            self.futures[task_id] = future

            return task_id

    def _download(self, task_id, url, control):
        """Thực hiện tải video trong một luồng riêng."""

        self._status(task_id, "downloading", "Đang chuẩn bị tải...")

        def progress_hook(data):
            if control.cancel_event.is_set():
                raise DownloadCancelled("Người dùng đã hủy tải.")

            while not control.pause_event.is_set():
                if control.cancel_event.is_set():
                    raise DownloadCancelled("Người dùng đã hủy tải.")

                control.pause_event.wait(0.2)

            if control.cancel_event.is_set():
                raise DownloadCancelled("Người dùng đã hủy tải.")

            if data.get("status") == "downloading":
                total = (
                    data.get("total_bytes")
                    or data.get("total_bytes_estimate")
                    or 0
                )

                downloaded = data.get("downloaded_bytes", 0)

                percent = (
                    downloaded * 100 / total
                    if total else 0
                )

                self._progress(
                    task_id,
                    round(percent, 1),
                    {
                        "downloaded": downloaded,
                        "total": total,
                        "speed": data.get("speed"),
                        "eta": data.get("eta"),
                        "filename": data.get("filename", "")
                    }
                )

            elif data.get("status") == "finished":
                self._progress(task_id, 100, data)

        options = {
            "format": "best",
            "outtmpl": str(
                self.output_dir / "%(title).100B [%(id)s].%(ext)s"
            ),
            "noplaylist": True,
            "continuedl": True,
            "nopart": False,
            "ignoreerrors": False,
            "quiet": True,
            "no_warnings": True,
            "retries": 3,
            "fragment_retries": 3,
            "progress_hooks": [progress_hook],
            "windowsfilenames": True,
        }

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)

                if control.cancel_event.is_set():
                    raise DownloadCancelled("Đã hủy tải.")

                if not info:
                    raise RuntimeError("Không lấy được thông tin video.")

                if info.get("_type") == "playlist":
                    raise RuntimeError(
                        "Đường link trả về danh sách video, "
                        "không phải một video riêng lẻ."
                    )

                filename = info.get("filepath")

                if not filename:
                    filename = ydl.prepare_filename(info)

                file_path = Path(filename)

                if not file_path.exists():
                    requested = info.get("requested_downloads") or []

                    for item in requested:
                        candidate = item.get("filepath")
                        if candidate and Path(candidate).exists():
                            file_path = Path(candidate)
                            break

                if not file_path.exists():
                    raise RuntimeError(
                        "Không tìm thấy tệp video sau khi tải."
                    )

                self._status(
                    task_id,
                    "completed",
                    str(file_path)
                )

                return {
                    "task_id": task_id,
                    "status": "completed",
                    "file_path": str(file_path),
                    "title": info.get("title", ""),
                    "video_id": info.get("id", "")
                }

        except DownloadCancelled as error:
            self._status(task_id, "cancelled", str(error))

            return {
                "task_id": task_id,
                "status": "cancelled",
                "error": str(error)
            }

        except Exception as error:
            if control.cancel_event.is_set():
                status = "cancelled"
            else:
                status = "failed"

            self._status(task_id, status, str(error))

            return {
                "task_id": task_id,
                "status": status,
                "error": str(error)
            }

    def pause_download(self, task_id):
        control = self.controls.get(task_id)

        if control:
            control.pause()
            self._status(task_id, "paused", "Đã yêu cầu tạm dừng.")
            return True

        return False

    def resume_download(self, task_id):
        control = self.controls.get(task_id)

        if control:
            control.resume()
            self._status(task_id, "downloading", "Đang tiếp tục tải.")
            return True

        return False

    def cancel_download(self, task_id):
        control = self.controls.get(task_id)

        if control:
            control.cancel()
            return True

        return False

    def get_future(self, task_id):
        return self.futures.get(task_id)

    def shutdown(self, wait=True):
        with self.lock:
            self.closed = True

            for control in self.controls.values():
                control.cancel()

        self.executor.shutdown(
            wait=wait,
            cancel_futures=True
        )
