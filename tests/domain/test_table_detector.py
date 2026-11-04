from src.infrastructure.pdf.table_detector import detect_tables
from tests.conftest import PDF


def test_member_tables_found_and_drawing_pages_clean():
    pdf = PDF.read_bytes()
    assert len(detect_tables(pdf, 6)) == 1   # bảng thanh L50x5 đoạn B
    assert len(detect_tables(pdf, 8)) == 1   # bảng thanh đoạn C
    for page in (3, 4, 5, 7):                # trang hình vẽ: mặt cắt vuông không được nhận nhầm là bảng
        assert detect_tables(pdf, page) == []
