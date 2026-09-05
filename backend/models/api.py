"""
Request/response models for FastAPI endpoints.

Kept separate from `schemas.py` (the storage models) so the public API
contract can evolve independently of the internal document shape.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from models.schemas import ActionTaken, AuditLog, Order, OrderStatus


# --------------------------------------------------------------------------
# Checkout
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
    order_status: OrderStatus
    message: str
    simulated_crash: bool = False


# --------------------------------------------------------------------------
# Agent
# --------------------------------------------------------------------------

class RunReconciliationResponse(BaseModel):
    scanned_payments: int
    anomalies_found: int
    auto_healed: int
    escalated: int
    audit_log_ids: list[str]


# --------------------------------------------------------------------------
# Admin
# --------------------------------------------------------------------------

class DesyncOrderView(BaseModel):
    order_id: str
    razorpay_order_id: str
    razorpay_payment_id: Optional[str]
    amount: float
    customer_email: EmailStr
    db_status: OrderStatus
    razorpay_status: str
    created_at: str


class AdminMetrics(BaseModel):
    total_scanned: int
    active_desyncs: int
    auto_healed: int
    escalated: int
