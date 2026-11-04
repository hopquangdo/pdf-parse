"""OCR of a document image: plain text, or a table as rows of cells (and an Excel file). Model-agnostic via TableReader."""
import contextvars
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import List, Sequence

from PIL import Image, ImageDraw, ImageFont

from src.domain.ports import TableReader
from src.infrastructure.excel.table_writer import rows_to_xlsx
from src.infrastructure.prompts import load_prompt, render_prompt
from src.infrastructure.vision.table_chunks import band_png, line_gaps, split_rows

ROTATIONS = (0, 90, 180, 270)


@dataclass
class TableResult:
    rows: List[List[str]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    chunks: int = 0

    def xlsx(self, title: str = "", header_rows: int = 1) -> bytes:
        return rows_to_xlsx(self.rows, title=title, header_rows=header_rows)


def _png(im: Image.Image, longest: int = 2600) -> bytes:
    import io
    im = im.copy()
    im.thumbnail((longest, longest))
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "PNG", optimize=True)
    return buf.getvalue()


class OcrService:
    def __init__(self, reader: TableReader, workers: int = 4, retries: int = 3):
        self.reader, self.workers, self.retries = reader, workers, retries

    # ------------------------------------------------------------------ orientation
    def rotate(self, im: Image.Image, rotate) -> Image.Image:
        """rotate = 0/90/180/270 (clockwise, as you would turn the page) or 'auto' (the model says which turn is needed)."""
        deg = self.detect_rotation(im) if str(rotate) == "auto" else int(rotate)
        if deg not in ROTATIONS:
            raise ValueError("rotate phải là 0, 90, 180, 270 hoặc auto")
        return im.rotate(-deg, expand=True) if deg else im

    def detect_rotation(self, im: Image.Image) -> int:
        """Clockwise turn (0/90/180/270) that makes the text upright: the model sees all four turns at once and picks one."""
        small = im.copy()
        small.thumbnail((1200, 1200))
        cell = 1000
        sheet = Image.new("RGB", (cell * 2 + 20, cell * 2 + 20), "white")
        for k, deg in enumerate(ROTATIONS):
            t = small.rotate(-deg, expand=True)
            t.thumbnail((cell, cell))
            x, y = (k % 2) * (cell + 20), (k // 2) * (cell + 20)
            sheet.paste(t, (x, y))
            ImageDraw.Draw(sheet).text((x + 8, y + 4), "ABCD"[k], fill="red", font=ImageFont.load_default(size=64))
        ans = self.reader.ask_json(_png(sheet, 2200), load_prompt("ocr_orientation"), "ocr_orientation")
        pick = str(ans.get("upright", "A")).strip().upper()[:1] if isinstance(ans, dict) else "A"
        return ROTATIONS["ABCD".index(pick)] if pick in "ABCD" else 0

    # ------------------------------------------------------------------ text
    def text(self, im: Image.Image) -> str:
        ans = self._ask(_png(im), load_prompt("ocr_text"), "ocr_text")
        return str(ans.get("text", "")) if isinstance(ans, dict) else ""

    # ------------------------------------------------------------------ table
    def table(self, im: Image.Image, header_frac: float = 0.05, chunk_ratio: float = 0.24,
              columns: Sequence[str] | None = None) -> TableResult:
        """columns: optional names of the table's columns (for a table type you know). Cells drawn as several small boxes
        (e.g. "60 x 5,5") are then merged into the one column they belong to."""
        header_h, spans = split_rows(im, header_frac, chunk_ratio)
        pngs = [band_png(im, header_h, a, b) for a, b in spans]
        ctx = contextvars.copy_context()  # keep the usage scope inside the pool threads

        later_note = "Phía trên cùng của ảnh là dòng tiêu đề cột chỉ để tham chiếu cột: KHÔNG chép lại nó, chỉ chép các dòng dữ liệu bên dưới."

        def prompt_for(i: int, first: bool, pin: str) -> str:
            part = "toàn bộ bảng" if len(spans) == 1 else f"phần {i + 1}/{len(spans)} của một bảng dài"
            if columns:
                return render_prompt("ocr_table_columns", columns=json.dumps(list(columns), ensure_ascii=False), part=part,
                                     header_note="Dòng tiêu đề cột ở trên cùng ảnh chỉ để tham chiếu, KHÔNG chép lại nó.")
            note = "Chép cả dòng tiêu đề cột." if first else later_note
            return render_prompt("ocr_table", columns_note="", part=part, header_note=note + pin)

        def one(i: int, pin: str = ""):
            first = i == 0 or len(spans) == 1
            y0, y1 = spans[i]
            return ctx.copy().run(self._read_band, im, header_h, y0, y1, lambda f: prompt_for(i, first and f, pin),
                                  f"ocr_table_{i + 1}of{len(spans)}", pngs[i])

        answers = [self._safe(one, 0)]          # the first band fixes the column grid for all the others
        grid = answers[0][0].get("rows") if isinstance(answers[0][0], dict) else None
        pin = ""
        if grid and not columns:
            n = max(len(r) for r in grid if isinstance(r, list))
            pin = f" Bảng này có ĐÚNG {n} cột theo lưới của dòng tiêu đề: mỗi dòng phải có đúng {n} ô, ô nào trống thì để \"\"; chữ nằm ở cột nào thì đặt đúng ô của cột đó."
        with ThreadPoolExecutor(self.workers) as ex:
            answers += list(ex.map(lambda i: self._safe(lambda j: one(j, pin), i), range(1, len(spans))))
        out = TableResult(chunks=len(spans))
        if columns:
            out.rows.append(list(columns))      # the header row, written once
        for i, (ans, err) in enumerate(answers, 1):
            rows = ans.get("rows") if isinstance(ans, dict) else None
            if err or not isinstance(rows, list):
                out.warnings.append(f"Đoạn {i}/{len(spans)} không đọc được ({err or 'không có rows'}); thiếu các dòng của đoạn này")
                continue
            for r in rows:
                if isinstance(r, dict):          # keyed by column name: put every cell in its own column
                    out.rows.append([str(r.get(c, "") if r.get(c) is not None else "") for c in columns or []])
                elif isinstance(r, list):
                    out.rows.append([str(c if c is not None else "") for c in r])
        width = max((len(r) for r in out.rows), default=0)
        ragged = sum(len(r) != width for r in out.rows)
        if ragged:
            out.warnings.append(f"{ragged} dòng có số ô khác số cột ({width}); đã bù ô trống, nên kiểm tra các dòng này")
            out.rows = [r + [""] * (width - len(r)) for r in out.rows]
        if not out.rows:
            out.warnings.append("Không đọc được dòng nào")
        return out

    # ------------------------------------------------------------------ helpers
    def _read_band(self, im: Image.Image, header_h: int, y0: int, y1: int, prompt, label: str, png: bytes | None = None, depth: int = 0):
        """Read one band. A band the model cannot finish (the answer is cut off or is not JSON) is split in two at a white gap
        near its middle and each half is read on its own, so a dense table degrades into more calls instead of a lost band.
        prompt(first_half) -> the prompt; only the first half of the first band copies the header row."""
        splittable = depth < 2 and y1 - y0 >= 500
        try:                                          # one attempt is enough when a split is the next step
            return self._ask(png or band_png(im, header_h, y0, y1), prompt(True), label, tries=1 if splittable else self.retries)
        except (ValueError, json.JSONDecodeError):
            if not splittable:
                raise
        mid = (y0 + y1) // 2
        gaps = [c for c in line_gaps(im.crop((0, y0, im.width, y1))) if abs(c - (mid - y0)) < (y1 - y0) // 4]
        if gaps:
            mid = y0 + min(gaps, key=lambda c: abs(c - (mid - y0)))
        top = self._read_band(im, header_h, y0, mid, prompt, f"{label}a", None, depth + 1)
        low = self._read_band(im, header_h, mid, y1, lambda f: prompt(False), f"{label}b", None, depth + 1)
        rows = [*(top.get("rows") or []), *(low.get("rows") or [])] if isinstance(top, dict) and isinstance(low, dict) else None
        if rows is None:
            raise ValueError("không ghép được hai nửa đoạn")
        return {"rows": rows}

    def _ask(self, png: bytes, prompt: str, label: str, tries: int | None = None):
        last = None
        for _ in range(tries or self.retries):
            try:
                return self.reader.ask_json(png, prompt, label)
            except (ValueError, json.JSONDecodeError) as e:   # the model answered, but not with usable JSON: ask again
                last = e
        raise last

    @staticmethod
    def _safe(fn, i):
        try:
            return fn(i), None
        except Exception as e:  # noqa: BLE001 - one band failing must not lose the rest
            return None, f"{type(e).__name__}: {str(e)[:100]}"
