"""Quy tắc kiểm tra cứng cho bảng thanh thép (a, b, c, d, L, số lượng).

Công thức suy ra từ các cột có dữ liệu, không cần cấu hình theo nhóm:
  có d      : L = a + 2c  và  L = b + d     (thanh giằng ngang có lỗ lệch)
  có b      : L = a + b + 2c               (thanh giằng chéo)
  chỉ có a  : L = a + 2c                   (thanh giằng quá trầm)
"""
import re
from typing import Dict, List, Optional

FIELDS = ("mark", "a", "b", "c", "d", "L", "qty")
NUMERIC = ("a", "b", "c", "d", "L", "qty")


def _num(v) -> Optional[float]:
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, bool):
        raise ValueError("không phải số")
    if isinstance(v, str):
        v = float(v.strip().replace(",", "."))
    return int(v) if float(v).is_integer() else float(v)


def normalize_row(raw: dict) -> Dict:
    """Chuẩn hoá một dòng model trả về: ô trống thành None, số ép về int/float."""
    row = {"mark": re.sub(r"\s+", "", str(raw.get("mark", "")))}
    for k in NUMERIC:
        try:
            row[k] = _num(raw.get(k))
        except (ValueError, TypeError):
            row[k] = None
    return row


def check_row(row: dict, tol: float = 1) -> List[str]:
    a, b, c, d, L = (row.get(k) for k in ("a", "b", "c", "d", "L"))
    if L is None or a is None or c is None:
        return ["thiếu a, c hoặc L"]
    out = []
    if d is not None:
        if b is None:
            return ["có d nhưng thiếu b"]
        if abs(a + 2 * c - L) > tol:
            out.append(f"L={L} nhưng a+2c={a + 2 * c}")
        if abs(b + d - L) > tol:
            out.append(f"L={L} nhưng b+d={b + d}")
    elif b is not None:
        if abs(a + b + 2 * c - L) > tol:
            out.append(f"L={L} nhưng a+b+2c={a + b + 2 * c}")
    elif abs(a + 2 * c - L) > tol:
        out.append(f"L={L} nhưng a+2c={a + 2 * c}")
    if row.get("qty") is None or row["qty"] <= 0:
        out.append("số lượng thiếu hoặc ≤ 0")
    return out
