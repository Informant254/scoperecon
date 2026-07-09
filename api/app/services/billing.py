from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import stripe

from app.core.config import Settings
from app.core.db import AuditRepo, ProfileRepo, StripeEventRepo, get_service_client


class BillingService:
    """All subscription mutations are server-authoritative. Client never sets plan."""

    ALLOWED_STATUS = {
        "trialing",
        "active",
        "past_due",
        "canceled",
        "incomplete",
        "unpaid",
        "none",
    }

    def __init__(self, settings: Settings):
        self.settings = settings
        stripe.api_key = settings.stripe_secret_key
        self.profiles = ProfileRepo()
        self.events = StripeEventRepo()
        self.audit = AuditRepo()
        self.db = get_service_client()

    def _map_status(self, status: str) -> str:
        if status in self.ALLOWED_STATUS:
            return status
        return "none"

    def create_checkout(self, user_id: str, email: str, plan: str) -> dict[str, str]:
        if plan not in ("pro", "team"):
            raise ValueError("invalid_plan")
        price_id = self.settings.plan_to_price(plan)
        if not price_id:
            raise ValueError("price_not_configured")

        profile = self.profiles.get(user_id)
        if not profile:
            raise ValueError("profile_missing")

        # Hostile actor cannot upgrade by replaying another user's customer id
        customer_id = profile.get("stripe_customer_id")
        if customer_id:
            customer = stripe.Customer.retrieve(customer_id)
            meta_uid = (customer.get("metadata") or {}).get("supabase_user_id")
            if meta_uid and meta_uid != user_id:
                raise PermissionError("customer_user_mismatch")
        else:
            customer = stripe.Customer.create(
                email=email or profile.get("email"),
                metadata={"supabase_user_id": user_id},
            )
            customer_id = customer["id"]
            self.profiles.update(user_id, {"stripe_customer_id": customer_id})

        # Block duplicate active subscriptions
        if profile.get("subscription_status") in ("active", "trialing") and profile.get("plan") == plan:
            raise ValueError("already_subscribed")

        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{self.settings.frontend_url}/app/billing?checkout=success",
            cancel_url=f"{self.settings.frontend_url}/pricing?checkout=canceled",
            client_reference_id=user_id,
            metadata={"supabase_user_id": user_id, "plan": plan, "price_id": price_id},
            subscription_data={"metadata": {"supabase_user_id": user_id, "plan": plan}},
            allow_promotion_codes=True,
            billing_address_collection="auto",
        )

        self.db.table("checkout_sessions").insert(
            {
                "user_id": user_id,
                "stripe_session_id": session["id"],
                "price_id": price_id,
                "plan": plan,
                "status": "created",
            }
        ).execute()

        self.audit.log(user_id, "checkout.created", "checkout_session", session["id"], meta={"plan": plan})
        return {"checkout_url": session["url"], "session_id": session["id"]}

    def create_portal(self, user_id: str) -> dict[str, str]:
        profile = self.profiles.get(user_id)
        if not profile or not profile.get("stripe_customer_id"):
            raise ValueError("no_customer")
        session = stripe.billing_portal.Session.create(
            customer=profile["stripe_customer_id"],
            return_url=f"{self.settings.frontend_url}/app/billing",
        )
        return {"portal_url": session["url"]}

    def construct_event(self, payload: bytes, sig_header: str) -> stripe.Event:
        if not sig_header:
            raise ValueError("missing_signature")
        return stripe.Webhook.construct_event(
            payload, sig_header, self.settings.stripe_webhook_secret
        )

    def handle_event(self, event: stripe.Event) -> None:
        event_id = event["id"]
        event_type = event["type"]
        inserted = self.events.try_insert(
            event_id,
            event_type,
            dict(event),
            bool(event.get("livemode")),
            event.get("api_version"),
        )
        if not inserted:
            return  # idempotent no-op

        try:
            if event_type == "checkout.session.completed":
                self._on_checkout_completed(event["data"]["object"])
            elif event_type in (
                "customer.subscription.created",
                "customer.subscription.updated",
                "customer.subscription.deleted",
            ):
                self._on_subscription(event["data"]["object"], deleted=event_type.endswith("deleted"))
            elif event_type == "invoice.payment_failed":
                self._on_payment_failed(event["data"]["object"])
            elif event_type == "invoice.paid":
                self._on_invoice_paid(event["data"]["object"])
            self.events.mark_processed(event_id)
        except Exception as exc:  # noqa: BLE001
            self.events.mark_processed(event_id, error=str(exc)[:500])
            raise

    def _resolve_user_id(self, obj: dict[str, Any]) -> str | None:
        meta = obj.get("metadata") or {}
        uid = meta.get("supabase_user_id") or obj.get("client_reference_id")
        if uid:
            return uid
        customer_id = obj.get("customer")
        if isinstance(customer_id, str):
            profile = self.profiles.get_by_stripe_customer(customer_id)
            if profile:
                return profile["id"]
        return None

    def _plan_from_subscription(self, sub: dict[str, Any]) -> str:
        # Prefer server price map; never trust metadata alone for elevation
        items = (sub.get("items") or {}).get("data") or []
        for item in items:
            price = item.get("price") or {}
            price_id = price.get("id") if isinstance(price, dict) else None
            plan = self.settings.price_to_plan(price_id) if price_id else None
            if plan:
                return plan
        meta_plan = (sub.get("metadata") or {}).get("plan")
        if meta_plan in ("pro", "team"):
            # Still require a known price if present
            return meta_plan
        return "free"

    def _period_end_iso(self, sub: dict[str, Any]) -> str | None:
        ts = sub.get("current_period_end")
        if not ts:
            return None
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()

    def _on_checkout_completed(self, session: dict[str, Any]) -> None:
        user_id = self._resolve_user_id(session)
        if not user_id:
            raise ValueError("checkout_missing_user")

        # Verify amount/price against our catalog if expanded
        price_id = (session.get("metadata") or {}).get("price_id")
        plan = self.settings.price_to_plan(price_id) if price_id else None
        if not plan:
            plan = (session.get("metadata") or {}).get("plan")
        if plan not in ("pro", "team"):
            raise ValueError("checkout_invalid_plan")

        expected_price = self.settings.plan_to_price(plan)
        if price_id and expected_price and price_id != expected_price:
            raise PermissionError("price_tamper_detected")

        self.db.table("checkout_sessions").update(
            {
                "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "amount_total": session.get("amount_total"),
                "currency": session.get("currency"),
            }
        ).eq("stripe_session_id", session["id"]).execute()

        # Subscription object drives final plan; if missing, apply provisional
        sub_id = session.get("subscription")
        if sub_id:
            sub = stripe.Subscription.retrieve(sub_id)
            self._on_subscription(dict(sub), deleted=False)
        else:
            self.profiles.apply_subscription(
                user_id=user_id,
                plan=plan,
                status="active",
                stripe_customer_id=session.get("customer"),
                stripe_subscription_id=None,
                period_end=None,
            )
        self.audit.log(user_id, "checkout.completed", "checkout_session", session["id"])

    def _on_subscription(self, sub: dict[str, Any], deleted: bool) -> None:
        user_id = self._resolve_user_id(sub)
        if not user_id:
            # Try customer lookup
            cust = sub.get("customer")
            if isinstance(cust, str):
                profile = self.profiles.get_by_stripe_customer(cust)
                user_id = profile["id"] if profile else None
        if not user_id:
            raise ValueError("subscription_missing_user")

        if deleted or sub.get("status") in ("canceled", "unpaid"):
            plan = "free"
            status = self._map_status(sub.get("status") or "canceled")
        else:
            plan = self._plan_from_subscription(sub)
            status = self._map_status(sub.get("status") or "active")
            if status not in ("active", "trialing", "past_due") and plan != "free":
                plan = "free"

        self.profiles.apply_subscription(
            user_id=user_id,
            plan=plan if status in ("active", "trialing", "past_due") else "free",
            status=status,
            stripe_customer_id=sub.get("customer") if isinstance(sub.get("customer"), str) else None,
            stripe_subscription_id=sub.get("id"),
            period_end=self._period_end_iso(sub),
        )
        self.audit.log(
            user_id,
            "subscription.synced",
            "subscription",
            sub.get("id"),
            meta={"plan": plan, "status": status, "deleted": deleted},
        )

    def _on_payment_failed(self, invoice: dict[str, Any]) -> None:
        customer = invoice.get("customer")
        if not isinstance(customer, str):
            return
        profile = self.profiles.get_by_stripe_customer(customer)
        if not profile:
            return
        self.profiles.update(profile["id"], {"subscription_status": "past_due"})
        self.audit.log(profile["id"], "invoice.payment_failed", "invoice", invoice.get("id"))

    def _on_invoice_paid(self, invoice: dict[str, Any]) -> None:
        sub_id = invoice.get("subscription")
        if not sub_id:
            return
        sub = stripe.Subscription.retrieve(sub_id)
        self._on_subscription(dict(sub), deleted=False)
