
import sys
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import yt_dlp
import imageio_ffmpeg

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton, QFileDialog,
    QProgressBar, QMessageBox, QComboBox
)


def normalize_input(value):
    value = value.strip()

    if not value:
        return None

    if value.startswith("@"):
        return "https://www.tiktok.com/" + value

    if re.fullmatch(r"[A-Za-z0-9._]+", value):
        return "https://www.tiktok.com/@" + value

    if value.startswith(("www.tiktok.com/", "vt.tiktok.com/")):
        return "https://" + value

    return value


def safe_filename(name):
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:100] or "TikTok_video"


class DownloadWorker(QThread):
    log_signal = Signal(str)
    progress_signal = Signal(int)
    finished_signal = Signal()

    def __init__(self, items, folder, device_id, max_workers):
        super().__init__()
        self.items = items
        self.folder = folder
        self.device_id = device_id
        self.max_workers = max_workers
        self.downloaded = 0
        self.failed = 0

    def log(self, message):
        self.log_signal.emit(message)

    def verify_video(self, file_path, ffmpeg_path):
        try:
            result = subprocess.run(
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
                timeout=40
            )
            return result.returncode == 0
        except Exception:
            return False

    def download_tikwm(self, url, ffmpeg_path, output_folder):
        self.log("Đang thử tải bằng TikWM...")

        api_url = "https://www.tikwm.com/api/"

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36"
            )
        }

        response = requests.post(
            api_url,
            data={"url": url, "hd": 1},
            headers=headers,
            timeout=(20, 60)
        )

        response.raise_for_status()
        result = response.json()

        data = result.get("data") or {}

        if result.get("code") not in (0, None) and result.get("msg") != "success":
            raise Exception(
                result.get("msg") or "TikWM không lấy được video."
            )

        video_url = data.get("hdplay") or data.get("play")

        if not video_url:
            raise Exception("TikWM không trả về đường dẫn video.")

        title = safe_filename(data.get("title") or "TikTok_video")
        video_id = safe_filename(str(data.get("id") or "video"))

        filename = f"{title}_{video_id}.mp4"
        final_path = Path(output_folder) / filename
        temp_path = Path(output_folder) / (filename + ".part")

        self.log("TikWM đã tìm thấy video. Đang tải MP4...")

        try:
            with requests.get(
                video_url,
                headers=headers,
                stream=True,
                timeout=(20, 120)
            ) as video_response:

                video_response.raise_for_status()

                content_type = video_response.headers.get(
                    "Content-Type", ""
                ).lower()

                if "text/html" in content_type:
                    raise Exception("TikWM trả về trang lỗi thay vì video.")

                with open(temp_path, "wb") as file:
                    for chunk in video_response.iter_content(1024 * 256):
                        if chunk:
                            file.write(chunk)

            if not temp_path.exists() or temp_path.stat().st_size < 10000:
                raise Exception("File tải về quá nhỏ hoặc không hợp lệ.")

            if not self.verify_video(temp_path, ffmpeg_path):
                raise Exception("File TikWM trả về không có hình ảnh video.")

            os.replace(temp_path, final_path)

            self.log("TikWM tải và kiểm tra video thành công.")
            return final_path

        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass

    def download_ytdlp(self, url, ffmpeg_path, output_folder):
        self.log("Đang thử tải bằng yt-dlp...")

        options = {
            "format": (
                "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
                "bestvideo+bestaudio/"
                "best[height>0]"
            ),
            "outtmpl": os.path.join(
                output_folder,
                "%(uploader)s_%(title).80B_%(id)s.%(ext)s"
            ),
            "noplaylist": False,
            "ignoreerrors": True,
            "quiet": True,
            "no_warnings": False,
            "windowsfilenames": True,
            "retries": 5,
            "fragment_retries": 5,
            "extractor_retries": 5,
            "socket_timeout": 45,
            "concurrent_fragment_downloads": 2,
            "merge_output_format": "mp4",
            "ffmpeg_location": ffmpeg_path,
            "progress_hooks": [self.progress_hook],
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36"
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

        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])

        valid = []

        for path in Path(output_folder).glob("*"):
            if not path.is_file():
                continue

            if path.suffix.lower() not in (
                ".mp4", ".mkv", ".webm", ".mov", ".avi"
            ):
                continue

            if path.stat().st_size < 10000:
                continue

            if self.verify_video(path, ffmpeg_path):
                valid.append(path)

        return valid

    def progress_hook(self, data):
        if data.get("status") == "finished":
            self.log("Đã tải dữ liệu, đang xử lý video...")

    def move_to_main_folder(self, source):
        source = Path(source)
        destination = Path(self.folder) / source.name

        counter = 2

        while destination.exists():
            destination = (
                Path(self.folder) /
                f"{source.stem}_{counter}{source.suffix}"
            )
            counter += 1

        shutil.move(str(source), str(destination))
        return destination

    def process_item(self, index, url, ffmpeg_path):
        task_folder = Path(
            tempfile.mkdtemp(
                prefix=".tiktok_task_",
                dir=self.folder
            )
        )

        try:
            self.log("")
            self.log(f"ĐANG XỬ LÝ LINK {index}/{len(self.items)}")
            self.log(url)

            is_profile = (
                re.search(r"tiktok\.com/@[^/?]+/?$", url) is not None
            )

            videos = []

            if is_profile:
                videos = self.download_ytdlp(
                    url, ffmpeg_path, str(task_folder)
                )

            else:
                try:
                    video = self.download_tikwm(
                        url, ffmpeg_path, str(task_folder)
                    )
                    videos = [video]

                except Exception as tikwm_error:
                    self.log("TikWM chưa tải được: " + str(tikwm_error))
                    self.log("Chuyển sang phương án dự phòng...")

                    videos = self.download_ytdlp(
                        url, ffmpeg_path, str(task_folder)
                    )

            moved = []

            for video in videos:
                if Path(video).is_file():
                    moved.append(self.move_to_main_folder(video))

            if moved:
                self.log(
                    f"THÀNH CÔNG: Đã lưu {len(moved)} video."
                )
                return len(moved), 0

            self.log("THẤT BẠI: Không tìm thấy video hợp lệ.")
            return 0, 1

        except Exception as e:
            self.log(f"LỖI LINK {index}: {e}")
            return 0, 1

        finally:
            shutil.rmtree(task_folder, ignore_errors=True)

    def run(self):
        try:
            ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception as e:
            self.log("Không tìm thấy FFmpeg: " + str(e))
            self.finished_signal.emit()
            return

        os.makedirs(self.folder, exist_ok=True)

        total = len(self.items)
        completed = 0

        self.log(f"BẮT ĐẦU TẢI {total} LINK")
        self.log(f"SỐ LUỒNG ĐỒNG THỜI: {self.max_workers}")

        try:
            with ThreadPoolExecutor(
                max_workers=self.max_workers
            ) as executor:

                futures = {
                    executor.submit(
                        self.process_item,
                        index,
                        url,
                        ffmpeg_path
                    ): index
                    for index, url in enumerate(self.items, start=1)
                }

                for future in as_completed(futures):
                    try:
                        downloaded, failed = future.result()
                        self.downloaded += downloaded
                        self.failed += failed

                    except Exception as e:
                        self.failed += 1
                        self.log("Lỗi tiến trình: " + str(e))

                    completed += 1

                    percent = int(completed * 100 / total)
                    self.progress_signal.emit(percent)

                    self.log(
                        f"Đã xử lý {completed}/{total} link."
                    )

        except Exception as e:
            self.log("Lỗi hệ thống tải: " + str(e))

        self.log("")
        self.log("========== KẾT QUẢ ==========")
        self.log(f"Video tải thành công: {self.downloaded}")
        self.log(f"Lượt tải không thành công: {self.failed}")
        self.log("Đã hoàn tất.")

        self.progress_signal.emit(100)
        self.finished_signal.emit()


