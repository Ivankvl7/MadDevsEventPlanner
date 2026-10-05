"""Пароли и токены сессий. Только стандартная библиотека."""

import base64
import hashlib
import hmac
import secrets

# Параметры scrypt: n=2^14, r=8, p=1 — рекомендованный минимум для интерактивного входа.
_N, _R, _P = 2**14, 8, 1
_DKLEN = 32


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_b64, dk_b64 = stored.split("$")
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    expected = base64.b64decode(dk_b64)
    dk = hashlib.scrypt(
        password.encode(),
        salt=base64.b64decode(salt_b64),
        n=int(n),
        r=int(r),
        p=int(p),
        dklen=len(expected),
    )
    return hmac.compare_digest(dk, expected)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def normalize_email(email: str) -> str:
    return email.strip().lower()
