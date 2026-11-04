import time

import jwt
from fastapi.testclient import TestClient

from app.main import app
from src.infrastructure.security.tokens import AUDIENCE, ISSUER, TokenCodec, utcnow
from tests.conftest import PASSWORD, PDF, sign_in

PROTECTED = [("get", "/extractions"), ("get", "/extractions/000000000000"), ("get", "/exports/000000000000"),
             ("get", "/reference/catalog"), ("get", "/admin/users"), ("get", "/auth/me")]


def login(client, email="user@example.com", password=PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def test_every_data_endpoint_demands_a_token_but_health_and_ui_stay_open(anon):
    for method, path in PROTECTED:
        r = getattr(anon, method)(path)
        assert r.status_code == 401 and r.json()["detail"]["code"] == "not_authenticated", path
    assert anon.post("/extractions", files={"file": ("a.pdf", PDF.read_bytes(), "application/pdf")}).status_code == 401
    assert anon.post("/exports", json={"rows": []}).status_code == 401
    assert anon.get("/health").status_code == 200


def test_login_returns_an_access_token_in_the_body_and_a_locked_down_refresh_cookie(anon, make_user):
    make_user()
    r = login(anon)
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 900 and body["user"]["email"] == "user@example.com"
    assert set(body["user"]) == {"id", "email", "name", "role", "must_change_password"}  # no hash, no secrets
    claims = jwt.decode(body["access_token"], options={"verify_signature": False})
    assert claims["sub"] == body["user"]["id"] and claims["typ"] == "access" and claims["exp"] - claims["iat"] == 900
    cookies = r.headers.get_list("set-cookie")
    assert len(cookies) == 1 and cookies[0].startswith("refresh_token=")  # the access token is NOT in a cookie
    low = cookies[0].lower()
    assert "httponly" in low and "samesite=strict" in low and "path=/auth" in low
    assert r.headers["cache-control"] == "no-store"


def test_the_bearer_header_authenticates_and_the_cookie_alone_does_not(anon, make_user):
    make_user()
    body = login(anon).json()
    fresh = TestClient(app)
    fresh.cookies.update(anon.cookies)  # a browser holding only cookies, no header
    assert fresh.get("/extractions").status_code == 401
    assert fresh.get("/extractions", headers={"Authorization": f"Bearer {body['access_token']}"}).status_code == 200
    assert fresh.get("/extractions", headers={"Authorization": f"Basic {body['access_token']}"}).status_code == 401


def test_wrong_password_and_unknown_email_look_identical(anon, make_user):
    make_user()
    a = login(anon, password="not the password")
    b = login(anon, email="nobody@example.com", password="whatever it is")
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json() and a.json()["detail"]["code"] == "invalid_credentials"
    assert not a.headers.get_list("set-cookie")


def test_email_is_case_insensitive(anon, make_user):
    make_user("Mixed.Case@Example.com")
    assert login(anon, "MIXED.case@example.COM").status_code == 200


def test_forged_tampered_wrong_key_and_none_algorithm_tokens_are_rejected(client, anon, make_user):
    body = client.get("/auth/me").json()
    uid = body["user"]["id"]
    good = client.headers["Authorization"].split(" ", 1)[1]
    sid = jwt.decode(good, options={"verify_signature": False})["sid"]
    now = int(time.time())
    claims = {"iss": ISSUER, "aud": AUDIENCE, "sub": uid, "sid": sid, "typ": "access", "iat": now, "exp": now + 600}
    candidates = {
        "wrong key": jwt.encode(claims, "x" * 40, algorithm="HS256"),
        "alg none": jwt.encode(claims, key="", algorithm="none"),
        "wrong audience": jwt.encode({**claims, "aud": "other"}, "x" * 40, algorithm="HS256"),
        "tampered": good[:-4] + ("AAAA" if not good.endswith("AAAA") else "BBBB"),
        "garbage": "not.a.jwt",
    }
    for name, token in candidates.items():
        r = anon.get("/extractions", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401, name


def test_a_refresh_token_cannot_be_used_as_an_access_token(anon, make_user):
    make_user()
    login(anon)
    refresh = anon.cookies.get("refresh_token", path="/auth")
    assert anon.get("/extractions", headers={"Authorization": f"Bearer {refresh}"}).status_code == 401


def test_an_expired_access_token_says_so_and_a_refresh_fixes_it(client, make_user, db_factory):
    from app.api import deps
    uid = client.get("/auth/me").json()["user"]["id"]
    sid = jwt.decode(client.headers["Authorization"].split(" ", 1)[1], options={"verify_signature": False})["sid"]
    expired = deps.token_codec().issue_access(uid, sid, utcnow().replace(year=2020), __import__("datetime").timedelta(minutes=15))
    r = client.get("/extractions", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401 and r.json()["detail"]["code"] == "token_expired"
    refreshed = client.post("/auth/refresh")
    assert refreshed.status_code == 200
    assert client.get("/extractions", headers={"Authorization": f"Bearer {refreshed.json()['access_token']}"}).status_code == 200


def test_refresh_rotates_the_cookie_and_is_idempotent_inside_the_grace_window(anon, make_user):
    make_user()
    login(anon)
    first = anon.cookies.get("refresh_token", path="/auth")
    r1 = anon.post("/auth/refresh")
    second = r1.cookies.get("refresh_token") or anon.cookies.get("refresh_token", path="/auth")
    assert r1.status_code == 200 and second and second != first
    # a second tab that still holds the OLD cookie, a moment later: allowed, but it gets no new refresh cookie
    other = TestClient(app)
    other.cookies.set("refresh_token", first, path="/auth")
    r2 = other.post("/auth/refresh")
    assert r2.status_code == 200 and r2.json()["access_token"] and not r2.headers.get_list("set-cookie")


def test_refresh_without_or_with_a_bad_cookie_fails_and_clears_it(anon):
    assert anon.post("/auth/refresh").status_code == 401
    anon.cookies.set("refresh_token", "x" * 64, path="/auth")
    r = anon.post("/auth/refresh")
    assert r.status_code == 401 and r.json()["detail"]["code"] == "invalid_refresh"
    assert "max-age=0" in r.headers["set-cookie"].lower() or "expires=" in r.headers["set-cookie"].lower()


def test_logout_kills_the_session_immediately_and_is_idempotent(anon, make_user):
    make_user()
    body = login(anon).json()
    auth = {"Authorization": f"Bearer {body['access_token']}"}
    assert anon.get("/extractions", headers=auth).status_code == 200
    out = anon.post("/auth/logout", headers=auth)
    assert out.status_code == 204
    assert anon.get("/extractions", headers=auth).status_code == 401  # the access token dies with the session
    assert anon.post("/auth/refresh").status_code == 401  # and so does the refresh token
    assert anon.post("/auth/logout").status_code == 204


def test_logout_with_only_the_refresh_cookie_still_revokes(anon, make_user):
    make_user()
    body = login(anon).json()
    assert anon.post("/auth/logout").status_code == 204  # no Authorization header, e.g. the access token expired
    assert anon.get("/extractions", headers={"Authorization": f"Bearer {body['access_token']}"}).status_code == 401


def test_five_wrong_passwords_lock_the_account_even_for_the_right_one(anon, make_user, admin_client):
    make_user()
    for _ in range(5):
        assert login(anon, password="wrong wrong wrong").status_code == 401
    locked = login(anon)
    assert locked.status_code == 429 and locked.json()["detail"]["code"] == "locked"
    assert int(locked.headers["retry-after"]) > 0
    uid = next(u["id"] for u in admin_client.get("/admin/users").json() if u["email"] == "user@example.com")
    assert admin_client.post(f"/admin/users/{uid}/unlock").status_code == 200
    assert login(anon).status_code == 200


def test_a_successful_login_resets_the_failure_count(anon, make_user):
    make_user()
    for _ in range(4):
        login(anon, password="wrong wrong wrong")
    assert login(anon).status_code == 200
    for _ in range(4):
        login(anon, password="wrong wrong wrong")
    assert login(anon).status_code == 200  # 4 + 4 failures, but never 5 in a row


def test_a_disabled_account_cannot_sign_in_and_is_signed_out_at_once(client, admin_client, anon):
    uid = client.get("/auth/me").json()["user"]["id"]
    assert client.get("/extractions").status_code == 200
    assert admin_client.patch(f"/admin/users/{uid}", json={"is_active": False}).status_code == 200
    assert client.get("/extractions").status_code == 401
    assert client.post("/auth/refresh").status_code == 401
    r = login(anon)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "account_disabled"
    assert admin_client.patch(f"/admin/users/{uid}", json={"is_active": True}).status_code == 200
    assert login(anon).status_code == 200


def test_a_forced_password_change_blocks_everything_but_the_change_itself(anon, make_user):
    make_user(must_change=True)
    body = login(anon).json()
    assert body["user"]["must_change_password"] is True
    h = {"Authorization": f"Bearer {body['access_token']}"}
    blocked = anon.get("/extractions", headers=h)
    assert blocked.status_code == 403 and blocked.json()["detail"]["code"] == "password_change_required"
    assert anon.get("/auth/me", headers=h).status_code == 200
    weak = anon.post("/auth/change-password", headers=h, json={"current_password": PASSWORD, "new_password": "short"})
    assert weak.status_code == 422 and weak.json()["detail"]["code"] == "weak_password"
    wrong = anon.post("/auth/change-password", headers=h, json={"current_password": "not it at all", "new_password": "a brand new passphrase"})
    assert wrong.status_code == 400
    same = anon.post("/auth/change-password", headers=h, json={"current_password": PASSWORD, "new_password": PASSWORD})
    assert same.status_code == 422
    ok = anon.post("/auth/change-password", headers=h, json={"current_password": PASSWORD, "new_password": "a brand new passphrase"})
    assert ok.status_code == 200 and ok.json()["user"]["must_change_password"] is False
    assert anon.get("/extractions", headers=h).status_code == 200  # the same session carries on
    assert login(TestClient(app), password=PASSWORD).status_code == 401
    assert login(TestClient(app), password="a brand new passphrase").status_code == 200


def test_changing_the_password_signs_out_every_other_device(make_user, app_env):
    make_user()
    laptop, phone = TestClient(app), TestClient(app)
    sign_in(laptop, "user@example.com")
    sign_in(phone, "user@example.com")
    r = laptop.post("/auth/change-password", json={"current_password": PASSWORD, "new_password": "a brand new passphrase"})
    assert r.status_code == 200
    assert laptop.get("/extractions").status_code == 200
    assert phone.get("/extractions").status_code == 401 and phone.post("/auth/refresh").status_code == 401


def test_a_foreign_origin_is_refused_for_writes_but_same_origin_and_scripts_pass(anon, make_user):
    make_user()
    body = {"email": "user@example.com", "password": PASSWORD}
    assert anon.post("/auth/login", json=body, headers={"Origin": "https://evil.example"}).status_code == 403
    assert anon.post("/auth/login", json=body, headers={"Origin": "http://testserver"}).status_code == 200
    assert anon.post("/auth/login", json=body).status_code == 200  # curl / server-to-server sends no Origin


def test_everyone_signed_in_sees_every_upload_there_is_no_per_user_separation(client, make_user, app_env):
    job = client.post("/extractions", files={"file": ("a.pdf", PDF.read_bytes(), "application/pdf")}).json()["id"]
    make_user("colleague@example.com")
    other = TestClient(app)
    sign_in(other, "colleague@example.com")
    assert [j["id"] for j in other.get("/extractions").json()] == [job]
    assert other.get(f"/extractions/{job}").status_code == 200
    assert other.get(f"/extractions/{job}/file").status_code == 200
    assert other.get(f"/extractions/{job}/run").status_code == 200
    assert other.put(f"/extractions/{job}/rows", json={"rows": []}).status_code == 200
