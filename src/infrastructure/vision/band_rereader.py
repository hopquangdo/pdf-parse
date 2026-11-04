"""Đọc lại một dòng bảng ở ảnh phóng to (tiêu đề + dòng đó). Độ phân giải tăng theo mỗi lần thử."""
from typing import Dict, List, Optional

from src.infrastructure.pdf.table_detector import TableBox
from src.infrastructure.pdf.table_geometry import render_row_zoom


class BandRereader:
    DPIS = (400, 600, 800)

    def __init__(self, pdf: bytes, box: TableBox, rotate: int, data_bands: List[int], reader):
        """data_bands[i] = chỉ số dải (trong row_bands) của dòng dữ liệu thứ i."""
        self.pdf, self.box, self.rotate = pdf, box, rotate
        self.data_bands, self.reader = data_bands, reader
        self.errors: List[str] = []

    def __call__(self, idx: int, attempt: int) -> Optional[Dict]:
        dpi = self.DPIS[min(attempt, len(self.DPIS) - 1)]
        try:
            png = render_row_zoom(self.pdf, self.box, self.rotate, self.data_bands[idx], dpi=dpi)
            return self.reader.read_row(png, label=f"row{idx}@{dpi}dpi")
        except Exception as e:  # noqa: BLE001 - một dòng lỗi không làm hỏng cả bảng
            self.errors.append(f"dòng {idx} lần {attempt}: {type(e).__name__}: {str(e)[:100]}")
            return None
