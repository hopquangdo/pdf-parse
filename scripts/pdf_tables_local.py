"""Pages of a PDF -> one Excel sheet per table, with NO language model: ruling lines + VietOCR.

  python scripts/pdf_tables_local.py "file.pdf" 14,31 out.xlsx

Per page: render -> find the upright turn -> find the tables by their ruling lines -> cut each table out of a high-resolution
render -> read it cell by cell (rows that a broken line glued together are cut apart again) -> read the table's name from the
line above it -> Excel.
"""
import sys
import time
from pathlib import Path

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src import config  # noqa: E402
from src.application.cell_llm_fix import LlmCellFixer  # noqa: E402
from src.application.table_postprocess import repair  # noqa: E402
from src.infrastructure.excel.catalog import load_catalog  # noqa: E402
from src.infrastructure.excel.table_writer import sheets_to_xlsx  # noqa: E402
from src.infrastructure.vision.cell_ocr import CellReader, clean_rows, deskew, find_cells, fix_sizes, horizontal_votes, median_height, merge_header  # noqa: E402
from src.infrastructure.vision.table_regions import find_tables  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
SIDE = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--side=")), 8000))     # long side of the render the tables are cut from
MIN_FILL = 0.5                # a table's cells nearly fill its rows x columns grid; a drawing's boxes leave most of it empty
BAD_SHARE = 0.12              # share of cells that break a rule above which the table goes to the language model whole (the recognizer's own confidence is not a reliable sign: it stays high on a blurry scan)
MIN_TEXT_CELLS = 6            # a boxed drawing detail has a few cells at most; a table has many


def render(pdf: Path, page: int, long_side: int) -> Image.Image:
    with pymupdf.open(pdf) as doc:
        pg = doc[page - 1]
        dpi = int(long_side / (max(pg.rect.width, pg.rect.height) / 72))
        pix = pg.get_pixmap(dpi=dpi)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def upright(reader: CellReader, pdf: Path, page: int) -> int:
    """Clockwise turn that makes the text upright: text runs horizontally on two turns (by cell shape), and of those the
    recognizer is clearly more confident on the one that is not upside down."""
    small = render(pdf, page, 2400)
    votes = {d: horizontal_votes(small.rotate(-d, expand=True), find_tables(small.rotate(-d, expand=True))) for d in (0, 90)}
    flat = 0 if votes[0] >= votes[90] else 90
    mid = render(pdf, page, 4800)
    scores = {}
    for d in (flat, flat + 180):
        turned = mid.rotate(-d, expand=True)
        boxes = find_tables(turned)
        biggest = max(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1])) if boxes else None
        scores[d] = reader.confidence(turned.crop(biggest), sample=20) if biggest else 0.0
    best = max(scores, key=lambda d: (scores[d] == scores[d], scores[d]))     # a NaN (nothing readable) never wins
    print(f"  turn: votes {votes} confidence { {d: round(v, 2) for d, v in scores.items()} } -> {best}", flush=True)
    return best


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    pdf, pages, out = Path(args[0]), [int(p) for p in args[1].split(",")], Path(args[2])
    reader = CellReader(super_res="--sr" in sys.argv)
    fixer, whole = None, None
    if "--llm" in sys.argv:                                   # optional: unsure cells, and tables too blurry to rely on, go to the language model
        import os
        from src.application.ocr_service import OcrService
        from src.infrastructure.vision.table_reader import TableVisionReader
        llm = TableVisionReader(os.environ["LLM_API_KEY"], config.LLM_MODEL_NAME)
        fixer, whole = LlmCellFixer(llm), OcrService(llm)
    angles = dict(load_catalog(config.TEMPLATE_XLSM)["angles"])
    sheets, t0 = [], time.time()
    for page in pages:
        print(f"page {page}", flush=True)
        deg = upright(reader, pdf, page)
        small = render(pdf, page, 2400).rotate(-deg, expand=True)
        big = render(pdf, page, SIDE).rotate(-deg, expand=True)
        k = big.width / small.width
        n = 0
        for box in find_tables(small):
            crop_box = tuple(round(v * k) for v in box)
            table = deskew(big.crop(crop_box))
            cells = find_cells(table)
            if len(cells) < MIN_TEXT_CELLS:
                continue
            t = time.time()
            raw = reader.read(table)
            conf, pieces = reader.last["conf"], reader.last["pieces"]
            rows = fix_sizes(clean_rows(raw))
            llm_n = 0
            if fixer:
                todo = fixer.pick(rows, conf, set())
                for (r, c), text in fixer.fix(rows, pieces, todo).items():
                    rows[r][c] = text
                llm_n = len(todo)
            merged = merge_header(rows)
            shift = len(rows) - len(merged)                   # rows folded into the header: later rows move up by this much
            filled = sum(bool(str(c).strip()) for r in merged for c in r)
            slots = len(merged) * max((len(r) for r in merged), default=0)
            if len(merged) < 3 or max((len(r) for r in merged), default=0) < 3 or filled < MIN_TEXT_CELLS or len(cells) < MIN_FILL * slots:
                continue                                      # a stamp, a title-block box or a dimensioned drawing detail, not a data table
            fixed, flags = repair(merged, angles)
            if whole and len(flags) > BAD_SHARE * max(filled, 1):      # many cells break a rule: the scan is too poor for cell-by-cell reading
                rows = fix_sizes(clean_rows(whole.table(table).rows))
                conf = [[1.0] * len(r) for r in rows]
                merged = merge_header(rows)
                shift, llm_n = len(rows) - len(merged), -1
                fixed, flags = repair(merged, angles)
            for r, row in enumerate(rows):                    # cells the recognizer itself doubted and nothing could confirm
                for c, text in enumerate(row):
                    if text.strip() and conf[r][c] < 0.6 and r - shift >= 1 and (r - shift, c) not in flags and 0 <= r - shift < len(fixed):
                        flags[(r - shift, c)] = f"độ tin cậy thấp ({conf[r][c]:.2f}): cần soát"
            n += 1
            name = reader.caption(big, crop_box, median_height(cells))
            if name:
                fixed, flags = [[name]] + fixed, {(r + 1, c): v for (r, c), v in flags.items()}
            sheets.append((f"T{page}-{n}", fixed, flags))
            print(f"  table {n}: {len(fixed)} rows x {max(len(r) for r in fixed)} cols, {len(cells)} cells, {len(flags)} flagged, {llm_n} to the model (-1: whole table), {time.time() - t:.0f}s | {name[:50]!r}", flush=True)
    out.write_bytes(sheets_to_xlsx(sheets))
    print(f"-> {out}  {len(sheets)} sheets, total {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
