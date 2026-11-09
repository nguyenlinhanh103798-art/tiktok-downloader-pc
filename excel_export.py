
from pathlib import Path
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter


class ExcelExporter:
    """Xuất lịch sử tải video TikTok ra Excel."""

    HEADERS = [
        "STT",
        "Đường link TikTok",
        "Tên video",
        "Trạng thái",
        "Tiến độ (%)",
        "Đường dẫn file",
        "Lỗi",
        "Ngày tạo",
        "Cập nhật lần cuối"
    ]

    def export(self, tasks, output_path=None):
        if not tasks:
            raise ValueError("Không có dữ liệu để xuất Excel.")

        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = (
                Path.home() / "Downloads" /
                f"TikTok_History_{timestamp}.xlsx"
            )

        output_path = Path(output_path)
        output_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Lich su tai"

        sheet.append(self.HEADERS)

        for index, task in enumerate(tasks, start=1):
            sheet.append([
                index,
                task.get("url", ""),
                task.get("title", ""),
                task.get("status", ""),
                task.get("progress", 0),
                task.get("file_path", ""),
                task.get("error", ""),
                task.get("created_at", ""),
                task.get("updated_at", "")
            ])

        # Định dạng hàng tiêu đề
        for cell in sheet[1]:
            cell.font = Font(
                bold=True,
                color="FFFFFF"
            )
            cell.fill = PatternFill(
                fill_type="solid",
                fgColor="1877F2"
            )
            cell.alignment = Alignment(
                horizontal="center",
                vertical="center"
            )

        # Định dạng dữ liệu
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(
                    vertical="center"
                )

        # Độ rộng cột
        widths = [
            8, 45, 35, 18, 14, 55, 45, 22, 22
        ]

        for index, width in enumerate(widths, start=1):
            sheet.column_dimensions[
                get_column_letter(index)
            ].width = width

        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions

        workbook.save(output_path)

        return str(output_path)
