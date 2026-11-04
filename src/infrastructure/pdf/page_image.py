"""Turn an upload (image or one page of a PDF) into one RGB image ready for OCR."""
import io
from PIL import Image, ImageOps

import pymupdf

from src.infrastructure.pdf.renderer import _LOCK

Image.MAX_IMAGE_PIXELS = None


class UnsupportedFile(ValueError):
    pass


def page_count(data: bytes) -> int:
    with _LOCK, pymupdf.open(stream=data, filetype="pdf") as doc:
        return len(doc)


def load_image(data: bytes, page: int = 1, dpi: int = 200, min_cover: float = 0.25, image: int = 1) -> Image.Image:
    """PDF: a page that carries a large embedded image (a table pasted in as a picture) gives that image at full
    resolution; `image` picks the 1st, 2nd... largest one. A page without such an image is rendered at `dpi`.
    Anything else must be an image PIL can open."""
    if data[:5] == b"%PDF-":
        with _LOCK, pymupdf.open(stream=data, filetype="pdf") as doc:
            if not 1 <= page <= len(doc):
                raise UnsupportedFile(f"trang {page} không có trong file ({len(doc)} trang)")
            pg = doc[page - 1]
            area = pg.rect.width * pg.rect.height
            found = {}
            for info in pg.get_images(full=True):
                for r in pg.get_image_rects(info[0]):
                    found[info[0]] = max(found.get(info[0], 0.0), r.width * r.height)
            ranked = sorted(found.items(), key=lambda kv: -kv[1])
            if ranked and ranked[0][1] >= min_cover * area:
                if not 1 <= image <= len(ranked):
                    raise UnsupportedFile(f"trang {page} chỉ có {len(ranked)} ảnh nhúng")
                return Image.open(io.BytesIO(doc.extract_image(ranked[image - 1][0])["image"])).convert("RGB")
            if image != 1:
                raise UnsupportedFile(f"trang {page} không có ảnh nhúng nào đủ lớn; để image=1 để đọc cả trang")
            return Image.open(io.BytesIO(pg.get_pixmap(dpi=dpi).tobytes("png"))).convert("RGB")
    try:
        return ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    except Exception as e:  # noqa: BLE001
        raise UnsupportedFile("file không phải PDF hoặc ảnh đọc được (png, jpg, webp, tiff)") from e


def load_page(data: bytes, page: int = 1, dpi: int = 300, scan_cover: float = 0.8, longest: int = 7000) -> Image.Image:
    """The WHOLE page as one image, for finding every table on it: a page that is one scanned picture gives that picture at
    full resolution, any other page is rendered at `dpi` (capped so a huge sheet stays a workable size)."""
    if data[:5] != b"%PDF-":
        return load_image(data, page)
    with _LOCK, pymupdf.open(stream=data, filetype="pdf") as doc:
        if not 1 <= page <= len(doc):
            raise UnsupportedFile(f"trang {page} không có trong file ({len(doc)} trang)")
        pg = doc[page - 1]
        area = pg.rect.width * pg.rect.height
        for info in pg.get_images(full=True):
            if max((r.width * r.height for r in pg.get_image_rects(info[0])), default=0) >= scan_cover * area:
                return Image.open(io.BytesIO(doc.extract_image(info[0])["image"])).convert("RGB")
        dpi = min(dpi, int(longest / (max(pg.rect.width, pg.rect.height) / 72)))
        return Image.open(io.BytesIO(pg.get_pixmap(dpi=dpi).tobytes("png"))).convert("RGB")


def render_page(data: bytes, page: int = 1, long_side: int = 2400) -> Image.Image:
    """The whole page rendered so that its longer side is `long_side` px."""
    with _LOCK, pymupdf.open(stream=data, filetype="pdf") as doc:
        if not 1 <= page <= len(doc):
            raise UnsupportedFile(f"trang {page} không có trong file ({len(doc)} trang)")
        pg = doc[page - 1]
        pix = pg.get_pixmap(dpi=max(30, int(long_side / (max(pg.rect.width, pg.rect.height) / 72))))
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
