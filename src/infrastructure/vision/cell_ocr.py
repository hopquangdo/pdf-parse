"""Read a ruled table cell by cell with a local recognizer (VietOCR): no language model.

The ruling lines give the cells, the shared cell edges give each cell its row and column (a merged cell lands in the first
row and column of its span), and the recognizer only has to read one short piece of text at a time.
"""
import os
import re
import threading
from typing import List, Tuple

import numpy as np
from PIL import Image, ImageFilter, ImageOps
from scipy import ndimage

from src.infrastructure.vision.table_regions import _lines

Cell = Tuple[int, int, int, int]
INSET = 7                      # px cut off every side of a cell so the cell border never reaches the recognizer (it reads as a '1')
WORK = 2400                    # lines are found on a copy this wide, the boxes are scaled back to the full image


def skew_angle(table: Image.Image, limit: float = 2.0, step: float = 0.1) -> float:
    """Degrees the scan is turned (counter-clockwise positive): the angle at which the horizontal rules are sharpest."""
    k = min(1.0, 900 / table.width)
    g = np.asarray(table.convert("L").resize((max(1, round(table.width * k)), max(1, round(table.height * k))))) < 150
    img = Image.fromarray((g * 255).astype(np.uint8))
    best, best_score = 0.0, -1.0
    for a in np.arange(-limit, limit + 1e-9, step):
        rows = np.asarray(img.rotate(float(a), resample=Image.BILINEAR)).astype(np.float32).sum(axis=1)
        score = float(np.square(np.diff(rows)).sum())
        if score > best_score:
            best, best_score = float(a), score
    return best


def deskew(table: Image.Image, min_angle: float = 0.25) -> Image.Image:
    """The table turned back by its skew (white fill); left as it is when the skew is negligible."""
    a = skew_angle(table)
    return table if abs(a) < min_angle else table.rotate(a, resample=Image.BICUBIC, expand=False, fillcolor=(255, 255, 255))


