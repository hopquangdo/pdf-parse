"""Steel column shaft drawings from CAD (vector PDF, text outlined).

What is read, and from where:
  * title block      -> the section ("ĐOẠN B", "KIM THU SÉT") and whether the sheet holds details
  * drilling tables  -> bracing angles: mark, L, qty per row; the angle size from the QUY CÁCH column
                        (two independent readings + zoomed row re-reads, voted by the table-review graph)
  * detail sheets    -> gusset plates and bars from their call-outs ("D8-172x100: SL=8")
"""
import re
from collections import OrderedDict
from typing import Dict, List

from src.application.drawing_types.base import ExtractionContext, ExtractionOutcome
from src.application.table_review.graph import TableReviewer
from src.domain.models import Issue
from src.domain.steel_members import angle_rows_to_members, plate_to_member, section_from_title
from src.domain.table_rules import normalize_row
from src.infrastructure.pdf.table_geometry import nonblank_bands
from src.infrastructure.prompts import load_prompt
from src.infrastructure.vision.band_rereader import BandRereader

TITLE_BLOCK = (0.85, 0.74, 0.98, 0.89)   # fractions of the upright page: the "Tên bản vẽ" cell
MARK = re.compile(r"^[A-Za-z]{1,3}\d{1,3}[a-z]?$")   # B12, BP3, C16a; not "B3-B3a" (a table row) or "HL100*8-3900" (a spec)
TYPE_ORDER = {"L": 0, "d": 1, "Ф": 2, "M": 3}


