
import sys
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
import imageio_ffmpeg

from PySide6.QtCore import QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QTextEdit, QPushButton,
    QLineEdit, QFileDialog, QProgressBar, QMessageBox
)


VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".webm", ".mov", ".avi"
}

AUDIO_EXTENSIONS = {
    ".mp3", ".m4a", ".aac", ".wav", ".opus", ".ogg"
}


def normalize_input(value):
    value = value.strip()

    if re.fullmatch(r"@[\w.-]+", value):
        return "https://www.tiktok.com/" + value, True

    if re.fullmatch(r"[\w.-]+", value):
        return "https://www.tiktok.com/@" + value, True

    if value.startswith(("https://", "http://")):
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()

        if not (
            host == "tiktok.com"
            or host.endswith(".tiktok.com")
        ):
            return None, False

        match = re.match(r"^/@([\w.-]+)/?$", parsed.path)

        if match:
            return (
                "https://www.tiktok.com/@" + match.group(1),
                True
            )

        if "/video/" in parsed.path:
            return value, False

        return value, False

    return None, False


class DownloadWorker(QThread):
    progress = Signal(int)
    status = Signal(str)
    finished_item = Signal(str)
    completed = Signal()

    def __init__(self, items, folder):
        super().__init__()
        self.items = items
        self.folder = folder

    def run(self):
        os.makedirs(self.folder, exist_ok=True)

        try:
            ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception as error:
            self.finished_item.emit(
                "LỖI FFmpeg: Không tìm thấy chương trình ghép video.\n"
                + str(error)
            )
            self.completed.emit()
            return

        for index, item in enumerate(self.items, start=1):
            url, is_profile = item

            label = "tài khoản" if is_profile else "video"

            self.progress.emit(0)
            self.status.emit(
                f"Đang xử lý {label} {index}/{len(self.items)}..."
            )

            start_time = time.time()
            downloaded_paths = []

            def progress_hook(data):
                info = data.get("info_dict") or {}

                if data.get("status") == "downloading":
                    total = (
                        data.get("total_bytes")
                        or data.get("total_bytes_estimate")
                        or 0
                    )
                    current = data.get("downloaded_bytes", 0)

                    if total:
                        percent = int(current * 100 / total)
                        self.progress.emit(min(percent, 100))

                elif data.get("status") == "finished":
                    filename = (
                        info.get("filepath")
                        or data.get("filename")
                    )

                    if filename:
                        downloaded_paths.append(filename)

                    self.progress.emit(100)

            def postprocessor_hook(data):
                info = data.get("info_dict") or {}
                filename = info.get("filepath")

                if filename:
                    downloaded_paths.append(filename)

            options = {
                # Ưu tiên video MP4 + âm thanh M4A.
                # Nếu không có thì thử các luồng video khác.
                # Tuyệt đối không chọn định dạng chỉ có âm thanh.
                "format": (
                    "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
                    "bestvideo+bestaudio/"
                    "best[ext=mp4]/best"
                ),

                "outtmpl": os.path.join(
                    self.folder,
                    "%(uploader)s_%(title).80B_%(id)s.%(ext)s"
                ),

                "noplaylist": not is_profile,
                "ignoreerrors": True,

                "quiet": True,
                "no_warnings": False,
                "windowsfilenames": True,

                "retries": 5,
                "fragment_retries": 5,
                "extractor_retries": 5,
                "socket_timeout": 45,

                # Ghép hình và tiếng thành MP4.
                "merge_output_format": "mp4",

                # Dùng FFmpeg được đóng gói cùng phần mềm.
                "ffmpeg_location": ffmpeg_path,

                "progress_hooks": [progress_hook],
                "postprocessor_hooks": [postprocessor_hook],

                "http_headers": {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/130.0.0.0 "
                        "Safari/537.36"
                    ),
                    "Referer": "https://www.tiktok.com/",
                },
            }

            try:
                with yt_dlp.YoutubeDL(options) as downloader:
                    info = downloader.extract_info(
                        url,
                        download=True
                    )

                # Lấy các file được tạo hoặc cập nhật trong lần tải này.
                candidates = list(downloaded_paths)

                for path in Path(self.folder).iterdir():
                    if path.is_file():
                        try:
                            if path.stat().st_mtime >= start_time - 2:
                                candidates.append(str(path))
                        except OSError:
                            pass

                saved_files = []

                for filename in candidates:
                    if not filename:
                        continue

                    path = os.path.abspath(filename)

                    if not os.path.isfile(path):
                        continue

                    extension = Path(path).suffix.lower()

                    # Không nhận file âm thanh là video.
                    if extension in AUDIO_EXTENSIONS:
                        continue

                    if extension not in VIDEO_EXTENSIONS:
                        continue

                    if path not in saved_files:
                        saved_files.append(path)

                if not saved_files:
                    raise Exception(
                        "Không tìm thấy file video có hình ảnh.\n"
                        "TikTok có thể không cung cấp luồng hình ảnh "
                        "hoặc đã hạn chế truy cập video này."
                    )

                if is_profile:
                    self.finished_item.emit(
                        f"HOÀN TẤT TÀI KHOẢN: {url}\n"
                        f"Tìm thấy {len(saved_files)} file video.\n"
                        + "\n".join(saved_files)
                    )
                else:
                    self.finished_item.emit(
                        f"THÀNH CÔNG: {saved_files[-1]}"
                    )

            except Exception as error:
                self.finished_item.emit(
                    f"THẤT BẠI: {url}\nLý do: {error}"
                )

        self.status.emit("Đã xử lý xong danh sách.")
        self.completed.emit()


