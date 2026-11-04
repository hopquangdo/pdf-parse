"""Bỏ phiếu từng ô giữa các lần đọc độc lập của cùng một dòng bảng."""
from collections import Counter
from itertools import product
from typing import Callable, Dict, List, Optional, Tuple

from src.domain.table_rules import FIELDS, check_row

RowCheck = Callable[[Dict], List[str]]


class RowVoter:
    def __init__(self, check: RowCheck = check_row):
        self.check = check

    def vote(self, candidates: List[Dict]) -> Tuple[Dict, List[str]]:
        """Mỗi ô lấy giá trị có ≥2 phiếu và hơn hẳn giá trị kế tiếp. Trả (dòng, các ô chưa phân định).

        Ô chưa phân định giữ giá trị của ứng viên đầu tiên (bản đọc gốc) để vẫn có dòng hiển thị.
        """
        row, unresolved = {}, []
        for f in FIELDS:
            ranked = Counter(c.get(f) for c in candidates).most_common()
            top_val, top_n = ranked[0]
            if top_n >= 2 and (len(ranked) == 1 or ranked[1][1] < top_n):
                row[f] = top_val
            else:
                row[f] = candidates[0].get(f)
                unresolved.append(f)
        return row, unresolved

    def rule_fix(self, candidates: List[Dict], voted: Dict) -> Optional[Dict]:
        """Khi dòng thắng phiếu sai công thức: thử các tổ hợp giá trị đã từng được đọc.

        Chỉ nhận khi có đúng một tổ hợp qua kiểm tra, tức công thức và một lần đọc phóng to cùng ủng hộ.
        """
        options = {f: list(dict.fromkeys(c.get(f) for c in candidates)) for f in FIELDS}
        passing = []
        for combo in product(*(options[f] for f in FIELDS)):
            row = dict(zip(FIELDS, combo))
            if row["mark"] == voted["mark"] and not self.check(row):
                passing.append(row)
        return passing[0] if len(passing) == 1 else None
