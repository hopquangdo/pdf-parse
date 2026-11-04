"""Render trang PDF thành ảnh PNG (đã xoay, cắt lưới) để gửi cho mô hình đọc ảnh."""
import io
import threading
from typing import Iterator, Tuple

import pymupdf
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
MAX_SIDE = 2000
_LOCK = threading.Lock()  # MuPDF keeps global state: render one at a time, call the model in parallel


def page_count(pdf: bytes) -> int:
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        return len(doc)


def render_tiles(pdf: bytes, page: int, rotate: int = 0, dpi: int = 300,
                 cols: int = 1, rows: int = 1, overlap: float = 0.08) -> Iterator[Tuple[str, bytes]]:
    """Trả (nhãn vùng, PNG bytes). rotate: độ ngược chiều kim đồng hồ."""
    with _LOCK, pymupdf.open(stream=pdf, filetype="pdf") as doc:
        pix = doc[page - 1].get_pixmap(dpi=dpi)
        im = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    if rotate:
        im = im.rotate(rotate, expand=True)
    W, H = im.size
    for r in range(rows):
        for c in range(cols):
            x0 = max(0, int(W * (c / cols - overlap * (c > 0))))
            x1 = min(W, int(W * ((c + 1) / cols + overlap * (c < cols - 1))))
            y0 = max(0, int(H * (r / rows - overlap * (r > 0))))
            y1 = min(H, int(H * ((r + 1) / rows + overlap * (r < rows - 1))))
            tile = im.crop((x0, y0, x1, y1))
            tile.thumbnail((MAX_SIDE, MAX_SIDE))
            buf = io.BytesIO()
            tile.save(buf, "PNG", optimize=True)
            yield f"p{page}_r{r}c{c}", buf.getvalue()


def render_box(pdf: bytes, page: int, box, rotate: int = 0, dpi: int = 400, margin: float = 6) -> bytes:
    """Cắt vùng (x0,y0,x1,y1 theo toạ độ trang PDF chưa xoay), chừa lề, rồi xoay cho chữ đứng."""
    x0, y0, x1, y1 = box
    with _LOCK, pymupdf.open(stream=pdf, filetype="pdf") as doc:
        pg = doc[page - 1]
        clip = pymupdf.Rect(x0 - margin, y0 - margin, x1 + margin, y1 + margin) & pg.rect
        pix = pg.get_pixmap(dpi=dpi, clip=clip)
        im = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    if rotate:
        im = im.rotate(rotate, expand=True)
    im.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def page_is_portrait(pdf: bytes, page: int) -> bool:
    with _LOCK, pymupdf.open(stream=pdf, filetype="pdf") as doc:
        r = doc[page - 1].rect
        return r.height > r.width


def render_fraction(pdf: bytes, page: int, frac: Tuple[float, float, float, float], rotate: int = 0, dpi: int = 300) -> bytes:
    """Crop a region given as fractions (x0, y0, x1, y1) of the page AFTER rotation, e.g. the title block."""
    with _LOCK, pymupdf.open(stream=pdf, filetype="pdf") as doc:
        pix = doc[page - 1].get_pixmap(dpi=dpi)
        im = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    if rotate:
        im = im.rotate(rotate, expand=True)
    W, H = im.size
    im = im.crop((int(W * frac[0]), int(H * frac[1]), int(W * frac[2]), int(H * frac[3])))
    im.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


class PyMuPdfRenderer:
    """PageRenderer port backed by the functions above."""
    page_count = staticmethod(page_count)
    page_is_portrait = staticmethod(page_is_portrait)
    render_tiles = staticmethod(render_tiles)
    render_fraction = staticmethod(render_fraction)
    render_box = staticmethod(render_box)
