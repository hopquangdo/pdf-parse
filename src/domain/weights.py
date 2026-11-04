"""Khối lượng đối chiếu (không thay cho công thức trong Excel)."""
from typing import Optional

from src.domain.models import Member

STEEL_DENSITY = 7850  # kg/m3
# đơn trọng kg/m của thép góc đều cạnh, theo 'Steel Lib' của mẫu
ANGLE_KG_PER_M = {(50, 5): 3.77, (100, 8): 12.2}


def member_mass_kg(m: Member) -> Optional[float]:
    """None nếu không đủ dữ liệu để tính (bu lông, thép góc ngoài bảng...)."""
    if m.type == "L":
        kg_m = ANGLE_KG_PER_M.get((m.w, m.t))
        return None if kg_m is None else kg_m * m.len / 1000 * m.qty
    if m.type == "d" and isinstance(m.t, (int, float)):
        return m.w * m.t * m.len / 1e9 * STEEL_DENSITY * m.qty
    if m.type == "Ф":
        return 3.14159265 * (m.w / 2000) ** 2 * (m.len / 1000) * STEEL_DENSITY * m.qty
    return None


def total_mass_kg(members) -> tuple:
    """(tổng khối lượng tính được, số dòng không tính được)."""
    total, skipped = 0.0, 0
    for m in members:
        v = member_mass_kg(m)
        if v is None:
            skipped += 1
        else:
            total += v
    return total, skipped
