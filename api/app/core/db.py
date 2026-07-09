from __future__ import annotations

from functools import lru_cache
from typing import Any

from supabase import Client, create_client

from app.core.config import Settings, get_settings


@lru_cache
def get_service_client() -> Client:
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_service_role_key)


def get_user_client(access_token: str) -> Client:
    """RLS-bound client for optional passthrough operations."""
    s = get_settings()
    client = create_client(s.supabase_url, s.supabase_anon_key)
    client.postgrest.auth(access_token)
    return client


class ProfileRepo:
    def __init__(self, client: Client | None = None):
        self.db = client or get_service_client()

    def get(self, user_id: str) -> dict[str, Any] | None:
        res = self.db.table("profiles").select("*").eq("id", user_id).limit(1).execute()
        return res.data[0] if res.data else None

    def get_by_stripe_customer(self, customer_id: str) -> dict[str, Any] | None:
        res = (
            self.db.table("profiles")
            .select("*")
            .eq("stripe_customer_id", customer_id)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None

    def update(self, user_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        res = self.db.table("profiles").update(patch).eq("id", user_id).execute()
        return res.data[0] if res.data else {}

    def apply_subscription(
        self,
        user_id: str,
        plan: str,
        status: str,
        stripe_customer_id: str | None,
        stripe_subscription_id: str | None,
        period_end: str | None,
    ) -> None:
        self.db.rpc(
            "apply_subscription",
            {
                "p_user_id": user_id,
                "p_plan": plan,
                "p_status": status,
                "p_stripe_customer_id": stripe_customer_id,
                "p_stripe_subscription_id": stripe_subscription_id,
                "p_period_end": period_end,
            },
        ).execute()

    def consume_scan_quota(self, user_id: str) -> bool:
        res = self.db.rpc("consume_scan_quota", {"p_user_id": user_id}).execute()
        return bool(res.data)


class StripeEventRepo:
    def __init__(self, client: Client | None = None):
        self.db = client or get_service_client()

    def try_insert(self, event_id: str, event_type: str, payload: dict, livemode: bool, api_version: str | None) -> bool:
        """Returns False if event already seen (idempotent)."""
        existing = self.db.table("stripe_events").select("id").eq("id", event_id).limit(1).execute()
        if existing.data:
            return False
        self.db.table("stripe_events").insert(
            {
                "id": event_id,
                "type": event_type,
                "payload": payload,
                "livemode": livemode,
                "api_version": api_version,
            }
        ).execute()
        return True

    def mark_processed(self, event_id: str, error: str | None = None) -> None:
        from datetime import datetime, timezone

        self.db.table("stripe_events").update(
            {
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "process_error": error,
            }
        ).eq("id", event_id).execute()


class AuditRepo:
    def __init__(self, client: Client | None = None):
        self.db = client or get_service_client()

    def log(
        self,
        user_id: str | None,
        action: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        ip_hash: str | None = None,
        meta: dict | None = None,
    ) -> None:
        self.db.table("audit_log").insert(
            {
                "user_id": user_id,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "ip_hash": ip_hash,
                "meta": meta or {},
            }
        ).execute()
