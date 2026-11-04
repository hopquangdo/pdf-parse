"""Đo lớp review bằng cách cài lỗi vào bản đọc A rồi xem hệ thống bắt/sửa được bao nhiêu.

Chạy:  python -m evaluation.review_eval [--seeds 2] [--pages 6,8]
Cần LLM_API_KEY trong .env. B_MODEL / C_MODEL chọn model đọc cả bảng / đọc lại từng dòng.
"""
import argparse
import copy
import json
import os
import random
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List

from src import config
from src.domain.table_rules import check_row, normalize_row
from src.infrastructure.pdf.table_detector import detect_tables
from src.infrastructure.pdf.table_geometry import nonblank_bands, render_row_zoom  # noqa: F401
from src.infrastructure.pdf.renderer import render_box
from src.infrastructure.vision.band_rereader import BandRereader
from src.infrastructure.vision.table_reader import TableVisionReader
from src.application.table_review.graph import TableReviewer
from evaluation.fault_injection import KINDS, mutate

ROOT = config.ROOT
PDF = ROOT / "3_-THAN-COT TD36m-2_66M_Hoa Tien Model (1).pdf"
TRUTH = ROOT / "tests" / "fixtures" / "tables_truth.json"
ROTATE = 90
USD_VND = 26000
PRICE = {  # USD / triệu token (vào, ra), theo bảng giá OpenRouter đã tra
    "deepseek/deepseek-v4.1-flash": (0.02, 1.0),
    "deepseek/deepseek-v4-flash-vision-exp": (0.2156, 0.6468),
}


class ReviewEvaluation:
    def __init__(self, b_model: str, c_model: str, cache_dir: Path, scenario_workers: int = 3, mutate_b: bool = False):
        key = os.environ["LLM_API_KEY"]
        self.b_reader, self.c_reader = TableVisionReader(key, b_model), TableVisionReader(key, c_model)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.workers, self.mutate_b = scenario_workers, mutate_b
        self.pdf = PDF.read_bytes()
        self.truth_all = json.loads(TRUTH.read_text(encoding="utf-8"))
        self.tables: Dict[int, dict] = {}

    # ---- chuẩn bị ----
    def prepare(self, page: int) -> dict:
        if page not in self.tables:
            box = detect_tables(self.pdf, page)[0]
            bands = nonblank_bands(self.pdf, box, ROTATE)
            truth = [normalize_row(r) for r in self.truth_all[str(page)]]
            assert len(bands) - 1 == len(truth), (page, len(bands) - 1, len(truth))
            self.tables[page] = {"box": box, "data_bands": bands[1:], "truth": truth, "expected": len(truth)}
        return self.tables[page]

    def reader_b_rows(self, page: int) -> List[Dict]:
        """Bản đọc B: đọc cả bảng một lần, lưu cache để các kịch bản dùng lại."""
        cache = self.cache_dir / f"b_p{page}.json"
        if cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))
        t = self.prepare(page)
        b = t["box"]
        png = render_box(self.pdf, page, (b.x0, b.y0, b.x1, b.y1), rotate=ROTATE)
        rows = self.b_reader.read_table(png)
        cache.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        return rows

    # ---- một kịch bản ----
    def run_scenario(self, page: int, kind: str, seed: int) -> dict:
        t = self.prepare(page)
        truth, b_rows = t["truth"], self.reader_b_rows(page)
        if kind == "clean":
            a_rows, fault = copy.deepcopy(truth), {"kind": "clean", "mark": None}
        else:
            a_rows, fault = mutate(truth, kind, random.Random(seed * 1000 + page))
        if self.mutate_b and kind != "clean":
            # bản đọc B cũng sai một ô ở dòng khác với A: hai reader sai độc lập
            b_rows = [normalize_row(r) for r in b_rows]
            for k in range(1, 50):
                b_rows2, bf = mutate(b_rows, random.Random(seed * 77 + k).choice(["digit_L", "digit_a", "qty"]),
                                     random.Random(seed * 77 + k))
                if bf["mark"] != fault.get("mark"):
                    b_rows = b_rows2
                    fault = {**fault, "b_fault": bf}
                    break
        rereader = BandRereader(self.pdf, t["box"], ROTATE, t["data_bands"], self.c_reader)
        res = TableReviewer(rereader).review(a_rows, b_rows, t["expected"])

        baseline = {r["mark"] for r in truth if check_row(r)}   # lỗi thật của bản vẽ (C16, C17)
        human = {r.mark for r in res.human} - baseline
        correct = res.rows == truth
        wrong_marks = [r["mark"] for r, tr in zip(res.rows, truth) if r != tr] if len(res.rows) == len(truth) else ["(lệch số dòng)"]
        if res.table_flag:
            outcome = "escalated"
        elif correct and not human:
            outcome = "fixed" if kind != "clean" else "clean_ok"
        elif correct:
            outcome = "false_alarm"
        elif human:
            outcome = "escalated"
        else:
            outcome = "missed"
        return {"page": page, "kind": kind, "seed": seed, "fault": fault, "outcome": outcome,
                "wrong_marks": wrong_marks, "human": sorted(human), "attempts": res.attempts,
                "reread_errors": rereader.errors}

    # ---- chạy hàng loạt ----
    def run(self, pages: List[int], seeds: int) -> List[dict]:
        jobs = [(p, "clean", 0) for p in pages] + [(p, k, s) for p in pages for k in KINDS for s in range(seeds)]
        for p in pages:
            self.reader_b_rows(p)  # đọc B trước để không gọi trùng giữa các luồng
        with ThreadPoolExecutor(self.workers) as ex:
            return list(ex.map(lambda j: self.run_scenario(*j), jobs))

    def cost(self) -> dict:
        out = {}
        for name, rd in (("B", self.b_reader), ("C", self.c_reader)):
            pin, pout = PRICE.get(rd.model, (0, 0))
            usd = (rd.usage["prompt_tokens"] * pin + rd.usage["completion_tokens"] * pout) / 1e6
            out[name] = {"model": rd.model, **rd.usage, "usd": round(usd, 4), "vnd": round(usd * USD_VND)}
        out["total_vnd"] = out["B"]["vnd"] + out["C"]["vnd"]
        return out


