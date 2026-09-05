"""
Standalone settings for the WAL sidecar process.

Deliberately independent from backend/config.py -- the sidecar is a
separate deployable unit and must not import anything from the main
Resync backend package.
"""
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class SidecarSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file="sidecar/.env", extra="ignore")

    razorpay_upstream_url: str = "https://api.razorpay.com"

    # Groq (used by the sidecar's own healing agent for verification/reasoning)
    groq_api_key: str = ""
    groq_model_name: str = "llama-3.3-70b-versatile"

    # MongoDB (same cluster/DB as the main backend -- both approaches heal
    # the same merchant database, they just use independent code paths to
    # get there)
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "resync"

    # Safety gate thresholds (independent copy -- Approach B has its own
    # safety policy, even though the values happen to match Approach A's).
    safety_max_amount_inr: float = 10000.0
    safety_min_confidence: float = 0.85


@lru_cache
def get_sidecar_settings() -> SidecarSettings:
    return SidecarSettings()
