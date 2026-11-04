import pytest
from fastapi.testclient import TestClient

from app.main import app
from src.infrastructure.security.passwords import password_problems
from src.application.auth.users import bootstrap_admin
from tests.conftest import PASSWORD, sign_in

NEW = {"email": "new.person@example.com", "name": "New Person", "role": "user", "password": "temporary passphrase 1"}


def test_only_administrators_manage_accounts(client, admin_client):
    for method, path, kw in [("get", "/admin/users", {}), ("post", "/admin/users", {"json": NEW}),
                             ("patch", "/admin/users/abc", {"json": {"is_active": False}}),
                             ("post", "/admin/users/abc/reset-password", {"json": {"new_password": "x" * 12}}),
                             ("post", "/admin/users/abc/unlock", {})]:
        r = getattr(client, method)(path, **kw)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "forbidden", path
    assert admin_client.get("/admin/users").status_code == 200


def test_admin_creates_an_account_that_must_choose_its_own_password(admin_client, app_env):
    r = admin_client.post("/admin/users", json=NEW)
    assert r.status_code == 201
    created = r.json()
    assert created["email"] == NEW["email"] and created["must_change_password"] is True and "password_hash" not in created and "password" not in created
    person = TestClient(app)
    body = sign_in(person, NEW["email"], NEW["password"])
    assert body["user"]["must_change_password"] is True
    assert person.get("/extractions").status_code == 403


def test_creating_an_account_validates_everything(admin_client):
    assert admin_client.post("/admin/users", json=NEW).status_code == 201
    dup = admin_client.post("/admin/users", json={**NEW, "email": "NEW.person@EXAMPLE.com"})
    assert dup.status_code == 409 and dup.json()["detail"]["code"] == "email_taken"
    assert admin_client.post("/admin/users", json={**NEW, "email": "not-an-email"}).status_code == 422
    assert admin_client.post("/admin/users", json={**NEW, "email": "x@y.com", "role": "root"}).status_code == 422
    weak = admin_client.post("/admin/users", json={**NEW, "email": "w@y.com", "password": "short"})
    assert weak.status_code == 422 and weak.json()["detail"]["code"] == "weak_password"


def test_an_admin_cannot_lock_the_company_out_by_disabling_or_demoting_the_last_admin(admin_client):
    me = admin_client.get("/auth/me").json()["user"]["id"]
    assert admin_client.patch(f"/admin/users/{me}", json={"is_active": False}).json()["detail"]["code"] == "last_admin"
    assert admin_client.patch(f"/admin/users/{me}", json={"role": "user"}).json()["detail"]["code"] == "last_admin"
    second = admin_client.post("/admin/users", json={**NEW, "role": "admin"}).json()["id"]
    assert admin_client.patch(f"/admin/users/{second}", json={"is_active": False}).status_code == 200  # another admin remains
    assert admin_client.patch(f"/admin/users/{me}", json={"role": "user"}).status_code == 409  # but never yourself


def test_reset_password_signs_the_person_out_and_forces_a_new_one(admin_client, client):
    uid = client.get("/auth/me").json()["user"]["id"]
    assert client.get("/extractions").status_code == 200
    bad = admin_client.post(f"/admin/users/{uid}/reset-password", json={"new_password": "short"})
    assert bad.status_code == 422
    ok = admin_client.post(f"/admin/users/{uid}/reset-password", json={"new_password": "reset passphrase 77"})
    assert ok.status_code == 200 and ok.json()["must_change_password"] is True
    assert client.get("/extractions").status_code == 401  # old sessions are gone
    fresh = TestClient(app)
    assert fresh.post("/auth/login", json={"email": "user@example.com", "password": PASSWORD}).status_code == 401
    assert sign_in(fresh, "user@example.com", "reset passphrase 77")["user"]["must_change_password"] is True


def test_unknown_user_id_is_a_404(admin_client):
    assert admin_client.patch("/admin/users/nope", json={"is_active": False}).status_code == 404


@pytest.mark.parametrize("password,expected", [
    ("short", True), ("a" * 129, True), (" leading space ok?", True), ("aaaaaaaaaaaa", True), ("Password123", True),
    ("password123", True), ("alice.smith is my name", True), ("correct horse battery", False), ("x9#Lw!qZ2m", False)])
def test_password_policy(password, expected):
    assert bool(password_problems(password, "alice.smith@example.com")) is expected


def test_bootstrap_creates_the_first_admin_once_and_only_when_empty(db_factory):
    from app.api import deps
    from src.application.auth.service import AuthService
    with db_factory() as db:
        auth = AuthService(db, deps.token_codec())
        assert bootstrap_admin(db, auth, "", "", "x") is False  # not configured
        assert bootstrap_admin(db, auth, "root@example.com", "first admin passphrase", "Root") is True
        assert bootstrap_admin(db, auth, "other@example.com", "another passphrase 22", "Other") is False  # users exist now
        with pytest.raises(RuntimeError, match="rejected"):
            from sqlalchemy import delete
            from src.infrastructure.db.models import User
            db.execute(delete(User))
            db.commit()
            bootstrap_admin(db, auth, "root@example.com", "short", "Root")


def test_bootstrap_admin_can_be_created_without_a_forced_password_change(db_factory):
    from app.api import deps
    from sqlalchemy import select
    from src.infrastructure.db.models import User
    from src.application.auth.service import AuthService
    with db_factory() as db:
        assert bootstrap_admin(db, AuthService(db, deps.token_codec()), "dev@example.com", "dev admin passphrase", "Dev", must_change_password=False)
        assert db.scalar(select(User.must_change_password).where(User.email == "dev@example.com")) is False
