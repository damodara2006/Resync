"""
Storefront checkout endpoints.

Every Razorpay call made here is durably logged to the local WAL before
the network call happens (see razorpay_client.py), so the record survives
even if this process crashes before finishing a request.

`create_order_crash_simulation` demonstrates the "Zero-DB-Footprint
Orphaned Payment" case: it creates a real Razorpay order but deliberately
never writes to MongoDB, and there is no corresponding verify call
afterward -- modeling a request whose handler never got to finish (e.g.
an OOM kill mid-request).
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field

from config import get_settings
from mongo import orders_collection
from razorpay_client import create_order_and_log, verify_signature_and_log

router = APIRouter(prefix="/api/checkout", tags=["checkout"])


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


# --------------------------------------------------------------------------
# Request/response models
# --------------------------------------------------------------------------

class CreateOrderRequest(BaseModel):
    amount: float = Field(gt=0, description="Amount in INR (e.g. 499.00)")
    customer_email: EmailStr


class CreateOrderResponse(BaseModel):
    order_id: str
    razorpay_order_id: str
    razorpay_key_id: str
    amount: float
    currency: str = "INR"


class VerifyPaymentRequest(BaseModel):
    order_id: str
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class VerifyPaymentResponse(BaseModel):
    success: bool
    order_status: str
    message: str


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------

@router.post("/create-order", response_model=CreateOrderResponse)
async def create_order(payload: CreateOrderRequest) -> CreateOrderResponse:
    settings = get_settings()
    order_id = _new_id("ord")

    rzp_order = create_order_and_log(
        amount_inr=payload.amount, receipt=order_id, internal_order_id=order_id
    )

    await orders_collection().insert_one(
        {
            "order_id": order_id,
            "razorpay_order_id": rzp_order["id"],
            "razorpay_payment_id": None,
            "amount": payload.amount,
            "customer_email": payload.customer_email,
            "status": "PENDING",
            "created_at": datetime.now(timezone.utc),
        }
    )

    return CreateOrderResponse(
        order_id=order_id,
        razorpay_order_id=rzp_order["id"],
        razorpay_key_id=settings.razorpay_key_id,
        amount=payload.amount,
    )


@router.post("/create-order-crash-simulation", response_model=CreateOrderResponse)
async def create_order_crash_simulation(payload: CreateOrderRequest) -> CreateOrderResponse:
    """Creates a real Razorpay order but DELIBERATELY skips writing anything
    to MongoDB at all -- not even a PENDING row.

    Reproduces the "Zero-DB-Footprint Orphaned Payment" case: after the
    customer pays, MongoDB has zero record of this order ever existing.
    The only trace left anywhere is whatever this process's own local WAL
    independently captured while making this Razorpay call -- durable
    because it was written to disk before this call even started, not
    because a different process happened to survive.

    Unlike /create-order, there is no corresponding /verify call for this
    path -- the frontend opens the Razorpay checkout modal directly with
    this response and never reports the outcome back, matching a request
    handler that never got to finish processing the payment result at all.
    """
    settings = get_settings()
    order_id = _new_id("ord")

    rzp_order = create_order_and_log(
        amount_inr=payload.amount, receipt=order_id, internal_order_id=order_id
    )

    # NOTE: deliberately no orders_collection().insert_one(...) here --
    # that is the entire point of this endpoint.

    return CreateOrderResponse(
        order_id=order_id,
        razorpay_order_id=rzp_order["id"],
        razorpay_key_id=settings.razorpay_key_id,
        amount=payload.amount,
    )


@router.post("/verify", response_model=VerifyPaymentResponse)
async def verify_payment(payload: VerifyPaymentRequest) -> VerifyPaymentResponse:
    order = await orders_collection().find_one({"order_id": payload.order_id})
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    signature_valid = verify_signature_and_log(
        payload.razorpay_order_id, payload.razorpay_payment_id, payload.razorpay_signature
    )
    if not signature_valid:
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    await orders_collection().update_one(
        {"order_id": order["order_id"]},
        {"$set": {"razorpay_payment_id": payload.razorpay_payment_id, "status": "FULFILLED"}},
    )

    return VerifyPaymentResponse(
        success=True,
        order_status="FULFILLED",
        message="Payment verified and order fulfilled.",
    )
