
import sys
import os
from pathlib import Path

import yt_dlp

from PySide6.QtCore import QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QTextEdit, QPushButton,
    QLineEdit, QFileDialog, QProgressBar, QMessageBox
)


class DownloadWorker(QThread):
    progress = Signal(int)
    status = Signal(str)
    finished_item = Signal(str)
    completed = Signal()

    def __init__(self, urls, folder):
        super().__init__()
        self.urls = urls
        self.folder = folder

    def run(self):
        os.makedirs(self.folder, exist_ok=True)

        for index, url in enumerate(self.urls, start=1):
            self.progress.emit(0)
            self.status.emit(
                f"Đang tải video {index}/{len(self.urls)}..."
            )

            downloaded_paths = []

            def progress_hook(data):
                if data.get("filename"):
                    downloaded_paths.append(data["filename"])

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
                    self.progress.emit(100)

            options = {
                "format": "best",
                "outtmpl": os.path.join(
                    self.folder,
                    "%(title).100B_%(id)s.%(ext)s"
                ),
                "noplaylist": True,
                "ignoreerrors": False,
                "quiet": True,
                "no_warnings": False,
                "windowsfilenames": True,
                "retries": 5,
                "fragment_retries": 5,
                "socket_timeout": 30,
                "merge_output_format": "mp4",
                "progress_hooks": [progress_hook],
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

                if not info:
                    raise Exception(
                        "Không lấy được thông tin video."
                    )

                # Lấy đường dẫn video từ kết quả tải
                paths = list(downloaded_paths)

                def collect_paths(data):
                    if not isinstance(data, dict):
                        return

                    for key in ("filepath", "_filename"):
                        value = data.get(key)
                        if value:
                            paths.append(value)

                    for item in data.get("requested_downloads") or []:
                        if isinstance(item, dict):
                            if item.get("filepath"):
                                paths.append(item["filepath"])

                    for entry in data.get("entries") or []:
                        collect_paths(entry)

                collect_paths(info)

                # Chỉ báo thành công khi file thực sự tồn tại
                saved_files = []
                for path in paths:
                    if path and os.path.isfile(path):
                        if path not in saved_files:
                            saved_files.append(path)

                if not saved_files:
                    raise Exception(
                        "Không tìm thấy file video đã lưu. "
                        "Có thể link không tải được hoặc video đã bị hạn chế."
                    )

                self.progress.emit(100)
                self.finished_item.emit(
                    f"THÀNH CÔNG: {saved_files[0]}"
                )

            except Exception as error:
                self.finished_item.emit(
                    f"THẤT BẠI: {url}\nLý do: {error}"
                )

        self.status.emit("Đã xử lý xong danh sách link.")
        self.completed.emit()


class TikTokDownloader(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("TikTok Downloader - Tải video hàng loạt")
        self.resize(750, 600)

        default_folder = os.path.join(
            str(Path.home()), "Downloads", "TikTokVideos"
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
            "Dán link video TikTok vào ô bên dưới. "
            "Mỗi link một dòng."
        )
        layout.addWidget(guide)

        self.url_box = QTextEdit()
        self.url_box.setPlaceholderText(
            "Ví dụ:\n"
            "https://www.tiktok.com/@user/video/123456789\n"
            "https://www.tiktok.com/@user/video/987654321"
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
            self, "Chọn thư mục lưu video",
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
            with open(file_path, "r", encoding="utf-8-sig") as file:
                content = file.read()

            self.url_box.setPlainText(content)
            self.status_label.setText("Đã thêm danh sách link.")
        except Exception as error:
            QMessageBox.critical(
                self, "Lỗi đọc file", str(error)
            )

    def start_download(self):
        text = self.url_box.toPlainText().strip()

        urls = [
            line.strip()
            for line in text.splitlines()
            if line.strip().startswith("http://")
            or line.strip().startswith("https://")
        ]

        if not urls:
            QMessageBox.warning(
                self,
                "Thiếu link",
                "Bạn hãy nhập ít nhất một link video TikTok."
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
            urls,
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
