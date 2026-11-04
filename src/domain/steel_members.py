"""Turning what is printed on the drawing into schedule rows (Member dicts). Pure functions, no I/O."""
import re
from typing import Dict, List, Optional

_ANGLE = re.compile(r"L\s*(\d+(?:[.,]\d+)?)\s*[xX×]\s*(\d+(?:[.,]\d+)?)")
_PLATE = re.compile(r"[dDđĐ]\s*(\d+(?:[.,]\d+)?)\s*[-–]\s*(\d+(?:[.,]\d+)?)\s*[xX×]\s*(\d+(?:[.,]\d+)?)")
_BAR = re.compile(r"H?L\s*(\d+(?:[.,]\d+)?)\s*[xX×*]\s*(\d+(?:[.,]\d+)?)\s*[-–]\s*(\d+(?:[.,]\d+)?)")
_PAIR = re.compile(r"^([A-Za-z]+\d+)-([A-Za-z]+\d+[a-z]?)$")
_SECTION = re.compile(r"ĐOẠN\s*(?:CỘT\s*)?([A-Z])\b", re.I)


def _n(s: str):
    v = float(s.replace(",", "."))
    return int(v) if v.is_integer() else v


def section_from_title(title: str) -> str:
    """'CHI TIẾT BẢN MÃ ĐOẠN CỘT B' -> 'ĐOẠN B'; 'CHI TIẾT KIM THU SÉT' -> 'KIM THU SÉT'."""
    t = (title or "").upper().replace("Đ", "Đ")
    if "KIM THU" in t:
        return "KIM THU SÉT"
    m = _SECTION.search(t)
    return f"ĐOẠN {m.group(1).upper()}" if m else (title or "").strip()


def parse_angle(spec: str) -> Optional[tuple]:
    """'THÉP L50x5' -> (50, 5)."""
    m = _ANGLE.search(spec or "")
    return (_n(m.group(1)), _n(m.group(2))) if m else None


def parse_plate(spec: str) -> Optional[Dict]:
    """'D8-172x100' -> thickness 8, length 172, width 100 (the drawing writes d<t>-<length>x<width>)."""
    m = _PLATE.search(spec or "")
    return {"t": _n(m.group(1)), "len": _n(m.group(2)), "w": _n(m.group(3))} if m else None


def angle_rows_to_members(section: str, spec: str, rows: List[Dict]) -> List[Dict]:
    """Rows of a drilling table (mark, L, qty) -> angle members. A joined mark 'B3-B3a' with qty 8 is two bars of 4."""
    wt = parse_angle(spec)
    if wt is None:
        raise ValueError(f"quy cách không đọc được: {spec!r}")
    out = []
    for r in rows:
        mark, qty = r["mark"], r["qty"]
        m = _PAIR.match(mark)
        parts = [m.group(1), m.group(2)] if m else [mark]
        if m and qty is not None and qty % 2 == 0:
            qty //= 2
        for p in parts:
            out.append({"section": section, "mark": p, "type": "L", "w": wt[0], "t": wt[1], "len": r["L"], "qty": qty})
    return out


def plate_to_member(section: str, mark: str, spec: str, qty: int) -> Dict:
    """A call-out is either a plate ("D8-172x100") or an angle bar with its length ("HL100*8-3900", "L50x5-704")."""
    b = _BAR.search(spec or "")
    if b and not _PLATE.search(spec or ""):
        return {"section": section, "mark": mark, "type": "L", "w": _n(b.group(1)), "t": _n(b.group(2)), "len": _n(b.group(3)), "qty": qty}
    p = parse_plate(spec)
    if p is None:
        raise ValueError(f"quy cách bản mã không đọc được: {spec!r}")
    return {"section": section, "mark": mark, "type": "d", "w": p["w"], "t": p["t"], "len": p["len"], "qty": qty}
