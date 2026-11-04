"""Đồ thị review bảng thanh: triage -> reread -> vote -> (lặp lại | finalize).

Đầu vào: hai bản đọc độc lập của cả bảng (A, B) và hàm đọc lại phóng to từng dòng (reader C).
Đầu ra: bảng đã soát kèm báo cáo từng dòng: ok / fixed / human.
"""
import contextvars
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph

from src.domain.table_rules import FIELDS, check_row, normalize_row
from src.application.table_review.voting import RowVoter

Rereader = Callable[[int, int], Optional[Dict]]  # (chỉ số dòng, lần thử) -> dòng đã đọc lại


class ReviewState(TypedDict, total=False):
    a_rows: List[Dict]
    b_rows: List[Dict]
    expected: int
    base: List[Dict]          # bản đọc khớp số dòng của lưới, dùng làm gốc để đánh chỉ số
    other: Dict[str, Dict]    # bản đọc còn lại, tra theo số hiệu thanh
    suspects: List[int]
    pending: List[int]
    c_reads: Dict[int, List[Dict]]
    attempt: int
    results: Dict[int, Dict]
    table_flag: Optional[str]
    log: List[str]


@dataclass
class RowReport:
    index: int
    mark: str
    status: str   # ok | fixed | human
    detail: Any


@dataclass
class ReviewResult:
    rows: List[Dict]
    report: List[RowReport]
    table_flag: Optional[str] = None
    attempts: int = 0
    log: List[str] = field(default_factory=list)

    @property
    def human(self) -> List[RowReport]:
        return [r for r in self.report if r.status == "human"]


class TableReviewer:
    def __init__(self, rereader: Rereader, voter: Optional[RowVoter] = None, max_attempts: int = 3,
                 workers: int = 6):
        self.rereader, self.voter = rereader, voter or RowVoter()
        self.max_attempts, self.workers = max_attempts, workers
        self.graph = self._build()

    # ---- API ----
    def review(self, a_rows: List[Dict], b_rows: List[Dict], expected: int) -> ReviewResult:
        out = self.graph.invoke({"a_rows": a_rows, "b_rows": b_rows, "expected": expected})
        results = out["results"]
        order = sorted(results)
        return ReviewResult(
            rows=[results[i]["row"] for i in order],
            report=[RowReport(i, results[i]["row"]["mark"], results[i]["status"], results[i]["detail"]) for i in order],
            table_flag=out.get("table_flag"),
            attempts=out.get("attempt", 0),
            log=out.get("log", []),
        )

    # ---- đồ thị ----
    def _build(self):
        g = StateGraph(ReviewState)
        g.add_node("triage", self._triage)
        g.add_node("reread", self._reread)
        g.add_node("vote", self._vote)
        g.add_node("finalize", self._finalize)
        g.set_entry_point("triage")
        g.add_conditional_edges("triage", self._after_triage, {"reread": "reread", "finalize": "finalize"})
        g.add_edge("reread", "vote")
        g.add_conditional_edges("vote", self._after_vote, {"reread": "reread", "finalize": "finalize"})
        g.add_edge("finalize", END)
        return g.compile()

    @staticmethod
    def _same(r1: Optional[Dict], r2: Optional[Dict]) -> bool:
        return r1 is not None and r2 is not None and all(r1.get(f) == r2.get(f) for f in FIELDS)

    def _triage(self, s: ReviewState) -> ReviewState:
        a = [normalize_row(r) for r in s["a_rows"]]
        b = [normalize_row(r) for r in s["b_rows"]]
        exp, log = s["expected"], []
        if len(b) == exp:
            base, other = b, a
        elif len(a) == exp:
            base, other = a, b
            log.append(f"bản đọc B có {len(b)} dòng, lưới có {exp}: dùng bản A làm gốc")
        else:
            return {"base": [], "other": {}, "suspects": [], "results": {}, "c_reads": {}, "attempt": 0,
                    "table_flag": f"số dòng đọc được (A={len(a)}, B={len(b)}) đều khác số dòng của lưới ({exp})",
                    "log": log}
        other_by = {r["mark"]: r for r in other}
        base_marks = {r["mark"] for r in base}
        log += [f"bản đọc phụ có dòng '{r['mark']}' không khớp dòng nào của gốc"
                for r in other if r["mark"] not in base_marks]
        suspects = []
        for i, r in enumerate(base):
            o = other_by.get(r["mark"])
            if o is None or not self._same(r, o) or check_row(r) or check_row(o):
                suspects.append(i)
        return {"base": base, "other": other_by, "suspects": suspects, "pending": list(suspects), "results": {},
                "c_reads": {}, "attempt": 0, "table_flag": None, "log": log}

    def _reread(self, s: ReviewState) -> ReviewState:
        reads = {k: list(v) for k, v in s["c_reads"].items()}
        todo, attempt = s["pending"], s["attempt"]
        ctx = contextvars.copy_context()  # keep the job's usage/step scope inside the pool threads
        with ThreadPoolExecutor(self.workers) as ex:
            got = list(ex.map(lambda i: ctx.copy().run(self.rereader, i, attempt), todo))
        for i, row in zip(todo, got):
            if row is not None:
                reads.setdefault(i, []).append(normalize_row(row))
        return {"c_reads": reads, "attempt": attempt + 1}

    def _vote(self, s: ReviewState) -> ReviewState:
        results, pending = dict(s["results"]), []
        for i in s["pending"]:
            base_row = s["base"][i]
            cands = [base_row] + ([s["other"][base_row["mark"]]] if base_row["mark"] in s["other"] else [])
            cands += s["c_reads"].get(i, [])
            row, unresolved = self.voter.vote(cands)
            issues = check_row(row)
            if issues:
                alt = self.voter.rule_fix(cands, row)
                if alt is not None:
                    changed = {f: (base_row[f], alt[f]) for f in FIELDS if base_row[f] != alt[f]}
                    results[i] = {"row": alt, "status": "fixed",
                                  "detail": {"theo công thức + lần đọc phóng to": changed}}
                    continue
            if not unresolved and not issues:
                changed = {f: (base_row[f], row[f]) for f in FIELDS if base_row[f] != row[f]}
                results[i] = {"row": row, "status": "fixed" if changed else "ok",
                              "detail": changed or "đã xác nhận bằng đọc lại"}
            elif not unresolved:
                # mọi lần đọc đồng thuận nhưng công thức không khớp: đọc lại không giúp gì, có thể lỗi bản vẽ
                results[i] = {"row": row, "status": "human",
                              "detail": "các lần đọc đồng thuận nhưng sai công thức: " + "; ".join(issues)}
            else:
                results[i] = {"row": row, "status": "human", "detail": f"ô chưa phân định: {unresolved}"}
                pending.append(i)
        return {"results": results, "pending": pending}

    def _finalize(self, s: ReviewState) -> ReviewState:
        res = dict(s["results"])
        for i, r in enumerate(s["base"]):
            res.setdefault(i, {"row": r, "status": "ok", "detail": "hai bản đọc khớp nhau và qua kiểm tra"})
        return {"results": res}

    @staticmethod
    def _after_triage(s: ReviewState) -> str:
        return "reread" if s["suspects"] else "finalize"

    def _after_vote(self, s: ReviewState) -> str:
        return "reread" if s["pending"] and s["attempt"] < self.max_attempts else "finalize"
