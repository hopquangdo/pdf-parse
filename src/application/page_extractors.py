"""Ways to read every table of one PDF page into rows of cells. The OCR job picks one (config OCR_ENGINE); both return OcrTable.

* LlmPageExtractor   a language model reads each table image (slow per table, no extra packages).
* LocalPageExtractor ruling lines give the cells, VietOCR reads each cell, rules repair numbers; the language model, when given, only
                     re-reads the cells the rules doubt and takes over a table that is too poor to read cell by cell.
"""
from typing import Dict, List, Optional

from PIL import Image

from src.application.cell_llm_fix import LlmCellFixer
from src.application.ocr_service import OcrService
from src.application.table_postprocess import repair
from src.domain.models import OcrTable
from src.infrastructure.pdf.page_image import load_page, render_page
from src.infrastructure.vision.cell_ocr import (CellReader, clean_rows, deskew, find_cells, fix_sizes, horizontal_votes, median_height,
                                                merge_header)
from src.infrastructure.vision.table_regions import find_tables

MIN_CELLS = 6                  # a boxed drawing detail has a few cells at most; a table has many
MIN_FILL = 0.5                 # a table's cells nearly fill its rows x columns grid; a drawing's boxes leave most of it empty
BAD_SHARE = 0.12               # share of cells breaking a rule above which a table goes to the language model whole


def table_name(page: int, k: int, total: int) -> str:
    return f"Trang {page}" if total == 1 else f"Trang {page} - Bảng {k}"


class LlmPageExtractor:
    def __init__(self, ocr: OcrService):
        self.ocr = ocr

    def extract(self, pdf: bytes, page: int, rotate="auto") -> List[OcrTable]:
        sheet = self.ocr.rotate(load_page(pdf, page), rotate)
        boxes = find_tables(sheet) or [(0, 0, sheet.width, sheet.height)]          # no ruled table: read the whole page
        out = []
        for k, box in enumerate(boxes, 1):
            res = self.ocr.table(sheet.crop(box))
            out.append(OcrTable(table_name(page, k, len(boxes)), res.rows, res.warnings))
        return out


class LocalPageExtractor:
    def __init__(self, reader: CellReader, angles: Dict[str, float], ocr: Optional[OcrService] = None, bad_share: float = BAD_SHARE):
        self.reader, self.angles, self.ocr, self.bad_share = reader, angles, ocr, bad_share
        self.fixer = LlmCellFixer(ocr.reader) if ocr else None

    # ------------------------------------------------------------------ orientation
    def upright(self, pdf: bytes, page: int) -> int:
        """Clockwise turn that makes the text upright: text runs horizontally on two turns (by cell shape), and of those the
        recognizer is clearly more confident on the one that is not upside down."""
        small = render_page(pdf, page, 2400)
        votes = {d: horizontal_votes(small.rotate(-d, expand=True), find_tables(small.rotate(-d, expand=True))) for d in (0, 90)}
        flat = 0 if votes[0] >= votes[90] else 90
        mid = render_page(pdf, page, 4800)
        scores = {}
        for d in (flat, flat + 180):
            turned = mid.rotate(-d, expand=True)
            boxes = find_tables(turned)
            biggest = max(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1])) if boxes else None
            scores[d] = self.reader.confidence(turned.crop(biggest), sample=20) if biggest else 0.0
        return max(scores, key=lambda d: scores[d])

    # ------------------------------------------------------------------ one table
    def read_table(self, table: Image.Image, big: Image.Image, crop_box, cells) -> Optional[tuple]:
        """(rows, flags) of one table image, or None when it is not a data table."""
        raw = self.reader.read(table)
        conf, pieces = self.reader.last["conf"], self.reader.last["pieces"]
        rows = fix_sizes(clean_rows(raw))
        if self.fixer:
            for (r, c), text in self.fixer.fix(rows, pieces, self.fixer.pick(rows, conf, set())).items():
                rows[r][c] = text
        merged = merge_header(rows)
        shift = len(rows) - len(merged)
        filled = sum(bool(str(c).strip()) for r in merged for c in r)
        width = max((len(r) for r in merged), default=0)
        if len(merged) < 3 or width < 3 or filled < MIN_CELLS or len(cells) < MIN_FILL * len(merged) * width:
            return None                                       # a stamp, a title-block box or a dimensioned drawing detail
        fixed, flags = repair(merged, self.angles)
        if self.ocr and len(flags) > self.bad_share * max(filled, 1):      # too poor to read cell by cell: the model reads the whole table
            rows = fix_sizes(clean_rows(self.ocr.table(table).rows))
            conf = [[1.0] * len(r) for r in rows]
            merged = merge_header(rows)
            shift = len(rows) - len(merged)
            fixed, flags = repair(merged, self.angles)
        for r, row in enumerate(rows):                        # cells the recognizer doubted and nothing confirmed
            for c, text in enumerate(row):
                if text.strip() and conf[r][c] < 0.6 and 1 <= r - shift < len(fixed) and (r - shift, c) not in flags:
                    flags[(r - shift, c)] = f"độ tin cậy thấp ({conf[r][c]:.2f}): cần soát"
        name = self.reader.caption(big, crop_box, median_height(cells))
        if name:
            fixed, flags = [[name]] + fixed, {(r + 1, c): v for (r, c), v in flags.items()}
        return fixed, flags

    # ------------------------------------------------------------------ one page
    def extract(self, pdf: bytes, page: int, rotate="auto") -> List[OcrTable]:
        with self.reader.lock:                                # VietOCR and its `last` state serve one table at a time
            deg = self.upright(pdf, page) if str(rotate) == "auto" else int(rotate)
            small = render_page(pdf, page, 2400).rotate(-deg, expand=True)
            big = render_page(pdf, page, 8000).rotate(-deg, expand=True)
            k = big.width / small.width
            found = []
            for box in find_tables(small):
                crop_box = tuple(round(v * k) for v in box)
                table = deskew(big.crop(crop_box))
                cells = find_cells(table)
                if len(cells) < MIN_CELLS:
                    continue
                got = self.read_table(table, big, crop_box, cells)
                if got:
                    found.append(got)
        if not found:
            if self.ocr:                                      # no ruled table on the page: the model reads it as a whole
                res = self.ocr.table(self.ocr.rotate(load_page(pdf, page), rotate))
                return [OcrTable(table_name(page, 1, 1), res.rows, res.warnings)]
            raise ValueError("Không tìm thấy bảng nào trên trang này")
        return [OcrTable(table_name(page, i, len(found)), rows, [], {f"{r},{c}": why for (r, c), why in flags.items()})
                for i, (rows, flags) in enumerate(found, 1)]
