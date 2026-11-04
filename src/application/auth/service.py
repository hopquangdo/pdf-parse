"""Sign-in, token refresh with rotation and reuse detection, sign-out, password change."""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src import config
from src.infrastructure.db.models import AuthSession, RefreshToken, User, new_id
from src.infrastructure.security.passwords import DUMMY_HASH, hash_password, password_problems, verify_password
from src.infrastructure.security.tokens import TokenCodec, TokenError, hash_refresh_token, new_refresh_token, utcnow

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(Exception):
    """A failure the API reports to the client with a stable machine-readable `code`."""

    def __init__(self, code: str, message: str, status: int = 401, retry_after: Optional[int] = None):
        super().__init__(message)
        self.code, self.message, self.status, self.retry_after = code, message, status, retry_after


@dataclass(frozen=True)
class AuthSettings:
    access_ttl: timedelta = timedelta(minutes=config.ACCESS_TOKEN_MINUTES)
    refresh_ttl: timedelta = timedelta(days=config.REFRESH_TOKEN_DAYS)
    session_max: timedelta = timedelta(days=config.SESSION_MAX_DAYS)
    max_attempts: int = config.LOGIN_MAX_ATTEMPTS
    lock_for: timedelta = timedelta(minutes=config.LOGIN_LOCK_MINUTES)
    # Two tabs refreshing at once both present the same old token; within this window the second is not "reuse".
    refresh_grace: timedelta = timedelta(seconds=10)


@dataclass
class Tokens:
    user: User
    access: str
    refresh: Optional[str]  # None when only a fresh access token is issued (the grace-window case)


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


