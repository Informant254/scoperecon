from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.config import Settings, get_settings
from app.core.db import ProfileRepo, get_service_client
from app.core.security import AuthUser, enforce_rate_limit, generate_api_key, require_user
from app.models.schemas import MeResponse, ProgramCreateRequest

router = APIRouter(tags=["me"])


@router.get("/me", response_model=MeResponse)
async def me(
    request: Request,
    user: AuthUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
):
    await enforce_rate_limit(request, "me", max_requests=60, window=60, settings=settings)
    profile = ProfileRepo().get(user.id)
    if not profile:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile_missing")
    return MeResponse(
        id=profile["id"],
        email=profile["email"],
        plan=profile["plan"],
        subscription_status=profile["subscription_status"],
        scan_quota_monthly=profile["scan_quota_monthly"],
        scans_used_this_month=profile["scans_used_this_month"],
        current_period_end=profile.get("current_period_end"),
        onboarding_completed=profile.get("onboarding_completed") or False,
    )


@router.post("/programs")
async def create_program(
    body: ProgramCreateRequest,
    request: Request,
    user: AuthUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
):
    await enforce_rate_limit(request, "program_create", max_requests=30, window=60, settings=settings)
    db = get_service_client()
    # Free tier: max 3 programs
    profile = ProfileRepo().get(user.id)
    if not profile:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile_missing")
    count = (
        db.table("programs")
        .select("id", count="exact")
        .eq("user_id", user.id)
        .execute()
    )
    n = count.count or 0
    limits = {"free": 3, "pro": 50, "team": 500}
    if n >= limits.get(profile["plan"], 3):
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "program_limit")

    row = {
        "user_id": user.id,
        "name": body.name,
        "platform": body.platform,
        "program_url": body.program_url,
        "handle": body.handle,
        "notes": body.notes,
        "in_scope_summary": body.in_scope_summary,
        "out_of_scope_summary": body.out_of_scope_summary,
    }
    res = db.table("programs").insert(row).execute()
    return res.data[0]


@router.get("/programs")
async def list_programs(
    request: Request,
    user: AuthUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
):
    await enforce_rate_limit(request, "program_list", max_requests=60, window=60, settings=settings)
    res = (
        get_service_client()
        .table("programs")
        .select("*")
        .eq("user_id", user.id)
        .order("created_at", desc=True)
        .execute()
    )
    return {"items": res.data}


@router.get("/dashboard")
async def dashboard(
    request: Request,
    user: AuthUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
):
    await enforce_rate_limit(request, "dashboard", max_requests=60, window=60, settings=settings)
    db = get_service_client()
    profile = ProfileRepo().get(user.id)
    assets = (
        db.table("assets")
        .select("id,value,asset_type,risk_score,last_seen_at,program_id")
        .eq("user_id", user.id)
        .order("risk_score", desc=True)
        .limit(50)
        .execute()
    )
    findings = (
        db.table("findings")
        .select("id,title,severity,status,category,bounty_estimate_usd,created_at,program_id")
        .eq("user_id", user.id)
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    scans = (
        db.table("scans")
        .select("id,status,target_seed,progress,assets_discovered,findings_count,created_at")
        .eq("user_id", user.id)
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    bounty_est = sum(float(f.get("bounty_estimate_usd") or 0) for f in (findings.data or []))
    return {
        "profile": {
            "plan": profile["plan"] if profile else "free",
            "scans_used_this_month": profile["scans_used_this_month"] if profile else 0,
            "scan_quota_monthly": profile["scan_quota_monthly"] if profile else 5,
        },
        "stats": {
            "assets": len(assets.data or []),
            "findings": len(findings.data or []),
            "bounty_estimate_usd": bounty_est,
            "critical_high": sum(
                1
                for f in (findings.data or [])
                if f.get("severity") in ("high", "critical")
            ),
        },
        "assets": assets.data,
        "findings": findings.data,
        "scans": scans.data,
    }


@router.post("/api-keys/rotate")
async def rotate_api_key(
    request: Request,
    user: AuthUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
):
    await enforce_rate_limit(request, "api_key", max_requests=5, window=3600, settings=settings)
    profile = ProfileRepo().get(user.id)
    if not profile or profile["plan"] == "free":
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "pro_required")
    raw, prefix, digest = generate_api_key()
    from datetime import datetime, timezone

    ProfileRepo().update(
        user.id,
        {
            "api_key_hash": digest,
            "api_key_prefix": prefix,
            "api_key_created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    # Raw key shown once
    return {"api_key": raw, "prefix": prefix}
