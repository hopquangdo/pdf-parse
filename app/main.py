"""Chạy:  uvicorn app.main:app --reload   (từ thư mục gốc dự án)

Một tiến trình phục vụ cả API lẫn giao diện (app/frontend/dist)."""
import logging
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from src import config
from src.infrastructure.db.engine import get_engine, get_sessionmaker, upgrade_db
from src.application.auth.service import AuthService
from src.application.auth.users import bootstrap_admin
from .api import deps
from .api.routers import admin, auth, exports, extractions, history, ocr, reference

# Windows' registry has no entry for .mjs, so pdf.js's worker would be served as text/plain and refused.
mimetypes.add_type("application/javascript", ".mjs")
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    upgrade_db(get_engine())  # create / migrate the schema before serving
    with get_sessionmaker()() as db:
        if bootstrap_admin(db, AuthService(db, deps.token_codec()), config.ADMIN_EMAIL, config.ADMIN_PASSWORD, config.ADMIN_NAME,
                           config.ADMIN_MUST_CHANGE):
            log.warning("first administrator created: %s", config.ADMIN_EMAIL)
    yield


app = FastAPI(title="Thống kê thân cột", lifespan=lifespan)


@app.middleware("http")
async def same_origin_for_writes(request: Request, call_next):
    """The refresh cookie is the only credential a browser attaches by itself. It is SameSite=Strict and scoped to /auth,
    and writes from a foreign origin are refused outright as a second line of defence."""
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin")
        if origin and urlsplit(origin).netloc != request.headers.get("host", ""):
            return JSONResponse(status_code=403, content={"detail": {"code": "bad_origin", "message": "Cross-origin request refused."}})
    return await call_next(request)


app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(extractions.router)
app.include_router(exports.router)
app.include_router(reference.router)
app.include_router(ocr.router)
app.include_router(history.router)


@app.get("/health")
def health():
    return {"ok": True}


WEB = Path(__file__).resolve().parent / "frontend" / "dist"


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/app/")


if WEB.exists():
    app.mount("/app", StaticFiles(directory=WEB, html=True), name="web")
