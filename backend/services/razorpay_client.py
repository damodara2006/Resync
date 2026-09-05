"""
Thin wrapper around the Razorpay Python SDK.

Centralizes client construction and the handful of operations Resync needs:
creating orders, verifying payment signatures, fetching captured payments
(for the reconciliation scan), and issuing refunds.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

import razorpay
from razorpay.errors import SignatureVerificationError

from config import get_settings


@lru_cache
def get_razorpay_client() -> razorpay.Client:
    settings = get_settings()
    client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
    return client


def create_order(amount_inr: float, receipt: str, notes: dict[str, str] | None = None) -> dict[str, Any]:
    """Create a Razorpay order. Amount must be passed to Razorpay in paise."""
    client = get_razorpay_client()
    amount_paise = int(round(amount_inr * 100))
    return client.order.create(
        {
            "amount": amount_paise,
            "currency": "INR",
            "receipt": receipt,
            "notes": notes or {},
        }
    )


def verify_payment_signature(
    razorpay_order_id: str, razorpay_payment_id: str, razorpay_signature: str
) -> bool:
    """Verify the HMAC signature Razorpay returns after checkout completes."""
    client = get_razorpay_client()
    params = {
        "razorpay_order_id": razorpay_order_id,
        "razorpay_payment_id": razorpay_payment_id,
        "razorpay_signature": razorpay_signature,
    }
    try:
        client.utility.verify_payment_signature(params)
        return True
    except SignatureVerificationError:
        return False


def fetch_payment(payment_id: str) -> dict[str, Any]:
    client = get_razorpay_client()
    return client.payment.fetch(payment_id)


def capture_payment(payment_id: str, amount_inr: float) -> dict[str, Any]:
    """Explicitly capture a payment (used in the crash-simulation path, where
    we still want Razorpay's side of the world to show a captured payment)."""
    client = get_razorpay_client()
    amount_paise = int(round(amount_inr * 100))
    return client.payment.capture(payment_id, amount_paise)


def refund_payment(payment_id: str, amount_inr: float | None = None) -> dict[str, Any]:
    client = get_razorpay_client()
    payload: dict[str, Any] = {}
    if amount_inr is not None:
        payload["amount"] = int(round(amount_inr * 100))
    return client.payment.refund(payment_id, payload)


def fetch_recent_captured_payments(hours: int = 24) -> list[dict[str, Any]]:
    """Fetch payments captured in the last `hours` hours.

    Used by the reconciliation agent's anomaly-detection step to find
    payments Razorpay considers captured, which is the source of truth
    it reconciles the local DB against.
    """
    client = get_razorpay_client()
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    from_ts = int(since.timestamp())

    payments = client.payment.all({"from": from_ts, "count": 100})
    items = payments.get("items", [])
    return [p for p in items if p.get("status") == "captured"]
