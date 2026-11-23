"""Senhas (scrypt, stdlib) e sessão do painel (JWT em cookie httpOnly)."""

import base64
import hashlib
import hmac
import os
import secrets
import time

import jwt

SESSION_TTL_S = 12 * 3600


def _secret() -> str:
    secret = os.environ.get("SESSION_SECRET")
    if not secret:
        raise RuntimeError("defina SESSION_SECRET no .env")
    return secret


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_b64, digest_b64 = stored.split("$")
    except ValueError:
        return False
    digest = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), n=2**14, r=8, p=1)
    return hmac.compare_digest(digest, base64.b64decode(digest_b64))


def issue_session(user_id: int) -> str:
    return jwt.encode({"sub": str(user_id), "exp": int(time.time()) + SESSION_TTL_S}, _secret(), algorithm="HS256")


def read_session(token: str) -> int | None:
    try:
        return int(jwt.decode(token, _secret(), algorithms=["HS256"])["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
