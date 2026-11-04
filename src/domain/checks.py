"""Kiểm tra chéo dữ liệu bóc tách."""
from collections import Counter
from typing import Iterable, List

from src.domain.models import MEMBER_TYPES, Issue, Member


def check_members(members: Iterable[Member]) -> List[Issue]:
    members = list(members)
    issues: List[Issue] = []
    dup = Counter((m.section, m.mark) for m in members if m.mark)
    for (sec, mark), n in dup.items():
        if n > 1:
            issues.append(Issue("error", f"Trùng mã thanh {mark} trong {sec} ({n} dòng)", mark))
    for m in members:
        if m.type not in MEMBER_TYPES:
            issues.append(Issue("error", f"Loại '{m.type}' không hợp lệ (cần {MEMBER_TYPES})", m.mark))
        if m.w <= 0 or m.len <= 0 or m.qty <= 0:
            issues.append(Issue("error", "Rộng, dài, số lượng phải > 0", m.mark))
        if m.type == "M" and m.t != "Bộ":
            issues.append(Issue("warning", "Bu lông nên có cột Dày = 'Bộ'", m.mark))
    return issues


def check_bracing_length(mark: str, L: float, a: float, b: float, c: float, tol: float = 1) -> List[Issue]:
    """L = a + b + 2c cho thanh xiên/ngang."""
    expected = a + b + 2 * c
    if abs(expected - L) > tol:
        return [Issue("warning", f"{mark}: L={L} nhưng a+b+2c={expected}", mark)]
    return []


def check_chain(label: str, parts: List[float], total: float, tol: float = 1) -> List[Issue]:
    """Tổng chuỗi kích thước phải bằng kích thước tổng."""
    if abs(sum(parts) - total) > tol:
        return [Issue("warning", f"{label}: tổng chuỗi {sum(parts)} ≠ {total}")]
    return []
