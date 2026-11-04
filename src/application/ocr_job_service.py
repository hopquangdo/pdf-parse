"""OCR jobs: save the PDF, read the chosen pages as tables in the background, keep the result for the history."""
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import List

from src.domain.models import OcrJob, OcrPage
from src.infrastructure.excel.table_writer import sheets_to_xlsx
from src.infrastructure.llm.usage import get_usage_logger
from src.infrastructure.pdf.page_image import page_count


class OcrJobService:
    def __init__(self, extractor, repo, storage, workers: int = 2):
        self.extractor, self.repo, self.storage, self.workers = extractor, repo, storage, workers
        self._lock = threading.Lock()                  # pages of one job finish on different threads and save the same file

    def create(self, pdf: bytes, filename: str, pages: List[int], rotate: int | str = 0, owner_id: str = "") -> OcrJob:
        total = page_count(pdf)
        if not pages or any(not 1 <= p <= total for p in pages):
            raise ValueError(f"Trang phải nằm trong 1..{total}")
        job = OcrJob(id=uuid.uuid4().hex[:12], filename=filename, owner_id=owner_id, created_at=time.time(), page_count=total,
                     rotate=rotate, pages=[OcrPage(p) for p in sorted(set(pages))])
        self.storage.save(f"{job.id}.pdf", pdf)
        self.repo.save(job)
        return job

    def run(self, job_id: str, only_failed: bool = False) -> None:
        job = self.repo.get(job_id)
        if not job:
            return
        pdf = self.storage.path(f"{job.id}.pdf").read_bytes()
        todo = [p for p in job.pages if p.status == "error"] if only_failed else job.pages
        for p in todo:
            p.status, p.error = "wait", ""
        self.repo.save(job)

        def one(p: OcrPage) -> None:
            rid = f"{job.id}-{p.page}"
            t0 = time.time()
            with self._lock:
                p.status = "run"
                self.repo.save(job)
            try:
                with get_usage_logger().scope(rid):
                    out = dict(status="done", tables=self.extractor.extract(pdf, p.page, job.rotate))
            except Exception as e:  # noqa: BLE001 - one bad page must not stop the others
                out = dict(status="error", error=str(e)[:300])
            with self._lock:
                for k, v in out.items():
                    setattr(p, k, v)
                p.cost_vnd = int(get_usage_logger().totals(rid).get("cost_vnd") or 0)
                p.seconds = round(time.time() - t0, 1)
                self.repo.save(job)

        with ThreadPoolExecutor(self.workers) as ex:
            list(ex.map(one, todo))

    def xlsx(self, job: OcrJob) -> bytes:
        done = [(t.name, t.rows, {tuple(map(int, k.split(","))): v for k, v in t.flags.items()})
                for p in job.pages if p.status == "done" for t in p.tables]
        if not done:
            raise ValueError("Chưa có trang nào đọc xong")
        return sheets_to_xlsx(done)