def inner(c: Cell) -> Cell:
    """The cell without its border: INSET px off each side, but never more than a quarter of a small cell."""
    x0, y0, x1, y1 = c
    px, py = min(INSET, (x1 - x0) // 4), min(INSET, (y1 - y0) // 4)
    return x0 + px, y0 + py, x1 - px, y1 - py


def find_cells(table: Image.Image, close_frame: bool = False) -> List[Cell]:
    """The white regions enclosed by ruling lines (x0, y0, x1, y1 on the full image)."""
    k = min(1.0, WORK / table.width)
    small = table.resize((round(table.width * k), round(table.height * k)), Image.LANCZOS) if k < 1 else table
    ink = np.asarray(small.convert("L")) < 150
    H, W = ink.shape
    hl, vl = _lines(ink, max(20, W // 60), True), _lines(ink, max(20, H // 80), False)
    grid = hl | vl
    # Draw the outermost lines solid from end to end: a scan often breaks the outer border, and the last column would leak into the margin.
    cols, rows = np.where(hl.any(axis=0))[0], np.where(vl.any(axis=1))[0]      # the table spans as far as its rules do: horizontal rules give left/right, vertical rules top/bottom
    if close_frame and len(cols) and len(rows):
        for x in (cols.min(), cols.max()):
            grid[rows.min(): rows.max() + 1, max(0, x - 1): x + 2] = True
        for y in (rows.min(), rows.max()):
            grid[max(0, y - 1): y + 2, cols.min(): cols.max() + 1] = True
    grid = ndimage.binary_dilation(grid, iterations=1)
    lab, _ = ndimage.label(~grid)
    cells = []
    for sl in ndimage.find_objects(lab):
        w, h = sl[1].stop - sl[1].start, sl[0].stop - sl[0].start
        if w < 12 or h < 12 or w > 0.9 * W or h > 0.9 * H:           # sliver, or the page margin around the table
            continue
        cells.append((round(sl[1].start / k), round(sl[0].start / k), round(sl[1].stop / k), round(sl[0].stop / k)))
    return _split_glued(table, cells)


def median_height(cells: List[Cell]) -> float:
    return float(np.median([c[3] - c[1] for c in cells])) if cells else 0.0


def text_lines(ink: np.ndarray, merge: int) -> List[Tuple[int, int]]:
    """(top, bottom) of every line of text in a block of ink, lines closer than `merge` px counting as one."""
    rows = np.where(ink.any(axis=1))[0]
    if not len(rows):
        return []
    lines = [[rows[0], rows[0]]]
    for y in rows[1:]:
        if y - lines[-1][1] <= merge:
            lines[-1][1] = y
        else:
            lines.append([y, y])
    return [(a, b) for a, b in lines if b - a >= max(4, merge)]


def _split_glued(table: Image.Image, cells: List[Cell]) -> List[Cell]:
    """A cell several rows tall that holds one line of text per row is two or more rows glued by a missing ruling line: cut it
    between the lines. A tall cell with a single centred line (a vertically merged cell) is left alone."""
    med = median_height(cells)
    out: List[Cell] = []
    for x0, y0, x1, y1 in cells:
        if y1 - y0 < 1.7 * med:
            out.append((x0, y0, x1, y1))
            continue
        ink = np.asarray(table.crop((x0 + 3, y0 + 3, x1 - 3, y1 - 3)).convert("L")) < 150
        lines = text_lines(ink, merge=int(0.25 * med))
        if len(lines) >= 2 and 0.6 * med <= (y1 - y0) / len(lines) <= 1.5 * med:
            cuts = [y0] + [y0 + 3 + (lines[i][1] + lines[i + 1][0]) // 2 for i in range(len(lines) - 1)] + [y1]
            out.extend((x0, a, x1, b) for a, b in zip(cuts, cuts[1:]))
        else:
            out.append((x0, y0, x1, y1))
    return out


def _centres(values: List[int], tol: float) -> List[float]:
    groups: List[List[int]] = []
    for v in sorted(values):
        if groups and v - groups[-1][-1] <= tol:
            groups[-1].append(v)
        else:
            groups.append([v])
    return [float(np.mean(g)) for g in groups]


def place(cells: List[Cell], tol: float | None = None) -> Tuple[List[Tuple[Cell, int, int]], int, int]:
    """[(cell, row, column)] from the shared edges of the cells, and the grid size."""
    tol = tol or max(10.0, 0.22 * median_height(cells))
    xs, ys = _centres([c[0] for c in cells], tol), _centres([c[1] for c in cells], tol)
    near = lambda grid, v: int(np.argmin([abs(g - v) for g in grid]))
    return [(c, near(ys, c[1]), near(xs, c[0])) for c in cells], len(ys), len(xs)


def tight(crop: Image.Image, margin: int = 4) -> Image.Image | None:
    """The cell cut down to its text (a tall merged cell would otherwise be squashed to a sliver); None when it holds no text."""
    ink = np.asarray(crop.convert("L")) < 150
    if ink.mean() < 0.004:
        return None
    ys, xs = np.where(ink)
    return crop.crop((max(0, xs.min() - margin), max(0, ys.min() - margin), min(crop.width, xs.max() + margin + 1), min(crop.height, ys.max() + margin + 1)))


class SuperResolver:
    """Doubles the resolution of a small cell picture with EDSR (a learned upscaler: it redraws strokes instead of smearing them).
    Loaded on first use; needs the `super-image` package."""

    def __init__(self, scale: int = 2):
        self.scale, self._model = scale, None

    def __call__(self, piece: Image.Image) -> Image.Image:
        import torch
        from super_image import EdsrModel, ImageLoader
        if self._model is None:
            self._model = EdsrModel.from_pretrained("eugenesiow/edsr-base", scale=self.scale).eval()
        with torch.no_grad():
            out = self._model(ImageLoader.load_image(piece.convert("RGB")))
        arr = (out.squeeze(0).clamp(0, 1).permute(1, 2, 0).numpy() * 255).astype(np.uint8)
        return Image.fromarray(arr)


class CellReader:
    """VietOCR over the cells of one table image. The model loads on first use."""

    def __init__(self, config: str = "vgg_transformer", device: str = "cpu", sure: float = 0.9, super_res: bool = False):
        self.config, self.device, self.sure, self._predictor = config, device, sure, None
        self.upscale = SuperResolver() if super_res else None
        self.degrade = float(os.environ.get("OCR_DEGRADE", "1"))
        self.lock = threading.RLock()
        self.last: dict = {}                    # confidence and picture of every cell of the table read last

    @property
    def predictor(self):
        if self._predictor is None:
            from vietocr.tool.config import Cfg
            from vietocr.tool.predictor import Predictor
            cfg = Cfg.load_config_from_name(self.config)
            cfg["device"] = self.device
            if os.environ.get("VIETOCR_WEIGHTS"):
                cfg["weights"] = os.environ["VIETOCR_WEIGHTS"]
            cfg["predictor"]["beamsearch"] = False
            self._predictor = Predictor(cfg)
        return self._predictor

    def _predict(self, piece: Image.Image) -> Tuple[str, float]:
        with self.lock:                                   # the recognizer keeps state while it decodes: one cell at a time
            text, prob = self.predictor.predict(piece, return_prob=True)
        return text, float(prob) if np.isfinite(prob) else 0.0                    # an empty decode gives NaN: count it as no confidence

    def _read(self, piece: Image.Image) -> Tuple[str, float]:
        """The cell as it is; when the recognizer is unsure, also an enlarged and a sharpened copy, and the reading it trusts most wins
        (two copies that agree win together)."""
        first = self._predict(piece)
        if first[1] >= self.sure:
            return first
        big = ImageOps.autocontrast(piece.convert("L").resize((piece.width * 2, piece.height * 2), Image.LANCZOS), cutoff=1).convert("RGB")
        sharp = big.filter(ImageFilter.UnsharpMask(radius=2, percent=170, threshold=2))
        tries = [first, self._predict(big), self._predict(sharp)]
        if self.upscale is not None:
            tries.append(self._predict(self.upscale(piece)))
        votes: dict = {}
        for text, prob in tries:
            votes[text] = votes.get(text, 0.0) + prob + (0.15 if sum(t == text for t, _ in tries) > 1 else 0.0)
        text = max(votes, key=votes.get)
        return text, max(p for t, p in tries if t == text)

    def _texts(self, table: Image.Image, cells: List[Cell], degrade: bool = False) -> List[Tuple[str, float]]:
        out = []
        for x0, y0, x1, y1 in cells:
            piece = tight(table.crop(inner((x0, y0, x1, y1))))
            if piece is None:
                out.append(("", 1.0))
                continue
            if (y1 - y0) > 2.5 * (x1 - x0) and piece.height > 2 * piece.width:
                piece = piece.rotate(-90, expand=True)               # a label written bottom-to-top in a narrow merged cell
            if degrade and self.degrade > 1:                               # test aid: what a poorer scan would give (resolution divided by `degrade`)
                small = piece.resize((max(1, round(piece.width / self.degrade)), max(1, round(piece.height / self.degrade))), Image.BILINEAR)
                piece = small.resize(piece.size, Image.BICUBIC)
            text, prob = self._read(piece)
            out.append((text, prob))
        return out

    def read(self, table: Image.Image) -> List[List[str]]:
        cells = find_cells(table, close_frame=True)
        if not cells:
            return []
        placed, nr, nc = place(cells)
        grid = [[""] * nc for _ in range(nr)]
        med = median_height(cells)
        conf = [[1.0] * nc for _ in range(nr)]
        pieces = {}
        for (cell, r, c), (text, prob) in zip(placed, self._texts(table, [p[0] for p in placed], degrade=True)):
            if text and 1.6 * med <= cell[3] - cell[1] < 2.5 * med and r + 1 < nr:
                ink = np.asarray(table.crop(inner(cell)).convert("L")) < 150
                ys = np.where(ink.any(axis=1))[0]
                if len(ys) and (ys.min() + ys.max()) / 2 / ink.shape[0] > 0.62:
                    r += 1
            grid[r][c] = text
            conf[r][c] = prob
            if text:
                piece = tight(table.crop(inner(cell)))
                if piece is not None:
                    pieces[(r, c)] = piece
        self.last = {"conf": conf, "pieces": pieces}
        return grid

    def caption(self, page: Image.Image, box: Tuple[int, int, int, int], row_h: float) -> str:
        """The line of text just above a table (its name), read in chunks because VietOCR reads short lines best; "" if there is none."""
        x0, y0, x1, y1 = box
        top = max(0, int(y0 - 3.2 * row_h))
        strip = page.crop((x0, top, x1, max(top + 1, y0 - 2)))
        ink = np.asarray(strip.convert("L")) < 150
        ink[ink.mean(axis=1) > 0.5, :] = False                                   # a ruling line is not text
        lines = [ln for ln in text_lines(ink, merge=int(0.3 * row_h)) if ln[1] - ln[0] <= 2.2 * row_h]
        if not lines:
            return ""
        a, b = lines[-1]                                                          # the nearest line above the table
        if strip.height - b > 2.4 * row_h:
            return ""
        band = ink[max(0, a - 2): b + 3]
        cols = np.where(band.any(axis=0))[0]
        if not len(cols):
            return ""
        chunks, start, last = [], cols[0], cols[0]
        for x in cols[1:]:
            if x - last > 0.7 * (b - a) and last - start > 14 * (b - a):          # break the line at a word gap once a chunk is long
                chunks.append((start, last)); start = x
            last = x
        chunks.append((start, last))
        words = []
        for cs, ce in chunks:
            piece = strip.crop((max(0, cs - 4), max(0, a - 4), min(strip.width, ce + 5), min(strip.height, b + 5)))
            with self.lock:
                words.append(self.predictor.predict(piece))
        return " ".join(words).strip()

    def confidence(self, table: Image.Image, sample: int = 12) -> float:
        """Mean recognizer confidence over a spread of the table's text cells: high when the text is upright and readable."""
        cells = [c for c in find_cells(table) if tight(table.crop(inner(c))) is not None]
        if not cells:
            return 0.0
        pick = [cells[i] for i in np.linspace(0, len(cells) - 1, min(sample, len(cells))).astype(int)]
        return float(np.mean([p for _, p in self._texts(table, pick)]))


def text_aspect(table: Image.Image, sample: int = 80) -> float:
    """Median width/height of the text blocks inside the cells: well above 1 when the text runs horizontally, below 1 when it is turned."""
    cells = find_cells(table)
    if not cells:
        return 1.0
    pick = [cells[i] for i in np.linspace(0, len(cells) - 1, min(sample, len(cells))).astype(int)]
    ratios = []
    for x0, y0, x1, y1 in pick:
        piece = tight(table.crop(inner((x0, y0, x1, y1))), margin=0)
        if piece is not None and piece.width * piece.height > 60:
            ratios.append(piece.width / piece.height)
    return float(np.median(ratios)) if ratios else 1.0


def horizontal_votes(page: Image.Image, boxes: List[Tuple[int, int, int, int]], per_table: int = 150) -> int:
    """Over all tables: cells whose text runs horizontally minus cells whose text is turned. The big data tables outvote a small title block
    that happens to be drawn the other way on a sheet."""
    votes = 0
    for box in boxes:
        table = page.crop(box)
        cells = find_cells(table)
        if not cells:
            continue
        for x0, y0, x1, y1 in [cells[i] for i in np.linspace(0, len(cells) - 1, min(per_table, len(cells))).astype(int)]:
            piece = tight(table.crop(inner((x0, y0, x1, y1))), margin=0)
            if piece is not None and piece.width * piece.height > 60:
                ratio = piece.width / piece.height
                votes += 1 if ratio > 1.2 else -1 if ratio < 0.8 else 0
    return votes


_DIM = re.compile(r"^[0-9.,]+$")
_NUM_FIX = re.compile(r"(?<=\d);(?=\d)")


def clean_rows(rows: List[List[str]]) -> List[List[str]]:
    """Fixes for what the recognizer cannot know from one cell alone: ';' read for ',' inside a number, a diameter sign read as 0/O,
    and a size drawn as several boxes ("60", "x", "5,5") joined into one cell (the cells after it are left empty so columns hold)."""
    out = []
    for row in rows:
        row = [_NUM_FIX.sub(",", c) for c in row]
        row = [re.sub(r"(?<=\b(ống|tròn|Bulon|bulon|tấm|Thép) )[0OØ](?=\d)", "Ø", c) if False else c for c in row]
        fixed = []
        for c in row:
            c = re.sub(r"\b(ống|tròn|tấm|Ống|Tròn) [0O]$", lambda m: m.group(1).lower() + " Ø", c)
            c = re.sub(r"\b(Bulon|bulon|ống|Ống|tròn|tấm)\s?[0O](?=\d)", lambda m: m.group(1) + " Ø", c)
            fixed.append(c)
        row = fixed
        i = 0
        while i < len(row) - 2:
            if _DIM.match(row[i].strip()) and row[i + 1].strip() in ("x", "X", "×") and _DIM.match(row[i + 2].strip()):
                j = i + 2
                size = f"{row[i].strip()} x {row[j].strip()}"
                while j + 2 < len(row) and row[j + 1].strip() in ("x", "X", "×") and _DIM.match(row[j + 2].strip()):
                    size += f" x {row[j + 2].strip()}"
                    j += 2
                row[i] = size
                for k in range(i + 1, j + 1):
                    row[k] = ""
                i = j + 1
            else:
                i += 1
        out.append(row)
    return out


_SIZE_LEAD = re.compile(r"^[\"']?[0OPpΦφĐđ](?=\d{1,3}(?:,\d)?\s?x\s?\d)")
_STT = re.compile(r"^\d+$")


def fix_sizes(rows: List[List[str]]) -> List[List[str]]:
    """The diameter sign is read as 0, O or P ("027x2,5x1000", "P16x290"); in a size such as 16x290 it is always Ø."""
    return [[_SIZE_LEAD.sub("Ø", c) if c else c for c in row] for row in rows]


def merge_header(rows: List[List[str]]) -> List[List[str]]:
    """A column title printed on several lines ("Số" / "lượng" / "(ck)") comes out as several rows above the first numbered row:
    join them, column by column, into one header row."""
    first = next((i for i, r in enumerate(rows) if r and _STT.match(r[0].strip())), None)
    if first is None or first < 2 or first > 5:
        return rows
    head = [" ".join(p for p in (r[j].strip() for r in rows[:first] if j < len(r)) if p) for j in range(max(len(r) for r in rows[:first]))]
    return [head] + rows[first:]
