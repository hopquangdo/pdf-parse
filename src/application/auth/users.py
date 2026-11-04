"""Account administration (admin only) and first-run bootstrap."""
import logging
from datetime import datetime
from typing import Callable, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.infrastructure.db.models import User, new_id
from src.infrastructure.security.passwords import hash_password, password_problems
from src.application.auth.service import EMAIL, AuthError, AuthService, normalize_email
from src.infrastructure.security.tokens import utcnow

log = logging.getLogger("auth")


class UserService:
    def __init__(self, db: Session, auth: AuthService, now: Callable[[], datetime] = utcnow):
        self.db, self.auth, self.now = db, auth, now

    def list(self) -> List[User]:
        return list(self.db.scalars(select(User).order_by(User.created_at)))

    def get(self, user_id: str) -> User:
        user = self.db.get(User, user_id)
        if user is None:
            raise AuthError("not_found", "User not found.", status=404)
        return user

    def create(self, email: str, name: str, role: str, password: str, must_change_password: bool = True) -> User:
        email = normalize_email(email)
        if not EMAIL.match(email) or len(email) > 254:
            raise AuthError("invalid_email", "Enter a valid email address.", status=422)
        if role not in ("admin", "user"):
            raise AuthError("invalid_role", "Role must be admin or user.", status=422)
        problems = password_problems(password, email)
        if problems:
            raise AuthError("weak_password", " ".join(problems), status=422)
        if self.db.scalar(select(User.id).where(User.email == email)):
            raise AuthError("email_taken", "An account with that email already exists.", status=409)
        user = User(id=new_id(), email=email, name=(name or "").strip()[:120], password_hash=hash_password(password), role=role,
                    must_change_password=must_change_password, created_at=self.now(), password_changed_at=self.now())
        self.db.add(user)
        self.db.commit()
        return user

    def _active_admins(self) -> int:
        return self.db.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True))) or 0

    def update(self, actor: User, user_id: str, is_active: Optional[bool] = None, role: Optional[str] = None) -> User:
        user = self.get(user_id)
        if role is not None and role not in ("admin", "user"):
            raise AuthError("invalid_role", "Role must be admin or user.", status=422)
        demoting = user.role == "admin" and ((role == "user") or (is_active is False))
        if demoting and (user.id == actor.id or self._active_admins() <= 1):
            raise AuthError("last_admin", "You cannot disable or demote yourself or the last administrator.", status=409)
        if is_active is not None:
            user.is_active = is_active
        if role is not None:
            user.role = role
        self.db.commit()
        if is_active is False:
            self.auth.revoke_user_sessions(user.id, "user_disabled")
        return user

    def reset_password(self, user_id: str, new_password: str) -> User:
        user = self.get(user_id)
        problems = password_problems(new_password, user.email)
        if problems:
            raise AuthError("weak_password", " ".join(problems), status=422)
        user.password_hash = hash_password(new_password)
        user.must_change_password = True  # the person must pick their own password at the next sign-in
        user.failed_attempts, user.locked_until = 0, None
        user.password_changed_at = self.now()
        self.db.commit()
        self.auth.revoke_user_sessions(user.id, "password_reset")
        return user

    def unlock(self, user_id: str) -> User:
        user = self.get(user_id)
        user.failed_attempts, user.locked_until = 0, None
        self.db.commit()
        return user


def bootstrap_admin(db: Session, auth: AuthService, email: str, password: str, name: str, must_change_password: bool = True) -> bool:
    """Create the first administrator when the database has no users. Returns whether one was created."""
    if not email or not password or db.scalar(select(func.count()).select_from(User)):
        return False
    try:
        UserService(db, auth).create(email, name, "admin", password, must_change_password=must_change_password)
    except AuthError as e:
        raise RuntimeError(f"ADMIN_EMAIL / ADMIN_PASSWORD rejected: {e.message}") from None
    log.warning("Created the first administrator %s%s", email, "; the password must be changed at first sign-in" if must_change_password else "")
    return True
