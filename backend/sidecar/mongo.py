"""
Standalone MongoDB connection for the WAL sidecar's healing agent.

Deliberately independent from backend/db/mongo.py -- this process does not
import anything from the main Resync backend package. It connects to the
same merchant database, because both approaches (Approach A: the
reconciliation agent, Approach B: this WAL sidecar) are ultimately healing
the same `orders` / `audit_logs` collections -- they just get there via
completely separate code paths and detection mechanisms.
"""
from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase

from sidecar.config import get_sidecar_settings

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        settings = get_sidecar_settings()
        _client = AsyncIOMotorClient(settings.mongodb_uri)
    return _client


def get_database() -> AsyncIOMotorDatabase:
    settings = get_sidecar_settings()
    return get_client()[settings.mongodb_db_name]


def orders_collection() -> AsyncIOMotorCollection:
    return get_database()["orders"]


def audit_logs_collection() -> AsyncIOMotorCollection:
    return get_database()["audit_logs"]
