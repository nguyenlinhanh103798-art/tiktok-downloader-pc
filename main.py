
import sys
from pathlib import Path

from PySide6.QtCore import QThread, Signal, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QTextEdit, QPushButton,
    QLineEdit, QFileDialog, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QSpinBox
)

from task_manager import TaskManager
from account_manager import TikTokAccountManager
from excel_export import ExcelExporter
from security import AppSecurity


class AccountWorker(QThread):
    finished_links = Signal(list)
    failed = Signal(str)

    def __init__(self, username, limit):
        super().__init__()
        self.username = username
        self.limit = limit

    def run(self):
        try:
            manager = TikTokAccountManager()
            videos = manager.get_video_urls(
                self.username,
                self.limit
            )
            self.finished_links.emit(videos)
        except Exception as error:
            self.failed.emit(str(error))


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("TikTok Downloader Pro")
        self.resize(1150, 780)

        self.security = AppSecurity()
        self.settings = self.security.load_settings()

        self.download_folder = self.settings["output_dir"]

        self.manager = TaskManager(
            output_dir=self.download_folder,
            max_workers=5
        )

        self.account_worker = None
        self.exporter = ExcelExporter()

        self.build_interface()
        self.refresh_table()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_table)
        self.timer.start(1500)

    def build_interface(self):

        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)

        title = QLabel("TIKTOK DOWNLOADER PRO")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "font-size:26px;font-weight:bold;color:#e53935;"
            "padding:12px;"
        )
        layout.addWidget(title)

        subtitle = QLabel(
            "Tải video hàng loạt | Quản lý tài khoản | "
            "Lịch sử | Xuất Excel"
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        layout.addWidget(QLabel("DANH SÁCH LINK VIDEO"))

        self.url_box = QTextEdit()
        self.url_box.setPlaceholderText(
            "Dán nhiều link TikTok vào đây.\n"
            "Mỗi link một dòng."
        )
        self.url_box.setMinimumHeight(110)
        layout.addWidget(self.url_box)

        row = QHBoxLayout()

        self.add_button = QPushButton("THÊM LINK VÀO HÀNG ĐỢI")
        self.add_button.clicked.connect(self.add_links)

        self.txt_button = QPushButton("NHẬP FILE TXT")
        self.txt_button.clicked.connect(self.load_txt)

        row.addWidget(self.add_button)
        row.addWidget(self.txt_button)
        layout.addLayout(row)

        layout.addWidget(QLabel("LẤY VIDEO TỪ TÀI KHOẢN TIKTOK"))

        account_row = QHBoxLayout()

        self.account_input = QLineEdit()
        self.account_input.setPlaceholderText(
            "Nhập @username hoặc link trang cá nhân"
        )

        self.limit_input = QSpinBox()
        self.limit_input.setRange(1, 10000)
        self.limit_input.setValue(100)
        self.limit_input.setPrefix("Số video: ")

        self.account_button = QPushButton("LẤY DANH SÁCH VIDEO")
        self.account_button.clicked.connect(
            self.fetch_account
        )

        account_row.addWidget(self.account_input)
        account_row.addWidget(self.limit_input)
        account_row.addWidget(self.account_button)

        layout.addLayout(account_row)

        layout.addWidget(QLabel("THƯ MỤC LƯU VIDEO"))

        folder_row = QHBoxLayout()

        self.folder_input = QLineEdit(self.download_folder)
        self.folder_input.setReadOnly(True)

        choose_button = QPushButton("CHỌN THƯ MỤC")
        choose_button.clicked.connect(self.choose_folder)

        open_button = QPushButton("MỞ THƯ MỤC")
        open_button.clicked.connect(self.open_folder)

        folder_row.addWidget(self.folder_input)
        folder_row.addWidget(choose_button)
        folder_row.addWidget(open_button)

        layout.addLayout(folder_row)

        layout.addWidget(QLabel("QUẢN LÝ TÁC VỤ"))

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "ID",
            "Link TikTok",
            "Trạng thái",
            "Tiến độ",
            "Đường dẫn file"
        ])

        self.table.setColumnHidden(0, True)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch
        )

        layout.addWidget(self.table)

        control_row = QHBoxLayout()

        pause_button = QPushButton("TẠM DỪNG")
        pause_button.clicked.connect(self.pause_selected)

        resume_button = QPushButton("TIẾP TỤC")
        resume_button.clicked.connect(self.resume_selected)

        cancel_button = QPushButton("HỦY TẢI")
        cancel_button.clicked.connect(self.cancel_selected)

        export_button = QPushButton("XUẤT EXCEL")
        export_button.clicked.connect(self.export_excel)

        control_row.addWidget(pause_button)
        control_row.addWidget(resume_button)
        control_row.addWidget(cancel_button)
        control_row.addWidget(export_button)

        layout.addLayout(control_row)

        self.status_label = QLabel("Sẵn sàng.")
        self.status_label.setStyleSheet(
            "padding:8px;font-weight:bold;"
        )
        layout.addWidget(self.status_label)

    def add_links(self):

        text = self.url_box.toPlainText().strip()

        if not text:
            QMessageBox.warning(
                self, "Thông báo", "Bạn chưa nhập link."
            )
            return

        urls = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]

        valid_urls = [
            url for url in urls
            if self.security.validate_tiktok_url(url)
        ]

        if not valid_urls:
            QMessageBox.warning(
                self,
                "Link không hợp lệ",
                "Không tìm thấy link TikTok hợp lệ."
            )
            return

        results = self.manager.add_urls(
            "\n".join(valid_urls)
        )

        self.refresh_table()

        self.status_label.setText(
            f"Đã thêm: {results['added']} | "
            f"Trùng: {results['duplicates']} | "
            f"Lỗi: {results['errors']}"
        )

    def load_txt(self):

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn file TXT",
            "",
            "Text files (*.txt)"
        )

        if not path:
            return

        try:
            with open(
                path, "r", encoding="utf-8-sig"
            ) as file:
                self.url_box.setPlainText(file.read())

            self.status_label.setText(
                "Đã nhập danh sách từ file TXT."
            )

        except Exception as error:
            QMessageBox.critical(
                self, "Lỗi", str(error)
            )

    def fetch_account(self):

        username = self.account_input.text().strip()

        if not username:
            QMessageBox.warning(
                self, "Thông báo",
                "Hãy nhập tên tài khoản TikTok."
            )
            return

        if (
            self.account_worker
            and self.account_worker.isRunning()
        ):
            return

        self.account_button.setEnabled(False)
        self.status_label.setText(
            "Đang lấy danh sách video tài khoản..."
        )

        self.account_worker = AccountWorker(
            username,
            self.limit_input.value()
        )

        self.account_worker.finished_links.connect(
            self.account_finished
        )
        self.account_worker.failed.connect(
            self.account_failed
        )
        self.account_worker.finished.connect(
            lambda: self.account_button.setEnabled(True)
        )

        self.account_worker.start()

    def account_finished(self, links):

        self.url_box.setPlainText(
            "\n".join(links)
        )

        self.status_label.setText(
            f"Đã tìm thấy {len(links)} video. "
            "Kiểm tra danh sách rồi bấm thêm link."
        )

    def account_failed(self, message):

        self.status_label.setText(
            "Không lấy được danh sách tài khoản."
        )

        QMessageBox.warning(
            self,
            "Lỗi lấy video",
            message
        )

    def choose_folder(self):

        folder = QFileDialog.getExistingDirectory(
            self,
            "Chọn thư mục lưu video",
            self.download_folder
        )

        if not folder:
            return

        self.download_folder = folder
        self.folder_input.setText(folder)

        self.settings["output_dir"] = folder
        self.security.save_settings(self.settings)

        QMessageBox.information(
            self,
            "Thông báo",
            "Đã lưu thư mục cho lần chạy sau.\n"
            "Thư mục mới sẽ áp dụng cho bộ tải sau khi "
            "khởi động lại chương trình."
        )

    def open_folder(self):

        folder = Path(self.download_folder)
        folder.mkdir(parents=True, exist_ok=True)

        QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(folder))
        )

    def selected_id(self):

        row = self.table.currentRow()

        if row < 0:
            return None

        item = self.table.item(row, 0)

        if not item:
            return None

        try:
            return int(item.text())
        except ValueError:
            return None

    def pause_selected(self):

        task_id = self.selected_id()

        if task_id is None:
            return

        if self.manager.pause(task_id):
            self.status_label.setText(
                "Đã gửi yêu cầu tạm dừng."
            )

        self.refresh_table()

    def resume_selected(self):

        task_id = self.selected_id()

        if task_id is None:
            return

        if self.manager.resume(task_id):
            self.status_label.setText(
                "Đã gửi yêu cầu tiếp tục."
            )

        self.refresh_table()

    def cancel_selected(self):

        task_id = self.selected_id()

        if task_id is None:
            return

        answer = QMessageBox.question(
            self,
            "Xác nhận",
            "Bạn muốn hủy tác vụ này?"
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        self.manager.cancel(task_id)
        self.refresh_table()

    def refresh_table(self):

        tasks = self.manager.database.list_tasks()

        self.table.setRowCount(len(tasks))

        for row, task in enumerate(tasks):

            values = [
                str(task["id"]),
                task.get("url", ""),
                task.get("status", ""),
                f"{task.get('progress', 0)}%",
                task.get("file_path", "")
            ]

            for column, value in enumerate(values):

                item = QTableWidgetItem(value)

                if column == 0:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter
                    )

                self.table.setItem(row, column, item)

    def export_excel(self):

        tasks = self.manager.database.export_rows()

        if not tasks:
            QMessageBox.information(
                self, "Thông báo",
                "Chưa có lịch sử để xuất Excel."
            )
            return

        default_path = str(
            Path.home() / "Downloads" /
            "TikTok_History.xlsx"
        )

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Lưu file Excel",
            default_path,
            "Excel (*.xlsx)"
        )

        if not path:
            return

        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        try:
            saved = self.exporter.export(
                tasks,
                path
            )

            QMessageBox.information(
                self,
                "Thành công",
                f"Đã xuất Excel:\n{saved}"
            )

        except Exception as error:
            QMessageBox.critical(
                self, "Lỗi xuất Excel", str(error)
            )

    def closeEvent(self, event):

        answer = QMessageBox.question(
            self,
            "Thoát chương trình",
            "Bạn có muốn thoát không? "
            "Các tác vụ đang chạy sẽ bị yêu cầu hủy."
        )

        if answer != QMessageBox.StandardButton.Yes:
            event.ignore()
            return

        self.timer.stop()

        if (
            self.account_worker
            and self.account_worker.isRunning()
        ):
            self.account_worker.wait(3000)

        self.manager.downloader.shutdown(wait=False)

        event.accept()


if __name__ == "__main__":

    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())
