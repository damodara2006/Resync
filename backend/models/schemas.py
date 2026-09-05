"""
Pydantic v2 data models for Resync.

These models are the single source of truth for both MongoDB document
shape and API request/response validation. Every field is strictly typed
so the reconciliation agent can trust the shape of what it reads and
writes without defensive re-validation downstream.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------

class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FULFILLED = "FULFILLED"
    REFUNDED = "REFUNDED"
    DESYNCHRONIZED = "DESYNCHRONIZED"


class LogLevel(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ActionTaken(str, Enum):
    AUTO_FULFILL = "AUTO_FULFILL"
    AUTO_REFUND = "AUTO_REFUND"
    HUMAN_ESCALATION = "HUMAN_ESCALATION"


# --------------------------------------------------------------------------
# Order
# --------------------------------------------------------------------------

class OrderBase(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    razorpay_order_id: str
    razorpay_payment_id: Optional[str] = None
    amount: float = Field(gt=0, description="Order amount in INR")
    customer_email: EmailStr
    status: OrderStatus = OrderStatus.PENDING


class OrderCreate(OrderBase):
    """Payload used internally when a new order is first created."""
    order_id: str


class Order(OrderBase):
    """Full order document as stored in / read from MongoDB."""
    order_id: str
    created_at: datetime = Field(default_factory=_utcnow)


# --------------------------------------------------------------------------
# ServerLog
# --------------------------------------------------------------------------

class ServerLogBase(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    level: LogLevel
    raw_log_text: str
    resolved: bool = False


class ServerLogCreate(ServerLogBase):
    log_id: str
    order_id: Optional[str] = None


class ServerLog(ServerLogBase):
    log_id: str
    order_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=_utcnow)


# --------------------------------------------------------------------------
# AuditLog
# --------------------------------------------------------------------------

class AuditLogBase(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    order_id: str
    razorpay_payment_id: str
    action_taken: ActionTaken
    confidence_score: float = Field(ge=0.0, le=1.0)
    reasoning: str
    safety_gate_passed: bool


class AuditLogCreate(AuditLogBase):
    audit_id: str


class AuditLog(AuditLogBase):
    audit_id: str
    timestamp: datetime = Field(default_factory=_utcnow)


# --------------------------------------------------------------------------
# Agent-internal structured output (used by the Groq structured parser)
# --------------------------------------------------------------------------

class LogForensicsResult(BaseModel):
    """Structured extraction the LLM must produce from a raw crash log."""

    customer_email: Optional[EmailStr] = Field(
        default=None, description="Customer email recovered from the log, if present"
    )
    amount: Optional[float] = Field(
        default=None, description="Payment amount recovered from the log, if present"
    )
    failure_reason: str = Field(
        description="Concise, human-readable reason the webhook/update failed"
    )
    confidence_score: float = Field(
        ge=0.0, le=1.0,
        description="Model's confidence (0-1) that the extraction is accurate and complete",
    )
