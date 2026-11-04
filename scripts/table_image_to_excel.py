"""Prototype: a table printed as an image (or an image embedded in a PDF) -> an Excel workbook.

  python scripts/table_image_to_excel.py output/page29/main_upright.png output/page29/khoi_luong.xlsx

Steps: split the image into bands of text lines at white gaps -> group the bands into chunks that each keep the header
strip -> a vision model transcribes every chunk to JSON rows -> arithmetic checks -> Excel (flagged cells highlighted).
The column schema below is for the steel quantity table of page 29; for another table type only SCHEMA/PROMPT change.
"""
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src import config  # noqa: E402  (loads .env)
from src.infrastructure.vision.table_reader import TableVisionReader  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
SCHEMA = [("stt", "STT", 6), ("ten", "Tên vật tư", 34), ("quy_cach", "Quy cách", 18), ("mo_ta", "Mô tả", 26), ("dvt", "ĐVT", 7),
          ("so_luong", "Số lượng", 10), ("kich_thuoc", "Kích thước", 12), ("tong", "Tổng", 11), ("don_trong", "Đơn trọng", 11),
          ("dv_don_trong", "ĐV đơn trọng", 12), ("khoi_luong", "Khối lượng (kg)", 15), ("dien_tich", "Diện tích sơn (m2)", 16), ("ghi_chu", "Ghi chú", 22)]
PROMPT = """Ảnh là một phần của bảng khối lượng thép: phía trên cùng là dòng tiêu đề cột (SỐ, ĐƠN, SỐ, KÍCH, TỔNG, ĐƠN, KHỐI, DIỆN, GHI CHÚ), bên dưới là các dòng dữ liệu cần chép.
Chép lại TẤT CẢ dòng dữ liệu bên dưới dòng tiêu đề, đúng thứ tự từ trên xuống, đúng nguyên văn (giữ dấu phẩy và dấu chấm trong số). Không đoán, không tính toán, không bỏ dòng.
Trả về DUY NHẤT một mảng JSON, mỗi dòng là một đối tượng có các khóa (ô trống = chuỗi rỗng):
"loai": "nhom" nếu là dòng tiêu đề của một nhóm (ví dụ "ĐOẠN CỘT :L=6M (7CK)", "KIM THU SÉT (1CK)", "KHỐI LƯỢNG THÂN CỘT"), ngược lại "dong";
"stt": số thứ tự ở cột đầu;
"ten": tên vật tư, hoặc tên nhóm;
"quy_cach": các kích thước nằm trong các ô nhỏ sau tên, ví dụ "200 x 200 x 16", "60 x 5,5", "M22 x 90" (chỉ phần kích thước, không gồm phần trong ngoặc);
"mo_ta": phần trong ngoặc ở giữa dòng, ví dụ "(bản mã)", "(2ecu + 1đệm)";
"dvt": đơn vị ở cột ĐƠN đầu tiên (mm, bộ, cái, kg, m2, KG);
"so_luong": cột SỐ thứ hai (số lượng);
"kich_thuoc": cột KÍCH;
"tong": cột TỔNG;
"don_trong": số ở cột ĐƠN thứ hai (đơn trọng);
"dv_don_trong": đơn vị của đơn trọng (kg/m, kg/m2, kg/bộ);
"khoi_luong": cột KHỐI;
"dien_tich": cột DIỆN;
"ghi_chu": cột GHI CHÚ (ví dụ "Thép CT3", "Tận dụng đốt cột cũ", "-")."""


def to_num(s):
    s = str(s or "").strip().replace(" ", "")
    if not s or s in "-–":
        return None
    if re.fullmatch(r"\d{1,3}(\.\d{3})+,\d+", s) or re.fullmatch(r"\d{1,3}(\.\d{3})+", s):   # 1.849,51 / 13.726
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def text_line_gaps(im: Image.Image, min_gap: int = 6):
    """Y positions in the middle of white gaps between text lines (cut points that never slice through a row)."""
    g = np.asarray(im.convert("L")) < 150
    vlines = g.mean(axis=0) > 0.30                       # ruled column lines would make every text line look inked
    vlines = np.convolve(vlines, np.ones(5), "same") > 0
    g = g.copy(); g[:, vlines] = False
    hl = g.mean(axis=1) > 0.60                            # full-width horizontal rules are gaps too, not text
    g[hl, :] = False
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


