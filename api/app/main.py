from __future__ import annotations

import time

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from app.core.config import get_settings
from app.core.security import limit_body_size
from app.routers import billing, me, scans

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    default_response_class=ORJSONResponse,
    docs_url=None if settings.app_env == "production" else "/docs",
    redoc_url=None,
    openapi_url=None if settings.app_env == "production" else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Idempotency-Key", "Stripe-Signature"],
    max_age=600,
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    # Reject oversized early
    cl = request.headers.get("content-length")
    if cl:
        try:
            if int(cl) > settings.max_body_bytes:
                return ORJSONResponse({"detail": "body_too_large"}, status_code=413)
        except ValueError:
            return ORJSONResponse({"detail": "bad_content_length"}, status_code=400)

    start = time.perf_counter()
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Cache-Control"] = "no-store"
    if settings.app_env == "production":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    response.headers["X-Response-Time"] = f"{(time.perf_counter() - start) * 1000:.1f}ms"
    # Never leak server stack
    if "server" in response.headers:
        del response.headers["server"]
    return response


@app.get("/healthz")
async def healthz():
    return {"ok": True, "service": "scoperecon"}


app.include_router(billing.router, prefix=settings.api_prefix, dependencies=[Depends(limit_body_size)])
app.include_router(scans.router, prefix=settings.api_prefix, dependencies=[Depends(limit_body_size)])
app.include_router(me.router, prefix=settings.api_prefix, dependencies=[Depends(limit_body_size)])
