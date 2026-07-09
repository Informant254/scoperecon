from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.core.db import AuditRepo, ProfileRepo, get_service_client
from app.services.recon import PassiveReconEngine, is_safe_public_host, normalize_seed


class ScanService:
    def __init__(self):
        self.db = get_service_client()
        self.profiles = ProfileRepo()
        self.audit = AuditRepo()
        self.engine = PassiveReconEngine()

    def create_scan(
        self,
        user_id: str,
        program_id: str,
        target_seed: str,
        idempotency_key: str | None,
        scan_type: str = "passive_recon",
    ) -> dict[str, Any]:
        if scan_type != "passive_recon":
            raise ValueError("unsupported_scan_type")

        seed = normalize_seed(target_seed)
        if not seed or len(seed) > 253 or not is_safe_public_host(seed):
            raise ValueError("invalid_target")

        try:
            UUID(program_id)
        except ValueError as e:
            raise ValueError("invalid_program_id") from e

        prog = (
            self.db.table("programs")
            .select("id,user_id")
            .eq("id", program_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not prog.data:
            raise PermissionError("program_not_found")

        if idempotency_key:
            if len(idempotency_key) > 128:
                raise ValueError("idempotency_key_too_long")
            existing = (
                self.db.table("scans")
                .select("*")
                .eq("user_id", user_id)
                .eq("idempotency_key", idempotency_key)
                .limit(1)
                .execute()
            )
            if existing.data:
                return existing.data[0]

        if not self.profiles.consume_scan_quota(user_id):
            raise PermissionError("quota_exceeded")

        row = {
            "user_id": user_id,
            "program_id": program_id,
            "status": "queued",
            "scan_type": scan_type,
            "target_seed": seed,
            "config": {},
            "progress": 0,
            "idempotency_key": idempotency_key,
        }
        res = self.db.table("scans").insert(row).execute()
        scan = res.data[0]
        self.audit.log(user_id, "scan.created", "scan", scan["id"], meta={"target": seed})
        return scan

    async def execute_scan(self, scan_id: str, user_id: str | None = None) -> dict[str, Any]:
        q = self.db.table("scans").select("*").eq("id", scan_id).limit(1)
        if user_id:
            q = q.eq("user_id", user_id)
        res = q.execute()
        if not res.data:
            raise ValueError("scan_not_found")
        scan = res.data[0]
        if scan["status"] in ("completed", "running", "canceled"):
            return scan

        self.db.table("scans").update(
            {
                "status": "running",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "progress": 5,
            }
        ).eq("id", scan_id).eq("status", "queued").execute()

        try:
            result = await self.engine.run(scan["target_seed"])
            if result.errors:
                self.db.table("scans").update(
                    {
                        "status": "failed",
                        "error_message": result.errors[0][:500],
                        "finished_at": datetime.now(timezone.utc).isoformat(),
                        "progress": 100,
                    }
                ).eq("id", scan_id).execute()
                return self.db.table("scans").select("*").eq("id", scan_id).single().execute().data

            asset_ids: dict[str, str] = {}
            for a in result.assets:
                upsert = {
                    "user_id": scan["user_id"],
                    "program_id": scan["program_id"],
                    "asset_type": a["asset_type"],
                    "value": a["value"],
                    "tech_stack": a.get("tech_stack") or [],
                    "risk_score": a.get("risk_score") or 0,
                    "metadata": a.get("metadata") or {},
                    "last_seen_at": datetime.now(timezone.utc).isoformat(),
                }
                existing = (
                    self.db.table("assets")
                    .select("id")
                    .eq("program_id", scan["program_id"])
                    .eq("value", a["value"])
                    .limit(1)
                    .execute()
                )
                if existing.data:
                    aid = existing.data[0]["id"]
                    self.db.table("assets").update(upsert).eq("id", aid).execute()
                else:
                    ins = self.db.table("assets").insert(upsert).execute()
                    aid = ins.data[0]["id"]
                asset_ids[a["value"]] = aid

            findings_count = 0
            for f in result.findings:
                asset_id = None
                # crude bind: first matching host in title/evidence
                for val, aid in asset_ids.items():
                    if val in (f.get("title") or "") or val in str(f.get("evidence") or {}):
                        asset_id = aid
                        break
                self.db.table("findings").insert(
                    {
                        "user_id": scan["user_id"],
                        "program_id": scan["program_id"],
                        "asset_id": asset_id,
                        "scan_id": scan_id,
                        "title": (f.get("title") or "Finding")[:300],
                        "description": f.get("description"),
                        "severity": f.get("severity") or "info",
                        "category": f.get("category"),
                        "evidence": f.get("evidence") or {},
                        "bounty_estimate_usd": f.get("bounty_estimate_usd"),
                    }
                ).execute()
                findings_count += 1

            self.db.table("scans").update(
                {
                    "status": "completed",
                    "progress": 100,
                    "assets_discovered": len(result.assets),
                    "findings_count": findings_count,
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("id", scan_id).execute()
        except Exception as exc:  # noqa: BLE001
            self.db.table("scans").update(
                {
                    "status": "failed",
                    "error_message": str(exc)[:500],
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "progress": 100,
                }
            ).eq("id", scan_id).execute()
            raise

        return self.db.table("scans").select("*").eq("id", scan_id).single().execute().data
