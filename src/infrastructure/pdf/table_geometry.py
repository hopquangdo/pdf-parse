"""Tách bảng thành các dải dòng: đếm dòng có chữ, cắt phóng to từng dòng kèm tiêu đề."""
import io
from typing import List, Tuple

import numpy as np
import pymupdf
from PIL import Image

from src.infrastructure.pdf.renderer import _LOCK, MAX_SIDE, render_box
from src.infrastructure.pdf.table_detector import TableBox


def row_bands(box: TableBox, rotate: int) -> List[Tuple[float, float]]:
    """Các dải dòng theo thứ tự từ trên xuống khi nhìn chữ đứng. Dải 0 là dòng tiêu đề.

    Trang xoay 90/270 thì các dòng của bảng được ngăn bởi đường kẻ dọc (theo toạ độ trang gốc).
    Xoay ngược chiều kim đồng hồ 90 độ: cạnh trên của ảnh đứng ứng với x lớn nhất.
    """
    lines = box.xs if rotate in (90, 270) else box.ys
    ordered = sorted(lines, reverse=rotate in (90, 180))
    return list(zip(ordered[:-1], ordered[1:]))


def _band_box(box: TableBox, rotate: int, band: Tuple[float, float]):
    lo, hi = sorted(band)
    return (lo, box.y0, hi, box.y1) if rotate in (90, 270) else (box.x0, lo, box.x1, hi)


def nonblank_bands(pdf: bytes, box: TableBox, rotate: int, thr: float = 0.002) -> List[int]:
    """Chỉ số các dải có chữ (loại dòng trống ngăn nhóm). Đo mật độ mực, bỏ phần viền ô."""
    bands = row_bands(box, rotate)
    out = []
    with _LOCK, pymupdf.open(stream=pdf, filetype="pdf") as doc:
        page = doc[box.page - 1]
        for i, band in enumerate(bands):
            x0, y0, x1, y1 = _band_box(box, rotate, band)
            inset = 2.0
            clip = pymupdf.Rect(x0 + inset, y0 + inset, x1 - inset, y1 - inset)
            pix = page.get_pixmap(dpi=100, clip=clip, colorspace=pymupdf.csGRAY)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width) < 128
            # bỏ hàng/cột điểm ảnh gần như đen suốt dải (đường kẻ ngăn ô), chỉ đếm mực của chữ
            text = img[img.mean(axis=1) < 0.6][:, img.mean(axis=0) < 0.6]
            if text.size and text.mean() > thr:
                out.append(i)
    return out


def render_row_zoom(pdf: bytes, box: TableBox, rotate: int, band_index: int, dpi: int = 400) -> bytes:
    """Ảnh gồm dòng tiêu đề (dải 0) xếp trên dải dữ liệu cần đọc, đã xoay cho chữ đứng."""
    bands = row_bands(box, rotate)
    imgs = []
    for idx in (0, band_index):
        png = render_box(pdf, box.page, _band_box(box, rotate, bands[idx]), rotate=rotate, dpi=dpi, margin=1)
        imgs.append(Image.open(io.BytesIO(png)).convert("RGB"))
    w = max(i.width for i in imgs)
    canvas = Image.new("RGB", (w, sum(i.height for i in imgs)), "white")
    y = 0
    for im in imgs:
        canvas.paste(im, (0, y))
        y += im.height
    canvas.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    canvas.save(buf, "PNG", optimize=True)
    return buf.getvalue()
