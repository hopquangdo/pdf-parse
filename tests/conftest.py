import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api import deps
from app.main import app
from src.infrastructure.db.engine import make_engine, upgrade_db
from src.infrastructure.db.base import Base
from src.infrastructure.persistence.json_job_repo import JsonJobRepo
from src.infrastructure.persistence.json_ocr_repo import JsonOcrRepo
from src.infrastructure.runs.run_log import RunLog
from src.infrastructure.storage.local_storage import LocalStorage
from src.infrastructure.vision.fake_reader import FakeReader
from src.application.auth.service import AuthService
from src.application.auth.users import UserService
from src.application.extraction_service import ExtractionService

FIX = Path(__file__).parent / "fixtures"
PDF = Path(__file__).resolve().parent.parent / "3_-THAN-COT TD36m-2_66M_Hoa Tien Model (1).pdf"
PASSWORD = "correct horse battery"  # satisfies the password policy


@pytest.fixture
def rows():
    return json.loads((FIX / "rows.json").read_text(encoding="utf-8"))


@pytest.fixture
def db_factory(tmp_path):
    """A fresh migrated database per test: SQLite by default, real Postgres when TEST_DATABASE_URL is set."""
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    engine = make_engine(url)
    if not url.startswith("sqlite"):  # shared server: start from nothing
        Base.metadata.drop_all(engine)
        with engine.begin() as conn:
            conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    upgrade_db(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    yield factory
    engine.dispose()


@pytest.fixture
def make_user(db_factory):
    def make(email="user@example.com", password=PASSWORD, role="user", must_change=False, name="Test User"):
        with db_factory() as db:
            svc = UserService(db, AuthService(db, deps.token_codec()))
            return svc.create(email, name, role, password, must_change_password=must_change)
    return make


@pytest.fixture
def app_env(tmp_path, db_factory):
    """Wire the app to temporary storage and the test database. No sign-in yet."""
    storage, repo, runs = LocalStorage(tmp_path / "files"), JsonJobRepo(tmp_path / "jobs"), RunLog(tmp_path / "runs")
    reader = FakeReader([[{"section": "ĐOẠN B", "mark": "B1", "type": "L", "w": 100, "t": 8, "len": 3900, "qty": 4}]])

    def get_db():
        with db_factory() as db:
            yield db

    app.dependency_overrides[deps.get_db] = get_db
    app.dependency_overrides[deps.storage] = lambda: storage
    app.dependency_overrides[deps.job_repo] = lambda: repo
    app.dependency_overrides[deps.run_log] = lambda: runs
    ocr_repo = JsonOcrRepo(tmp_path / "ocr")
    app.dependency_overrides[deps.ocr_job_repo] = lambda: ocr_repo
    app.dependency_overrides[deps.extraction_service] = lambda: ExtractionService(reader, repo, storage, runs=runs, default_type="generic")
    yield
    app.dependency_overrides.clear()


def sign_in(client: TestClient, email: str, password: str = PASSWORD) -> dict:
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    body = r.json()
    client.headers["Authorization"] = f"Bearer {body['access_token']}"  # what the real UI does
    return body


@pytest.fixture
def anon(app_env):
    """A client that is not signed in."""
    return TestClient(app)


@pytest.fixture
def client(app_env, make_user):
    """A signed-in client (ordinary user): the default for the data-endpoint tests."""
    make_user("user@example.com")
    c = TestClient(app)
    sign_in(c, "user@example.com")
    return c


@pytest.fixture
def admin_client(app_env, make_user):
    make_user("admin@example.com", role="admin", name="Admin")
    c = TestClient(app)
    sign_in(c, "admin@example.com")
    return c
