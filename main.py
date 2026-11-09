
import sys
import os
import re
import subprocess
from pathlib import Path

import yt_dlp
import imageio_ffmpeg

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton, QFileDialog,
    QProgressBar, QMessageBox
)


def normalize_input(value):
    value = value.strip()

    if not value:
        return None

    if value.startswith("@"):
        return "https://www.tiktok.com/" + value

    if re.fullmatch(r"[A-Za-z0-9._]+", value):
        return "https://www.tiktok.com/@" + value

    if value.startswith("www.tiktok.com/") or value.startswith("vt.tiktok.com/"):
        return "https://" + value

    return value


class DownloadWorker(QThread):
    log_signal = Signal(str)
    progress_signal = Signal(int)
    finished_signal = Signal()

    def __init__(self, items, folder, device_id):
        super().__init__()
        self.items = items
        self.folder = folder
        self.device_id = device_id
        self.downloaded = 0
        self.failed = 0
        self.current_percent = 0

    def log(self, message):
        self.log_signal.emit(message)

    def run(self):
        try:
            ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception as e:
            self.log("Không tìm thấy FFmpeg: " + str(e))
            self.finished_signal.emit()
            return

        os.makedirs(self.folder, exist_ok=True)

        for index, url in enumerate(self.items, start=1):
            self.current_percent = 0
            self.log("")
            self.log(f"ĐANG XỬ LÝ {index}/{len(self.items)}")
            self.log(url)

            is_profile = (
                re.search(r"tiktok\.com/@[^/?]+/?$", url) is not None
            )

            options = {
                "format": (
                    "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
                    "bestvideo+bestaudio/"
                    "best[height>0]"
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
                "merge_output_format": "mp4",
                "ffmpeg_location": ffmpeg_path,
                "progress_hooks": [self.progress_hook],
                "http_headers": {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/130.0.0.0 Safari/537.36"
                    ),
                    "Referer": "https://www.tiktok.com/"
                }
            }

            if self.device_id:
                options["extractor_args"] = {
                    "tiktok": {
                        "device_id": [self.device_id]
                    }
                }

            try:
                before_files = set(Path(self.folder).glob("*"))

                with yt_dlp.YoutubeDL(options) as ydl:
                    result = ydl.download([url])

                after_files = set(Path(self.folder).glob("*"))
                new_files = after_files - before_files

                valid_videos = []
                for file_path in new_files:
                    if not file_path.is_file():
                        continue

                    if file_path.suffix.lower() not in (
                        ".mp4", ".mkv", ".webm", ".mov", ".avi"
                    ):
                        continue

                    if file_path.stat().st_size < 10000:
                        continue

                    # Kiểm tra file có hình ảnh video hay không
                    check = subprocess.run(
                        [
                            ffmpeg_path,
                            "-v", "error",
                            "-i", str(file_path),
                            "-map", "0:v:0",
                            "-frames:v", "1",
                            "-f", "null",
                            "-"
                        ],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )

                    if check.returncode == 0:
                        valid_videos.append(file_path)

                if valid_videos:
                    self.downloaded += len(valid_videos)
                    self.log(
                        f"THÀNH CÔNG: Đã tải {len(valid_videos)} video."
                    )
                else:
                    self.failed += 1
                    self.log(
                        "THẤT BẠI: Không tìm thấy file video có hình ảnh."
                    )
                    self.log(
                        "TikTok có thể đã hạn chế video hoặc chỉ trả về âm thanh."
                    )

            except Exception as e:
                self.failed += 1
                self.log("LỖI: " + str(e))

        self.log("")
        self.log("========== KẾT QUẢ ==========")
        self.log(f"Video tải thành công: {self.downloaded}")
        self.log(f"Lượt tải không thành công: {self.failed}")
        self.log("Đã hoàn tất.")

        self.progress_signal.emit(100)
        self.finished_signal.emit()

    def progress_hook(self, data):
        if data.get("status") == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            downloaded = data.get("downloaded_bytes", 0)

            if total:
                percent = int(downloaded * 100 / total)
                self.progress_signal.emit(max(0, min(percent, 100)))

        elif data.get("status") == "finished":
            self.progress_signal.emit(100)
            self.log("Đã tải xong dữ liệu, đang xử lý video...")


