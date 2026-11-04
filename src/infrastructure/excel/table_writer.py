"""Rows of cells -> an .xlsx file (bytes). Cells that are plain numbers become numbers; the rest stay text."""
import io
import re
from typing import Dict, List, Sequence, Tuple

import openpyxl
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.properties import PageSetupProperties
from openpyxl.utils import get_column_letter

from src.domain.numbers import parse_vn_number


def rows_to_xlsx(rows: Sequence[Sequence[str]], title: str = "", header_rows: int = 1, sheet: str = "OCR",
                 flags: Dict[Tuple[int, int], str] | None = None) -> bytes:
    """flags[(row_index, column_index)] = reason: those cells are highlighted with a comment for the reviewer."""
    wb = openpyxl.Workbook()
    _fill(wb.active, rows, title, header_rows, sheet, flags)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def sheets_to_xlsx(sheets: Sequence[Tuple], header_rows: int | None = None) -> bytes:
    """One worksheet per (name, rows) pair, in order. header_rows=None: the first well-filled row is the header, rows above it are titles."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for sheet in sheets:                       # (name, rows) or (name, rows, flags): flags {(row, col): reason} highlight cells to check
        name, rows = sheet[0], sheet[1]
        _fill(wb.create_sheet(), rows, "", header_rows, name, sheet[2] if len(sheet) > 2 else None)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


FONT = "Arial"
EDGE = Side(style="thin", color="A6A6A6")
BORDER = Border(left=EDGE, right=EDGE, top=EDGE, bottom=EDGE)
HEAD_FILL = PatternFill("solid", fgColor="1F4E78")
GROUP_FILL = PatternFill("solid", fgColor="DDEBF7")
TOTAL_FILL = PatternFill("solid", fgColor="BDD7EE")
FLAG_FILL = PatternFill("solid", fgColor="FFF2CC")
TOTAL_WORDS = re.compile(r"^\s*(tổng|cộng|khối lượng)", re.I)


def _is_group(row: Sequence[str], first_filled: bool) -> bool:
    """A section title or a subtotal: nothing in the first (index) column but something further along."""
    return first_filled and not str(row[0]).strip() and any(str(c).strip() for c in row[1:])


def _fill(ws, rows, title, header_rows, sheet, flags) -> None:
    ws.title = sheet[:31]
    ws.sheet_view.showGridLines = False
    top = 1
    if title:
        ws.cell(1, 1, title).font = Font(name=FONT, bold=True, size=13)
        top = 3
    width = max((len(r) for r in rows), default=0)
    titles = 0
    if header_rows is None:             # lines above the header hold only a table name: the first row filled across is the header
        titles = next((i for i, r in enumerate(rows) if sum(bool(str(c).strip()) for c in r) >= 0.6 * width), 0)
        if any(sum(bool(str(c).strip()) for c in r) > 2 for r in rows[:titles]):
            titles = 0                  # those lines are data, not a caption: there is no title above the header
        header_rows = 1 if rows else 0
    body = rows[titles + header_rows:]
    # Group rows only make sense when the first column is an index that most data rows fill.
    first_filled = bool(body) and sum(bool(str(r[0]).strip()) for r in body if r) >= 0.5 * len(body)
    for i, row in enumerate(rows):
        caption = i < titles
        header = titles <= i < titles + header_rows
        group = not caption and not header and _is_group(row, first_filled) if row else False
        total = group and any(TOTAL_WORDS.match(str(c)) for c in row)
        for j in range(width):
            raw = row[j] if j < len(row) else ""
            text = str(raw).strip()
            n = None if re.match(r"^0\d", text) else parse_vn_number(text)       # '007' is a code, '0,040' is a number
            cell = ws.cell(top + i, j + 1, n if n is not None else raw)
            if caption:
                cell.font = Font(name=FONT, size=12, bold=True)
                continue
            cell.border = BORDER
            cell.font = Font(name=FONT, size=10, bold=header or group, color="FFFFFF" if header else "000000")
            if header:
                cell.fill = HEAD_FILL
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                continue
            if n is not None:
                decimals = len(text.split(",")[-1]) if "," in text else 0   # keep the precision the table printed
                cell.number_format = "#,##0" + ("." + "0" * decimals if decimals else "")
                cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=not group)
            if group:
                cell.fill = TOTAL_FILL if total else GROUP_FILL
            if flags and (i, j) in flags:
                cell.fill = FLAG_FILL
                cell.comment = Comment(flags[(i, j)], "ocr")
        ws.row_dimensions[top + i].height = 22 if caption else 30 if header else 18
    for j in range(width):
        longest = max((len(str(r[j])) for r in body if j < len(r) and str(r[j]).strip()), default=6)
        head = max((len(str(r[j])) for r in rows[titles:titles + header_rows] if j < len(r)), default=6)
        ws.column_dimensions[get_column_letter(j + 1)].width = min(max(8, longest + 3, min(head, 18) + 3), 42)
    ws.freeze_panes = ws.cell(top + titles + header_rows, 1)
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    if header_rows:
        ws.print_title_rows = f"{top + titles}:{top + titles + header_rows - 1}"