class SteelColumn:
    key = "steel_column"
    label = "Steel column shaft (CAD PDF)"
    MIN_TABLE_ROWS, MIN_TABLE_COLS = 6, 8      # smaller grids on these sheets are notes / legends, not drilling tables

    def extract(self, ctx: ExtractionContext) -> ExtractionOutcome:
        out = ExtractionOutcome()
        rot = {p: 90 if ctx.renderer.page_is_portrait(ctx.pdf, p) else 0 for p in ctx.pages}

        with ctx.step("read_title_blocks") as d:
            crops = [(p, ctx.renderer.render_fraction(ctx.pdf, p, TITLE_BLOCK, rotate=rot[p])) for p in ctx.pages]
            got = ctx.run_parallel(lambda c: ctx.table_reader.ask_json(c[1], load_prompt("title_block"), f"p{c[0]}_title"), crops)
            titles: Dict[int, str] = {}
            for (p, _), (ans, err) in zip(crops, got):
                titles[p] = ans.get("title", "") if isinstance(ans, dict) else ""
                if err is not None or not titles[p]:
                    out.issues.append(Issue("warning", f"Trang {p}: không đọc được tên bản vẽ ({err or 'rỗng'})"))
            d["titles"] = {str(p): t for p, t in titles.items()}

        jobs = []   # (kind, page, payload)
        with ctx.step("locate") as d:
            for p in ctx.pages:
                for box in ctx.locator.find(ctx.pdf, p):
                    if box.rows >= self.MIN_TABLE_ROWS and box.cols >= self.MIN_TABLE_COLS:
                        jobs.append(("table", p, box))
                if "CHI TIẾT" in titles[p].upper():
                    for label, png in ctx.renderer.render_tiles(ctx.pdf, p, rotate=rot[p], cols=2, rows=2):
                        jobs.append(("plates", p, (label, png)))
            d["tables"] = sum(j[0] == "table" for j in jobs)
            d["plate_regions"] = sum(j[0] == "plates" for j in jobs)

        with ctx.step("read_details", workers=ctx.workers) as d:
            results = ctx.run_parallel(lambda j: self._run_job(ctx, j, rot, titles), jobs)
            d["jobs"] = len(jobs)
            d["failed"] = sum(1 for _, err in results if err is not None)

        members: List[dict] = []
        seen = set()
        # tables first: a row printed in a drilling table wins over the same mark read from a call-out
        for (kind, page, _), (res, err) in sorted(zip(jobs, results), key=lambda jr: jr[0][0] != "table"):
            if err is not None:
                out.issues.append(Issue("error", f"Trang {page}: không đọc được ({type(err).__name__}: {str(err)[:120]})"))
                continue
            rows, issues = res
            out.issues += issues
            for r in rows:
                if kind == "plates" and not MARK.match(r["mark"] or ""):
                    continue                    # a table row or a spec read as if it were a call-out
                key = (r["section"], r["mark"])
                if kind == "plates" and key in seen:  # regions overlap: the same call-out is seen twice
                    continue
                seen.add(key)
                members.append(r)
        out.rows = self._ordered(members)
        out.issues += self._missing_main_members(out.rows)
        return out

    @staticmethod
    def _missing_main_members(rows: List[dict]) -> List[Issue]:
        """Legs and the lightning rod are dimensioned on the elevations, not listed in a table: flag them for the reviewer."""
        marks = {(r["section"], r["mark"]) for r in rows}
        issues = []
        for section in sorted({r["section"] for r in rows}):
            if section.startswith("ĐOẠN ") and (section, f"{section[-1]}1") not in marks:
                issues.append(Issue("warning", f"{section}: chưa có thanh chính {section[-1]}1 (chân cột) và các thanh chỉ ghi trên mặt đứng — nhập thêm từ bản vẽ", f"{section[-1]}1"))
            if section == "KIM THU SÉT" and (section, "KTS") not in marks:
                issues.append(Issue("warning", "KIM THU SÉT: chưa có thanh KTS (thanh tròn) — nhập thêm từ bản vẽ", "KTS"))
        return issues

    # ------------------------------------------------------------------ jobs
    def _run_job(self, ctx: ExtractionContext, job, rot, titles):
        kind, page, payload = job
        section = section_from_title(titles.get(page, ""))
        if kind == "plates":
            label, png = payload
            ans = ctx.table_reader.ask_json(png, load_prompt("plates"), label)
            rows, issues = [], []
            for it in ans if isinstance(ans, list) else []:
                try:
                    rows.append(plate_to_member(section, str(it["mark"]).replace(" ", ""), str(it["spec"]), int(it["qty"])))
                except (KeyError, ValueError, TypeError) as e:
                    issues.append(Issue("warning", f"Trang {page}: nhãn chi tiết đọc lỗi {it!r} ({e})"))
            return rows, issues
        return self._read_table(ctx, page, payload, rot[page], section)

    def _read_table(self, ctx: ExtractionContext, page: int, box, rotate: int, section: str):
        pdf = ctx.pdf
        png = ctx.renderer.render_box(pdf, page, (box.x0, box.y0, box.x1, box.y1), rotate=rotate)
        bands = nonblank_bands(pdf, box, rotate)
        expected = len(bands) - 1                                   # band 0 is the header
        tag = f"p{page}"
        a_rows = ctx.table_reader.read_table(png, f"{tag}_table_A")
        b_rows = ctx.review_reader.read_table(png, f"{tag}_table_B")
        meta = ctx.table_reader.ask_json(png, load_prompt("table_meta"), f"{tag}_table_spec")
        spec = str(meta.get("spec", "")) if isinstance(meta, dict) else ""
        rereader = BandRereader(pdf, box, rotate, bands[1:], ctx.review_reader)
        res = TableReviewer(rereader, workers=ctx.workers).review(a_rows, b_rows, expected)
        issues: List[Issue] = []
        if res.table_flag:
            pick = a_rows if len(a_rows) == expected else (b_rows if len(b_rows) == expected else max(a_rows, b_rows, key=len))
            rows = [normalize_row(x) for x in pick]
            issues.append(Issue("warning", f"Trang {page}: {res.table_flag}; dùng bản đọc A, cần kiểm tra cả bảng"))
        else:
            rows = res.rows
            for h in res.human:
                if str(h.detail).startswith("ô chưa phân định"):
                    issues.append(Issue("warning", f"Trang {page}: dòng {h.mark} chưa chắc chắn ({h.detail})", h.mark))
        return angle_rows_to_members(section, spec, rows), issues

    # ------------------------------------------------------------------ output order
    @staticmethod
    def _ordered(members: List[dict]) -> List[dict]:
        """Rows of one section stay together (the workbook groups consecutive rows by section): angles, plates, bars."""
        by_section: "OrderedDict[str, List[dict]]" = OrderedDict()
        for m in sorted(members, key=lambda m: m["section"]):
            by_section.setdefault(m["section"], []).append(m)
        return [m for rows in by_section.values() for m in sorted(rows, key=lambda m: TYPE_ORDER.get(m["type"], 9))]