class TikTokDownloader(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("TikTok Downloader - Tải video hàng loạt")
        self.resize(850, 700)

        self.download_folder = str(Path.home() / "Downloads" / "TikTok")

        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)

        title = QLabel("TIKTOK DOWNLOADER")
        title.setStyleSheet("font-size: 23px; font-weight: bold;")
        layout.addWidget(title)

        layout.addWidget(QLabel(
            "Nhập link video, link trang cá nhân hoặc @username. "
            "Mỗi dòng một link:"
        ))

        self.url_input = QTextEdit()
        self.url_input.setPlaceholderText(
            "Ví dụ:\n"
            "https://www.tiktok.com/@username/video/123456\n"
            "@username\n"
            "https://vt.tiktok.com/xxxxx/"
        )
        layout.addWidget(self.url_input)

        layout.addWidget(QLabel(
            "Device ID TikTok (không phải mật khẩu):"
        ))

        self.device_id_input = QLineEdit()
        self.device_id_input.setPlaceholderText(
            "Dán Device ID 19 chữ số vào đây"
        )
        layout.addWidget(self.device_id_input)

        layout.addWidget(QLabel(
            "Device ID chỉ được dùng khi chạy ứng dụng trên máy này, "
            "không ghi vào mã nguồn GitHub."
        ))

        folder_layout = QHBoxLayout()

        self.folder_label = QLabel(
            "Thư mục lưu: " + self.download_folder
        )
        folder_layout.addWidget(self.folder_label)

        self.folder_button = QPushButton("Chọn thư mục")
        self.folder_button.clicked.connect(self.choose_folder)
        folder_layout.addWidget(self.folder_button)

        layout.addLayout(folder_layout)

        button_layout = QHBoxLayout()

        self.download_button = QPushButton("BẮT ĐẦU TẢI VIDEO")
        self.download_button.clicked.connect(self.start_download)
        button_layout.addWidget(self.download_button)

        self.open_button = QPushButton("MỞ THƯ MỤC VIDEO")
        self.open_button.clicked.connect(self.open_folder)
        button_layout.addWidget(self.open_button)

        layout.addLayout(button_layout)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        layout.addWidget(QLabel("Nhật ký tải video:"))

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        layout.addWidget(self.log_box)

        self.worker = None

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Chọn thư mục lưu video",
            self.download_folder
        )

        if folder:
            self.download_folder = folder
            self.folder_label.setText("Thư mục lưu: " + folder)

    def open_folder(self):
        os.makedirs(self.download_folder, exist_ok=True)
        os.startfile(self.download_folder)

    def start_download(self):
        raw_text = self.url_input.toPlainText().strip()

        if not raw_text:
            QMessageBox.warning(
                self, "Thiếu link", "Bạn hãy nhập link TikTok trước."
            )
            return

        device_id = self.device_id_input.text().strip()

        if device_id and not re.fullmatch(r"\d{19}", device_id):
            QMessageBox.warning(
                self,
                "Device ID không hợp lệ",
                "Device ID phải gồm đúng 19 chữ số. "
                "Bạn hãy kiểm tra và nhập lại."
            )
            return

        items = []
        for line in raw_text.splitlines():
            value = normalize_input(line)
            if value:
                items.append(value)

        if not items:
            QMessageBox.warning(
                self, "Thiếu link", "Không tìm thấy link hợp lệ."
            )
            return

        self.log_box.clear()
        self.progress.setValue(0)
        self.download_button.setEnabled(False)

        self.worker = DownloadWorker(
            items,
            self.download_folder,
            device_id
        )

        self.worker.log_signal.connect(self.add_log)
        self.worker.progress_signal.connect(self.progress.setValue)
        self.worker.finished_signal.connect(self.download_finished)

        self.worker.start()

    def add_log(self, message):
        self.log_box.append(message)

    def download_finished(self):
        self.download_button.setEnabled(True)
        QMessageBox.information(
            self,
            "Hoàn tất",
            "Đã kết thúc quá trình tải. "
            "Bạn hãy kiểm tra thư mục video."
        )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TikTokDownloader()
    window.show()
    sys.exit(app.exec())
