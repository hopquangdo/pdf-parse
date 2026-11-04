import io
import threading

import openpyxl
import pymupdf

from src.application.ocr_job_service import OcrJobService
from src.application.page_extractors import LlmPageExtractor, LocalPageExtractor
from src.application.ocr_service import OcrService
from src.domain.models import OcrTable
from src.infrastructure.persistence.json_ocr_repo import JsonOcrRepo
from src.infrastructure.storage.local_storage import LocalStorage
from tests.application.test_ocr_service import FakeTableReader

ANGLES = {"L63x63x5": 4.81}
HEAD = ["STT", "Quy cách", "Số lượng", "C.dài", "Đ.trọng", "Tổng", "Khối lượng"]


def ruled_pdf(rows: int = 5, cols: int = 7) -> bytes:
    """One landscape page with a ruled grid (and nothing else): the lines are all the page-level table finder needs."""
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    x0, y0, x1, y1 = 110, 80, 700, 80 + rows * 50
    for r in range(rows + 1):
        y = y0 + r * (y1 - y0) / rows
        page.draw_line((x0, y), (x1, y), width=1.2)
    for c in range(cols + 1):
        x = x0 + c * (x1 - x0) / cols
        page.draw_line((x, y0), (x, y1), width=1.2)
    return doc.tobytes()


class FakeCellReader:
    """Stands in for VietOCR: returns a fixed grid, as if each cell had been read, with one doubtful cell."""
    def __init__(self, grid):
        self.grid, self.lock, self.last = grid, threading.RLock(), {}

    def read(self, table):
        conf = [[0.97] * len(self.grid[0]) for _ in self.grid]
        conf[2][2] = 0.3
        self.last = {"conf": conf, "pieces": {}}
        return [list(r) for r in self.grid]

    def caption(self, page, box, row_h):
        return "BẢNG THỐNG KÊ"

    def confidence(self, table, sample=12):
        return 0.9


GRID = [HEAD,
        ["1", "L63x63x5x470", "1", "0,470", "13:34", "0,470", "2,26"],       # unit weight misread: the catalog says 4,81
        ["2", "L63x63x5x470", "1", "0,470", "4,81", "0,470", "2,26"],
        ["3", "L63x63x5x470", "1", "0,470", "4,81", "0,470", "2,26"],
        ["4", "L63x63x5x470", "1", "0,470", "4,81", "0,470", "2,26"]]


def test_local_extractor_reads_repairs_and_flags():
    ex = LocalPageExtractor(FakeCellReader(GRID), ANGLES)
    tables = ex.extract(ruled_pdf(), 1, rotate=0)
    assert len(tables) == 1 and tables[0].name == "Trang 1"
    rows = tables[0].rows
    assert rows[0] == ["BẢNG THỐNG KÊ"] and rows[1] == HEAD                      # the name found above the table heads the sheet
    assert rows[2][4] == "4,81"                                                  # repaired from the catalog
    assert "2,4" in tables[0].flags and "4,81" in tables[0].flags["2,4"]         # ... and flagged where it changed (row 2 of the sheet, col 4)
    assert "3,2" in tables[0].flags and "tin cậy" in tables[0].flags["3,2"]      # the doubtful cell is flagged too


def test_a_page_without_a_table_is_an_error_when_no_model_can_take_over():
    doc = pymupdf.open()
    doc.new_page(width=842, height=595)
    try:
        LocalPageExtractor(FakeCellReader(GRID), ANGLES).extract(doc.tobytes(), 1, rotate=0)
        raise AssertionError("expected an error")
    except ValueError as e:
        assert "bảng" in str(e)


def test_llm_extractor_names_each_table_of_the_page():
    reader = FakeTableReader([{"rows": [["A", "B"], ["1", "2"]]}] * 6)
    tables = LlmPageExtractor(OcrService(reader)).extract(ruled_pdf(), 1, rotate=0)
    assert [t.name for t in tables] == ["Trang 1"] and tables[0].rows[1] == ["1", "2"]


class StubExtractor:
    def extract(self, pdf, page, rotate="auto"):
        return [OcrTable(f"Trang {page}", [["STT", "KL"], ["1", "2,5"]], [], {"1,1": "kiểm tra lại"})]


def test_job_workbook_highlights_the_cells_that_need_a_person(tmp_path):
    svc = OcrJobService(StubExtractor(), JsonOcrRepo(tmp_path / "o"), LocalStorage(tmp_path / "f"))
    job = svc.create(ruled_pdf(), "a.pdf", [1], "auto")
    svc.run(job.id)
    job = svc.repo.get(job.id)
    assert job.status == "done" and job.pages[0].tables[0].flags == {"1,1": "kiểm tra lại"}
    ws = openpyxl.load_workbook(io.BytesIO(svc.xlsx(job))).active
    assert ws["B2"].comment.text == "kiểm tra lại" and ws["B2"].fill.fgColor.rgb.endswith("FFF2CC")