def chunks(im: Image.Image, header_frac: float = 0.05, rows_per_chunk_px: int = 1100):
    H = im.height
    header_h = int(H * header_frac)
    cuts = [c for c in text_line_gaps(im) if c > header_h]
    bounds, last = [header_h], header_h
    for c in cuts:
        if c - last >= rows_per_chunk_px:
            bounds.append(c); last = c
    if bounds[-1] < H - 5:
        bounds.append(H)
    return header_h, list(zip(bounds[:-1], bounds[1:]))


def chunk_image(im: Image.Image, header_h: int, y0: int, y1: int, width: int = 2600) -> bytes:
    head = im.crop((0, int(header_h * 0.55), im.width, header_h))      # skip the title, keep the column header
    body = im.crop((0, y0, im.width, y1))
    sheet = Image.new("RGB", (im.width, head.height + body.height), "white")
    sheet.paste(head, (0, 0)); sheet.paste(body, (0, head.height))
    sheet = sheet.resize((width, round(sheet.height * width / sheet.width)), Image.LANCZOS)
    import io
    buf = io.BytesIO(); sheet.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def read_chunks(im, key, model):
    header_h, spans = chunks(im)
    reader = TableVisionReader(key, model)
    pngs = [chunk_image(im, header_h, a, b) for a, b in spans]
    print(f"{len(spans)} chunks:", [(a, b) for a, b in spans], flush=True)

    def one(i):
        for attempt in range(3):
            try:
                rows = reader.ask_json(pngs[i], PROMPT, f"chunk{i}")
                if isinstance(rows, list):
                    return rows
            except Exception as e:  # noqa: BLE001
                print("chunk", i, "retry:", type(e).__name__, str(e)[:100], flush=True)
        return []
    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(one, range(len(spans))))
    return [r for part in res for r in part], spans


def check(rows):
    """Mark cells that cannot be right: khoi_luong should equal tong x don_trong (within 1.5%)."""
    flags = {}
    for i, r in enumerate(rows):
        if r.get("loai") == "nhom":
            continue
        t, d, k = to_num(r.get("tong")), to_num(r.get("don_trong")), to_num(r.get("khoi_luong"))
        if None not in (t, d, k) and k and abs(t * d - k) / k > 0.015:
            flags[(i, "khoi_luong")] = f"tong x don_trong = {t * d:.2f}"
    return flags


def write_excel(rows, flags, out: Path, title: str):
    wb = openpyxl.Workbook()
    ws = wb.active; ws.title = "Khoi luong"
    ws["A1"] = title; ws["A1"].font = Font(bold=True, size=13)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(SCHEMA))
    for c, (_, label, w) in enumerate(SCHEMA, 1):
        cell = ws.cell(3, c, label); cell.font = Font(bold=True); cell.fill = PatternFill("solid", fgColor="D9E1F2")
        cell.alignment = Alignment(horizontal="center", wrap_text=True); ws.column_dimensions[cell.column_letter].width = w
    bad = PatternFill("solid", fgColor="FFF2CC")
    for i, r in enumerate(rows):
        y = 4 + i
        is_group = r.get("loai") == "nhom"
        for c, (k, _, _) in enumerate(SCHEMA, 1):
            v = str(r.get(k, "") or "")
            num = to_num(v) if k in ("so_luong", "kich_thuoc", "tong", "don_trong", "khoi_luong", "dien_tich", "stt") else None
            cell = ws.cell(y, c, num if num is not None else v)
            if num is not None and k not in ("stt", "so_luong"):
                cell.number_format = "#,##0.00" if k != "kich_thuoc" else "#,##0.0"
            if is_group:
                cell.font = Font(bold=True); cell.fill = PatternFill("solid", fgColor="F2F2F2")
            if (i, k) in flags:
                cell.fill = bad; cell.comment = openpyxl.comments.Comment(flags[(i, k)], "check")
    ws.freeze_panes = "A4"
    wb.save(out)


def main():
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    import os
    im = Image.open(src).convert("RGB")
    t0 = time.time()
    rows, spans = read_chunks(im, os.environ["LLM_API_KEY"], config.LLM_MODEL_NAME)
    flags = check(rows)
    write_excel(rows, flags, out, "KHỐI LƯỢNG SẢN XUẤT THÂN CỘT VÀ PHỤ KIỆN CỘT AN TEN DÂY CO 42M")
    (out.with_suffix(".json")).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(rows)} rows, {sum(r.get('loai') == 'nhom' for r in rows)} group rows, {len(flags)} flagged, {time.time() - t0:.0f}s -> {out}")


if __name__ == "__main__":
    main()
