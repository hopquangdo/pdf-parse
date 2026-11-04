"""Per-run log: one JSON file per drawing, data/runs/<id>.json.

Each file records everything about a run: the input file, the options, every step of the flow with its duration,
every model call with its cost (which model, tokens in / cached / out, USD, VND, seconds), the final cost, and the
output files. The job list API reads these files, so what the history page shows is exactly what was logged.
"""
import contextvars
import hashlib
import json
import os
import re
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from src.infrastructure.llm.usage import CallUsage

_step: contextvars.ContextVar[str] = contextvars.ContextVar("run_step", default="")
_ID = re.compile(r"[0-9a-f]{12}")

# Fields the list API returns; they live at the top level of the run file so a listing never parses the call log.
SUMMARY_FIELDS = ("id", "owner_id", "filename", "status", "page_count", "created_at", "rows", "issues", "cost_usd", "cost_vnd", "wall_seconds")


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _bucket() -> Dict:
    return {"calls": 0, "input_tokens": 0, "cached_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "cost_vnd": 0,
            "unpriced_calls": 0, "call_seconds": 0.0}


def _add(bucket: Dict, c: Dict) -> None:
    bucket["calls"] += 1
    bucket["input_tokens"] += c["input_tokens"]
    bucket["cached_tokens"] += c["cached_tokens"]
    bucket["output_tokens"] += c["output_tokens"]
    bucket["call_seconds"] = round(bucket["call_seconds"] + c["seconds"], 3)
    if c["cost_usd"] is None:
        bucket["unpriced_calls"] += 1
    else:
        bucket["cost_usd"] = round(bucket["cost_usd"] + c["cost_usd"], 8)
        bucket["cost_vnd"] += c["cost_vnd"] or 0


def totals_of(calls: List[Dict]) -> Dict:
    """Final cost plus the breakdown by model and by step."""
    total, by_model, by_step = _bucket(), {}, {}
    for c in calls:
        _add(total, c)
        _add(by_model.setdefault(c["model"], _bucket()), c)
        _add(by_step.setdefault(c.get("step") or "", _bucket()), c)
    return {**total, "by_model": by_model, "by_step": by_step}


class RunLog:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    # ---- storage ----
    def path(self, run_id: str) -> Path:
        if not _ID.fullmatch(run_id):
            raise ValueError("invalid run id")
        return self.root / f"{run_id}.json"

    def get(self, run_id: str) -> Optional[Dict]:
        try:
            return json.loads(self.path(run_id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _write(self, run_id: str, run: Dict) -> None:
        path = self.path(run_id)
        tmp = path.with_suffix(f".{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)  # atomic: a reader never sees a half-written file

    def _modify(self, run_id: str, fn) -> Optional[Dict]:
        with self._lock:
            run = self.get(run_id)
            if run is None:
                return None
            fn(run)
            self._write(run_id, run)
            return run

    # ---- lifecycle ----
    def start(self, run_id: str, *, filename: str, stored_as: str, data: bytes, pages: int, owner_id: str = "") -> None:
        with self._lock:
            self._write(run_id, {
                "id": run_id, "owner_id": owner_id, "filename": filename, "status": "pending", "error": None, "created_at": time.time(),
                "page_count": pages, "rows": 0, "issues": 0, "cost_usd": 0.0, "cost_vnd": 0, "wall_seconds": None,
                "started_at": None, "finished_at": None,
                "input": {"filename": filename, "stored_as": stored_as, "size_bytes": len(data), "sha256": sha256_of(data),
                          "pages": pages, "options": {}},
                "steps": [], "calls": [], "totals": totals_of([]), "models": [], "outputs": [],
            })

    def begin(self, run_id: str, options: Dict) -> None:
        def f(r):
            r["status"], r["started_at"], r["input"]["options"] = "running", time.time(), options
        self._modify(run_id, f)

    def finish(self, run_id: str, *, status: str, error: Optional[str], rows: int, issues: int) -> Optional[Dict]:
        def f(r):
            now = time.time()
            totals = totals_of(r["calls"])
            r.update(status=status, error=error, finished_at=now, rows=rows, issues=issues, totals=totals,
                     models=sorted(totals["by_model"]), cost_usd=totals["cost_usd"], cost_vnd=totals["cost_vnd"],
                     wall_seconds=round(now - (r["started_at"] or r["created_at"]), 2))
        return self._modify(run_id, f)

    def update_counts(self, run_id: str, *, rows: int, issues: int) -> None:
        def f(r):
            r["rows"], r["issues"] = rows, issues
        self._modify(run_id, f)

    # ---- steps ----
    @contextmanager
    def step(self, run_id: str, name: str, **detail) -> Iterator[Dict]:
        """Times one step of the flow. The yielded dict collects details; model calls made inside are tagged with it."""
        rec: Dict = {"name": name, "status": "running", "started": time.time(), "ended": None, "seconds": None, "detail": dict(detail)}
        idx: Dict = {}

        def add(r):
            r["steps"].append(rec)
            idx["i"] = len(r["steps"]) - 1
        self._modify(run_id, add)
        token = _step.set(name)
        t0 = time.perf_counter()
        error: Optional[BaseException] = None
        try:
            yield rec["detail"]
        except BaseException as e:  # noqa: BLE001 - re-raised below, only recorded here
            error = e
            raise
        finally:
            _step.reset(token)
            rec.update(status="failed" if error else "done", ended=time.time(), seconds=round(time.perf_counter() - t0, 3))
            if error:
                rec["detail"]["error"] = f"{type(error).__name__}: {str(error)[:200]}"

            def done(r):
                if "i" in idx and idx["i"] < len(r["steps"]):
                    r["steps"][idx["i"]] = rec
            self._modify(run_id, done)

    # ---- model calls ----
    def record_call(self, call: CallUsage) -> None:
        """Usage-logger listener: file every model call under the run named by its scope."""
        if not _ID.fullmatch(call.scope or ""):
            return
        entry = {"ts": call.ts, "step": _step.get(), "model": call.model, "label": call.label,
                 "input_tokens": call.input_tokens, "cached_tokens": call.cached_tokens, "output_tokens": call.output_tokens,
                 "seconds": round(call.seconds, 3), "cost_usd": call.cost_usd, "cost_vnd": call.cost_vnd,
                 "cost_source": call.cost_source}

        def f(r):
            r["calls"].append(entry)
            t = totals_of(r["calls"])  # keep the running total current, so a crashed run still shows what it spent
            r.update(totals=t, cost_usd=t["cost_usd"], cost_vnd=t["cost_vnd"], models=sorted(t["by_model"]))
        self._modify(call.scope, f)

    # ---- outputs ----
    def add_output(self, run_id: str, output: Dict) -> None:
        self._modify(run_id, lambda r: r["outputs"].append({**output, "at": time.time()}))

    # ---- listing ----
    def list(self) -> List[Dict]:
        out = []
        for p in self.root.glob("*.json"):
            try:
                run = json.loads(p.read_text(encoding="utf-8"))
                out.append({k: run.get(k) for k in SUMMARY_FIELDS})
            except (OSError, ValueError):
                continue  # a damaged file must not break the history page
        return sorted(out, key=lambda r: r.get("created_at") or 0, reverse=True)
