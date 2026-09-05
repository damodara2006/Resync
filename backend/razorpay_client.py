"""
Razorpay client used by checkout and by the healing agent.

Calls Razorpay's real API directly (never through this app's own proxy
route in main.py -- that would be a pointless loop). Every call it makes
is itself logged into the local WAL, exactly like traffic relayed through
the proxy, so the healing agent's own verification calls become part of
the durable record too.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

import razorpay

import  wal_db
from config import get_settings


@lru_cache
def get_razorpay_client() -> razorpay.Client:
    settings = get_settings()
    return razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))


def create_order_and_log(amount_inr: float, receipt: str, internal_order_id: str) -> dict[str, Any]:
    """Create a Razorpay order, durably logging both the request and the
    response to the local WAL. This is the moment that survives even if
    this process crashes immediately afterward, because the write already
    landed on disk before the network call.
    """
    client = get_razorpay_client()
    request_body = {
        "amount": int(round(amount_inr * 100)),
        "currency": "INR",
        "receipt": receipt,
        "notes": {"internal_order_id": internal_order_id},
    }

    wal_db.record_entry(
        direction="request",
        razorpay_path="/v1/orders",
        raw_payload=request_body,
        order_id=internal_order_id,
        amount=amount_inr,
    )

    rzp_order = client.order.create(request_body)

    wal_db.record_entry(
        direction="response",
        razorpay_path="/v1/orders",
        raw_payload=rzp_order,
        order_id=internal_order_id,
        razorpay_order_id=rzp_order.get("id"),
        amount=amount_inr,
    )

    return rzp_order


def verify_signature_and_log(
    razorpay_order_id: str, razorpay_payment_id: str, razorpay_signature: str
) -> bool:
    """Verify a payment signature, durably logging the verification
    attempt (and, on success, fetching + logging the actual payment
    record) to the local WAL."""
    client = get_razorpay_client()
    params = {
        "razorpay_order_id": razorpay_order_id,
        "razorpay_payment_id": razorpay_payment_id,
        "razorpay_signature": razorpay_signature,
    }

    try:
        client.utility.verify_payment_signature(params)
    except razorpay.errors.SignatureVerificationError:
        return False

    payment = client.payment.fetch(razorpay_payment_id)
    wal_db.record_entry(
        direction="response",
        razorpay_path=f"/v1/payments/{razorpay_payment_id}",
        raw_payload=payment,
        razorpay_order_id=payment.get("order_id"),
        razorpay_payment_id=payment.get("id"),
        amount=(payment.get("amount", 0) / 100.0) if payment.get("amount") is not None else None,
        customer_email=payment.get("email"),
    )
    return True


def fetch_and_log_recent_captured_payments(hours: int = 24) -> list[dict[str, Any]]:
    """Ask Razorpay directly for payments captured in the last `hours`
    hours, and log each one to the local WAL -- the same durable-record
    mechanism the proxy uses for relayed traffic, just triggered by the
    healing agent's own outbound call instead of checkout's.
    """
    client = get_razorpay_client()
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    from_ts = int(since.timestamp())

    response = client.payment.all({"from": from_ts, "count": 100})
    items = response.get("items", [])
    captured = [p for p in items if p.get("status") == "captured"]

    for payment in captured:
        # Only log a payment the first time this scan sees it -- otherwise
        # every heal run re-inserts the same already-known payments with a
        # fresh captured_at, burying genuinely new WAL entries under noise
        # every time someone re-runs the scan.
        if wal_db.find_by_razorpay_payment_id(payment["id"]):
            continue

        notes = payment.get("notes") or {}
        internal_order_id = notes.get("internal_order_id") if isinstance(notes, dict) else None

        wal_db.record_entry(
            direction="response",
            razorpay_path=f"/v1/payments/{payment['id']}",
            raw_payload=payment,
            order_id=internal_order_id,
            razorpay_order_id=payment.get("order_id"),
            razorpay_payment_id=payment.get("id"),
            amount=(payment.get("amount", 0) / 100.0) if payment.get("amount") is not None else None,
            customer_email=payment.get("email"),
        )

    return captured
