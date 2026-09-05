"""
MongoDB connection layer (motor async client) and thin collection accessors.

A single AsyncIOMotorClient is created lazily and reused for the life of the
process; FastAPI's lifespan hook (see main.py) closes it on shutdown.
"""
from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase

from config import get_settings

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncIOMotorClient(settings.mongodb_uri)
    return _client


def get_database() -> AsyncIOMotorDatabase:
    settings = get_settings()
    return get_client()[settings.mongodb_db_name]


def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None


def orders_collection() -> AsyncIOMotorCollection:
    return get_database()["orders"]


def server_logs_collection() -> AsyncIOMotorCollection:
    return get_database()["server_logs"]


def audit_logs_collection() -> AsyncIOMotorCollection:
    return get_database()["audit_logs"]


async def ensure_indexes() -> None:
    """Create the indexes Resync relies on. Safe to call on every startup."""
    await orders_collection().create_index("order_id", unique=True)
    await orders_collection().create_index("razorpay_order_id")
    await orders_collection().create_index("razorpay_payment_id")
    await orders_collection().create_index("status")

    await server_logs_collection().create_index("log_id", unique=True)
    await server_logs_collection().create_index("resolved")

    await audit_logs_collection().create_index("audit_id", unique=True)
    await audit_logs_collection().create_index("order_id")
