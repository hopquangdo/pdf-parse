"""Password hashing (Argon2id) and the password policy."""
import secrets
from typing import List, Tuple

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()  # argon2id with the library's current recommended cost
# Verified against when the account does not exist, so "unknown email" and "wrong password" take the same time.
DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))

MIN_LENGTH, MAX_LENGTH = 10, 128
_COMMON = {
    "password", "password1", "password123", "passw0rd123", "1234567890", "12345678910", "qwertyuiop", "qwerty12345",
    "iloveyou123", "admin12345", "administrator", "letmein1234", "welcome1234", "abc1234567", "changeme123",
}


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> Tuple[bool, bool]:
    """(matches, needs_rehash). Never raises on a malformed hash: that is simply a non-match."""
    try:
        ok = _hasher.verify(stored_hash, password)
    except (VerificationError, InvalidHashError):
        return False, False
    return ok, ok and _hasher.check_needs_rehash(stored_hash)


def password_problems(password: str, email: str = "") -> List[str]:
    """Reasons a new password is rejected (empty list = acceptable)."""
    problems: List[str] = []
    if len(password) < MIN_LENGTH:
        problems.append(f"Use at least {MIN_LENGTH} characters.")
    if len(password) > MAX_LENGTH:
        problems.append(f"Use at most {MAX_LENGTH} characters.")
    if password.strip() != password or not password.strip():
        problems.append("Do not start or end the password with a space.")
    if password and len(set(password)) < 4:
        problems.append("Use a less repetitive password.")
    if password.lower() in _COMMON:
        problems.append("That password is too common.")
    local = email.split("@", 1)[0].lower()
    if len(local) >= 4 and local in password.lower():
        problems.append("Do not include your email name in the password.")
    return problems
