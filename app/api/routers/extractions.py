from dataclasses import asdict

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse

from src import config
from src.infrastructure.db.models import User
from src.infrastructure.pdf import renderer
from .. import deps
from ..schemas import RowsUpdate

# Everything here needs a signed-in user. There is no per-user separation: every account sees every drawing.
router = APIRouter(prefix="/extractions", tags=["extractions"], dependencies=[Depends(deps.current_user)])


def _get(repo, job_id: str):
    try:
        job = repo.get(job_id)
    except ValueError:
        job = None
    if job is None:
        raise HTTPException(404, "Không tìm thấy job")
    return job


@router.post("", status_code=202)
async def create_extraction(bg: BackgroundTasks, file: UploadFile = File(...), rotate: int = 0,
                            cols: int = 1, rows: int = 1, drawing_type: str | None = None, svc=Depends(deps.extraction_service),
                            user: User = Depends(deps.current_user)):
    data = await file.read(config.MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"PDF vượt quá {config.MAX_UPLOAD_MB}MB")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "File không phải PDF")
    if rotate not in (0, 90, 180, 270) or not (1 <= cols <= 6 and 1 <= rows <= 6):
        raise HTTPException(422, "rotate phải là 0/90/180/270; cols, rows trong 1..6")
    try:
        job = svc.create(data, file.filename or "upload.pdf", owner_id=user.id, drawing_type=drawing_type)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    # owner_id is recorded as "uploaded by", not enforced
    bg.add_task(svc.run, job.id, rotate, cols, rows)
    return {"id": job.id, "status": job.status, "status_url": f"/extractions/{job.id}"}


@router.get("")
def list_extractions(runs=Depends(deps.run_log)):
    """Read from the run logs (data/runs): what the history shows is exactly what was logged."""
    return runs.list()


@router.get("/{job_id}/run")
def run_log(job_id: str, runs=Depends(deps.run_log)):
    """The full log of one run: input file, options, every step, every model call and its cost, outputs."""
    try:
        run = runs.get(job_id)
    except ValueError:
        run = None
    if run is None:
        raise HTTPException(404, "Không tìm thấy run")
    return run


@router.get("/{job_id}/file")
def source_pdf(job_id: str, repo=Depends(deps.job_repo), store=Depends(deps.storage)):
    """PDF gốc cho trình xem canvas (pdf.js) trên giao diện."""
    _get(repo, job_id)
    return FileResponse(store.path(f"{job_id}.pdf"), media_type="application/pdf",
                        headers={"Cache-Control": "private, max-age=3600"})


@router.get("/{job_id}/pages/{page}.png")
def page_image(job_id: str, page: int, dpi: int = 110, rotate: int = 0, repo=Depends(deps.job_repo),
               store=Depends(deps.storage)):
    job = _get(repo, job_id)
    if not 1 <= page <= job.page_count or not 40 <= dpi <= 300 or rotate not in (0, 90, 180, 270):
        raise HTTPException(422, "page, dpi hoặc rotate không hợp lệ")
    pdf = store.path(f"{job_id}.pdf").read_bytes()
    png = next(iter(renderer.render_tiles(pdf, page, rotate=rotate, dpi=dpi)))[1]
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/{job_id}")
def get_extraction(job_id: str, repo=Depends(deps.job_repo)):
    return asdict(_get(repo, job_id))


@router.put("/{job_id}/rows")
def update_rows(job_id: str, body: RowsUpdate, svc=Depends(deps.review_service)):
    _get(svc.repo, job_id)
    return asdict(svc.update_rows(job_id, [r.model_dump() for r in body.rows]))