class AuthService:
    def __init__(self, db: Session, codec: TokenCodec, settings: Optional[AuthSettings] = None,
                 now: Callable[[], datetime] = utcnow):
        self.db, self.codec, self.settings, self.now = db, codec, settings or AuthSettings(), now

    # ---------------------------------------------------------------- sign in
    def login(self, email: str, password: str, ip: str = "", user_agent: str = "") -> Tokens:
        now = self.now()
        user = self.db.scalar(select(User).where(User.email == normalize_email(email)))
        if user is None:
            verify_password(DUMMY_HASH, password)  # same work as a real check, so timing does not reveal the account
            raise AuthError("invalid_credentials", "Invalid email or password.")
        if user.locked_until and user.locked_until > now:
            wait = max(1, int((user.locked_until - now).total_seconds()))
            raise AuthError("locked", f"Too many failed sign-in attempts. Try again in {-(-wait // 60)} minute(s).",
                            status=429, retry_after=wait)
        ok, needs_rehash = verify_password(user.password_hash, password)
        if not ok:
            user.failed_attempts += 1
            if user.failed_attempts >= self.settings.max_attempts:
                user.locked_until, user.failed_attempts = now + self.settings.lock_for, 0
            self.db.commit()
            raise AuthError("invalid_credentials", "Invalid email or password.")
        if not user.is_active:  # only reached with the right password, so this reveals nothing new
            raise AuthError("account_disabled", "This account has been disabled. Contact an administrator.", status=403)
        user.failed_attempts, user.locked_until, user.last_login_at = 0, None, now
        if needs_rehash:
            user.password_hash = hash_password(password)
        session = AuthSession(id=new_id(), user_id=user.id, created_at=now, last_refreshed_at=now,
                              absolute_expires_at=now + self.settings.session_max, ip=ip[:64], user_agent=user_agent[:255])
        self.db.add(session)
        refresh = self._new_refresh(session, now)
        self.db.commit()
        return Tokens(user, self.codec.issue_access(user.id, session.id, now, self.settings.access_ttl), refresh)

    def _new_refresh(self, session: AuthSession, now: datetime) -> str:
        token = new_refresh_token()
        expires = min(now + self.settings.refresh_ttl, session.absolute_expires_at)
        self.db.add(RefreshToken(token_hash=hash_refresh_token(token), session_id=session.id, created_at=now, expires_at=expires))
        return token

    # ---------------------------------------------------------------- refresh
    def refresh(self, token: str) -> Tokens:
        now = self.now()
        row = self.db.get(RefreshToken, hash_refresh_token(token)) if token else None
        if row is None:
            raise AuthError("invalid_refresh", "Your session has ended. Please sign in again.")
        session, user = row.session, row.session.user
        if session.revoked_at is not None or session.absolute_expires_at <= now or row.expires_at <= now:
            raise AuthError("invalid_refresh", "Your session has ended. Please sign in again.")
        if not user.is_active:
            self._revoke(session, "user_disabled", now)
            self.db.commit()
            raise AuthError("invalid_refresh", "Your session has ended. Please sign in again.")
        if row.rotated_at is not None:
            if now - row.rotated_at <= self.settings.refresh_grace:  # a concurrent refresh, not theft
                return Tokens(user, self.codec.issue_access(user.id, session.id, now, self.settings.access_ttl), None)
            self._revoke(session, "reuse_detected", now)  # an already-used token came back: assume it was stolen
            self.db.commit()
            raise AuthError("invalid_refresh", "Your session has ended. Please sign in again.")
        row.rotated_at = now
        session.last_refreshed_at = now
        new_refresh = self._new_refresh(session, now)
        self.db.commit()
        return Tokens(user, self.codec.issue_access(user.id, session.id, now, self.settings.access_ttl), new_refresh)

    # ---------------------------------------------------------------- verify an access token
    def authenticate(self, access_token: Optional[str]) -> Tuple[User, AuthSession]:
        if not access_token:
            raise AuthError("not_authenticated", "Sign in to continue.")
        now = self.now()
        try:
            claims = self.codec.read_access(access_token, now)
        except TokenError as e:
            if e.code == "expired":
                raise AuthError("token_expired", "Your access token expired.") from None
            raise AuthError("not_authenticated", "Sign in to continue.") from None
        session = self.db.get(AuthSession, claims.session_id)
        if (session is None or session.user_id != claims.user_id or session.revoked_at is not None
                or session.absolute_expires_at <= now):
            raise AuthError("not_authenticated", "Your session has ended. Please sign in again.")
        user = session.user
        if not user.is_active:
            raise AuthError("not_authenticated", "This account has been disabled.")
        return user, session

    # ---------------------------------------------------------------- sign out / revoke
    def _revoke(self, session: AuthSession, reason: str, now: datetime) -> None:
        if session.revoked_at is None:
            session.revoked_at, session.revoked_reason = now, reason

    def logout_session(self, session_id: str) -> None:
        session = self.db.get(AuthSession, session_id)
        if session:
            self._revoke(session, "logout", self.now())
            self.db.commit()

    def logout_by_refresh_token(self, token: str) -> None:
        row = self.db.get(RefreshToken, hash_refresh_token(token)) if token else None
        if row:
            self._revoke(row.session, "logout", self.now())
            self.db.commit()

    def revoke_user_sessions(self, user_id: str, reason: str, keep_session_id: Optional[str] = None) -> None:
        stmt = (update(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
                .values(revoked_at=self.now(), revoked_reason=reason))
        if keep_session_id:
            stmt = stmt.where(AuthSession.id != keep_session_id)
        self.db.execute(stmt)
        self.db.commit()

    # ---------------------------------------------------------------- password change
    def change_password(self, user: User, session_id: str, current: str, new: str) -> None:
        ok, _ = verify_password(user.password_hash, current)
        if not ok:
            raise AuthError("invalid_credentials", "Your current password is not correct.", status=400)
        problems = password_problems(new, user.email)
        if problems:
            raise AuthError("weak_password", " ".join(problems), status=422)
        if verify_password(user.password_hash, new)[0]:
            raise AuthError("weak_password", "Choose a password different from the current one.", status=422)
        user.password_hash = hash_password(new)
        user.must_change_password = False
        user.password_changed_at = self.now()
        self.db.commit()
        self.revoke_user_sessions(user.id, "password_changed", keep_session_id=session_id)  # other devices sign out