def summarize(results: List[dict]) -> str:
    lines = []
    by_kind: Dict[str, Counter] = {}
    for r in results:
        by_kind.setdefault(r["kind"], Counter())[r["outcome"]] += 1
    for k, c in by_kind.items():
        lines.append(f"{k:10s} " + ", ".join(f"{o}={n}" for o, n in sorted(c.items())))
    faults = [r for r in results if r["kind"] != "clean"]
    n = len(faults)
    ok = sum(r["outcome"] == "fixed" for r in faults)
    esc = sum(r["outcome"] == "escalated" for r in faults)
    miss = sum(r["outcome"] == "missed" for r in faults)
    fa = sum(r["outcome"] == "false_alarm" for r in results)
    lines.append(f"Tổng {n} kịch bản có lỗi: tự sửa đúng {ok}, chuyển người {esc}, BỎ SÓT {miss}; báo nhầm {fa}")
    clean = [r for r in results if r["kind"] == "clean"]
    lines.append(f"Kịch bản không lỗi: {sum(r['outcome'] == 'clean_ok' for r in clean)}/{len(clean)} sạch")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--pages", default="6,8")
    ap.add_argument("--mutate-b", action="store_true", help="cài thêm lỗi độc lập vào bản đọc B")
    ap.add_argument("--b-model", default=os.environ.get("B_MODEL", "deepseek/deepseek-v4-flash-vision-exp"))
    ap.add_argument("--c-model", default=os.environ.get("C_MODEL", "deepseek/deepseek-v4.1-flash"))
    a = ap.parse_args()
    ev = ReviewEvaluation(a.b_model, a.c_model, config.DATA_DIR / "eval", mutate_b=a.mutate_b)
    t0 = time.time()
    results = ev.run([int(p) for p in a.pages.split(",")], a.seeds)
    out = config.DATA_DIR / "eval" / ("results_mutate_b.json" if a.mutate_b else "results.json")
    out.write_text(json.dumps({"results": results, "cost": ev.cost()}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(summarize(results))
    print("thời gian", round(time.time() - t0), "s | chi phí", json.dumps(ev.cost(), ensure_ascii=False))
    for r in results:
        if r["outcome"] in ("missed", "false_alarm") or r["reread_errors"]:
            print("CHÚ Ý", json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()
