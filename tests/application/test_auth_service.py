"""Time-dependent auth rules, driven by a fake clock instead of sleeping."""
from datetime import datetime, timedelta, timezone

import pytest

from src.application.auth.service import AuthError, AuthService, AuthSettings
from src.infrastructure.security.tokens import TokenCodec
from src.application.auth.users import UserService
from tests.conftest import PASSWORD

CODEC = TokenCodec("k" * 40)


class Clock:
    def __init__(self):
        self.t = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.t

    def advance(self, **kw):
        self.t += timedelta(**kw)


@pytest.fixture
def env(db_factory):
    clock = Clock()
    db = db_factory()
    auth = AuthService(db, CODEC, AuthSettings(), now=clock)
    UserService(db, auth, now=clock).create("a@example.com", "A", "user", PASSWORD, must_change_password=False)
    yield auth, clock, db
    db.close()


def code(fn, *a):
    with pytest.raises(AuthError) as e:
        fn(*a)
    return e.value.code


def test_access_token_lifetime_is_exactly_fifteen_minutes(env):
    auth, clock, _ = env
    t = auth.login("a@example.com", PASSWORD)
    auth.authenticate(t.access)
    clock.advance(minutes=14, seconds=50)
    auth.authenticate(t.access)  # still valid
    clock.advance(minutes=1)
    assert code(auth.authenticate, t.access) == "token_expired"


def test_refresh_gives_a_working_pair_and_the_old_refresh_token_stops_working_after_the_grace_window(env):
    auth, clock, _ = env
    t = auth.login("a@example.com", PASSWORD)
    clock.advance(minutes=20)
    t2 = auth.refresh(t.refresh)
    assert t2.refresh and t2.refresh != t.refresh and auth.authenticate(t2.access)[0].email == "a@example.com"
    clock.advance(seconds=30)  # past the 10 s grace: this is no longer "two tabs at once"
    assert code(auth.refresh, t.refresh) == "invalid_refresh"


def test_reusing_an_old_refresh_token_revokes_the_whole_session_even_the_new_tokens(env):
    auth, clock, _ = env
    t = auth.login("a@example.com", PASSWORD)
    t2 = auth.refresh(t.refresh)
    clock.advance(minutes=1)
    assert code(auth.refresh, t.refresh) == "invalid_refresh"  # a stolen copy was replayed...
    assert code(auth.refresh, t2.refresh) == "invalid_refresh"  # ...so the legitimate holder is cut off too
    assert code(auth.authenticate, t2.access) == "not_authenticated"


def test_two_tabs_refreshing_at_once_are_not_treated_as_theft(env):
    auth, clock, _ = env
    t = auth.login("a@example.com", PASSWORD)
    auth.refresh(t.refresh)
    clock.advance(seconds=3)
    second = auth.refresh(t.refresh)  # same old token, 3 s later
    assert second.refresh is None and auth.authenticate(second.access)


def test_refresh_token_expires_after_seven_days_idle(env):
    auth, clock, _ = env
    t = auth.login("a@example.com", PASSWORD)
    clock.advance(days=7, minutes=1)
    assert code(auth.refresh, t.refresh) == "invalid_refresh"


def test_an_active_session_can_stretch_beyond_seven_days_but_never_past_the_absolute_cap(env):
    auth, clock, _ = env
    t = auth.login("a@example.com", PASSWORD)
    for _ in range(4):  # each refresh inside the 7-day window slides the expiry forward
        clock.advance(days=6)
        t = auth.refresh(t.refresh)
    assert clock.t - datetime(2026, 1, 1, 12, tzinfo=timezone.utc) == timedelta(days=24)  # far past a single 7-day token
    clock.advance(days=5)  # day 29: still inside the 30-day absolute lifetime
    t = auth.refresh(t.refresh)
    clock.advance(days=2)  # day 31: the sliding window alone would allow it, the absolute cap does not
    assert code(auth.refresh, t.refresh) == "invalid_refresh"
    assert code(auth.authenticate, t.access) == "token_expired" or code(auth.authenticate, t.access) == "not_authenticated"


def test_lock_expires_by_itself(env):
    auth, clock, _ = env
    for _ in range(5):
        code(auth.login, "a@example.com", "wrong wrong wrong")
    assert code(auth.login, "a@example.com", PASSWORD) == "locked"
    clock.advance(minutes=14)
    assert code(auth.login, "a@example.com", PASSWORD) == "locked"
    clock.advance(minutes=2)
    assert auth.login("a@example.com", PASSWORD).access


def test_refresh_tokens_are_stored_only_as_hashes(env):
    from sqlalchemy import select
    from src.infrastructure.db.models import RefreshToken
    auth, _, db = env
    t = auth.login("a@example.com", PASSWORD)
    stored = db.scalars(select(RefreshToken.token_hash)).all()
    assert stored and t.refresh not in stored and all(len(h) == 64 for h in stored)


def test_passwords_are_stored_as_argon2id_hashes(env):
    from sqlalchemy import select
    from src.infrastructure.db.models import User
    _, _, db = env
    h = db.scalar(select(User.password_hash))
    assert h.startswith("$argon2id$") and PASSWORD not in h


def test_each_login_is_its_own_session_so_signing_out_one_device_keeps_the_other(env):
    auth, _, _ = env
    laptop, phone = auth.login("a@example.com", PASSWORD), auth.login("a@example.com", PASSWORD)
    _, laptop_session = auth.authenticate(laptop.access)
    auth.logout_session(laptop_session.id)
    assert code(auth.authenticate, laptop.access) == "not_authenticated"
    assert auth.authenticate(phone.access)
