"""Lookup tables the template's formulas rely on, read from the template itself so they never drift."""
from pathlib import Path
from typing import Dict

import openpyxl

PAINT_CELL = ("THAN COT 36M K CO GIA", "P3")


def load_catalog(template: Path) -> Dict:
    """angles: {"L50x50x5": kg/m}; bolts: {"M16": {"50": kg per bolt}}; paint_factor: number."""
    wb = openpyxl.load_workbook(template, data_only=True, keep_vba=True)  # cached values, not formulas
    steel = wb["Steel Lib"]
    angles = {}
    for r in range(11, 128):
        key, kg_m = steel.cell(r, 15).value, steel.cell(r, 17).value
        if isinstance(key, str) and isinstance(kg_m, (int, float)):
            angles.setdefault(key, kg_m)  # the template has repeated keys; VLOOKUP(FALSE) returns the FIRST match, so must we

    sheet = wb["khoi luong"]
    lengths = {c: sheet.cell(4, c).value for c in range(7, 34) if isinstance(sheet.cell(4, c).value, (int, float))}
    bolts: Dict[str, Dict[str, float]] = {}
    for r in range(5, 19):
        key = sheet.cell(r, 6).value
        if not isinstance(key, str):
            continue
        row = {str(int(length) if float(length).is_integer() else length): sheet.cell(r, c).value for c, length in lengths.items()}
        bolts[key] = {k: v for k, v in row.items() if isinstance(v, (int, float))}

    factor = wb[PAINT_CELL[0]][PAINT_CELL[1]].value
    return {"angles": angles, "bolts": bolts, "paint_factor": factor if isinstance(factor, (int, float)) else 1}
