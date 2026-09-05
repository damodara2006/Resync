"""
Centralized application settings, loaded from environment variables / .env.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Razorpay
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""

    # Groq
    groq_api_key: str = ""
    groq_model_name: str = "llama-3.3-70b-versatile"

    # MongoDB
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "resync"

    # App
    frontend_origin: str = "http://localhost:5173"
    safety_max_amount_inr: float = 10000.0
    safety_min_confidence: float = 0.85


@lru_cache
def get_settings() -> Settings:
    return Settings()
