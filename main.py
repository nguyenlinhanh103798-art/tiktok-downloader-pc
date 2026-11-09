
import sys
import os
from pathlib import Path

import yt_dlp
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QPushButton, QLineEdit, QFileDialog,
    QProgressBar, QMessageBox
)


class DownloadWorker(QThread):
    progress = Signal(int)
    status = Signal(str)
    finished_item = Signal(str)

    def __init__(self, urls, folder):
        super().__init__()
        self.urls = urls
        self.folder = folder
        self.current_percent = 0

    def run(self):
        os.makedirs(self.folder, exist_ok=True)

        for index, url in enumerate(self.urls, start=1):
            self.status.emit(
                f"Đang xử lý video {index}/{len(self.urls)}"
            )

            def progress_hook(data):
                if data["status"] == "downloading":
                    total = data.get("total_bytes") or data.get(
                        "total_bytes_estimate", 0
                    )
                    downloaded = data.get("downloaded_bytes", 0)

                    if total:
                        percent = int(downloaded * 100 / total)
                        self.progress.emit(percent)

                elif data["status"] == "finished":
                    self.progress.emit(100)

            options = {
                "format": "best",
                "outtmpl": os.path.join(
                    self.folder, "%(uploader)s_%(id)s.%(ext)s"
                ),
                "noplaylist": False,
                "ignoreerrors": True,
                "quiet": True,
                "no_warnings": True,
                "windowsfilenames": True,
                "merge_output_format": "mp4",
                "download_archive": os.path.join(
                    self.folder, "downloaded.txt"
                ),
                "progress_hooks": [progress_hook],
            }

            try:
                with yt_dlp.YoutubeDL(options) as downloader:
                    downloader.download([url])

                self.finished_item.emit(f"Hoàn tất: {url}")

            except Exception as error:
                self.finished_item.emit(
                    f"Lỗi: {url} | {str(error)[:200]}"
                )

        self.status.emit("Đã xử lý xong danh sách!")
        self.progress.emit(100)


class TikTokDownloader(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("TikTok Downloader - FREE")
        self.setMinimumSize(850, 650)

        self.folder = str(Path.home() / "Videos" / "TikTok")
        self.worker = None

        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setSpacing(12)

        title = QLabel("TIKTOK DOWNLOADER")
        title.setStyleSheet(
            "font-size: 27px; font-weight: bold; color: #1677d2;"
        )
        layout.addWidget(title)

        subtitle = QLabel(
            "Tải video TikTok trên máy tính - Hỗ trợ danh sách hàng loạt"
        )
        layout.addWidget(subtitle)

        layout.addWidget(QLabel(
            "Dán link video, link tài khoản hoặc nhiều link "
            "(mỗi link một dòng):"
        ))

        self.input = QTextEdit()
        self.input.setPlaceholderText(
            "https://www.tiktok.com/@username/video/123456789\n"
            "https://www.tiktok.com/@username/video/987654321"
        )
        layout.addWidget(self.input)

        file_row = QHBoxLayout()

        self.folder_text = QLineEdit(self.folder)
        self.folder_text.setReadOnly(True)

        choose = QPushButton("Chọn thư mục lưu")
        choose.clicked.connect(self.choose_folder)

        file_row.addWidget(self.folder_text)
        file_row.addWidget(choose)
        layout.addLayout(file_row)

        self.start_button = QPushButton("BẮT ĐẦU TẢI VIDEO")
        self.start_button.setMinimumHeight(48)
        self.start_button.setStyleSheet(
            "background-color: #087bce; color: white; "
            "font-size: 16px; font-weight: bold; border-radius: 7px;"
        )
        self.start_button.clicked.connect(self.start_download)
        layout.addWidget(self.start_button)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Sẵn sàng")
        layout.addWidget(self.status_label)

        layout.addWidget(QLabel("Nhật ký tải xuống:"))

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

        footer = QLabel(
            "FREE VERSION | Chỉ tải nội dung bạn có quyền sử dụng."
        )
        footer.setStyleSheet("color: gray;")
        layout.addWidget(footer)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục lưu video", self.folder
        )

        if folder:
            self.folder = folder
            self.folder_text.setText(folder)

    def start_download(self):
        urls = [
            line.strip()
            for line in self.input.toPlainText().splitlines()
            if line.strip()
        ]

        if not urls:
            QMessageBox.warning(
                self, "Thông báo", "Bạn chưa nhập link TikTok!"
            )
            return

        if self.worker and self.worker.isRunning():
            return

        self.start_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log.append(f"Bắt đầu tải {len(urls)} mục...")

        self.worker = DownloadWorker(urls, self.folder)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.status.connect(self.status_label.setText)
        self.worker.finished_item.connect(self.log.append)
        self.worker.finished.connect(
            lambda: self.start_button.setEnabled(True)
        )
        self.worker.start()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = TikTokDownloader()
    window.show()

    sys.exit(app.exec())
