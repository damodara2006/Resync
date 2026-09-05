"""
Admin dashboard endpoints: desynchronized orders, audit trail, and summary
metrics for the top-of-page stat cards.
"""
from __future__ import annotations

from fastapi import APIRouter

from db.mongo import audit_logs_collection, orders_collection
from models.api import AdminMetrics, DesyncOrderView
from models.schemas import ActionTaken, AuditLog, OrderStatus

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/desyncs", response_model=list[DesyncOrderView])
async def get_desyncs() -> list[DesyncOrderView]:
    cursor = orders_collection().find(
        {"status": {"$in": [OrderStatus.DESYNCHRONIZED.value, OrderStatus.PENDING.value]}}
    )
    docs = await cursor.to_list(length=200)

    views: list[DesyncOrderView] = []
    for doc in docs:
        # Razorpay-side status is inferred from the fact this order was
        # flagged: if it has a payment id recorded it means Razorpay showed
        # it as captured while the local DB lagged behind.
        razorpay_status = "captured" if doc.get("razorpay_payment_id") else "unknown"
        views.append(
            DesyncOrderView(
                order_id=doc["order_id"],
                razorpay_order_id=doc["razorpay_order_id"],
                razorpay_payment_id=doc.get("razorpay_payment_id"),
                amount=doc["amount"],
                customer_email=doc["customer_email"],
                db_status=doc["status"],
                razorpay_status=razorpay_status,
                created_at=doc["created_at"].isoformat(),
            )
        )
    return views


@router.get("/audit-logs", response_model=list[AuditLog])
async def get_audit_logs() -> list[AuditLog]:
    # Approach A (this reconciliation agent) and Approach B (the WAL
    # sidecar, backend/sidecar/) are independent solutions that happen to
    # share the same `audit_logs` collection. The sidecar tags its own
    # entries with source="wal_sidecar" and uses a different action_taken
    # vocabulary (e.g. "AUTO_FULFILL_VIA_WAL"), which doesn't fit this
    # endpoint's strict ActionTaken enum -- so exclude those here and let
    # the WAL Sidecar page read its own entries via the sidecar's own
    # GET /wal/audit-logs instead.
    cursor = (
        audit_logs_collection()
        .find({"source": {"$ne": "wal_sidecar"}})
        .sort("timestamp", -1)
    )
    docs = await cursor.to_list(length=500)
    return [AuditLog(**doc) for doc in docs]


@router.get("/metrics", response_model=AdminMetrics)
async def get_metrics() -> AdminMetrics:
    total_scanned = await orders_collection().count_documents({})
    active_desyncs = await orders_collection().count_documents(
        {"status": {"$in": [OrderStatus.DESYNCHRONIZED.value, OrderStatus.PENDING.value]}}
    )
    auto_healed = await audit_logs_collection().count_documents(
        {"action_taken": ActionTaken.AUTO_FULFILL.value, "source": {"$ne": "wal_sidecar"}}
    )
    escalated = await audit_logs_collection().count_documents(
        {"action_taken": ActionTaken.HUMAN_ESCALATION.value, "source": {"$ne": "wal_sidecar"}}
    )
    return AdminMetrics(
        total_scanned=total_scanned,
        active_desyncs=active_desyncs,
        auto_healed=auto_healed,
        escalated=escalated,
    )
