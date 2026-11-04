"""One history for both tools: drawing extractions and OCR runs, newest first."""
from fastapi import APIRouter, Depends

from .. import deps

router = APIRouter(prefix="/history", tags=["history"], dependencies=[Depends(deps.current_user)])


@router.get("")
def history(runs=Depends(deps.run_log), ocr=Depends(deps.ocr_job_repo)):
    """kind = steel | ocr. The same summary fields for both so the UI can show them in one table."""
    items = [{**r, "kind": "steel"} for r in runs.list()]
    for j in ocr.list():
        done = [p for p in j.pages if p.status == "done"]
        failed = sum(p.status == "error" for p in j.pages)
        items.append({"id": j.id, "kind": "ocr", "filename": j.filename, "status": j.status, "page_count": len(j.pages),
                      "created_at": j.created_at, "rows": sum(len(t.rows) for p in done for t in p.tables), "issues": failed,
                      "cost_usd": None, "cost_vnd": sum(p.cost_vnd for p in j.pages),
                      "wall_seconds": round(sum(p.seconds for p in j.pages), 1) or None})
    return sorted(items, key=lambda r: r.get("created_at") or 0, reverse=True)
