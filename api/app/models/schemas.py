from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class CheckoutRequest(BaseModel):
    plan: Literal["pro", "team"]


class ScanCreateRequest(BaseModel):
    program_id: str = Field(..., min_length=36, max_length=36)
    target_seed: str = Field(..., min_length=1, max_length=253)
    scan_type: Literal["passive_recon"] = "passive_recon"
    idempotency_key: str | None = Field(default=None, max_length=128)

    @field_validator("target_seed")
    @classmethod
    def strip_seed(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("empty_target")
        # Reject credentials in URL
        if "@" in v.split("://")[-1].split("/")[0] and "://" in v:
            raise ValueError("credentials_not_allowed")
        return v


class ProgramCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    platform: str | None = Field(default=None, max_length=64)
    program_url: str | None = Field(default=None, max_length=2048)
    handle: str | None = Field(default=None, max_length=128)
    notes: str | None = Field(default=None, max_length=5000)
    in_scope_summary: str | None = Field(default=None, max_length=10000)
    out_of_scope_summary: str | None = Field(default=None, max_length=10000)


class FindingStatusUpdate(BaseModel):
    status: Literal["new", "triaged", "reported", "duplicate", "resolved", "ignored"]


class MeResponse(BaseModel):
    id: str
    email: str
    plan: str
    subscription_status: str
    scan_quota_monthly: int
    scans_used_this_month: int
    current_period_end: str | None
    onboarding_completed: bool
