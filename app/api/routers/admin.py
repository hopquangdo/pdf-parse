"""Account administration. Administrators only."""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.infrastructure.db.models import User
from src.application.auth.service import AuthError
from src.infrastructure.security.tokens import utcnow
from src.application.auth.users import UserService
from .. import deps

router = APIRouter(prefix="/admin/users", tags=["admin"], dependencies=[Depends(deps.require_admin)])


class NewUser(BaseModel):
    email: str = Field(max_length=254)
    name: str = Field(default="", max_length=120)
    role: str = "user"
    password: str = Field(max_length=256)  # temporary: the person must change it at first sign-in


class UserPatch(BaseModel):
    is_active: Optional[bool] = None
    role: Optional[str] = None


class PasswordReset(BaseModel):
    new_password: str = Field(max_length=256)


def out(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "is_active": u.is_active,
            "must_change_password": u.must_change_password, "locked": bool(u.locked_until and u.locked_until > utcnow()),
            "created_at": u.created_at.isoformat(), "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None}


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except AuthError as e:
        raise deps.auth_http(e) from None


@router.get("")
def list_users(svc: UserService = Depends(deps.user_service)):
    return [out(u) for u in svc.list()]


@router.post("", status_code=201)
def create_user(body: NewUser, svc: UserService = Depends(deps.user_service)):
    return out(_run(svc.create, body.email, body.name, body.role, body.password))


@router.patch("/{user_id}")
def update_user(user_id: str, body: UserPatch, admin: User = Depends(deps.require_admin), svc: UserService = Depends(deps.user_service)):
    return out(_run(svc.update, admin, user_id, body.is_active, body.role))


@router.post("/{user_id}/reset-password")
def reset_password(user_id: str, body: PasswordReset, svc: UserService = Depends(deps.user_service)):
    return out(_run(svc.reset_password, user_id, body.new_password))


@router.post("/{user_id}/unlock")
def unlock(user_id: str, svc: UserService = Depends(deps.user_service)):
    return out(_run(svc.unlock, user_id))
