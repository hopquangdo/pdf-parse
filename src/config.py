"""Cấu hình đọc từ biến môi trường."""
import logging
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv(ROOT / ".env")


def _bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


TEMPLATE_XLSM = Path(os.environ.get("TEMPLATE_XLSM", ROOT / "templates" / "than-cot-36m.xlsm"))
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data"))
TEMPLATE_SHEETS = os.environ.get("TEMPLATE_SHEETS", "THAN COT 36M K CO GIA,THAN COT 36M").split(",")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
USD_VND = float(os.environ.get("USD_VND", "26000"))
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "30"))
# Which engine reads the tables of an OCR job: "llm" (a language model reads each table image) or "local" (ruling lines + VietOCR cell by cell,
# the language model only repairs the doubtful cells). "local" needs requirements-ocr.txt; it is the right choice when the image was built with it.
OCR_ENGINE = os.environ.get("OCR_ENGINE", "llm").lower()
OCR_SUPER_RES = os.environ.get("OCR_SUPER_RES", "0") == "1"
VIETOCR_WEIGHTS = os.environ.get("VIETOCR_WEIGHTS", "")       # path of the VietOCR weights baked into the image (else downloaded on first use)
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1")
LLM_MODEL_NAME = os.environ.get("LLM_MODEL_NAME", "")
LLM_REVIEW_MODEL = os.environ.get("LLM_REVIEW_MODEL", "") or LLM_MODEL_NAME  # second, independent reader of every table

# ---- database: PostgreSQL in production (docker compose), a local SQLite file when nothing is configured ----
DATABASE_URL = os.environ.get("DATABASE_URL") or f"sqlite:///{(DATA_DIR / 'app.db').as_posix()}"

# ---- authentication ----
# JWT signing key. Without one a random key is used, so every restart signs everyone out: fine for development only.
JWT_SECRET = os.environ.get("JWT_SECRET", "")
if not JWT_SECRET:
    JWT_SECRET = secrets.token_urlsafe(48)
    logging.getLogger("auth").warning("JWT_SECRET is not set: using a random key, sessions will not survive a restart")
elif len(JWT_SECRET) < 32:
    raise RuntimeError("JWT_SECRET must be at least 32 characters")
ACCESS_TOKEN_MINUTES = int(os.environ.get("ACCESS_TOKEN_MINUTES", "15"))
REFRESH_TOKEN_DAYS = int(os.environ.get("REFRESH_TOKEN_DAYS", "7"))
SESSION_MAX_DAYS = int(os.environ.get("SESSION_MAX_DAYS", "30"))
LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_LOCK_MINUTES = int(os.environ.get("LOGIN_LOCK_MINUTES", "15"))
COOKIE_SECURE = _bool("COOKIE_SECURE", False)  # set true whenever the site is served over HTTPS
# First-run administrator, created only when the users table is empty. Forced to choose a new password at first login.
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").strip().lower()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
ADMIN_NAME = os.environ.get("ADMIN_NAME", "Administrator")
# Keep true in production. Set false only on a development machine, so the first administrator can sign in as is.
ADMIN_MUST_CHANGE = _bool("ADMIN_MUST_CHANGE", True)
