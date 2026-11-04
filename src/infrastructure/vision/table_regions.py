"""Find the tables on a page image by their ruling lines, so each one can be read (and exported) on its own.

A table is a block where long horizontal and vertical lines cross. The lines are found, thickened until the cells of one
table join into a single blob, and every big enough blob that still holds several rows and columns is a table. Works on a
scan or a render alike; a table with no ruling at all is not found (the caller then reads the whole page).
"""
from typing import List, Tuple

import numpy as np
from PIL import Image
from scipy import ndimage

Box = Tuple[int, int, int, int]       # x0, y0, x1, y1 in pixels


def _lines(mask: np.ndarray, length: int, horizontal: bool) -> np.ndarray:
    shape = (1, length) if horizontal else (length, 1)
    return ndimage.binary_dilation(ndimage.binary_erosion(mask, structure=np.ones(shape, bool)), structure=np.ones(shape, bool))


def _without_frame(lines: np.ndarray, horizontal: bool, share: float = 0.8) -> np.ndarray:
    """Drop lines that run across most of the page: the sheet frame would otherwise join every table into one blob."""
    lab, _ = ndimage.label(lines)
    out = lines.copy()
    for k, sl in enumerate(ndimage.find_objects(lab), 1):
        span = (sl[1].stop - sl[1].start) / lines.shape[1] if horizontal else (sl[0].stop - sl[0].start) / lines.shape[0]
        if span > share:
            out[sl][lab[sl] == k] = False
    return out


def _count_lines(mask: np.ndarray, axis: int) -> int:
    """How many separate lines cross the blob along `axis` (rows of a table for axis=1, columns for axis=0)."""
    profile = mask.mean(axis=axis) > 0.5
    return int(ndimage.label(profile)[1])


def find_tables(im: Image.Image, min_area: float = 0.015, min_lines: int = 3) -> List[Box]:
    """Table boxes, largest first. min_area is a fraction of the page; min_lines is the least rows AND columns of lines."""
    work = im.convert("L")
    scale = min(1.0, 2400 / max(work.size))
    if scale < 1:
        work = work.resize((round(work.width * scale), round(work.height * scale)), Image.LANCZOS)
    ink = np.asarray(work) < 150
    H, W = ink.shape
    hl, vl = _lines(ink, max(30, W // 45), True), _lines(ink, max(30, H // 45), False)
    hl, vl = _without_frame(hl, True), _without_frame(vl, False)
    grid = hl | vl
    joined = ndimage.binary_dilation(grid, structure=np.ones((3, 3)), iterations=max(2, W // 800))

    def blobs(mask: np.ndarray) -> List[Box]:
        lab, _ = ndimage.label(mask)
        return [(s[1].start, s[0].start, s[1].stop, s[0].stop) for s in ndimage.find_objects(lab)]

    found = blobs(joined)
    tables = []
    for x0, y0, x1, y1 in found:
        if (x1 - x0) * (y1 - y0) < min_area * W * H:
            continue
        rows = _count_lines(hl[y0:y1, x0:x1], 1)
        cols = _count_lines(vl[y0:y1, x0:x1], 0)
        if rows >= min_lines and cols >= min_lines:
            tables.append((x0, y0, x1, y1))
    tables.sort(key=lambda b: -(b[2] - b[0]) * (b[3] - b[1]))
    pad = max(4, W // 400)
    return [(max(0, round((x0 - pad) / scale)), max(0, round((y0 - pad) / scale)),
             min(im.width, round((x1 + pad) / scale)), min(im.height, round((y1 + pad) / scale))) for x0, y0, x1, y1 in tables]
