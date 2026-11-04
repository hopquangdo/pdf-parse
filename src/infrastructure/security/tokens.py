"""Access tokens (JWT, HS256) and opaque refresh tokens."""
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

ISSUER = "steel-takeoff"
AUDIENCE = "steel-takeoff-web"
ALGORITHM = "HS256"
LEEWAY = timedelta(seconds=5)


class TokenError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code  # "expired" | "invalid"


@dataclass(frozen=True)
class AccessClaims:
    user_id: str
    session_id: str
    expires_at: datetime


class TokenCodec:
    def __init__(self, secret: str):
        if len(secret) < 32:
            raise ValueError("JWT secret must be at least 32 characters")
        self._secret = secret

    def issue_access(self, user_id: str, session_id: str, now: datetime, ttl: timedelta) -> str:
        claims = {"iss": ISSUER, "aud": AUDIENCE, "sub": user_id, "sid": session_id, "typ": "access",
                  "jti": secrets.token_hex(8), "iat": int(now.timestamp()), "exp": int((now + ttl).timestamp())}
        return jwt.encode(claims, self._secret, algorithm=ALGORITHM)

    def read_access(self, token: str, now: datetime) -> AccessClaims:
        """Verify signature, issuer, audience and type. Expiry is judged against `now` (injectable for tests)."""
        try:
            # `algorithms` is pinned so a token cannot pick its own (e.g. "none"); exp is checked by hand below.
            c = jwt.decode(token, self._secret, algorithms=[ALGORITHM], issuer=ISSUER, audience=AUDIENCE,
                           options={"verify_exp": False, "require": ["exp", "sub", "sid", "typ"]})
        except jwt.PyJWTError:
            raise TokenError("invalid") from None
        if c.get("typ") != "access":
            raise TokenError("invalid")
        expires = datetime.fromtimestamp(c["exp"], tz=timezone.utc)
        if now > expires + LEEWAY:
            raise TokenError("expired")
        return AccessClaims(c["sub"], c["sid"], expires)


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_cookie_token(value: Optional[str]) -> Optional[str]:
    return value if value and 20 <= len(value) <= 2048 else None
