from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status

from app.core.config import Settings, get_settings
from app.core.security import AuthUser, enforce_rate_limit, require_user, require_worker
from app.models.schemas import ScanCreateRequest
from app.services.scans import ScanService

router = APIRouter(prefix="/scans", tags=["scans"])


@router.post("")
async def create_scan(
    body: ScanCreateRequest,
    request: Request,
    background: BackgroundTasks,
    user: AuthUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
):
    await enforce_rate_limit(
        request,
        "scan_create",
        max_requests=settings.rate_limit_scan_per_hour,
        window=3600,
        settings=settings,
    )
    svc = ScanService()
    try:
        scan = svc.create_scan(
            user_id=user.id,
            program_id=body.program_id,
            target_seed=body.target_seed,
            idempotency_key=body.idempotency_key,
            scan_type=body.scan_type,
        )
    except PermissionError as e:
        code = status.HTTP_402_PAYMENT_REQUIRED if str(e) == "quota_exceeded" else status.HTTP_403_FORBIDDEN
        raise HTTPException(code, str(e)) from e
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e

    # Execute async in-process (swap for Redis/RQ in multi-instance prod)
    background.add_task(_run_scan_safe, scan["id"])
    return scan


async def _run_scan_safe(scan_id: str) -> None:
    try:
        await ScanService().execute_scan(scan_id)
    except Exception:
        pass


@router.get("/{scan_id}")
async def get_scan(
    scan_id: str,
    request: Request,
    user: AuthUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
):
    await enforce_rate_limit(request, "scan_get", max_requests=120, window=60, settings=settings)
    from app.core.db import get_service_client

    res = (
        get_service_client()
        .table("scans")
        .select("*")
        .eq("id", scan_id)
        .eq("user_id", user.id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    return res.data[0]


@router.post("/{scan_id}/run")
async def worker_run_scan(
    scan_id: str,
    _: None = Depends(require_worker),
):
    """Internal worker entry — X-Worker-Token required."""
    try:
        return await ScanService().execute_scan(scan_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
