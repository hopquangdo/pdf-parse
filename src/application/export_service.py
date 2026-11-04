"""rows -> file .xlsm theo mẫu."""
import uuid
from pathlib import Path
from typing import List

from src.domain.checks import check_members
from src.domain.models import Member
from src.domain.weights import total_mass_kg
from src.infrastructure.excel.template_filler import fill_template


class ExportService:
    def __init__(self, template, sheets, storage, runs=None):
        self.template, self.sheets, self.storage, self.runs = template, sheets, storage, runs

    def export(self, rows: List[dict], paint_factor: float = 1, job_id: str | None = None) -> dict:
        members = [Member.from_dict(r) for r in rows]
        errors = [i for i in check_members(members) if i.level == "error"]
        if errors:
            raise ValueError("; ".join(i.message for i in errors))
        eid = uuid.uuid4().hex[:12]
        fill_template(self.template, [m.to_dict() for m in members], self.storage.path(f"{eid}.xlsm"), self.sheets,
                      paint_factor=paint_factor)
        mass, skipped = total_mass_kg(members)
        result = {"id": eid, "rows": len(members), "expected_mass_kg": round(mass, 1), "rows_without_mass": skipped}
        if self.runs and job_id:
            self.runs.add_output(job_id, {"kind": "xlsm", "export_id": eid, "file": f"{eid}.xlsm", "rows": len(members),
                                          "expected_mass_kg": result["expected_mass_kg"], "paint_factor": paint_factor,
                                          "template": Path(str(self.template)).name})
        return result
