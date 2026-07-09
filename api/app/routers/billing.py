from __future__ import annotations

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.config import Settings, get_settings
from app.core.security import AuthUser, enforce_rate_limit, hash_ip, require_user
from app.core.db import AuditRepo
from app.models.schemas import CheckoutRequest
from app.services.billing import BillingService

router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/checkout")
async def create_checkout(
    body: CheckoutRequest,
    request: Request,
    user: AuthUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
):
    await enforce_rate_limit(request, "billing_checkout", max_requests=10, window=60, settings=settings)
    svc = BillingService(settings)
    try:
        result = svc.create_checkout(user.id, user.email or "", body.plan)
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e)) from e
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    except stripe.StripeError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "stripe_error") from e
    return result


@router.post("/portal")
async def create_portal(
    request: Request,
    user: AuthUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
):
    await enforce_rate_limit(request, "billing_portal", max_requests=10, window=60, settings=settings)
    svc = BillingService(settings)
    try:
        return svc.create_portal(user.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    except stripe.StripeError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "stripe_error") from e


@router.post("/webhook")
async def stripe_webhook(request: Request, settings: Settings = Depends(get_settings)):
    """
    No JWT. Signature verification is the only auth.
    Raw body required — do not parse JSON before construct_event.
    """
    await enforce_rate_limit(request, "stripe_webhook", max_requests=200, window=60, settings=settings)
    payload = await request.body()
    if len(payload) > settings.max_body_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "body_too_large")

    sig = request.headers.get("stripe-signature")
    svc = BillingService(settings)
    try:
        event = svc.construct_event(payload, sig or "")
    except ValueError as e:
        AuditRepo().log(None, "webhook.invalid", meta={"reason": str(e), "ip": hash_ip(request.client.host if request.client else "")})
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_payload") from e
    except stripe.SignatureVerificationError as e:
        AuditRepo().log(None, "webhook.bad_signature", meta={"ip": hash_ip(request.client.host if request.client else "")})
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_signature") from e

    try:
        svc.handle_event(event)
    except Exception:
        # Stripe will retry; return 500 only for transient failures after insert
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "processing_failed") from None

    return {"received": True}
