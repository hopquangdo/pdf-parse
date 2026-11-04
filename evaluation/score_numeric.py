"""Cell accuracy of a quantity table against a hand-read gold file.

  python -m evaluation.score_numeric out.xlsx T26-1 evaluation/gold/hv26.json

A row is found by its index (first column); a cell counts as right when its number matches the gold one (0.5% apart at most)
and a blank gold cell must be blank. A missing row is all wrong.
"""
import json
import re
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.application.table_postprocess import align_columns, find_header, locate_columns, to_float  # noqa: E402


def score(xlsx: Path, sheet: str, gold: dict) -> dict:
    rows = [["" if c is None else c for c in r] for r in openpyxl.load_workbook(xlsx)[sheet].iter_rows(values_only=True)]
    h = find_header(rows)
    cols = locate_columns([str(c) for c in rows[h]]) if h is not None else {}
    cols = (align_columns(rows, h, cols) or cols) if h is not None else cols     # same placement of the numbers as the pipeline uses
    spec_col = next((j for j, t in enumerate(rows[h]) if "quy cách" in str(t).lower()), 2) if h is not None else 2
    right = {k: 0 for k in gold["columns"][1:]}
    total = dict(right)
    missing = 0
    for g in gold["rows"]:
        hit = next((r for r in rows[(h or 0) + 1:] if str(r[0]).strip() == g[0]), None)
        missing += hit is None
        for k, want in zip(gold["columns"][1:], g[1:]):
            total[k] += 1
            if hit is None:
                continue
            if k == "spec":
                have = str(hit[spec_col]) if spec_col < len(hit) else ""
                right[k] += re.sub(r"\s", "", have).lower() == re.sub(r"\s", "", str(want)).lower()
                continue
            j = cols.get(k)
            cell = hit[j] if j is not None and j < len(hit) else ""
            have = to_float(cell) if str(cell).strip() else None
            right[k] += (have is None) if want is None else (have is not None and abs(have - want) <= 0.005 * max(abs(want), 1e-9))
    n, ok = sum(total.values()), sum(right.values())
    return {"rows_missing": missing, "rows": len(gold["rows"]), "cells": n, "right": ok, "percent": round(100 * ok / n, 1), "by_column": {k: f"{right[k]}/{total[k]}" for k in right}}


if __name__ == "__main__":
    print(json.dumps(score(Path(sys.argv[1]), sys.argv[2], json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))), ensure_ascii=False))