class TikTokDownloader(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(
            "TikTok Downloader - Tải video hàng loạt"
        )
        self.resize(750, 600)

        default_folder = os.path.join(
            str(Path.home()),
            "Downloads",
            "TikTokVideos"
        )

        self.worker = None
        self.download_folder = default_folder

        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)

        title = QLabel("TIKTOK VIDEO DOWNLOADER")
        title.setStyleSheet(
            "font-size: 23px; font-weight: bold; color: #e53935;"
        )
        layout.addWidget(title)

        guide = QLabel(
            "Dán link video hoặc nhập @username TikTok. "
            "Mỗi dòng một link hoặc một tài khoản."
        )
        layout.addWidget(guide)

        self.url_box = QTextEdit()
        self.url_box.setPlaceholderText(
            "Ví dụ:\n"
            "https://www.tiktok.com/@user/video/123456789\n"
            "@vanlamiaday\n"
            "https://www.tiktok.com/@anotheruser"
        )
        layout.addWidget(self.url_box)

        file_row = QHBoxLayout()

        self.folder_input = QLineEdit(default_folder)
        self.folder_input.setReadOnly(True)

        browse_button = QPushButton("Chọn thư mục")
        browse_button.clicked.connect(self.choose_folder)

        open_button = QPushButton("Mở thư mục")
        open_button.clicked.connect(self.open_folder)

        file_row.addWidget(self.folder_input)
        file_row.addWidget(browse_button)
        file_row.addWidget(open_button)

        layout.addLayout(file_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Sẵn sàng tải video.")
        layout.addWidget(self.status_label)

        button_row = QHBoxLayout()

        self.load_button = QPushButton("Thêm link từ file TXT")
        self.load_button.clicked.connect(self.load_txt)

        self.download_button = QPushButton("TẢI VIDEO")
        self.download_button.setStyleSheet(
            "background-color: #e53935; color: white; "
            "font-size: 16px; font-weight: bold; padding: 10px;"
        )
        self.download_button.clicked.connect(self.start_download)

        button_row.addWidget(self.load_button)
        button_row.addWidget(self.download_button)

        layout.addLayout(button_row)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setPlaceholderText(
            "Kết quả tải video sẽ hiển thị ở đây..."
        )
        layout.addWidget(self.log_box)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Chọn thư mục lưu video",
            self.download_folder
        )

        if folder:
            self.download_folder = folder
            self.folder_input.setText(folder)

    def open_folder(self):
        os.makedirs(self.download_folder, exist_ok=True)

        QDesktopServices.openUrl(
            QUrl.fromLocalFile(self.download_folder)
        )

    def load_txt(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn file chứa danh sách link",
            "",
            "Text files (*.txt)"
        )

        if not file_path:
            return

        try:
            with open(
                file_path,
                "r",
                encoding="utf-8-sig"
            ) as file:
                content = file.read()

            self.url_box.setPlainText(content)
            self.status_label.setText(
                "Đã thêm danh sách từ file TXT."
            )

        except Exception as error:
            QMessageBox.critical(
                self,
                "Lỗi đọc file",
                str(error)
            )

    def start_download(self):
        text = self.url_box.toPlainText().strip()

        if not text:
            QMessageBox.warning(
                self,
                "Thiếu dữ liệu",
                "Bạn hãy nhập link video hoặc @username."
            )
            return

        items = []
        invalid = []

        for line in text.splitlines():
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            url, is_profile = normalize_input(line)

            if url:
                items.append((url, is_profile))
            else:
                invalid.append(line)

        if invalid:
            QMessageBox.warning(
                self,
                "Link không hợp lệ",
                "Các dòng sau không phải link TikTok "
                "hoặc username hợp lệ:\n\n"
                + "\n".join(invalid[:10])
            )
            return

        if not items:
            QMessageBox.warning(
                self,
                "Thiếu link",
                "Không tìm thấy link TikTok hợp lệ."
            )
            return

        if self.worker and self.worker.isRunning():
            return

        os.makedirs(self.download_folder, exist_ok=True)

        self.log_box.clear()
        self.progress_bar.setValue(0)

        self.download_button.setEnabled(False)
        self.load_button.setEnabled(False)

        self.worker = DownloadWorker(
            items,
            self.download_folder
        )

        self.worker.progress.connect(
            self.progress_bar.setValue
        )

        self.worker.status.connect(
            self.status_label.setText
        )

        self.worker.finished_item.connect(
            self.show_result
        )

        self.worker.completed.connect(
            self.download_finished
        )

        self.worker.start()

    def show_result(self, message):
        self.log_box.append(message)

    def download_finished(self):
        self.download_button.setEnabled(True)
        self.load_button.setEnabled(True)

        self.status_label.setText(
            "Đã hoàn tất. Hãy kiểm tra thư mục lưu video."
        )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TikTokDownloader()
    window.show()
    sys.exit(app.exec())
