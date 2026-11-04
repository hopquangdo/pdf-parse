"""Điền mẫu 'THỐNG KÊ KHỐI LƯỢNG THÂN CỘT' (.xlsm), giữ macro và công thức."""
import copy
import re
from pathlib import Path
from typing import List

import openpyxl

FIRST = 4
FORMULA_COLS = ["A", "H", "J", "K", "L", "M", "N"]


def _shift(formula: str, src_row: int, dst_row: int) -> str:
    f = re.sub(rf"(?<![$\w])([A-Z]{{1,2}}){src_row}(?!\d)", rf"\g<1>{dst_row}", formula)
    if "AGGREGATE" in formula:
        f = re.sub(rf"(?<![$\w])([A-Z]{{1,2}}){src_row - 1}(?!\d)", rf"\g<1>{dst_row - 1}", f)
    return f


def _fill_sheet(ws, rows: List[dict]) -> int:
    tmpl = {c: ws[f"{c}{FIRST}"].value for c in FORMULA_COLS}
    styles = {c: copy.copy(ws.cell(FIRST + 1, c)._style) for c in range(1, ws.max_column + 1)}
    total_style = {c: copy.copy(ws.cell(ws.max_row, c)._style) for c in range(1, ws.max_column + 1)}
    for rng in [r for r in ws.merged_cells.ranges if r.min_row >= FIRST]:
        ws.unmerge_cells(str(rng))
    if ws.max_row >= FIRST:
        ws.delete_rows(FIRST, ws.max_row - FIRST + 1)

    r = FIRST
    groups = []
    for row in rows:
        for c, st in styles.items():
            ws.cell(r, c)._style = copy.copy(st)
        if not groups or groups[-1][0] != row["section"]:
            groups.append([row["section"], r, r])
            ws[f"B{r}"] = row["section"]
        groups[-1][2] = r
        ws[f"C{r}"] = row.get("mark")
        ws[f"D{r}"] = row["type"]
        ws[f"E{r}"] = row["w"]
        ws[f"F{r}"] = row.get("t")
        ws[f"G{r}"] = row["len"]
        ws[f"I{r}"] = row.get("qty")
        for c, f in tmpl.items():
            ws[f"{c}{r}"] = _shift(f, FIRST, r) if isinstance(f, str) and f.startswith("=") else f
        r += 1
    for _, a, b in groups:
        if b > a:
            ws.merge_cells(f"B{a}:B{b}")
    for c, st in total_style.items():
        ws.cell(r, c)._style = copy.copy(st)
    ws[f"A{r}"] = "Tổng cộng"
    ws.merge_cells(f"A{r}:L{r}")
    ws[f"M{r}"] = f"=SUBTOTAL(9,M{FIRST}:M{r - 1})"
    ws[f"N{r}"] = f"=SUBTOTAL(9,N{FIRST}:N{r - 1})"
    # mẫu gốc ẩn sẵn các dòng dữ liệu và lưu khung nhìn đang cuộn tới dòng 220: bỏ ẩn dòng vừa ghi
    # và đặt lại vị trí khoá khung (nếu không, Excel mở file ra không thấy dòng nào)
    for rr in range(FIRST, r + 1):
        ws.row_dimensions[rr].hidden = False
    ws.freeze_panes = f"A{FIRST}"
    ws.sheet_view.topLeftCell = "A1"
    return r


def fill_template(template: Path, rows: List[dict], out: Path, sheets: List[str], paint_factor: float = 1) -> Path:
    wb = openpyxl.load_workbook(template, keep_vba=True)
    found = [s for s in sheets if s in wb.sheetnames]
    if not found:
        raise ValueError(f"Mẫu không có sheet nào trong {sheets}")
    for s in found:
        _fill_sheet(wb[s], rows)
        wb[s]["P3"] = paint_factor  # hệ số sơn: every paint-area formula reads $P$3
    wb.save(out)
    return out
