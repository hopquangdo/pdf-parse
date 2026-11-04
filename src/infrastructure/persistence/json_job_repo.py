"""Lưu job dạng file JSON, mỗi job một file."""
import json
import os
import re
import threading
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from src.domain.models import ExtractionJob, Issue


class JsonJobRepo:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, job_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{12}", job_id):
            raise ValueError("job id không hợp lệ")
        return self.root / f"{job_id}.json"

    def save(self, job: ExtractionJob) -> None:
        path = self._path(job.id)
        tmp = path.with_suffix(f".{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(asdict(job), ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)

    def list(self) -> List[ExtractionJob]:
        jobs = []
        for p in self.root.glob("*.json"):
            try:
                jobs.append(self.get(p.stem))
            except (ValueError, KeyError, TypeError, json.JSONDecodeError):
                continue  # bỏ qua file hỏng, không làm sập danh sách
        return sorted((j for j in jobs if j), key=lambda j: j.created_at, reverse=True)

    def get(self, job_id: str) -> Optional[ExtractionJob]:
        p = self._path(job_id)
        if not p.exists():
            return None
        d = json.loads(p.read_text(encoding="utf-8"))
        d["issues"] = [Issue(**i) for i in d["issues"]]
        return ExtractionJob(**d)
