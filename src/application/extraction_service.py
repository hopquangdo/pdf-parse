"""PDF -> rows -> checked rows. WHAT is read and how depends on the drawing type; this service only orchestrates."""
import contextvars
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from typing import List, Optional

from src.application.drawing_types import registry
from src.application.drawing_types.base import ExtractionContext
from src.domain.checks import check_members
from src.domain.models import ExtractionJob, Issue, Member
from src.domain.ports import FileStorage, JobRepository, PageRenderer, RunRecorder, TableLocator, TableReader, VisionReader
from src.infrastructure.llm.usage import UsageLogger, get_usage_logger
from src.infrastructure.pdf.renderer import PyMuPdfRenderer
from src.infrastructure.pdf.table_detector import LineTableLocator


class ExtractionService:
    def __init__(self, reader: Optional[VisionReader], repo: JobRepository, storage: FileStorage, workers: int = 6,
                 backoff: float = 1.0, usage: UsageLogger | None = None, runs: RunRecorder | None = None,
                 table_reader: Optional[TableReader] = None, review_reader: Optional[TableReader] = None,
                 renderer: PageRenderer | None = None, locator: TableLocator | None = None,
                 default_type: str = registry.DEFAULT):
        self.reader, self.repo, self.storage = reader, repo, storage
        self.table_reader, self.review_reader = table_reader, review_reader or table_reader
        self.renderer, self.locator = renderer or PyMuPdfRenderer(), locator or LineTableLocator()
        self.usage = usage or get_usage_logger()
        self.runs = runs
        if runs is not None and runs.record_call not in self.usage.listeners:
            self.usage.listeners.append(runs.record_call)
        self.workers, self.backoff, self.default_type = workers, backoff, default_type

    def create(self, pdf: bytes, filename: str, owner_id: str = "", drawing_type: str | None = None) -> ExtractionJob:
        drawing_type = drawing_type or self.default_type
        registry.get(drawing_type)  # unknown type: fail now, not in the background
        job = ExtractionJob(id=uuid.uuid4().hex[:12], filename=filename, owner_id=owner_id, created_at=time.time(),
                            page_count=self.renderer.page_count(pdf), drawing_type=drawing_type)
        self.storage.save(f"{job.id}.pdf", pdf)
        self.repo.save(job)
        if self.runs:
            self.runs.start(job.id, filename=filename, stored_as=f"{job.id}.pdf", data=pdf, pages=job.page_count, owner_id=owner_id)
        return job

    def _read(self, png: bytes, label: str, retries: int = 3):
        """Đọc một vùng, thử lại với khoảng chờ tăng dần. Trả (rows, lỗi)."""
        for attempt in range(retries):
            try:
                return self.reader.read(png, label), None
            except Exception as e:  # noqa: BLE001 - mạng/giới hạn tốc độ/JSON hỏng
                err = e
                time.sleep(2 ** attempt * self.backoff)
        return [], err

    def _step(self, job_id: str, name: str, **detail):
        """Time a step in the run log (a no-op when no run log is attached)."""
        return self.runs.step(job_id, name, **detail) if self.runs else nullcontext({})

    def _parallel(self, fn, items):
        """Run fn over items in a pool, keeping order and the usage/step scope; returns [(result, error)]."""
        ctx = contextvars.copy_context()  # worker threads do not inherit it: hand the scope and step over

        def one(item):
            try:
                return ctx.copy().run(fn, item), None
            except Exception as e:  # noqa: BLE001 - one failing region must not sink the job
                return None, e
        with ThreadPoolExecutor(self.workers) as ex:
            return list(ex.map(one, items))  # map keeps the order

    def run(self, job_id: str, rotate: int = 0, cols: int = 1, rows: int = 1, pages=None) -> ExtractionJob:
        job = self.repo.get(job_id)
        job.status = "running"
        self.repo.save(job)
        started = time.perf_counter()
        if self.runs:
            self.runs.begin(job_id, {"drawing_type": job.drawing_type, "rotate": rotate, "cols": cols, "rows": rows,
                                     "pages": list(pages) if pages else "all"})
        try:
            with self.usage.scope(job_id):
                with self._step(job_id, "load_pdf") as d:
                    pdf = self.storage.path(f"{job_id}.pdf").read_bytes()
                    d["bytes"] = len(pdf)
                ctx = ExtractionContext(
                    pdf=pdf, pages=list(pages or range(1, self.renderer.page_count(pdf) + 1)), renderer=self.renderer,
                    locator=self.locator, step=lambda name, **detail: self._step(job_id, name, **detail),
                    options={"rotate": rotate, "cols": cols, "rows": rows}, workers=self.workers, reader=self.reader,
                    table_reader=self.table_reader, review_reader=self.review_reader,
                    read_region=(lambda png, label: self._read(png, label)) if self.reader else None,
                    run_parallel=self._parallel)
                outcome = registry.get(job.drawing_type).extract(ctx)
                with self._step(job_id, "validate") as d:
                    seen, out, issues = set(), [], list(outcome.issues)
                    for raw in outcome.rows:
                        try:
                            m = Member.from_dict(raw)
                        except (KeyError, TypeError, ValueError, AttributeError) as e:
                            issues.append(Issue("warning", f"dòng đọc lỗi {raw!r} ({e})"))
                            continue
                        key = (m.section, m.mark)
                        if m.mark and key in seen:  # overlapping regions read the same row twice
                            continue
                        seen.add(key)
                        out.append(m)
                    if not out and not issues:
                        issues.append(Issue("error", "Không đọc được dòng nào từ bản vẽ: vùng ảnh có thể quá nhỏ/quá rộng để đọc chữ"))
                    job.rows = [m.to_dict() for m in out]
                    job.issues = issues + check_members(out)
                    d["rows"], d["issues"] = len(job.rows), len(job.issues)
            job.status = "done"
        except Exception as e:  # noqa: BLE001 - ghi lỗi vào job thay vì làm sập tác vụ nền
            job.status, job.error = "failed", str(e)
        job.usage = {**self.usage.totals(job_id), "wall_seconds": round(time.perf_counter() - started, 2)}
        if job.usage["calls"]:
            from src.infrastructure.llm.usage import log
            log.info("job %s %s: %s", job_id, job.status, UsageLogger.format_totals(job.usage))
        self.repo.save(job)
        if self.runs:
            self.runs.finish(job_id, status=job.status, error=job.error, rows=len(job.rows), issues=len(job.issues))
        return job

    def update_rows(self, job_id: str, rows: List[dict]) -> ExtractionJob:
        job = self.repo.get(job_id)
        members = [Member.from_dict(r) for r in rows]
        job.rows = [m.to_dict() for m in members]
        job.issues = check_members(members)
        self.repo.save(job)
        if self.runs:
            self.runs.update_counts(job_id, rows=len(job.rows), issues=len(job.issues))
        return job
