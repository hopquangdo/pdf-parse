import io

import openpyxl
from PIL import Image, ImageDraw

from src.application.ocr_service import OcrService
from src.domain.numbers import parse_vn_number
from src.infrastructure.excel.table_writer import rows_to_xlsx, sheets_to_xlsx
from src.infrastructure.vision.table_chunks import split_rows


class FakeTableReader:
    """ask_json answers from a list of canned answers, one per call, and records the prompts it was given."""
    def __init__(self, answers):
        self.answers, self.prompts = list(answers), []

    def ask_json(self, png, prompt, label=""):
        self.prompts.append((label, prompt))
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a


def blank(w=800, h=400):
    return Image.new("RGB", (w, h), "white")


def tall_table(rows=120, w=1000):
    """A tall image of text-like lines separated by white gaps, to be cut into several bands."""
    im = Image.new("RGB", (w, rows * 40), "white")
    d = ImageDraw.Draw(im)
    for r in range(rows):
        d.rectangle([100, r * 40 + 10, 100 + w // 4, r * 40 + 26], fill="black")
    return im


def test_vietnamese_numbers():
    assert parse_vn_number("1.849,51") == 1849.51
    assert parse_vn_number("0,040") == 0.04
    assert parse_vn_number("13.726,0") == 13726.0
    assert parse_vn_number("-") is None and parse_vn_number("Thép CT3") is None


def test_single_image_table_keeps_header_and_pads_ragged_rows():
    reader = FakeTableReader([{"columns": 3, "rows": [["STT", "Tên", "KL"], ["1", "Thép", "2,5"], ["2", "Bu lông"]]}])
    res = OcrService(reader).table(blank())
    assert res.rows == [["STT", "Tên", "KL"], ["1", "Thép", "2,5"], ["2", "Bu lông", ""]]
    assert any("2" not in w and "số ô" in w for w in res.warnings) or any("số ô" in w for w in res.warnings)
    assert "Chép cả dòng tiêu đề" in reader.prompts[0][1]


def test_tall_table_is_read_in_bands_and_joined_in_order():
    im = tall_table()
    _, spans = split_rows(im)
    assert len(spans) > 1 and spans[0][0] < spans[1][0] and spans[-1][1] == im.height     # contiguous, top to bottom
    answers = [{"rows": [[f"band{i}", "x"]]} for i in range(len(spans))]
    reader = FakeTableReader(answers)
    res = OcrService(reader, workers=1).table(im)
    assert [r[0] for r in res.rows] == [f"band{i}" for i in range(len(spans))]
    assert "Chép cả dòng tiêu đề" in reader.prompts[0][1] and "KHÔNG chép lại" in reader.prompts[1][1]


def test_failed_band_is_reported_not_silent():
    im = tall_table()
    _, spans = split_rows(im)
    answers = [{"rows": [["a"]]}] + [ValueError("no JSON")] * 3 + [{"rows": [["c"]]}] * (len(spans) - 2)
    res = OcrService(FakeTableReader(answers), workers=1).table(im)
    assert any("không đọc được" in w for w in res.warnings) and res.rows[0] == ["a"]


def test_text_is_returned():
    reader = FakeTableReader([{"text": "KHỐI LƯỢNG | 1.849,51"}])
    assert OcrService(reader).text(blank()) == "KHỐI LƯỢNG | 1.849,51"


def test_rotation_is_the_model_pick_among_four_turns():
    page = tall_table(rows=60, w=1000)
    for letter, deg in (("A", 0), ("B", 90), ("C", 180), ("D", 270)):
        assert OcrService(FakeTableReader([{"upright": letter}])).detect_rotation(page) == deg


def test_explicit_rotation_turns_the_image_clockwise():
    assert OcrService(FakeTableReader([])).rotate(Image.new("RGB", (400, 100)), 90).size == (100, 400)
    out = OcrService(FakeTableReader([{"upright": "D"}])).rotate(Image.new("RGB", (400, 100)), "auto")
    assert out.size == (100, 400)                            # 270 degrees swaps width and height


def test_later_bands_are_told_the_column_count_of_the_first():
    im = tall_table()
    _, spans = split_rows(im)
    reader = FakeTableReader([{"rows": [["STT", "Tên", "KL"], ["1", "x", "2"]]}] + [{"rows": [["2", "y", "3"]]}] * (len(spans) - 1))
    OcrService(reader, workers=1).table(im)
    assert "ĐÚNG 3 cột" not in reader.prompts[0][1] and all("ĐÚNG 3 cột" in p for _, p in reader.prompts[1:])


def test_xlsx_numbers_text_and_flags():
    data = rows_to_xlsx([["Tên", "KL"], ["Thép", "1.849,51"], ["Mã", "007"]], title="Bảng", flags={(1, 1): "kiểm tra"})
    ws = openpyxl.load_workbook(io.BytesIO(data)).active
    assert ws["A1"].value == "Bảng"
    assert ws["B4"].value == 1849.51 and ws["B5"].value == "007"          # a number stays a number, a code stays text
    assert ws["B4"].comment.text == "kiểm tra"


def test_a_band_the_model_cannot_finish_is_split_in_two_and_joined():
    im = tall_table(rows=40)                          # one band at this size, so the only way out is halving
    reader = FakeTableReader([ValueError("cut off"), {"rows": [["top"]]}, {"rows": [["low"]]}])
    res = OcrService(reader, workers=1).table(im, chunk_ratio=5)
    assert [r[0] for r in res.rows] == ["top", "low"] and not res.warnings
    assert "KHÔNG chép lại" in reader.prompts[2][1] and "KHÔNG chép lại" not in reader.prompts[1][1]


def test_sheet_styling_caption_header_groups_and_precision():
    rows = [["BẢNG THỐNG KÊ", "", "", ""], ["STT", "Tên", "SL", "KL"], ["1", "Thép", "3", "0,040"], ["", "TỔNG CỘNG", "", "1.849,50"]]
    ws = openpyxl.load_workbook(io.BytesIO(sheets_to_xlsx([("T", rows)]))).active
    assert ws["A1"].font.bold and not ws["A1"].border.left.style           # caption: bold, no grid
    assert ws["A2"].font.bold and ws["A2"].fill.fgColor.rgb.endswith("1F4E78") and ws["A2"].border.left.style   # header
    assert ws["D3"].number_format == "#,##0.000" and ws["D3"].alignment.horizontal == "right"                  # keeps the printed precision
    assert ws["B4"].font.bold and ws["B4"].fill.fgColor.rgb.endswith("BDD7EE")                                  # total row
    assert ws.freeze_panes == "A3"
    data = [["A", "B"], ["x", "y"]]                                        # no caption: the first row is the header
    assert openpyxl.load_workbook(io.BytesIO(sheets_to_xlsx([("T", data)]))).active["A1"].fill.fgColor.rgb.endswith("1F4E78")
