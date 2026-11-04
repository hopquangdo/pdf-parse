import re
from pathlib import PurePath

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from .. import deps
from ..schemas import ExportRequest

router = APIRouter(prefix="/exports", tags=["exports"], dependencies=[Depends(deps.current_user)])
XLSM = "application/vnd.ms-excel.sheet.macroEnabled.12"


def download_name(source: str) -> str:
    """Source drawing name with only the extension swapped to .xlsm; falls back to a fixed name."""
    stem = PurePath(source.replace("\\", "/")).stem  # basename only: never let a client inject a path
    stem = "".join(c for c in stem if c.isprintable())  # no control characters
    stem = re.sub(r'[<>:"/|?*]', "", stem).replace(chr(92), "").strip(" .")[:150]
    return f"{stem or 'THONG KE THAN COT'}.xlsm"


@router.post("", status_code=201)
def create_export(req: ExportRequest, svc=Depends(deps.export_service)):
    try:
        res = svc.export([r.model_dump() for r in req.rows], req.paint_factor, req.job_id)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {**res, "download_url": f"/exports/{res['id']}"}


@router.get("/{export_id}")
def download(export_id: str, name: str = "", storage=Depends(deps.storage)):
    stored = f"{export_id}.xlsm"
    try:
        exists = storage.exists(stored)
    except ValueError:
        exists = False
    if not exists:
        raise HTTPException(404, "Không tìm thấy export")
    return FileResponse(storage.path(stored), media_type=XLSM, filename=download_name(name))
