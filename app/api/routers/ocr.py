"""OCR API: an image (or a page of a PDF) in, text or a table (JSON / Excel) out. Needs a signed-in user."""
import json
import uuid
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Response, UploadFile

from src import config
from dataclasses import asdict

from src.application.ocr_job_service import OcrJobService
from src.application.ocr_service import OcrService
from src.infrastructure.db.models import User
from src.infrastructure.llm.usage import get_usage_logger
from src.infrastructure.pdf.page_image import UnsupportedFile, load_image
from .. import deps

router = APIRouter(prefix="/ocr", tags=["ocr"], dependencies=[Depends(deps.current_user)])


async def _image(file: UploadFile, page: int, svc: OcrService, rotate: str, image: int = 1):
    data = await file.read(config.MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"File vượt quá {config.MAX_UPLOAD_MB}MB")
    try:
        return svc.rotate(load_image(data, page, image=image), rotate)
    except UnsupportedFile as e:
        raise HTTPException(422, str(e)) from None
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


def _columns(raw: str):
    """`columns` form field: a JSON list of column names, or empty to let the model use the grid it sees."""
    if not raw.strip():
        return None
    try:
        cols = json.loads(raw)
    except ValueError:
        raise HTTPException(422, "columns phải là mảng JSON các tên cột") from None
    if not (isinstance(cols, list) and cols and all(isinstance(c, str) for c in cols)):
        raise HTTPException(422, "columns phải là mảng JSON các tên cột")
    return cols


def _usage(rid: str) -> dict:
    t = get_usage_logger().totals(rid)
    return {k: t.get(k) for k in ("calls", "input_tokens", "output_tokens", "cost_usd", "cost_vnd")}


@router.post("/text")
async def ocr_text(file: UploadFile = File(...), page: int = Form(1), rotate: str = Form("0"), image: int = Form(1), svc: OcrService = Depends(deps.ocr_service)):
    """Plain text of an image or of one PDF page. rotate: 0, 90, 180, 270 (clockwise) or auto. image: which embedded picture of a PDF page (1 = the largest)."""
    im = await _image(file, page, svc, rotate, image)
    rid = uuid.uuid4().hex
    with get_usage_logger().scope(rid):
        text = svc.text(im)
    return {"text": text, "usage": _usage(rid)}


@router.post("/table")
async def ocr_table(file: UploadFile = File(...), page: int = Form(1), rotate: str = Form("0"),
                    format: str = Query("json", pattern="^(json|xlsx)$"), header_rows: int = Form(1), image: int = Form(1),
                    columns: str = Form(""), svc: OcrService = Depends(deps.ocr_service)):
    """A table as rows of cells. format=json returns the rows; format=xlsx returns the Excel file (named after the upload)."""
    cols = _columns(columns)
    im = await _image(file, page, svc, rotate, image)
    rid = uuid.uuid4().hex
    with get_usage_logger().scope(rid):
        res = svc.table(im, columns=cols)
    if format == "xlsx":
        name = (file.filename or "ocr").rsplit(".", 1)[0] + ".xlsx"
        return Response(res.xlsx(header_rows=header_rows), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f"attachment; filename=\"table.xlsx\"; filename*=utf-8''{quote(name)}",
                                 "X-OCR-Warnings": str(len(res.warnings))})
    return {"rows": res.rows, "columns": max((len(r) for r in res.rows), default=0), "chunks": res.chunks,
            "warnings": res.warnings, "usage": _usage(rid)}


def _page_list(spec: str) -> list:
    """'1,3-5' -> [1, 3, 4, 5]."""
    pages = []
    try:
        for part in spec.split(","):
            a, _, b = part.strip().partition("-")
            pages += range(int(a), int(b or a) + 1)
    except ValueError:
        raise HTTPException(422, "pages phải có dạng 1,3-5") from None
    return sorted(set(pages))


def _job(repo, job_id: str):
    try:
        job = repo.get(job_id)
    except ValueError:
        job = None
    if job is None:
        raise HTTPException(404, "Không tìm thấy lượt OCR")
    return job


@router.post("/jobs", status_code=202)
async def create_job(bg: BackgroundTasks, file: UploadFile = File(...), pages: str = Form("1"), rotate: str = Form("auto"),
                     svc: OcrJobService = Depends(deps.ocr_job_service), user: User = Depends(deps.current_user)):
    """Several pages of a PDF read as tables in the background; poll GET /ocr/jobs/{id}."""
    data = await file.read(config.MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"File vượt quá {config.MAX_UPLOAD_MB}MB")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "File không phải PDF")
    wanted = _page_list(pages)
    if len(wanted) > 20 or rotate not in ("0", "90", "180", "270", "auto"):
        raise HTTPException(422, "Tối đa 20 trang; rotate là 0/90/180/270/auto")
    try:
        job = svc.create(data, file.filename or "upload.pdf", wanted, rotate if rotate == "auto" else int(rotate), owner_id=user.id)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    bg.add_task(svc.run, job.id)
    return {"id": job.id, "status": job.status}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, repo=Depends(deps.ocr_job_repo)):
    job = _job(repo, job_id)
    return {**asdict(job), "status": job.status}


@router.post("/jobs/{job_id}/retry", status_code=202)
def retry_job(job_id: str, bg: BackgroundTasks, repo=Depends(deps.ocr_job_repo), svc: OcrJobService = Depends(deps.ocr_job_service)):
    """Read again only the pages that failed."""
    job = _job(repo, job_id)
    if not any(p.status == "error" for p in job.pages):
        raise HTTPException(409, "Không có trang nào lỗi")
    bg.add_task(svc.run, job.id, True)
    return {"id": job.id}


@router.get("/jobs/{job_id}/xlsx")
def job_xlsx(job_id: str, repo=Depends(deps.ocr_job_repo), svc: OcrJobService = Depends(deps.ocr_job_service)):
    job = _job(repo, job_id)
    try:
        data = svc.xlsx(job)
    except ValueError as e:
        raise HTTPException(409, str(e)) from None
    name = job.filename.rsplit(".", 1)[0] + ".xlsx"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename=\"table.xlsx\"; filename*=utf-8''{quote(name)}"})
