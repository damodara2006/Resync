"""
Resync — Webhook Drop & State Reconciliation Agent
FastAPI application entrypoint.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from db.mongo import close_client, ensure_indexes
from routers import admin, agent, checkout


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_indexes()
    yield
    close_client()


app = FastAPI(
    title="Resync — Webhook Drop & State Reconciliation Agent",
    description=(
        "Autonomous, state-driven reconciliation agent that detects Phantom "
        "Transactions (Razorpay-captured payments a crashed webhook never "
        "recorded locally) and heals them using a LangGraph + Groq agent "
        "behind a strict safety gate."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(checkout.router)
app.include_router(agent.router)
app.include_router(admin.router)


@app.get("/api/health", tags=["health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
