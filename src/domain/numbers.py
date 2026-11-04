"""Numbers as printed on Vietnamese drawings: '1.849,51' (thousands '.', decimal ','), '0,040', '13.726,0'."""
import re
from typing import Optional

_THOUSANDS = re.compile(r"^\d{1,3}(\.\d{3})+(,\d+)?$")


def parse_vn_number(text) -> Optional[float]:
    """The number in a cell, or None when the cell is empty, a dash or not a plain number."""
    s = str(text or "").strip().replace(" ", "")
    if not s or s in ("-", "–"):
        return None
    s = s.replace(".", "").replace(",", ".") if _THOUSANDS.match(s) else s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None
