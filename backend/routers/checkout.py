"""
Checkout endpoints: create a Razorpay order, then verify the payment once
the customer completes checkout in the Razorpay modal.

The `verify` endpoint has a `simulate_crash` flag used for the demo: when
true, Razorpay still captures the payment (so the money genuinely moves,
mirroring the real Phantom Transaction scenario), but the local DB update is
deliberately skipped and a CRITICAL crash-dump log is written instead. That
is exactly the discrepancy the reconciliation agent is built to find.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from db.mongo import orders_collection, server_logs_collection
from models.api import (
    CreateOrderRequest,
    CreateOrderResponse,
    VerifyPaymentRequest,
    VerifyPaymentResponse,
)
from models.schemas import LogLevel, OrderStatus
from services.crash_simulator import build_crash_dump
from services.razorpay_client import create_order as rzp_create_order
from services.razorpay_client import verify_payment_signature
from config import get_settings
from utils.ids import new_id

router = APIRouter(prefix="/api/checkout", tags=["checkout"])


@router.post("/create-order", response_model=CreateOrderResponse)
async def create_order(payload: CreateOrderRequest) -> CreateOrderResponse:
    settings = get_settings()
    order_id = new_id("ord")

    rzp_order = rzp_create_order(amount_inr=payload.amount, receipt=order_id)

    order_doc = {
        "order_id": order_id,
        "razorpay_order_id": rzp_order["id"],
        "razorpay_payment_id": None,
        "amount": payload.amount,
        "customer_email": payload.customer_email,
        "status": OrderStatus.PENDING.value,
        "created_at": datetime.now(timezone.utc),
    }
    await orders_collection().insert_one(order_doc)

    return CreateOrderResponse(
        order_id=order_id,
        razorpay_order_id=rzp_order["id"],
        razorpay_key_id=settings.razorpay_key_id,
        amount=payload.amount,
    )


@router.post("/verify", response_model=VerifyPaymentResponse)
async def verify_payment(
    payload: VerifyPaymentRequest, simulate_crash: bool = False
) -> VerifyPaymentResponse:
    order = await orders_collection().find_one({"order_id": payload.order_id})
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    if not verify_payment_signature(
        payload.razorpay_order_id, payload.razorpay_payment_id, payload.razorpay_signature
    ):
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    if simulate_crash:
        # Razorpay's side of the world is untouched here: the checkout flow
        # already captured the payment before this endpoint was called.
        # We deliberately do NOT update the order status, reproducing a
        # webhook-drop / server-crash mid-fulfillment.
        crash_log = build_crash_dump(
            order_id=order["order_id"],
            razorpay_order_id=payload.razorpay_order_id,
            razorpay_payment_id=payload.razorpay_payment_id,
            amount=order["amount"],
            customer_email=order["customer_email"],
        )
        await server_logs_collection().insert_one(
            {
                "log_id": new_id("log"),
                "order_id": order["order_id"],
                "level": LogLevel.CRITICAL.value,
                "raw_log_text": crash_log,
                "resolved": False,
                "timestamp": datetime.now(timezone.utc),
            }
        )
        # Record the payment id so the reconciliation agent can match this
        # order back to the Razorpay-side captured payment, but leave status
        # untouched (PENDING) to simulate the drop.
        await orders_collection().update_one(
            {"order_id": order["order_id"]},
            {"$set": {"razorpay_payment_id": payload.razorpay_payment_id}},
        )
        return VerifyPaymentResponse(
            success=False,
            order_status=OrderStatus.PENDING,
            message="Payment captured on Razorpay, but local fulfillment crashed before the DB update. "
            "This order is now a phantom transaction awaiting reconciliation.",
            simulated_crash=True,
        )

    await orders_collection().update_one(
        {"order_id": order["order_id"]},
        {
            "$set": {
                "razorpay_payment_id": payload.razorpay_payment_id,
                "status": OrderStatus.FULFILLED.value,
            }
        },
    )
    return VerifyPaymentResponse(
        success=True,
        order_status=OrderStatus.FULFILLED,
        message="Payment verified and order fulfilled.",
        simulated_crash=False,
    )
