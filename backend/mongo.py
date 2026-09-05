"""
MongoDB connection.
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


def orders_collection() -> AsyncIOMotorCollection:
    return get_database()["orders"]


def audit_logs_collection() -> AsyncIOMotorCollection:
    return get_database()["audit_logs"]
