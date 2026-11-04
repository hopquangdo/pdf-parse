"""Tìm bảng trong PDF vector bằng hình học đường kẻ (không dùng AI)."""
from dataclasses import dataclass, field
from typing import List

import pymupdf


@dataclass
class TableBox:
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    rows: int
    cols: int
    ys: List[float] = field(default_factory=list)  # toạ độ y các đường kẻ ngang chạy suốt
    xs: List[float] = field(default_factory=list)  # toạ độ x các đường kẻ dọc chạy suốt


def _segments(page, min_len: float, tol: float = 0.4):
    h, v = [], []
    for d in page.get_drawings():
        pts = []
        for it in d["items"]:
            if it[0] == "l":
                pts.append((it[1], it[2]))
            elif it[0] == "re":
                r = it[1]
                pts += [(pymupdf.Point(r.x0, r.y0), pymupdf.Point(r.x1, r.y0)),
                        (pymupdf.Point(r.x0, r.y1), pymupdf.Point(r.x1, r.y1)),
                        (pymupdf.Point(r.x0, r.y0), pymupdf.Point(r.x0, r.y1)),
                        (pymupdf.Point(r.x1, r.y0), pymupdf.Point(r.x1, r.y1))]
        for a, b in pts:
            if abs(a.y - b.y) <= tol and abs(a.x - b.x) >= min_len:
                h.append((min(a.x, b.x), max(a.x, b.x), (a.y + b.y) / 2))
            elif abs(a.x - b.x) <= tol and abs(a.y - b.y) >= min_len:
                v.append((min(a.y, b.y), max(a.y, b.y), (a.x + b.x) / 2))
    return h, v


def _components(h, v, gap: float):
    n = len(h) + len(v)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, (hx0, hx1, hy) in enumerate(h):
        for j, (vy0, vy1, vx) in enumerate(v):
            if hx0 - gap <= vx <= hx1 + gap and vy0 - gap <= hy <= vy1 + gap:
                parent[find(i)] = find(len(h) + j)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return groups.values()


def _distinct(vals, tol=1.0):
    out = []
    for x in sorted(vals):
        if not out or x - out[-1] > tol:
            out.append(x)
    return out


def detect_tables(pdf: bytes, page_no: int, min_len: float = 12, min_rows: int = 3, min_cols: int = 3,
                  max_frac: float = 0.6, span: float = 0.7, min_side: float = 100) -> List[TableBox]:
    """Trả các khung bảng (toạ độ trang PDF chưa xoay). Bỏ khung bản vẽ (quá lớn)."""
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        page = doc[page_no - 1]
        W, H = page.rect.width, page.rect.height
        h, v = _segments(page, min_len)
    boxes = []
    for comp in _components(h, v, gap=1.0):
        hs = [h[i] for i in comp if i < len(h)]
        vs = [v[i - len(h)] for i in comp if i >= len(h)]
        if not hs or not vs:
            continue
        ys, xs = _distinct([s[2] for s in hs]), _distinct([s[2] for s in vs])
        if len(ys) < min_rows + 1 or len(xs) < min_cols + 1:
            continue
        x0, x1 = min(s[0] for s in hs), max(s[1] for s in hs)
        y0, y1 = min(s[0] for s in vs), max(s[1] for s in vs)
        if (x1 - x0) > max_frac * max(W, H) and (y1 - y0) > max_frac * min(W, H):
            continue
        if max(x1 - x0, y1 - y0) < min_side:  # mặt cắt vuông nhỏ trong hình vẽ
            continue
        # bảng thật: các đường kẻ chạy suốt chiều rộng/cao; hình vẽ thì đường kẻ ngắn, lẻ tẻ
        full_h = _distinct([s[2] for s in hs if s[1] - s[0] >= span * (x1 - x0)])
        full_v = _distinct([s[2] for s in vs if s[1] - s[0] >= span * (y1 - y0)])
        if len(full_h) < min_rows + 1 or len(full_v) < min_cols + 1:
            continue
        boxes.append(TableBox(page_no, x0, y0, x1, y1, len(full_h) - 1, len(full_v) - 1, full_h, full_v))
    return sorted(boxes, key=lambda b: (b.y0, b.x0))


class LineTableLocator:
    """TableLocator port: tables drawn with ruling lines in a vector PDF."""
    def __init__(self, **options):
        self.options = options

    def find(self, pdf: bytes, page: int) -> List[TableBox]:
        return detect_tables(pdf, page, **self.options)
