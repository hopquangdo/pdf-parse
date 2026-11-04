"""OCR jobs as one JSON file each (same layout as the drawing jobs)."""
import json
import os
import re
import threading
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from src.domain.models import OcrJob, OcrPage, OcrTable


class JsonOcrRepo:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, job_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{12}", job_id):
            raise ValueError("id không hợp lệ")
        return self.root / f"{job_id}.json"

    def save(self, job: OcrJob) -> None:
        path = self._path(job.id)
        tmp = path.with_suffix(f".{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(asdict(job), ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)

    def get(self, job_id: str) -> Optional[OcrJob]:
        p = self._path(job_id)
        if not p.exists():
            return None
        d = json.loads(p.read_text(encoding="utf-8"))
        d["pages"] = [OcrPage(**{**x, "tables": [OcrTable(**t) for t in x.get("tables", [])]}) for x in d["pages"]]
        return OcrJob(**d)

    def list(self) -> List[OcrJob]:
        jobs = []
        for p in self.root.glob("*.json"):
            try:
                jobs.append(self.get(p.stem))
            except (ValueError, KeyError, TypeError, json.JSONDecodeError):
                continue
        return sorted((j for j in jobs if j), key=lambda j: j.created_at, reverse=True)
