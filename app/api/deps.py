"""Ghép services với infrastructure. Test ghi đè bằng app.dependency_overrides."""
import os
from functools import lru_cache
from typing import Optional, Tuple

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from src import config
from src.infrastructure.db.engine import get_sessionmaker
from src.infrastructure.db.models import AuthSession, User
from src.infrastructure.persistence.json_job_repo import JsonJobRepo
from src.infrastructure.persistence.json_ocr_repo import JsonOcrRepo
from src.infrastructure.runs.run_log import RunLog
from src.infrastructure.storage.local_storage import LocalStorage
from src.application.auth.service import AuthError, AuthService
from src.infrastructure.security.tokens import TokenCodec
from src.application.auth.users import UserService
from src.application.export_service import ExportService
from src.application.extraction_service import ExtractionService
from src.application.ocr_job_service import OcrJobService
from src.application.ocr_service import OcrService

REFRESH_COOKIE = "refresh_token"  # the only cookie: the access token travels in the Authorization header


@lru_cache
def storage() -> LocalStorage:
    return LocalStorage(config.DATA_DIR / "files")


@lru_cache
def job_repo() -> JsonJobRepo:
    return JsonJobRepo(config.DATA_DIR / "jobs")


@lru_cache
def ocr_job_repo() -> JsonOcrRepo:
    return JsonOcrRepo(config.DATA_DIR / "ocr")


@lru_cache
def run_log() -> RunLog:
    return RunLog(config.DATA_DIR / "runs")


# ------------------------------------------------------------------ database and authentication
def get_db():
    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()


@lru_cache
def token_codec() -> TokenCodec:
    return TokenCodec(config.JWT_SECRET)


def auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db, token_codec())


def user_service(db: Session = Depends(get_db), auth: AuthService = Depends(auth_service)) -> UserService:
    return UserService(db, auth)


def auth_http(e: AuthError) -> HTTPException:
    headers = {"Retry-After": str(e.retry_after)} if e.retry_after else None
    return HTTPException(e.status, detail={"code": e.code, "message": e.message}, headers=headers)


def bearer_token(request: Request) -> Optional[str]:
    """`Authorization: Bearer <access token>`; anything else counts as no token."""
    scheme, _, value = request.headers.get("authorization", "").partition(" ")
    return value.strip() if scheme.lower() == "bearer" and value.strip() else None


def auth_context(request: Request, auth: AuthService = Depends(auth_service)) -> Tuple[User, AuthSession]:
    """The signed-in user and their session, from the access token in the Authorization header.
    Allowed while a password change is pending (so the person can actually change it)."""
    try:
        return auth.authenticate(bearer_token(request))
    except AuthError as e:
        raise auth_http(e) from None


def current_user(ctx: Tuple[User, AuthSession] = Depends(auth_context)) -> User:
    """Every data endpoint depends on this: signed in, and not stuck on a forced password change."""
    user = ctx[0]
    if user.must_change_password:
        raise HTTPException(403, detail={"code": "password_change_required", "message": "Choose a new password to continue."})
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, detail={"code": "forbidden", "message": "Administrator access required."})
    return user


# ------------------------------------------------------------------ domain services
def export_service(store=Depends(storage), runs=Depends(run_log)) -> ExportService:
    return ExportService(config.TEMPLATE_XLSM, config.TEMPLATE_SHEETS, store, runs)


def llm_key() -> str:
    key = os.environ.get("LLM_API_KEY")
    if not key:
        raise HTTPException(503, "Chưa cấu hình LLM_API_KEY nên chưa đọc được bản vẽ")
    return key


def review_service(repo=Depends(job_repo), store=Depends(storage), runs=Depends(run_log)) -> ExtractionService:
    return ExtractionService(None, repo, store, runs=runs)  # không cần reader: chỉ đọc/sửa job


def extraction_service(runs=Depends(run_log)) -> ExtractionService:
    from src.infrastructure.vision.openai_compat_reader import OpenAICompatReader
    from src.infrastructure.vision.table_reader import TableVisionReader
    key = llm_key()
    return ExtractionService(OpenAICompatReader(key), job_repo(), storage(), runs=runs,
                             table_reader=TableVisionReader(key, config.LLM_MODEL_NAME),
                             review_reader=TableVisionReader(key, config.LLM_REVIEW_MODEL))


def ocr_service() -> OcrService:
    from src.infrastructure.vision.table_reader import TableVisionReader
    return OcrService(TableVisionReader(llm_key(), config.LLM_MODEL_NAME))


@lru_cache
def _local_reader():
    from src.infrastructure.vision.cell_ocr import CellReader
    return CellReader(super_res=config.OCR_SUPER_RES)       # the model loads once, on first use


@lru_cache
def _angle_weights() -> dict:
    from src.infrastructure.excel.catalog import load_catalog
    return dict(load_catalog(config.TEMPLATE_XLSM)["angles"])


def page_extractor(ocr: OcrService = Depends(ocr_service)):
    """How the tables of a page are read: config OCR_ENGINE=local (ruling lines + VietOCR, the model repairs doubtful cells) or llm."""
    from src.application.page_extractors import LlmPageExtractor, LocalPageExtractor
    if config.OCR_ENGINE == "local":
        return LocalPageExtractor(_local_reader(), _angle_weights(), ocr)
    return LlmPageExtractor(ocr)


def ocr_job_service(repo=Depends(ocr_job_repo), store=Depends(storage), extractor=Depends(page_extractor)) -> OcrJobService:
    return OcrJobService(extractor, repo, store)
