"""Sign in / refresh / sign out / who am I / change password.

The access token (a short-lived JWT) is returned in the response body; the client keeps it in memory and sends it on
every request as `Authorization: Bearer <token>`. It is never written to storage or a cookie.
The refresh token (an opaque random string, rotated on every use) lives only in an HttpOnly cookie scoped to /auth, so
page scripts can never read it; /auth/refresh uses it to mint a new access token (also after a page reload).
"""
from typing import Tuple

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src import config
from src.infrastructure.db.models import AuthSession, User
from src.application.auth.service import AuthError, AuthService, AuthSettings, Tokens
from .. import deps

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


def user_out(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "must_change_password": u.must_change_password}


def _session_body(tokens: Tokens, settings: AuthSettings) -> dict:
    return {"user": user_out(tokens.user), "access_token": tokens.access, "token_type": "bearer",
            "expires_in": int(settings.access_ttl.total_seconds())}


def _set_refresh_cookie(resp: Response, tokens: Tokens, settings: AuthSettings) -> None:
    if tokens.refresh:  # absent in the concurrent-refresh grace case: keep the cookie the other request just set
        resp.set_cookie(deps.REFRESH_COOKIE, tokens.refresh, max_age=int(settings.refresh_ttl.total_seconds()), path="/auth",
                        httponly=True, secure=config.COOKIE_SECURE, samesite="strict")


def _clear_cookies(resp: Response) -> None:
    resp.delete_cookie(deps.REFRESH_COOKIE, path="/auth", httponly=True, secure=config.COOKIE_SECURE, samesite="strict")


def _client(request: Request) -> Tuple[str, str]:
    return (request.client.host if request.client else ""), request.headers.get("user-agent", "")


@router.post("/login")
def login(body: LoginIn, request: Request, auth: AuthService = Depends(deps.auth_service)):
    ip, ua = _client(request)
    try:
        tokens = auth.login(body.email, body.password, ip, ua)
    except AuthError as e:
        raise deps.auth_http(e) from None
    resp = JSONResponse(_session_body(tokens, auth.settings), headers={"Cache-Control": "no-store"})
    _set_refresh_cookie(resp, tokens, auth.settings)
    return resp


@router.post("/refresh")
def refresh(request: Request, auth: AuthService = Depends(deps.auth_service)):
    try:
        tokens = auth.refresh(request.cookies.get(deps.REFRESH_COOKIE) or "")
    except AuthError as e:
        resp = JSONResponse(status_code=e.status, content={"detail": {"code": e.code, "message": e.message}})
        _clear_cookies(resp)  # a dead refresh token must not keep being sent
        return resp
    resp = JSONResponse(_session_body(tokens, auth.settings), headers={"Cache-Control": "no-store"})
    _set_refresh_cookie(resp, tokens, auth.settings)
    return resp


@router.post("/logout", status_code=204)
def logout(request: Request, auth: AuthService = Depends(deps.auth_service)):
    """Idempotent and best effort: always ends with the cookies cleared."""
    try:
        _, session = auth.authenticate(deps.bearer_token(request))
        auth.logout_session(session.id)
    except AuthError:
        auth.logout_by_refresh_token(request.cookies.get(deps.REFRESH_COOKIE) or "")  # access token already expired
    resp = Response(status_code=204)
    _clear_cookies(resp)
    return resp


@router.get("/me")
def me(ctx: Tuple[User, AuthSession] = Depends(deps.auth_context)):
    return {"user": user_out(ctx[0])}


@router.post("/change-password")
def change_password(body: ChangePasswordIn, ctx: Tuple[User, AuthSession] = Depends(deps.auth_context),
                    auth: AuthService = Depends(deps.auth_service)):
    user, session = ctx
    try:
        auth.change_password(user, session.id, body.current_password, body.new_password)
    except AuthError as e:
        raise deps.auth_http(e) from None
    return {"user": user_out(user)}
