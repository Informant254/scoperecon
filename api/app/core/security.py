from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from jwt import PyJWKClient

from app.core.config import Settings, get_settings


@dataclass(frozen=True, slots=True)
class AuthUser:
    id: str
    email: str | None
    role: str
    claims: dict[str, Any]


def hash_ip(ip: str) -> str:
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:32]


def constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def generate_api_key() -> tuple[str, str, str]:
    """Returns (raw_key, prefix, sha256_hex). Store only hash server-side."""
    raw = f"sr_{secrets.token_urlsafe(32)}"
    prefix = raw[:10]
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return raw, prefix, digest


class JWTVerifier:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._jwks: PyJWKClient | None = None
        jwks_url = f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        try:
            self._jwks = PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)
        except Exception:
            self._jwks = None

    def verify(self, token: str) -> AuthUser:
        options = {
            "require": ["exp", "sub", "role"],
            "verify_aud": False,
        }
        try:
            if self._jwks is not None:
                try:
                    key = self._jwks.get_signing_key_from_jwt(token)
                    payload = jwt.decode(
                        token,
                        key.key,
                        algorithms=["ES256", "RS256", "HS256"],
                        options=options,
                        leeway=10,
                    )
                except Exception:
                    payload = jwt.decode(
                        token,
                        self.settings.supabase_jwt_secret,
                        algorithms=["HS256"],
                        options=options,
                        leeway=10,
                    )
            else:
                payload = jwt.decode(
                    token,
                    self.settings.supabase_jwt_secret,
                    algorithms=["HS256"],
                    options=options,
                    leeway=10,
                )
        except jwt.ExpiredSignatureError as e:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token_expired") from e
        except jwt.InvalidTokenError as e:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_token") from e

        role = payload.get("role")
        if role not in ("authenticated", "service_role"):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_role")
        if role == "service_role":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "service_role_not_allowed")

        sub = payload.get("sub")
        if not sub or not isinstance(sub, str):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_subject")

        return AuthUser(
            id=sub,
            email=payload.get("email"),
            role=role,
            claims=payload,
        )


_verifier: JWTVerifier | None = None


def get_verifier(settings: Settings = Depends(get_settings)) -> JWTVerifier:
    global _verifier
    if _verifier is None:
        _verifier = JWTVerifier(settings)
    return _verifier


async def require_user(
    request: Request,
    authorization: str | None = Header(default=None),
    verifier: JWTVerifier = Depends(get_verifier),
) -> AuthUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing_bearer")
    token = authorization[7:].strip()
    if not token or len(token) > 4096:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_bearer")
    user = verifier.verify(token)
    request.state.user_id = user.id
    return user


async def require_worker(
    x_worker_token: str | None = Header(default=None, alias="X-Worker-Token"),
    settings: Settings = Depends(get_settings),
) -> None:
    if not x_worker_token or not constant_time_eq(x_worker_token, settings.internal_worker_token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_worker_token")


# In-process rate limiter fallback when Redis unavailable
_memory_buckets: dict[str, tuple[float, int]] = {}


async def enforce_rate_limit(
    request: Request,
    bucket: str,
    max_requests: int | None = None,
    window: int | None = None,
    settings: Settings = Depends(get_settings),
) -> None:
    max_r = max_requests or settings.rate_limit_max_requests
    win = window or settings.rate_limit_window_seconds
    ip = request.client.host if request.client else "unknown"
    key = f"{bucket}:{hash_ip(ip)}:{getattr(request.state, 'user_id', 'anon')}"
    now = time.time()

    if settings.redis_url:
        try:
            import redis.asyncio as redis

            r = redis.from_url(settings.redis_url, decode_responses=True)
            pipe = r.pipeline()
            pipe.incr(key)
            pipe.expire(key, win)
            count, _ = await pipe.execute()
            await r.aclose()
            if int(count) > max_r:
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "rate_limited")
            return
        except HTTPException:
            raise
        except Exception:
            pass

    start, count = _memory_buckets.get(key, (now, 0))
    if now - start > win:
        start, count = now, 0
    count += 1
    _memory_buckets[key] = (start, count)
    if count > max_r:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "rate_limited")


async def limit_body_size(request: Request, settings: Settings = Depends(get_settings)) -> None:
    cl = request.headers.get("content-length")
    if cl is not None:
        try:
            if int(cl) > settings.max_body_bytes:
                raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "body_too_large")
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "bad_content_length") from e
