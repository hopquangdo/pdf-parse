"""Cut a tall table image into bands of whole text lines so a model can transcribe it piece by piece.

A long table in one request loses rows and breaks the JSON; a band of ~15 rows plus the header strip does not.
"""
import io
from typing import List, Tuple

import numpy as np
from PIL import Image


def line_gaps(im: Image.Image, min_gap: int = 6) -> List[int]:
    """Y of the middle of every white gap between text lines. Ruling lines are ignored so they never hide a gap."""
    g = np.asarray(im.convert("L")) < 150
    vlines = np.convolve(g.mean(axis=0) > 0.60, np.ones(5), "same") > 0       # ruled column lines
    g = g.copy()
    g[:, vlines] = False
    g[g.mean(axis=1) > 0.60, :] = False                                         # full-width horizontal rules
    ink = g[:, int(g.shape[1] * 0.02): int(g.shape[1] * 0.98)].mean(axis=1) > 0.004
    cuts, start = [], None
    for y, v in enumerate(ink):
        if not v and start is None:
            start = y
        if v and start is not None:
            if y - start >= min_gap:
                cuts.append((start + y) // 2)
            start = None
    return cuts


def split_rows(im: Image.Image, header_frac: float = 0.035, chunk_ratio: float = 0.24) -> Tuple[int, List[Tuple[int, int]]]:
    """(header height in px, [(y0, y1), ...] bands). chunk_ratio = band height as a fraction of the image width."""
    H, W = im.height, im.width
    target = max(600, int(W * chunk_ratio))
    if H <= target * 1.3:
        return 0, [(0, H)]
    header_h = int(H * header_frac)
    bounds, last = [0], 0                 # the first band starts at the very top, so it holds the header row itself
    for c in line_gaps(im):
        if c > header_h and c - last >= target:
            bounds.append(c)
            last = c
    if bounds[-1] < H - 5:
        bounds.append(H)
    return header_h, list(zip(bounds[:-1], bounds[1:]))


def band_png(im: Image.Image, header_h: int, y0: int, y1: int, width: int = 2600) -> bytes:
    """The band with the column-header strip stacked above it (so the model knows which column is which)."""
    body = im.crop((0, y0, im.width, y1))
    if header_h and y0 > 0:
        head = im.crop((0, 0, im.width, header_h))                           # the strip of column headers, stacked above later bands
        sheet = Image.new("RGB", (im.width, head.height + body.height), "white")
        sheet.paste(head, (0, 0))
        sheet.paste(body, (0, head.height))
    else:
        sheet = body
    if sheet.width > width:
        sheet = sheet.resize((width, round(sheet.height * width / sheet.width)), Image.LANCZOS)
    buf = io.BytesIO()
    sheet.convert("RGB").save(buf, "PNG", optimize=True)
    return buf.getvalue()