class TikTokDownloader(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("TikTok Downloader - Tải video hàng loạt")
        self.resize(850, 740)

        self.download_folder = str(
            Path.home() / "Downloads" / "TikTok"
        )

        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)

        title = QLabel("TIKTOK DOWNLOADER")
        title.setStyleSheet(
            "font-size: 23px; font-weight: bold;"
        )
        layout.addWidget(title)

        layout.addWidget(QLabel(
            "Nhập link video hoặc tài khoản TikTok. "
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
            "Device ID TikTok (không phải mật khẩu, tùy chọn):"
        ))

        self.device_id_input = QLineEdit()
        self.device_id_input.setPlaceholderText(
            "Dán Device ID 19 chữ số nếu muốn dùng dự phòng yt-dlp"
        )
        layout.addWidget(self.device_id_input)

        speed_layout = QHBoxLayout()

        speed_layout.addWidget(QLabel("Số video tải cùng lúc:"))

        self.speed_combo = QComboBox()
        self.speed_combo.addItems([
            "1 video",
            "3 video",
            "5 video",
            "10 video"
        ])
        self.speed_combo.setCurrentIndex(2)

        speed_layout.addWidget(self.speed_combo)
        layout.addLayout(speed_layout)

        layout.addWidget(QLabel(
            "Nên thử 5 video trước. Nếu mạng ổn định có thể tăng lên 10."
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
            self.folder_label.setText(
                "Thư mục lưu: " + folder
            )

    def open_folder(self):
        os.makedirs(self.download_folder, exist_ok=True)
        os.startfile(self.download_folder)

    def start_download(self):
        raw_text = self.url_input.toPlainText().strip()

        if not raw_text:
            QMessageBox.warning(
                self,
                "Thiếu link",
                "Bạn hãy nhập link TikTok trước."
            )
            return

        device_id = self.device_id_input.text().strip()

        if device_id and not re.fullmatch(r"\d{19}", device_id):
            QMessageBox.warning(
                self,
                "Device ID không hợp lệ",
                "Device ID phải gồm đúng 19 chữ số."
            )
            return

        items = []

        for line in raw_text.splitlines():
            value = normalize_input(line)
            if value and value not in items:
                items.append(value)

        if not items:
            QMessageBox.warning(
                self,
                "Thiếu link",
                "Không tìm thấy link hợp lệ."
            )
            return

        workers = [1, 3, 5, 10][self.speed_combo.currentIndex()]

        self.log_box.clear()
        self.progress.setValue(0)
        self.download_button.setEnabled(False)
        self.speed_combo.setEnabled(False)

        self.worker = DownloadWorker(
            items,
            self.download_folder,
            device_id,
            workers
        )

        self.worker.log_signal.connect(self.add_log)
        self.worker.progress_signal.connect(
            self.progress.setValue
        )
        self.worker.finished_signal.connect(
            self.download_finished
        )

        self.worker.start()

    def add_log(self, message):
        self.log_box.append(message)

    def download_finished(self):
        self.download_button.setEnabled(True)
        self.speed_combo.setEnabled(True)

        QMessageBox.information(
            self,
            "Hoàn tất",
            "Đã kết thúc quá trình tải. "
            "Hãy kiểm tra thư mục video."
        )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TikTokDownloader()
    window.show()
    sys.exit(app.exec())
